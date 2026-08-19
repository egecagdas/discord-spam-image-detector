from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from spam_detector.cogs.scanner import ScannerCog
from spam_detector.store import HashEntry, sanitize_filename


def _bot(*, entries: bool = True, global_entries: bool = False, alert_channel_id: int | None = 200) -> MagicMock:
    bot = MagicMock()
    bot.config.download_concurrency = 2
    bot.user = SimpleNamespace(id=1)
    guild_entries = (
        [HashEntry(id="abc", name="scam", filename="scam.png", phash="ffff")]
        if entries
        else []
    )
    shared_entries = (
        [HashEntry(id="g1", name="global-scam", filename="global.png", phash="aaaa")]
        if global_entries
        else []
    )
    bot.stores.has_hashes.side_effect = lambda _guild_id: bool(guild_entries or shared_entries)
    bot.http_session = None
    bot.guild_settings.get_alert_channel_id.side_effect = lambda _guild_id: alert_channel_id
    return bot


def _message(
    *,
    guild_id: int | None = 100,
    channel_id: int = 300,
    author_id: int = 9,
    is_bot: bool = False,
    has_media: bool = True,
) -> MagicMock:
    message = MagicMock()
    if guild_id is None:
        message.guild = None
    else:
        message.guild.id = guild_id
    message.channel.id = channel_id
    message.author.id = author_id
    message.author.bot = is_bot
    message.attachments = [MagicMock()] if has_media else []
    message.embeds = []
    return message


def test_skips_dms() -> None:
    cog = ScannerCog(_bot())
    assert cog._should_scan(_message(guild_id=None)) is False


def test_scans_any_guild() -> None:
    cog = ScannerCog(_bot())
    assert cog._should_scan(_message(guild_id=999)) is True


def test_skips_alert_channel() -> None:
    cog = ScannerCog(_bot())
    message = _message(channel_id=200)
    assert cog._should_scan(message) is False
    assert cog._skip_reason(message) == "posted in the alert channel"


def test_scans_when_alert_channel_unset() -> None:
    cog = ScannerCog(_bot(alert_channel_id=None))
    assert cog._should_scan(_message(channel_id=200)) is True


def test_skips_bots_and_self() -> None:
    cog = ScannerCog(_bot())
    assert cog._should_scan(_message(is_bot=True)) is False
    assert cog._should_scan(_message(author_id=1)) is False


def test_skips_empty_store_and_no_media() -> None:
    cog = ScannerCog(_bot(entries=False))
    assert cog._should_scan(_message()) is False
    cog = ScannerCog(_bot(entries=False, global_entries=True))
    assert cog._should_scan(_message()) is True
    cog = ScannerCog(_bot())
    assert cog._should_scan(_message(has_media=False)) is False


def test_scans_normal_guild_image() -> None:
    cog = ScannerCog(_bot())
    assert cog._should_scan(_message()) is True


def test_download_rejects_non_http() -> None:
    cog = ScannerCog(_bot())

    async def _run() -> None:
        assert await cog._download_url("file:///tmp/x.png") is None
        assert await cog._download_url("http:///no-host") is None
        assert await cog._download_url("not-a-url") is None

    asyncio.run(_run())


def test_sanitize_filename_strips_paths() -> None:
    assert sanitize_filename("../../evil.png") == "evil.png"
    assert sanitize_filename("hi there.PNG") == "hi_there.PNG"
