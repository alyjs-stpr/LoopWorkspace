# Private Nightscout for LoKey

Prepared configuration; no instance has been deployed. Choose hosting before uploading health data.

## Recommended: managed Nightscout

[T1Pal](https://www.t1pal.com/) advertises service starting at $11.99/month as checked October 12, 2026; check the checkout for current charges. It provides the running server/database and maintenance. Other managed providers are listed in [Nightscout documentation](https://nightscout.github.io/index.html). Create the account yourself, choose an HTTPS site URL and keep its administrator secret in your password manager.

Apply these settings through the provider's supported controls, or have support apply them. Preserve any existing ENABLE values, appending missing words rather than duplicating them:

| Variable | Value |
| --- | --- |
| ENABLE | loop iob cob basal pump sage cage bage dbsize |
| DEVICESTATUS_ADVANCED | true |
| SHOW_FORECAST | loop |
| SHOW_PLUGINS | loop iob cob basal pump |
| AUTH_DEFAULT_ROLES | denied |
| ALLOW_UNRESTRICTED_FRAME_EMBEDDING | false |
| DISPLAY_UNITS | mg/dl |
| TIMEZONE | America/New_York |

These enable monitoring. Remote-control/APNs setup is unnecessary for Follow. No Dexcom bridge credentials are required when Loop uploads glucose. Confirm which settings your provider permits and how its tokens are issued.

## Connect your installed LoKey Loop

1. Open LoKey **Settings → Services → Add Service → Nightscout** (wording may vary by Loop version).
2. Enter the HTTPS Nightscout URL and uploader credential supplied by the host (the API secret for standard Nightscout). Save/enable the service. Enter this on your iPhone, not in a GitHub file or chat.
3. Let Loop upload a few cycles; verify that glucose, Loop status, IOB, predictions, and treatments appear on the Nightscout site. A successful website load alone does not verify upload.
4. Verify Nightscout's selected plugins include Loop, IOB and basal; forecast source is Loop.
5. Sign in to Nightscout administrator tools. Create **separate** `readable` subjects/tokens for your iPhone and your husband's phone. Use provider-issued equivalents if the provider has a different account flow.
6. Confirm an unauthenticated/private-browser visit cannot view readings. Enter the base URL and each device's readable token in Follow. Verify they can read but cannot write.

No Loop code change or new Loop build should be necessary merely to add its existing Nightscout upload service. Use the service/uploader, not Nightscout Remote CGM, as your data is already coming from Dexcom on the Loop phone.

## DIY alternative

The Compose file is for a Docker host **you control**, with an HTTPS reverse proxy to `127.0.0.1:1337`. It is not a Netlify static deployment. It creates a persistent MongoDB volume. Keep backups and updates. The MongoDB port is not published.

1. Copy `.env.example` to `.env`; generate different long random secrets for `API_SECRET` and `MONGO_PASSWORD`. Use at least 32 random alphanumeric characters for the database password so it can be used safely in the MongoDB URI. Never commit `.env`.
2. Run `docker compose --env-file .env config --quiet`, then `docker compose --env-file .env up -d`.
3. Configure your existing HTTPS reverse proxy and certificate before connecting phones. Do not expose plain HTTP to the internet.
4. Complete the same upload/token checks above. Monitor storage and establish backups before use.

The Nightscout image is pinned to the current released version 15.0.8; review release notes before updates. The host, HTTPS URL and billing choice are still needed to make this live.

References: [Loop configuration](https://loopkit.github.io/loopdocs/nightscout/update-user/), [Nightscout security](https://nightscout.github.io/nightscout/security/), [hosting choices](https://nightscout.github.io/nightscout/platform/), [15.0.8](https://github.com/nightscout/cgm-remote-monitor/releases/tag/v15.0.8).
