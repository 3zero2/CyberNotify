"""Tests for fetch_live_data response parsing."""

from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from cybernotify import fetch_live_data


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
