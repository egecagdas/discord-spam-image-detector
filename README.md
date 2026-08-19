# Discord Spam Image Detector

A Discord bot that perceptual-hashes incoming images, compares them to a curated spam set, **auto-deletes** matches, and posts a staff alert with the evidence image attached. Invite it to as many servers as you want; each server picks its own alert channel with `/spam alerts`.

Kick/ban is not wired yet. Alerts include a disabled Kick placeholder for that later work.

Exact file hashes miss Discord’s re-encode, compress, and WebP conversion. This bot uses **pHash** (Hamming distance) so near-duplicates still match.

## Discord setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Open **Bot** and create a bot user. Copy the token into `.env` as `DISCORD_TOKEN`.
3. Enable the privileged **Message Content Intent** (required to see attachments and embeds).
4. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: View Channels, Read Message History, Send Messages, Embed Links, Attach Files, **Manage Messages**
5. Invite the bot with the generated URL (repeat for each server).
6. In Discord, run `/spam alerts` and choose the staff channel for detection notices.

## Run locally (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit .env: DISCORD_TOKEN
python -m spam_detector
```

Alternatively: `pip install -r requirements.txt`, then:

```powershell
$env:PYTHONPATH = "src"
python -m spam_detector
```

## Run as a service (Linux)

To keep the bot running after you close SSH (and after reboot), install it as a systemd service. Example unit at `/etc/systemd/system/spam-detector.service`:

```ini
[Unit]
Description=Discord spam image detector bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/discord-spam-image-detector
ExecStart=/root/discord-spam-image-detector/.venv/bin/python -m spam_detector
Restart=always
RestartSec=10
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Then:

```bash
systemctl daemon-reload
systemctl enable --now spam-detector
```

Do not also run `python -m spam_detector` in a shell while the service is active — Discord will drop one of the two sessions.

```bash
systemctl status spam-detector
journalctl -u spam-detector -f
systemctl restart spam-detector
systemctl stop spam-detector
```

## Spam image sets

Each server has its own hash set. Drop PNG/JPEG/WebP/GIF files into that server’s folder under `data/guilds/<guild_id>/spam_images/` and run `/spam reload`, or add them in Discord:

- `/spam add` — attach an image; stored for **this server**
- `/spam remove` — remove by name from this server
- `/spam list` — show this server’s set with image previews
- `/spam reload` — re-hash this server’s files
- `/spam alerts` — set this server’s staff alert channel
- `/spam status` — this server’s count, global count, threshold, alert channel, uptime

The application owner (you) can also maintain a **global** set that matches in every server:

- `/spam global add` / `remove` / `list` / `reload`

Those global files live in `data/spam_images/` (existing images there stay global). Per-server files are under `data/guilds/`.

Server commands require **Manage Server**, or the optional `ADMIN_ROLE_ID`. Global commands require the Discord application owner.

## Matching

- Algorithm: 64-bit pHash (`HASH_THRESHOLD`, default `10`; lower is stricter)
- Sources: image attachments and embed images/thumbnails (not stickers or video)
- GIFs: first frame
- Downloads are capped (`MAX_IMAGE_BYTES`, default 10 MB) with timeouts and a concurrency limit

## Tests

```powershell
pytest
```
