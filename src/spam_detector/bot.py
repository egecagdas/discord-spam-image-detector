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
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.store = HashStore(config.hashes_path, config.images_dir)
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: datetime | None = None

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
