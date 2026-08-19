from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord

from spam_detector.cogs.admin import (
    MISSING_PERMISSION_MESSAGE,
    NOT_IN_GUILD_MESSAGE,
    _list_entry_display,
    admin_check_failure_message,
    is_global_spam_command,
)
from spam_detector.store import HashEntry

from helpers import bars_image, image_to_png_bytes

GUILD_ID = 100
OWNER_ID = 1
ADMIN_ROLE_ID = 55


def _interaction(
    *,
    guild_id: int | None = GUILD_ID,
    user_id: int = OWNER_ID,
    owner_id: int | None = OWNER_ID,
    guild_cached: bool = True,
    is_member: bool = True,
    administrator: bool = False,
    manage_guild: bool = False,
    has_admin_role: bool = False,
) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.permissions = discord.Permissions.none()
    interaction.permissions.administrator = administrator
    interaction.permissions.manage_guild = manage_guild

    if is_member:
        user = MagicMock(spec=discord.Member)
        user.id = user_id
        user.guild_permissions = discord.Permissions.none()
        user.guild_permissions.administrator = administrator
        user.guild_permissions.manage_guild = manage_guild
        user.get_role.side_effect = lambda role_id: object() if has_admin_role and role_id == ADMIN_ROLE_ID else None
    else:
        user = MagicMock(spec=discord.User)
        user.id = user_id

    interaction.user = user
    if guild_id is None or not guild_cached:
        interaction.guild = None
    else:
        interaction.guild = SimpleNamespace(id=guild_id, owner_id=owner_id)
    return interaction


def test_allows_server_owner_even_without_manage_guild_bit() -> None:
    interaction = _interaction(manage_guild=False, administrator=False)
    assert admin_check_failure_message(interaction, admin_role_id=None) is None


def test_allows_owner_when_user_is_not_a_member() -> None:
    interaction = _interaction(is_member=False, manage_guild=False)
    assert admin_check_failure_message(interaction, admin_role_id=None) is None


def test_allows_manage_server_when_guild_is_not_cached() -> None:
    interaction = _interaction(guild_cached=False, is_member=False, manage_guild=True)
    assert admin_check_failure_message(interaction, admin_role_id=None) is None


def test_allows_administrator_permission() -> None:
    interaction = _interaction(user_id=9, owner_id=OWNER_ID, administrator=True)
    assert admin_check_failure_message(interaction, admin_role_id=None) is None


def test_allows_configured_admin_role() -> None:
    interaction = _interaction(user_id=9, owner_id=OWNER_ID, has_admin_role=True)
    assert admin_check_failure_message(interaction, admin_role_id=ADMIN_ROLE_ID) is None


def test_allows_any_guild() -> None:
    interaction = _interaction(guild_id=999)
    assert admin_check_failure_message(interaction, admin_role_id=None) is None


def test_rejects_dms() -> None:
    interaction = _interaction(guild_id=None)
    assert admin_check_failure_message(interaction, admin_role_id=None) == NOT_IN_GUILD_MESSAGE


def test_rejects_plain_member() -> None:
    interaction = _interaction(user_id=9, owner_id=OWNER_ID)
    assert admin_check_failure_message(interaction, admin_role_id=None) == MISSING_PERMISSION_MESSAGE


def test_list_entry_display_attaches_image(tmp_path: Path) -> None:
    (tmp_path / "scam.png").write_bytes(image_to_png_bytes(bars_image()))
    entry = HashEntry(id="abc", name="scam", filename="scam.png", phash="ffff")
    embed, file = _list_entry_display(entry, tmp_path, max_pixels=1_000_000)
    assert embed.image.url == "attachment://abc.jpg"
    assert file is not None
    assert file.filename == "abc.jpg"


def test_list_entry_display_missing_file(tmp_path: Path) -> None:
    entry = HashEntry(id="abc", name="scam", filename="missing.png", phash="ffff")
    embed, file = _list_entry_display(entry, tmp_path, max_pixels=1_000_000)
    assert file is None
    assert embed.footer.text == "Image file is missing on disk"


def test_is_global_spam_command() -> None:
    interaction = MagicMock()
    interaction.command = SimpleNamespace(qualified_name="spam global add")
    assert is_global_spam_command(interaction) is True
    interaction.command = SimpleNamespace(qualified_name="spam add")
    assert is_global_spam_command(interaction) is False
    interaction.command = None
    assert is_global_spam_command(interaction) is False
