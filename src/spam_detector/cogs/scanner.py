from __future__ import annotations

import asyncio
import io
import logging
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import discord
from discord.ext import commands

from spam_detector.hasher import phash_bytes
from spam_detector.images import (
    ImageCandidate,
    ImageTooLargeError,
    InvalidImageError,
    is_image_content_type,
    is_image_filename,
)
from spam_detector.store import Match, sanitize_filename

if TYPE_CHECKING:
    from spam_detector.bot import SpamDetectorBot

log = logging.getLogger(__name__)

HANDLED_LIMIT = 2000


class AlertView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Kick (coming later)",
                style=discord.ButtonStyle.danger,
                disabled=True,
            )
        )


class ScannerCog(commands.Cog):
    def __init__(self, bot: SpamDetectorBot) -> None:
        self.bot = bot
        self._download_sem = asyncio.Semaphore(bot.config.download_concurrency)
        self._handled: OrderedDict[int, None] = OrderedDict()

    def _skip_reason(self, message: discord.Message) -> str | None:
        if message.guild is None:
            return "not in a guild"
        if message.guild.id != self.bot.config.guild_id:
            return f"wrong guild ({message.guild.id})"
        if message.channel.id == self.bot.config.alert_channel_id:
            return "posted in the alert channel"
        if self.bot.user and message.author.id == self.bot.user.id:
            return "own message"
        if message.author.bot:
            return "author is a bot"
        if not message.attachments and not message.embeds and not _message_snapshots(message):
            return "no attachments or embeds"
        if not self.bot.store.entries:
            return "spam hash set is empty"
        return None

    def _should_scan(self, message: discord.Message) -> bool:
        return self._skip_reason(message) is None

    def _mark_handled(self, message_id: int) -> bool:
        if message_id in self._handled:
            return False
        self._handled[message_id] = None
        while len(self._handled) > HANDLED_LIMIT:
            self._handled.popitem(last=False)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self._handle(message)

    @commands.Cog.listener()
    async def on_message_edit(self, _before: discord.Message, after: discord.Message) -> None:
        await self._handle(after)

    async def _handle(self, message: discord.Message) -> None:
        reason = self._skip_reason(message)
        if reason:
            if message.attachments or message.embeds or _message_snapshots(message):
                log.info("Not scanning message %s: %s", message.id, reason)
            return
        if message.id in self._handled:
            return
        try:
            hit = await self._find_match(message)
        except Exception:
            log.exception("Failed scanning message %s", message.id)
            return
        if hit is None:
            return
        if not self._mark_handled(message.id):
            return
        log.warning(
            "Spam match: user=%s message=%s sample=%s distance=%s",
            message.author.id,
            message.id,
            hit.match.entry.name,
            hit.match.distance,
        )
        try:
            await self._send_alert(message, hit)
        except Exception:
            log.exception("Failed to send spam alert for message %s", message.id)
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            log.error("Missing Manage Messages; could not delete message %s", message.id)
        except Exception:
            log.exception("Failed to delete spam message %s", message.id)

    async def _find_match(self, message: discord.Message) -> _Hit | None:
        candidates = await self._collect_candidates(message)
        if not candidates:
            log.info(
                "Message %s had no downloadable images (%s attachment(s), %s embed(s))",
                message.id,
                len(message.attachments),
                len(message.embeds),
            )
            return None
        best: _Hit | None = None
        closest: Match | None = None
        threshold = self.bot.config.hash_threshold
        for candidate in candidates:
            try:
                phash = await asyncio.to_thread(
                    phash_bytes,
                    candidate.data,
                    self.bot.config.max_image_pixels,
                    self.bot.config.hash_size,
                )
            except (InvalidImageError, ImageTooLargeError) as exc:
                log.info("Skipping image %s: %s", candidate.filename, exc)
                continue
            except Exception:
                log.exception("Hash failed for %s", candidate.filename)
                continue
            nearest = self.bot.store.closest(phash)
            if nearest is None:
                continue
            if closest is None or nearest.distance < closest.distance:
                closest = nearest
            if nearest.distance > threshold:
                continue
            if best is None or nearest.distance < best.match.distance:
                best = _Hit(candidate=candidate, match=nearest)
        if best is None:
            if closest is None:
                log.info("No spam match for message %s: hashing failed", message.id)
            else:
                log.info(
                    "No spam match for message %s: closest `%s` distance=%s threshold=%s",
                    message.id,
                    closest.entry.name,
                    closest.distance,
                    threshold,
                )
        return best

    async def _collect_candidates(self, message: discord.Message) -> list[ImageCandidate]:
        candidates: list[ImageCandidate] = []
        attachments = list(message.attachments)
        for snapshot in _message_snapshots(message):
            attachments.extend(list(getattr(snapshot, "attachments", None) or []))
        for attachment in attachments:
            if not _is_image_attachment(attachment):
                log.info(
                    "Skipping non-image attachment %s (%s)",
                    attachment.filename,
                    attachment.content_type,
                )
                continue
            if attachment.size and attachment.size > self.bot.config.max_image_bytes:
                log.info("Skipping oversized attachment %s", attachment.filename)
                continue
            async with self._download_sem:
                try:
                    data = await attachment.read()
                except Exception:
                    log.exception("Failed to read attachment %s", attachment.filename)
                    continue
            if len(data) > self.bot.config.max_image_bytes:
                continue
            candidates.append(ImageCandidate("attachment", attachment.filename, data))

        seen_urls: set[str] = set()
        for url in _embed_image_urls(message):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            async with self._download_sem:
                data = await self._download_url(url)
            if not data:
                continue
            filename = _filename_from_url(url)
            candidates.append(ImageCandidate("embed", filename, data))
        return candidates

    async def _download_url(self, url: str) -> bytes | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        session = self.bot.http_session
        if session is None:
            return None
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.bot.config.max_image_bytes:
                    return None
                content_type = response.headers.get("Content-Type")
                if content_type and not is_image_content_type(content_type) and not is_image_filename(parsed.path):
                    return None
                buffer = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    buffer.extend(chunk)
                    if len(buffer) > self.bot.config.max_image_bytes:
                        return None
                return bytes(buffer)
        except asyncio.TimeoutError:
            log.info("Timed out downloading %s", url)
            return None
        except Exception:
            log.exception("Failed downloading %s", url)
            return None

    async def _send_alert(self, message: discord.Message, hit: _Hit) -> None:
        channel = message.guild.get_channel(self.bot.config.alert_channel_id) if message.guild else None
        if channel is None:
            channel = self.bot.get_channel(self.bot.config.alert_channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.error("Alert channel %s is missing or not messageable", self.bot.config.alert_channel_id)
            return

        author = message.author
        joined = "unknown"
        if isinstance(author, discord.Member) and author.joined_at:
            joined = discord.utils.format_dt(author.joined_at, style="R")

        filename = sanitize_filename(hit.candidate.filename)
        embed = discord.Embed(
            title="Spam image detected",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{author.mention}\n`{author.id}`", inline=True)
        embed.add_field(
            name="Account",
            value=f"Created {discord.utils.format_dt(author.created_at, style='R')}\nJoined {joined}",
            inline=True,
        )
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(
            name="Match",
            value=f"`{hit.match.entry.name}`\nHamming distance `{hit.match.distance}`",
            inline=True,
        )
        embed.add_field(name="Source", value=hit.candidate.source, inline=True)
        embed.add_field(name="Message ID", value=str(message.id), inline=True)
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Kick is not enabled yet")

        file = discord.File(io.BytesIO(hit.candidate.data), filename=filename)
        await channel.send(embed=embed, file=file, view=AlertView())


class _Hit:
    def __init__(self, candidate: ImageCandidate, match: Match) -> None:
        self.candidate = candidate
        self.match = match


def _message_snapshots(message: discord.Message) -> list[object]:
    snapshots = getattr(message, "message_snapshots", None)
    if isinstance(snapshots, (list, tuple)):
        return list(snapshots)
    return []


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    if getattr(attachment, "width", None) and getattr(attachment, "height", None):
        return True
    if is_image_content_type(attachment.content_type):
        return True
    return is_image_filename(attachment.filename)


def _embed_image_urls(message: discord.Message) -> list[str]:
    urls: list[str] = []
    for embed in message.embeds:
        if embed.image and embed.image.url:
            urls.append(embed.image.url)
        if embed.thumbnail and embed.thumbnail.url:
            urls.append(embed.thumbnail.url)
    return urls


def _filename_from_url(url: str) -> str:
    path = Path(urlparse(url).path)
    if path.name:
        return path.name
    return "embed.png"
