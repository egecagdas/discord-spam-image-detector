from __future__ import annotations

import asyncio
import io
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
    jpeg_thumbnail,
)
from spam_detector.store import HashEntry, HashStore

if TYPE_CHECKING:
    from spam_detector.bot import SpamDetectorBot

log = logging.getLogger(__name__)

NOT_IN_GUILD_MESSAGE = "This command can only be used in a server."
NOT_BOT_OWNER_MESSAGE = "Only the bot owner can manage the global spam set."
MISSING_PERMISSION_MESSAGE = (
    "You need Manage Server or the configured admin role to use this command."
)


def admin_check_failure_message(
    interaction: discord.Interaction,
    *,
    admin_role_id: int | None,
    owner_id: int | None = None,
) -> str | None:
    """Return an error message if the user cannot run admin commands, else None."""
    guild_id = interaction.guild_id
    if guild_id is None:
        return NOT_IN_GUILD_MESSAGE

    user = interaction.user
    resolved_owner_id = owner_id
    if resolved_owner_id is None and interaction.guild is not None:
        resolved_owner_id = interaction.guild.owner_id
    if resolved_owner_id is not None and resolved_owner_id == user.id:
        return None

    perms = interaction.permissions
    if perms.administrator or perms.manage_guild:
        return None

    if isinstance(user, discord.Member):
        guild_perms = user.guild_permissions
        if guild_perms.administrator or guild_perms.manage_guild:
            return None
        if admin_role_id and user.get_role(admin_role_id):
            return None

    return MISSING_PERMISSION_MESSAGE


def is_global_spam_command(interaction: discord.Interaction) -> bool:
    command = interaction.command
    if command is None:
        return False
    name = getattr(command, "qualified_name", "") or ""
    return name.startswith("spam global")


