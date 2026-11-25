import json
import sqlite3

import pytest
import requests

from src.api_client import APIResponseError, WeatherAPIClient


class FakeResponse:
    def __init__(self, payload=None, status=200, bad_json=False):
        self.payload, self.status, self.bad_json = payload, status, bad_json

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status}")

    def json(self):
        if self.bad_json:
            raise ValueError("JSON corrompu")
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def mock_payload():
    return WeatherAPIClient._generate_mock_data(48.85, 2.35)


def make_client(tmp_path, responses):
    return WeatherAPIClient(db_path=tmp_path / "cache.db", session=FakeSession(responses))


def test_mock_payload_is_valid(mock_payload):
    WeatherAPIClient.validate_payload(mock_payload)


def test_fetch_from_api_then_cache(tmp_path, mock_payload):
    client = make_client(tmp_path, [FakeResponse(mock_payload["weather"]), FakeResponse(mock_payload["air_quality"])])
    first = client.fetch_weather_and_air_quality(48.85, 2.35)
    second = client.fetch_weather_and_air_quality(48.85, 2.35)
    assert first.source == "api"
    assert second.source == "cache"
    assert len(client.session.calls) == 2  # pas de nouvel appel grâce au cache


def test_params_are_passed_separately_with_timeout(tmp_path, mock_payload):
    client = make_client(tmp_path, [FakeResponse(mock_payload["weather"]), FakeResponse(mock_payload["air_quality"])])
    client.fetch_weather_and_air_quality(48.85, 2.35)
    call = client.session.calls[0]
    assert "?" not in call["url"]
    assert call["params"]["latitude"] == 48.85
    assert call["timeout"] is not None


def test_network_error_falls_back_to_flagged_mock(tmp_path):
    client = make_client(tmp_path, [requests.exceptions.ConnectionError("down")])
    result = client.fetch_weather_and_air_quality(48.85, 2.35)
    assert result.is_simulated
    assert result.error


def test_corrupted_json_is_handled(tmp_path):
    client = make_client(tmp_path, [FakeResponse(bad_json=True)])
    result = client.fetch_weather_and_air_quality(48.85, 2.35)
    assert result.is_simulated


def test_api_error_payload_is_rejected(tmp_path, mock_payload):
    error = {"error": True, "reason": "Cannot initialize WeatherVariable"}
    client = make_client(tmp_path, [FakeResponse(error), FakeResponse(mock_payload["air_quality"])])
    assert client.fetch_weather_and_air_quality(48.85, 2.35).is_simulated


def test_tampered_cache_entry_is_ignored(tmp_path, mock_payload):
    client = make_client(tmp_path, [FakeResponse(mock_payload["weather"]), FakeResponse(mock_payload["air_quality"])])
    with sqlite3.connect(tmp_path / "cache.db") as conn:
        conn.execute(
            "INSERT INTO api_cache VALUES (?, ?, datetime('now'))",
            ("data_48.8500_2.3500", json.dumps({"weather": "<script>"})),
        )
    assert client.fetch_weather_and_air_quality(48.85, 2.35).source == "api"


def test_invalid_coordinates_rejected(tmp_path):
    client = make_client(tmp_path, [])
    with pytest.raises(ValueError):
        client.fetch_weather_and_air_quality(200, 0)


def test_validate_payload_detects_missing_variable(mock_payload):
    del mock_payload["air_quality"]["hourly"]["pm2_5"]
    with pytest.raises(APIResponseError):
        WeatherAPIClient.validate_payload(mock_payload)
