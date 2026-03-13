# CyberNotify

Monitors a CyberPass van tracker and sends a Telegram notification when the van enters a target city.

## Setup

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **bot token**
4. Message your new bot (send anything), then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` to find your **chat ID** in the response JSON under `result[0].message.chat.id`

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description | Default |
|---|---|---|
| `CYBERPASS_USERNAME` | CyberPass login username | *(required)* |
| `CYBERPASS_PASSWORD` | CyberPass login password | *(required)* |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather | *(required)* |
| `TELEGRAM_CHAT_ID` | Telegram chat ID(s) to notify — comma-separated for multiple recipients | *(required)* |
| `TRACKER_ID` | Tracker ID of the van to monitor | `45540` |
| `TARGET_CITY` | City name to trigger notification (diacritics-insensitive) | `Ghaxaq` |
| `POLL_INTERVAL_SECONDS` | How often to check in seconds | `15` |
| `NOTIFY_WINDOW_START` | Start of notification window (24h) | `13:30` |
| `NOTIFY_WINDOW_END` | End of notification window (24h) | `14:30` |
| `NOTIFY_DAYS` | Days to monitor (0=Mon … 4=Fri) | `0,1,2,3,4` |
| `TZ` | Timezone | `Europe/Malta` |
| `LOG_LEVEL` | Log verbosity level | `INFO` |

### 3. Run with Docker

```bash
docker compose up -d
```

Check logs:

```bash
docker compose logs -f
```

### 4. Run without Docker

```bash
pip install -r requirements.txt
# either export env vars or source .env manually
python cybernotify.py
```

## How it works

1. Authenticates with the CyberPass tracking API
2. During the configured time window (Mon–Fri 13:30–14:30 by default), polls the LiveData endpoint every 15 seconds
3. When the van's `Position_CityName` contains the target city, sends a one-time Telegram notification
4. Sleeps outside the window and resets daily
5. Re-authenticates automatically if the session expires

The city matching strips Unicode diacritics, so `Ghaxaq` in the config will match `Ħal Għaxaq` from the API.
