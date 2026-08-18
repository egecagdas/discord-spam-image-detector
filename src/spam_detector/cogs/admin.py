from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from spam_detector.hasher import phash_bytes
from spam_detector.images import (
    ImageTooLargeError,
    InvalidImageError,
    is_image_content_type,
    is_image_filename,
)

if TYPE_CHECKING:
    from spam_detector.bot import SpamDetectorBot

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    spam = app_commands.Group(name="spam", description="Manage the spam image set")

    def __init__(self, bot: SpamDetectorBot) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.bot.config.guild_id:
            return False
        user = interaction.user
        if not isinstance(user, discord.Member):
            return False
        if user.guild_permissions.manage_guild:
            return True
        role_id = self.bot.config.admin_role_id
        return bool(role_id and user.get_role(role_id))

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            message = "You need Manage Server or the configured admin role to use this command."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return
        log.exception("Admin command failed")
        notice = "Something went wrong running that command."
        if interaction.response.is_done():
            await interaction.followup.send(notice, ephemeral=True)
        else:
            await interaction.response.send_message(notice, ephemeral=True)

    @spam.command(name="add", description="Add an image to the spam set")
    @app_commands.describe(image="Image that should be treated as spam")
    async def spam_add(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        if not _is_image_attachment(image):
            await interaction.response.send_message("That attachment is not a supported image.", ephemeral=True)
            return
        if image.size and image.size > self.bot.config.max_image_bytes:
            await interaction.response.send_message("That image is larger than the configured size limit.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            data = await image.read()
        except Exception:
            log.exception("Failed to read uploaded spam image")
            await interaction.followup.send("Could not download that attachment.", ephemeral=True)
            return
        if len(data) > self.bot.config.max_image_bytes:
            await interaction.followup.send("That image is larger than the configured size limit.", ephemeral=True)
            return
        try:
            phash = await asyncio.to_thread(
                phash_bytes,
                data,
                self.bot.config.max_image_pixels,
                self.bot.config.hash_size,
            )
        except (InvalidImageError, ImageTooLargeError) as exc:
            await interaction.followup.send(f"Could not hash that image: {exc}", ephemeral=True)
            return
        except Exception:
            log.exception("Failed to hash uploaded spam image")
            await interaction.followup.send("Could not hash that image.", ephemeral=True)
            return

        existing = self.bot.store.find_match(phash, threshold=0)
        entry = await asyncio.to_thread(
            self.bot.store.add,
            Path(image.filename).stem,
            image.filename,
            phash,
            data,
        )
        extra = ""
        if existing is not None:
            extra = f" (already similar to `{existing.entry.name}` at distance 0)"
        await interaction.followup.send(
            f"Added `{entry.name}` (`{entry.id}`) with pHash `{entry.phash}`.{extra}",
            ephemeral=True,
        )

    @spam.command(name="remove", description="Remove an image from the spam set")
    @app_commands.describe(name="Name, filename, or id from /spam list")
    async def spam_remove(self, interaction: discord.Interaction, name: str) -> None:
        removed = self.bot.store.remove(name)
        if removed is None:
            await interaction.response.send_message(f"No spam entry named `{name}`.", ephemeral=True)
            return
        await interaction.response.send_message(f"Removed `{removed.name}`.", ephemeral=True)

    @spam_remove.autocomplete("name")
    async def spam_remove_autocomplete(
        self,
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        needle = current.casefold()
        choices: list[app_commands.Choice[str]] = []
        for entry in self.bot.store.entries:
            if needle and needle not in entry.name.casefold() and needle not in entry.filename.casefold():
                continue
            choices.append(app_commands.Choice(name=entry.name, value=entry.name))
            if len(choices) >= 25:
                break
        return choices

    @spam.command(name="list", description="List known spam images")
    async def spam_list(self, interaction: discord.Interaction) -> None:
        entries = self.bot.store.entries
        if not entries:
            await interaction.response.send_message("The spam set is empty.", ephemeral=True)
            return
        lines = [f"`{entry.id}` — {entry.name} (`{entry.phash}`)" for entry in entries[:25]]
        suffix = "" if len(entries) <= 25 else f"\n…and {len(entries) - 25} more"
        await interaction.response.send_message(
            f"**{len(entries)}** known spam image(s):\n" + "\n".join(lines) + suffix,
            ephemeral=True,
        )

    @spam.command(name="reload", description="Re-hash every file in data/spam_images")
    async def spam_reload(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        def hash_file(path: Path) -> str:
            return phash_bytes(
                path.read_bytes(),
                self.bot.config.max_image_pixels,
                self.bot.config.hash_size,
            )

        try:
            count = await asyncio.to_thread(self.bot.store.reload_from_disk, hash_file)
        except Exception:
            log.exception("Failed to reload spam images")
            await interaction.followup.send("Reload failed. Check the bot logs.", ephemeral=True)
            return
        await interaction.followup.send(f"Reloaded **{count}** spam image(s) from disk.", ephemeral=True)

    @spam.command(name="status", description="Show scanner status")
    async def spam_status(self, interaction: discord.Interaction) -> None:
        started = self.bot.started_at
        uptime = discord.utils.format_dt(started, style="R") if started else "starting"
        await interaction.response.send_message(
            "\n".join(
                [
                    f"Hashes: **{len(self.bot.store.entries)}**",
                    f"Threshold: `{self.bot.config.hash_threshold}`",
                    f"Alert channel: <#{self.bot.config.alert_channel_id}>",
                    f"Ready: {uptime}",
                ]
            ),
            ephemeral=True,
        )


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    if is_image_content_type(attachment.content_type):
        return True
    return is_image_filename(attachment.filename)
