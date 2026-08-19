from __future__ import annotations

import pytest

from spam_detector.config import Config


def test_from_env_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        Config.from_env(dotenv_path=tmp_path / "missing.env")


def test_from_env_reads_values(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=test-token\nHASH_THRESHOLD=7\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("HASH_THRESHOLD", raising=False)
    config = Config.from_env(dotenv_path=env_file)
    assert config.token == "test-token"
    assert config.hash_threshold == 7
    assert config.guild_settings_path == config.data_dir / "guild_settings.json"
