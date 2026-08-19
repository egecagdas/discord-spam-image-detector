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
from spam_detector.store import HashStore

log = logging.getLogger(__name__)


class SpamDetectorBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.store = HashStore(config.hashes_path, config.images_dir)
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: datetime | None = None
        self.messages_seen = 0
        self.last_seen_channel_id: int | None = None

    async def setup_hook(self) -> None:
        self.store.load()
        timeout = aiohttp.ClientTimeout(total=self.config.download_timeout, connect=5)
        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "discord-spam-image-detector/0.1"},
        )
        await self.add_cog(ScannerCog(self))
        await self.add_cog(AdminCog(self))
        guild = discord.Object(id=self.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %s guild commands", len(synced))

    async def on_ready(self) -> None:
        if self.started_at is None:
            self.started_at = discord.utils.utcnow()
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        log.info(
            "Intents: messages=%s message_content=%s | hashes=%s",
            self.intents.messages,
            self.intents.message_content,
            len(self.store.entries),
        )
        guild = self.get_guild(self.config.guild_id)
        if guild is None:
            joined = ", ".join(f"{g.name} ({g.id})" for g in self.guilds) or "none"
            log.error(
                "Bot is not in GUILD_ID %s. It is currently in: %s. "
                "Set GUILD_ID to the ID of the server where the bot is online "
                "(Developer Mode → right-click the server name in the left sidebar → Copy Server ID).",
                self.config.guild_id,
                joined,
            )
            return
        me = guild.me
        perms = me.guild_permissions if me is not None else None
        log.info(
            "Watching guild %s (%s); visible channels=%s; view_channel=%s read_history=%s manage_messages=%s",
            guild.name,
            guild.id,
            len(guild.channels),
            getattr(perms, "view_channel", None),
            getattr(perms, "read_message_history", None),
            getattr(perms, "manage_messages", None),
        )
        alert = guild.get_channel(self.config.alert_channel_id) or self.get_channel(self.config.alert_channel_id)
        if alert is None:
            log.error(
                "ALERT_CHANNEL_ID %s is not visible to the bot. Grant View Channel on that channel.",
                self.config.alert_channel_id,
            )
        else:
            log.info("Alert channel is #%s (%s)", getattr(alert, "name", alert.id), alert.id)
        log.info(
            "Send a test message in a channel the bot can see. A 'Saw message' line should appear here."
        )

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
