from __future__ import annotations

import pytest

from spam_detector.config import Config


def test_from_env_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("GUILD_ID", "1")
    monkeypatch.setenv("ALERT_CHANNEL_ID", "2")
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        Config.from_env(dotenv_path=tmp_path / "missing.env")


def test_from_env_reads_values(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=test-token\nGUILD_ID=111\nALERT_CHANNEL_ID=222\nHASH_THRESHOLD=7\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("GUILD_ID", raising=False)
    monkeypatch.delenv("ALERT_CHANNEL_ID", raising=False)
    monkeypatch.delenv("HASH_THRESHOLD", raising=False)
    config = Config.from_env(dotenv_path=env_file)
    assert config.token == "test-token"
    assert config.guild_id == 111
    assert config.alert_channel_id == 222
    assert config.hash_threshold == 7
