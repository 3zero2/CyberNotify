"""CyberNotify — CyberPass van tracker with Telegram notifications."""

import logging
import os
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL) if _LOG_LEVEL in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cybernotify")

BASE_URL = "https://trak.cyberpass.com.mt/APIWeb"


# ── config ───────────────────────────────────────────────────────────────────

def _load_timezone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        log.warning("Invalid TZ value %r — falling back to 'Europe/Malta'.", tz_name)
        return ZoneInfo("Europe/Malta")


def load_config() -> dict:
    required = ["CYBERPASS_USERNAME", "CYBERPASS_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    cfg = {
        "username": os.environ.get("CYBERPASS_USERNAME", ""),
        "password": os.environ.get("CYBERPASS_PASSWORD", ""),
        "telegram_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_ids": [
            cid.strip() for cid in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()
        ],
        "tracker_id": int(os.environ.get("TRACKER_ID", "45540")),
        "target_city": os.environ.get("TARGET_CITY", "Ghaxaq"),
        "poll_interval": int(os.environ.get("POLL_INTERVAL_SECONDS", "15")),
        "window_start": os.environ.get("NOTIFY_WINDOW_START", "13:30"),
        "window_end": os.environ.get("NOTIFY_WINDOW_END", "14:30"),
        "notify_days": [int(d) for d in os.environ.get("NOTIFY_DAYS", "0,1,2,3,4").split(",")],
        "timezone": _load_timezone(os.environ.get("TZ", "Europe/Malta")),
    }
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
    return cfg


# ── helpers ──────────────────────────────────────────────────────────────────

def strip_diacritics(text: str) -> str:
    """Remove combining diacritical marks."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def city_matches(position_city: str, target: str) -> bool:
    """Case-insensitive, diacritics-insensitive substring match."""
    return strip_diacritics(target).lower() in strip_diacritics(position_city).lower()


def parse_time(t: str) -> tuple[int, int]:
    parts = t.split(":")
    return int(parts[0]), int(parts[1])


def in_notify_window(cfg: dict) -> bool:
    now = datetime.now(tz=cfg["timezone"])
    if now.weekday() not in cfg["notify_days"]:
        return False
    start_h, start_m = parse_time(cfg["window_start"])
    end_h, end_m = parse_time(cfg["window_end"])
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= now <= end


def seconds_until_next_window(cfg: dict) -> float:
    """Return seconds until the next notify window opens."""
    now = datetime.now(tz=cfg["timezone"])
    start_h, start_m = parse_time(cfg["window_start"])

    for day_offset in range(8):  # check up to a week ahead
        candidate = (now + timedelta(days=day_offset)).replace(
            hour=start_h, minute=start_m, second=0, microsecond=0
        )
        if candidate > now and candidate.weekday() in cfg["notify_days"]:
            return (candidate - now).total_seconds()
    return 60.0  # fallback


# ── API calls ────────────────────────────────────────────────────────────────

def login(cfg: dict) -> str:
    """Authenticate and return Session_ID."""
    log.info("Logging in to CyberPass...")
    resp = requests.get(
        f"{BASE_URL}/Authentication",
        params={
            "Username": cfg["username"],
            "Password": cfg["password"],
            "RememberMe": "true",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    session_id = data.get("Session_ID")
    if not session_id:
        raise RuntimeError(f"Login failed — no Session_ID in response: {data}")
    log.info("Logged in successfully (Session_ID: %s…)", session_id[:8])
    return session_id


def fetch_live_data(session_id: str, tz: ZoneInfo) -> list[dict]:
    """Fetch current positions from LiveData endpoint."""
    params = {
        "Session_ID": session_id,
        "LastUpdate": (datetime.now() - timedelta(seconds=3603)).strftime("%Y-%m-%d %H:%M:%S"),
    }
    log.debug("Calling %s/LiveData/Select with params: %s", BASE_URL, params)

    resp = requests.get(
        f"{BASE_URL}/LiveData/Select",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        positions = data.get("ListPosition", [])
        if not isinstance(positions, list):
            log.warning("Expected list for ListPosition but received %s — returning empty list.", type(positions).__name__)
            return []
        return [item for item in positions if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    log.warning("Unexpected response type from LiveData API: %s — returning empty list.", type(data).__name__)
    return []


def send_telegram(cfg: dict, message: str) -> None:
    """Send a Telegram message to all configured chat IDs."""
    for chat_id in cfg["telegram_chat_ids"]:
        resp = requests.post(
            f"https://api.telegram.org/bot{cfg['telegram_token']}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.ok:
            log.info("Telegram notification sent to %s.", chat_id)
        else:
            log.error("Telegram send failed for %s: %s %s", chat_id, resp.status_code, resp.text)


# ── main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = load_config()
    session_id: str | None = None
    notified_date: str | None = None  # tracks which date we already notified for

    log.info(
        "CyberNotify started — tracking ID %s for '%s' (%s–%s, days %s)",
        cfg["tracker_id"],
        cfg["target_city"],
        cfg["window_start"],
        cfg["window_end"],
        cfg["notify_days"],
    )

    while True:
        try:
            # Reset notification flag on new day
            today = datetime.now(tz=cfg["timezone"]).strftime("%Y-%m-%d")
            if notified_date and notified_date != today:
                notified_date = None

            # Sleep outside the window
            if not in_notify_window(cfg):
                wait = seconds_until_next_window(cfg)
                # Cap the sleep at 5 minutes so we stay responsive
                sleep_time = min(wait, 300)
                log.info("Outside notify window. Sleeping %.0fs (next window in %.0fs).", sleep_time, wait)
                time.sleep(sleep_time)
                continue

            # Already notified today — wait for window to pass
            if notified_date == today:
                time.sleep(cfg["poll_interval"])
                continue

            # Ensure we have a session
            if not session_id:
                session_id = login(cfg)

            # Poll live data
            positions = fetch_live_data(session_id, cfg["timezone"])
            log.debug("fetch_live_data returned %d position(s): %s", len(positions), positions)

            # Find our tracker
            for pos in positions:
                if pos.get("Tracker_ID") != cfg["tracker_id"]:
                    continue

                city = pos.get("Position_CityName", "")
                location = pos.get("Position_LocationName", "")
                pos_time = pos.get("Position_DateTime", "")
                speed = pos.get("Position_Speed", 0)

                log.info("Van at: %s — %s (speed: %s km/h, time: %s)", city, location, speed, pos_time)

                if city_matches(city, cfg["target_city"]):
                    message = (
                        f"🚐 <b>Van approaching!</b>\n\n"
                        f"📍 <b>{city}</b> — {location}\n"
                        f"🕐 {pos_time}\n"
                        f"💨 {speed} km/h"
                    )
                    send_telegram(cfg, message)
                    notified_date = today
                    log.info("Notification sent — cooldown until tomorrow.")
                break  # only check our tracker

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                log.warning("Session expired — re-authenticating.")
                session_id = None
            else:
                log.error("HTTP error: %s", e)
        except requests.exceptions.RequestException as e:
            log.error("Network error: %s", e)
            session_id = None  # force re-login on next iteration
        except Exception:
            log.exception("Unexpected error")

        time.sleep(cfg["poll_interval"])


if __name__ == "__main__":
    main()