class AdminCog(commands.Cog):
    spam = app_commands.Group(name="spam", description="Manage spam image sets")
    spam_global = app_commands.Group(
        name="global",
        description="Manage the global spam set (bot owner only)",
        parent=spam,
    )

    def __init__(self, bot: SpamDetectorBot) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_global_spam_command(interaction):
            if not await self.bot.is_owner(interaction.user):
                raise app_commands.CheckFailure(NOT_BOT_OWNER_MESSAGE)
            return True
        if await self.bot.is_owner(interaction.user):
            if interaction.guild_id is None:
                raise app_commands.CheckFailure(NOT_IN_GUILD_MESSAGE)
            return True
        guild = interaction.guild or (
            self.bot.get_guild(interaction.guild_id) if interaction.guild_id else None
        )
        message = admin_check_failure_message(
            interaction,
            admin_role_id=self.bot.config.admin_role_id,
            owner_id=guild.owner_id if guild is not None else None,
        )
        if message is None:
            return True
        raise app_commands.CheckFailure(message)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or MISSING_PERMISSION_MESSAGE
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

    def _guild_store(self, interaction: discord.Interaction) -> HashStore | None:
        if interaction.guild_id is None:
            return None
        return self.bot.stores.guild_store(interaction.guild_id)

    @spam.command(name="add", description="Add an image to this server's spam set")
    @app_commands.describe(image="Image that should be treated as spam in this server")
    async def spam_add(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        store = self._guild_store(interaction)
        if store is None:
            await interaction.response.send_message(NOT_IN_GUILD_MESSAGE, ephemeral=True)
            return
        await self._add_image(interaction, image, store, scope="this server")

    @spam_global.command(name="add", description="Add an image to the global spam set")
    @app_commands.describe(image="Image that should be treated as spam in every server")
    async def spam_global_add(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        await self._add_image(interaction, image, self.bot.stores.global_store, scope="the global set")

    async def _add_image(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        store: HashStore,
        *,
        scope: str,
    ) -> None:
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

        existing = store.find_match(phash, threshold=0)
        entry = await asyncio.to_thread(
            store.add,
            Path(image.filename).stem,
            image.filename,
            phash,
            data,
        )
        extra = ""
        if existing is not None:
            extra = f" (already similar to `{existing.entry.name}` at distance 0)"
        await interaction.followup.send(
            f"Added `{entry.name}` (`{entry.id}`) to {scope} with pHash `{entry.phash}`.{extra}",
            ephemeral=True,
        )

    @spam.command(name="remove", description="Remove an image from this server's spam set")
    @app_commands.describe(name="Name, filename, or id from /spam list")
    async def spam_remove(self, interaction: discord.Interaction, name: str) -> None:
        store = self._guild_store(interaction)
        if store is None:
            await interaction.response.send_message(NOT_IN_GUILD_MESSAGE, ephemeral=True)
            return
        await self._remove_image(interaction, name, store)

    @spam_global.command(name="remove", description="Remove an image from the global spam set")
    @app_commands.describe(name="Name, filename, or id from /spam global list")
    async def spam_global_remove(self, interaction: discord.Interaction, name: str) -> None:
        await self._remove_image(interaction, name, self.bot.stores.global_store)

    async def _remove_image(self, interaction: discord.Interaction, name: str, store: HashStore) -> None:
        removed = store.remove(name)
        if removed is None:
            await interaction.response.send_message(f"No spam entry named `{name}`.", ephemeral=True)
            return
        await interaction.response.send_message(f"Removed `{removed.name}`.", ephemeral=True)

    @spam_remove.autocomplete("name")
    async def spam_remove_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        store = self._guild_store(interaction)
        if store is None:
            return []
        return _autocomplete_entries(store, current)

    @spam_global_remove.autocomplete("name")
    async def spam_global_remove_autocomplete(
        self,
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return _autocomplete_entries(self.bot.stores.global_store, current)

    @spam.command(name="list", description="List this server's spam images")
    async def spam_list(self, interaction: discord.Interaction) -> None:
        store = self._guild_store(interaction)
        if store is None:
            await interaction.response.send_message(NOT_IN_GUILD_MESSAGE, ephemeral=True)
            return
        await self._list_images(
            interaction,
            store,
            heading="spam image(s) for this server",
            empty="This server's spam set is empty.",
        )

    @spam_global.command(name="list", description="List global spam images")
    async def spam_global_list(self, interaction: discord.Interaction) -> None:
        await self._list_images(
            interaction,
            self.bot.stores.global_store,
            heading="global spam image(s)",
            empty="The global spam set is empty.",
        )

    async def _list_images(
        self,
        interaction: discord.Interaction,
        store: HashStore,
        *,
        heading: str,
        empty: str,
    ) -> None:
        entries = store.entries
        if not entries:
            await interaction.response.send_message(empty, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        for page, start in enumerate(range(0, len(entries), LIST_PAGE_SIZE)):
            chunk = entries[start : start + LIST_PAGE_SIZE]
            embeds: list[discord.Embed] = []
            files: list[discord.File] = []
            for entry in chunk:
                embed, file = _list_entry_display(entry, store.images_dir, self.bot.config.max_image_pixels)
                embeds.append(embed)
                if file is not None:
                    files.append(file)
            content = f"**{len(entries)}** {heading}:" if page == 0 else None
            await interaction.followup.send(content=content, embeds=embeds, files=files, ephemeral=True)

    @spam.command(name="reload", description="Re-hash this server's spam image files")
    async def spam_reload(self, interaction: discord.Interaction) -> None:
        store = self._guild_store(interaction)
        if store is None:
            await interaction.response.send_message(NOT_IN_GUILD_MESSAGE, ephemeral=True)
            return
        await self._reload_store(interaction, store)

    @spam_global.command(name="reload", description="Re-hash files in data/spam_images")
    async def spam_global_reload(self, interaction: discord.Interaction) -> None:
        await self._reload_store(interaction, self.bot.stores.global_store)

    async def _reload_store(self, interaction: discord.Interaction, store: HashStore) -> None:
        await interaction.response.defer(ephemeral=True)

        def hash_file(path: Path) -> str:
            return phash_bytes(
                path.read_bytes(),
                self.bot.config.max_image_pixels,
                self.bot.config.hash_size,
            )

        try:
            count = await asyncio.to_thread(store.reload_from_disk, hash_file)
        except Exception:
            log.exception("Failed to reload spam images")
            await interaction.followup.send("Reload failed. Check the bot logs.", ephemeral=True)
            return
        await interaction.followup.send(f"Reloaded **{count}** spam image(s) from disk.", ephemeral=True)

    @spam.command(name="alerts", description="Set the staff channel for spam detection alerts")
    @app_commands.describe(channel="Text channel where detection alerts are posted")
    async def spam_alerts(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(NOT_IN_GUILD_MESSAGE, ephemeral=True)
            return
        me = channel.guild.me if channel.guild is not None else None
        if me is None and interaction.guild is not None:
            me = interaction.guild.me
        perms = channel.permissions_for(me) if me is not None else None
        if perms is not None and not (perms.view_channel and perms.send_messages):
            await interaction.response.send_message(
                f"I cannot post alerts in {channel.mention}. Grant View Channel and Send Messages.",
                ephemeral=True,
            )
            return
        self.bot.guild_settings.set_alert_channel_id(guild_id, channel.id)
        await interaction.response.send_message(
            f"Spam alerts for this server will be posted in {channel.mention}.",
            ephemeral=True,
        )

    @spam.command(name="status", description="Show scanner status")
    async def spam_status(self, interaction: discord.Interaction) -> None:
        started = self.bot.started_at
        uptime = discord.utils.format_dt(started, style="R") if started else "starting"
        guild_id = interaction.guild_id
        alert_channel_id = (
            self.bot.guild_settings.get_alert_channel_id(guild_id) if guild_id is not None else None
        )
        if alert_channel_id is None:
            alert_line = "Alert channel: not set — use `/spam alerts`"
        else:
            alert_line = f"Alert channel: <#{alert_channel_id}>"
        guild_count = len(self._guild_store(interaction).entries) if guild_id is not None else 0
        await interaction.response.send_message(
            "\n".join(
                [
                    f"This server: **{guild_count}** hash(es)",
                    f"Global: **{len(self.bot.stores.global_store.entries)}** hash(es)",
                    f"Threshold: `{self.bot.config.hash_threshold}`",
                    alert_line,
                    f"Messages seen: **{self.bot.messages_seen}**",
                    f"Last channel: {f'<#{self.bot.last_seen_channel_id}>' if self.bot.last_seen_channel_id else 'none'}",
                    f"Ready: {uptime}",
                ]
            ),
            ephemeral=True,
        )


LIST_PAGE_SIZE = 10


def _autocomplete_entries(store: HashStore, current: str) -> list[app_commands.Choice[str]]:
    needle = current.casefold()
    choices: list[app_commands.Choice[str]] = []
    for entry in store.entries:
        if needle and needle not in entry.name.casefold() and needle not in entry.filename.casefold():
            continue
        choices.append(app_commands.Choice(name=entry.name, value=entry.name))
        if len(choices) >= 25:
            break
    return choices


def _list_entry_display(
    entry: HashEntry,
    images_dir: Path,
    max_pixels: int,
) -> tuple[discord.Embed, discord.File | None]:
    embed = discord.Embed(title=entry.name, color=discord.Color.dark_red())
    embed.add_field(name="ID", value=f"`{entry.id}`", inline=True)
    embed.add_field(name="pHash", value=f"`{entry.phash}`", inline=True)
    path = images_dir / entry.filename
    if not path.is_file():
        embed.set_footer(text="Image file is missing on disk")
        return embed, None
    try:
        thumb = jpeg_thumbnail(path.read_bytes(), max_pixels=max_pixels)
    except (InvalidImageError, ImageTooLargeError, OSError):
        embed.set_footer(text="Could not load image preview")
        return embed, None
    filename = f"{entry.id}.jpg"
    embed.set_image(url=f"attachment://{filename}")
    return embed, discord.File(io.BytesIO(thumb), filename=filename)


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    if getattr(attachment, "width", None) and getattr(attachment, "height", None):
        return True
    if is_image_content_type(attachment.content_type):
        return True
    return is_image_filename(attachment.filename)
