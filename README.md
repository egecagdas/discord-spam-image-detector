# Discord Spam Image Detector

A Discord bot for a single large guild. It perceptual-hashes incoming images, compares them to a curated spam set, **auto-deletes** matches, and posts a staff alert with the evidence image attached.

Kick/ban is not wired yet. Alerts include a disabled Kick placeholder for that later work.

Exact file hashes miss Discord’s re-encode, compress, and WebP conversion. This bot uses **pHash** (Hamming distance) so near-duplicates still match.

## Discord setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Open **Bot** and create a bot user. Copy the token into `.env` as `DISCORD_TOKEN`.
3. Enable the privileged **Message Content Intent** (required to see attachments and embeds).
4. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: View Channels, Read Message History, Send Messages, Embed Links, Attach Files, **Manage Messages**
5. Invite the bot with the generated URL.
6. Enable Developer Mode in Discord, then copy:
   - Server ID → `GUILD_ID`
   - Staff alert channel ID → `ALERT_CHANNEL_ID`

## Run locally (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit .env: DISCORD_TOKEN, GUILD_ID, ALERT_CHANNEL_ID
python -m spam_detector
```

Alternatively: `pip install -r requirements.txt`, then:

```powershell
$env:PYTHONPATH = "src"
python -m spam_detector
```

## Spam image set

Drop PNG/JPEG/WebP/GIF files into `data/spam_images/` and run `/spam reload`, or add them in Discord:

- `/spam add` — attach an image; stored and hashed
- `/spam remove` — remove by name
- `/spam list` — show the current set
- `/spam reload` — re-hash everything in `data/spam_images/`
- `/spam status` — hash count, threshold, uptime

Commands require **Manage Server**, or the optional `ADMIN_ROLE_ID`.

## Matching

- Algorithm: 64-bit pHash (`HASH_THRESHOLD`, default `10`; lower is stricter)
- Sources: image attachments and embed images/thumbnails (not stickers or video)
- GIFs: first frame
- Downloads are capped (`MAX_IMAGE_BYTES`, default 10 MB) with timeouts and a concurrency limit

## Tests

```powershell
pytest
```
