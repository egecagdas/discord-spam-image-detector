from __future__ import annotations

import logging
import os
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands

from spam_detector.config import Config
from spam_detector.cogs.admin import AdminCog
from spam_detector.cogs.scanner import ScannerCog
from spam_detector.store import GuildSettingsStore, StoreManager

log = logging.getLogger(__name__)


class SpamDetectorBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.stores = StoreManager(config.data_dir)
        self.guild_settings = GuildSettingsStore(config.guild_settings_path)
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: datetime | None = None
        self.messages_seen = 0
        self.last_seen_channel_id: int | None = None

    async def setup_hook(self) -> None:
        self.stores.load()
        self.guild_settings.load()
        timeout = aiohttp.ClientTimeout(total=self.config.download_timeout, connect=5)
        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "discord-spam-image-detector/0.1"},
        )
        await self.add_cog(ScannerCog(self))
        await self.add_cog(AdminCog(self))
        synced = await self.tree.sync()
        log.info("Synced %s global commands", len(synced))

    async def on_ready(self) -> None:
        first_ready = self.started_at is None
        if first_ready:
            self.started_at = discord.utils.utcnow()
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        log.info(
            "Intents: messages=%s message_content=%s | global_hashes=%s",
            self.intents.messages,
            self.intents.message_content,
            len(self.stores.global_store.entries),
        )
        if not first_ready:
            return
        for guild in self.guilds:
            await self._clear_guild_commands(guild)
        if not self.guilds:
            log.warning("Bot is not in any servers yet. Invite it, then run /spam alerts to pick a staff channel.")
            return
        for guild in self.guilds:
            me = guild.me
            perms = me.guild_permissions if me is not None else None
            alert_id = self.guild_settings.get_alert_channel_id(guild.id)
            alert = guild.get_channel(alert_id) if alert_id is not None else None
            if alert is None and alert_id is not None:
                alert = self.get_channel(alert_id)
            if alert_id is None:
                alert_note = "not set (use /spam alerts)"
            elif alert is None:
                alert_note = f"missing channel {alert_id}"
            else:
                alert_note = f"#{getattr(alert, 'name', alert.id)} ({alert.id})"
            log.info(
                "Watching guild %s (%s); visible channels=%s; view_channel=%s read_history=%s "
                "manage_messages=%s; alert=%s",
                guild.name,
                guild.id,
                len(guild.channels),
                getattr(perms, "view_channel", None),
                getattr(perms, "read_message_history", None),
                getattr(perms, "manage_messages", None),
                alert_note,
            )
        log.info(
            "Send a test message in a channel the bot can see. A 'Saw message' line should appear here."
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("Joined guild %s (%s). Use /spam alerts to pick a staff channel.", guild.name, guild.id)
        await self._clear_guild_commands(guild)

    async def _clear_guild_commands(self, guild: discord.Guild) -> None:
        """Drop leftover guild-scoped copies so only the global commands remain."""
        try:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        except Exception:
            log.exception("Failed to clear duplicate guild commands for %s (%s)", guild.name, guild.id)

    async def on_message(self, message: discord.Message) -> None:
        self.messages_seen += 1
        self.last_seen_channel_id = message.channel.id
        channel = getattr(message.channel, "name", None) or message.channel.id
        log.info(
            "Saw message %s in #%s from %s attachments=%s embeds=%s content_len=%s",
            message.id,
            channel,
            message.author,
            len(message.attachments),
            len(message.embeds),
            len(message.content or ""),
        )
        await self.process_commands(message)

    async def close(self) -> None:
        if self.http_session is not None and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.from_env()
    bot = SpamDetectorBot(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
