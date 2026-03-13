"""Tests for fetch_live_data response parsing and send_telegram."""

from unittest.mock import MagicMock, call, patch
from zoneinfo import ZoneInfo

from cybernotify import fetch_live_data, send_telegram


TZ = ZoneInfo("Europe/Malta")


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@patch("cybernotify.requests.get")
def test_dict_response_extracts_list_position(mock_get):
    """API returns a dict with ListPosition — should extract position items."""
    mock_get.return_value = _mock_response({
        "LastUpdate": "2026-03-10 14:12:20",
        "ListPosition": [
            {"Tracker_ID": 123, "Position_CityName": "Ghaxaq"},
        ],
        "ListHeartbeat": [{"Tracker_ID": 123, "Heartbeat_State": 2}],
    })
    result = fetch_live_data("fake-session", TZ)
    assert result == [{"Tracker_ID": 123, "Position_CityName": "Ghaxaq"}]


@patch("cybernotify.requests.get")
def test_dict_response_empty_list_position(mock_get):
    """API returns a dict with empty ListPosition — should return empty list."""
    mock_get.return_value = _mock_response({
        "LastUpdate": "2026-03-10 14:12:20",
        "ListPosition": [],
        "ListHeartbeat": [{"Tracker_ID": 123}],
        "NoNewData": True,
    })
    result = fetch_live_data("fake-session", TZ)
    assert result == []


@patch("cybernotify.requests.get")
def test_dict_response_missing_list_position(mock_get):
    """API returns a dict without ListPosition key — should return empty list."""
    mock_get.return_value = _mock_response({
        "LastUpdate": "2026-03-10 14:12:20",
        "ListHeartbeat": [{"Tracker_ID": 123}],
    })
    result = fetch_live_data("fake-session", TZ)
    assert result == []


@patch("cybernotify.requests.get")
def test_list_response_still_works(mock_get):
    """Backward compat: if API returns a plain list, it should still work."""
    mock_get.return_value = _mock_response([
        {"Tracker_ID": 456, "Position_CityName": "Valletta"},
    ])
    result = fetch_live_data("fake-session", TZ)
    assert result == [{"Tracker_ID": 456, "Position_CityName": "Valletta"}]


@patch("cybernotify.requests.get")
def test_unexpected_type_returns_empty(mock_get):
    """API returns an unexpected type — should return empty list."""
    mock_get.return_value = _mock_response("unexpected string")
    result = fetch_live_data("fake-session", TZ)
    assert result == []


# ── send_telegram tests ───────────────────────────────────────────────────────

def _make_ok_response():
    resp = MagicMock()
    resp.ok = True
    return resp


def _make_error_response(status_code=400, text="Bad Request"):
    resp = MagicMock()
    resp.ok = False
    resp.status_code = status_code
    resp.text = text
    return resp


@patch("cybernotify.requests.post")
def test_send_telegram_single_chat_id(mock_post):
    """send_telegram sends to a single configured chat ID."""
    mock_post.return_value = _make_ok_response()
    cfg = {"telegram_token": "test-token", "telegram_chat_ids": ["111"]}
    send_telegram(cfg, "hello")
    mock_post.assert_called_once_with(
        "https://api.telegram.org/bottest-token/sendMessage",
        json={"chat_id": "111", "text": "hello", "parse_mode": "HTML"},
        timeout=15,
    )


@patch("cybernotify.requests.post")
def test_send_telegram_multiple_chat_ids(mock_post):
    """send_telegram sends to every chat ID in the list."""
    mock_post.return_value = _make_ok_response()
    cfg = {"telegram_token": "test-token", "telegram_chat_ids": ["111", "222", "333"]}
    send_telegram(cfg, "hello")
    assert mock_post.call_count == 3
    mock_post.assert_has_calls([
        call(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={"chat_id": "111", "text": "hello", "parse_mode": "HTML"},
            timeout=15,
        ),
        call(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={"chat_id": "222", "text": "hello", "parse_mode": "HTML"},
            timeout=15,
        ),
        call(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={"chat_id": "333", "text": "hello", "parse_mode": "HTML"},
            timeout=15,
        ),
    ])


@patch("cybernotify.requests.post")
def test_send_telegram_no_chat_ids(mock_post):
    """send_telegram does nothing when chat ID list is empty."""
    cfg = {"telegram_token": "test-token", "telegram_chat_ids": []}
    send_telegram(cfg, "hello")
    mock_post.assert_not_called()


@patch("cybernotify.requests.post")
def test_send_telegram_partial_failure(mock_post):
    """send_telegram continues sending to remaining IDs after a failure."""
    mock_post.side_effect = [_make_error_response(), _make_ok_response()]
    cfg = {"telegram_token": "test-token", "telegram_chat_ids": ["111", "222"]}
    send_telegram(cfg, "hello")
    assert mock_post.call_count == 2
