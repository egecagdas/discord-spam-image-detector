# Privacy Policy for Discord Spam Image Detector

**Effective date:** August 27, 2026  
**Last updated:** August 27, 2026  
**Contact:** **Replace this placeholder with a monitored email address before publishing.**

Discord Spam Image Detector ("the bot", "we", "us") is a Discord server-moderation bot that detects images matching a server's configured spam-image reference set. This policy describes how the bot processes information received through Discord.

## Information the bot processes

To perform its moderation function, the bot may process:

- Image attachments and image URLs embedded in messages in Discord servers where the bot is installed and can view the channel.
- Message, channel, server, and author identifiers needed to identify a match and notify moderators.
- Limited account metadata shown in a match alert, including the author's Discord ID, account-creation time, and server-join time when Discord provides it.
- Spam-image reference images, filenames, and perceptual hashes deliberately added by authorized server administrators or the bot operator.
- The server's configured staff-alert channel ID.
- Operational logs, which may contain message IDs, user IDs, channel IDs, image filenames, match results, and error information needed to operate and secure the bot.

The bot does not read or use message text to determine whether an image is spam. Discord's Message Content intent is enabled because Discord message events require it to provide the attachment and embed information the bot needs to inspect images.

## How information is used

The bot uses this information only to:

- Download and calculate a perceptual hash for supported image attachments and embedded images.
- Compare that hash against the relevant server-specific and, where configured, global spam-image reference sets.
- Delete a message that matches the configured similarity threshold, when the bot has the necessary Discord permission.
- Send a match alert to the staff channel selected by that server's administrators.
- Let authorized administrators manage their server's reference set and alert-channel setting.
- Maintain, secure, troubleshoot, and improve the bot's moderation functionality.

The bot does not use this information for advertising, user profiling, selling data, or unrelated analytics. It does not currently kick or ban users.

## Storage and sharing

### Images that do not match

The bot processes non-matching image bytes in memory to calculate a perceptual hash. It does not intentionally save those image bytes to its local data directory or reference database.

### Reference-set images

When an authorized administrator adds an image with `/spam add`, the bot stores the image and its perceptual hash in that server's local reference set. The bot operator may also maintain a global reference set, whose images can be used to detect matching spam in every server where the bot is installed.

### Matched images and moderator alerts

When the bot finds a match, it sends the matching image and relevant moderation details to the staff-alert channel configured by that server. Discord stores that alert as Discord content, subject to the server's settings and Discord's policies. Access to alert content is controlled by the server administrators and Discord channel permissions.

### Service providers

The bot may use hosting, storage, backup, and infrastructure providers to operate the service. Those providers may process data only to provide services for the bot and under appropriate confidentiality and security obligations.

We do not sell API data or share it with third parties for their independent use.

## Retention

We retain information only for as long as necessary to operate the bot, maintain the configured spam-image reference sets, meet legal obligations, resolve disputes, and enforce this policy.

- Non-matching image bytes are discarded after in-memory processing.
- Reference-set images and hashes are retained until an authorized administrator removes them, the bot operator removes them from the global set, or deletion is otherwise required.
- Match alerts are retained by Discord according to the applicable server and channel retention practices.
- Operational logs should be configured by the bot operator with a limited retention period appropriate to troubleshooting and security needs.

If the bot is discontinued, stored Discord API data will be deleted unless retention is required by law.

## Your choices and deletion requests

You may request access to, correction of, or deletion of Discord API data processed by the bot by contacting us at the email address listed above. Please include your Discord user ID, the relevant server, and enough detail to identify the data you are requesting.

We will review and respond to requests as required by applicable law and Discord's Developer Terms. Some information may be controlled by the server administrator or retained by Discord, such as staff-channel alerts; in those cases, you may also need to contact the relevant server administrator or Discord.

## Security

We use reasonable administrative, technical, and organizational measures designed to protect data processed by the bot from unauthorized access, use, loss, alteration, disclosure, or destruction. The bot operator must secure the hosting environment, restrict access to bot data and staff-alert channels, encrypt stored data and backups at rest, and keep credentials such as the Discord bot token confidential.

No method of storage or transmission is completely secure. If we discover unauthorized access to Discord API data, we will take appropriate remediation and notification steps as required by applicable law and Discord's Developer Terms.

## International processing

The bot may be hosted or operated in a country different from where you live. By using a Discord server where the bot is installed, information may be processed in the location where the bot and its service providers operate, subject to applicable law.

## Changes to this policy

We may update this policy when the bot's data practices change or when required by law or Discord policy. The current version will be published at the same public URL linked from the Discord Developer Portal.
