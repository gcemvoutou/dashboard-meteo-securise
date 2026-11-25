import pandas as pd
import pytest

from src.alerts import AlertEngine
from src.api_client import WeatherAPIClient
from src.data_processing import DataProcessor


@pytest.fixture
def raw():
    return WeatherAPIClient._generate_mock_data(45.76, 4.83)


@pytest.fixture
def simple_df():
    return pd.DataFrame({
        "datetime": pd.date_range("2026-01-01", periods=49, freq="h"),
        "temperature_2m": [10.0] * 24 + [12.0] * 24 + [16.0],
    })


def test_process_merges_and_sorts(raw):
    df = DataProcessor.process_raw_api_data(raw)
    assert not df.empty
    assert df["datetime"].is_monotonic_increasing
    assert {"temperature_2m", "pm2_5", "us_aqi"}.issubset(df.columns)


def test_process_empty_input():
    assert DataProcessor.process_raw_api_data({}).empty


def test_history_excludes_forecast(raw):
    df = DataProcessor.process_raw_api_data(raw)
    ref = pd.to_datetime(DataProcessor.get_current_values(raw)["time"])
    assert DataProcessor.history_until(df, ref)["datetime"].max() == ref


def test_statistics(simple_df):
    stats = DataProcessor.compute_statistics(simple_df, "temperature_2m", 24)
    assert stats["min"] == 12.0 and stats["max"] == 16.0
    assert stats["median"] == 12.0


def test_trend(simple_df):
    assert DataProcessor.compute_trend(simple_df, "temperature_2m", 24) == 4.0
    assert DataProcessor.compute_trend(simple_df, "temperature_2m", 24 * 7) is None


def test_health_index_orders_conditions():
    df = pd.DataFrame({
        "apparent_temperature": [21.0, 40.0],
        "relative_humidity_2m": [50.0, 20.0],
        "pm2_5": [5.0, 30.0],
        "nitrogen_dioxide": [10.0, 60.0],
    })
    scores = DataProcessor.calculate_custom_health_index(df)
    assert scores.iloc[0] > scores.iloc[1]
    assert scores.between(0, 100).all()


def test_today_min_max(raw):
    ref = pd.to_datetime(DataProcessor.get_current_values(raw)["time"])
    values = DataProcessor.get_today_min_max(raw, ref)
    assert values["min"] <= values["max"]


@pytest.mark.parametrize("aqi,label", [(10, "Bon"), (75, "Modéré"), (350, "Dangereux"), (None, "Inconnu")])
def test_aqi_category(aqi, label):
    assert DataProcessor.aqi_category(aqi) == label


def test_alerts_levels():
    alerts = AlertEngine().detect_alerts({
        "pm2_5": 30.0, "nitrogen_dioxide": 30.0, "temperature_2m": 39.0, "pm10": 10.0, "ozone": None,
    })
    by_var = {a["variable"]: a for a in alerts}
    assert by_var["pm2_5"]["level"] == "danger"
    assert by_var["nitrogen_dioxide"]["level"] == "warning"
    assert "Canicule" in by_var["temperature_2m"]["message"]
    assert "pm10" not in by_var and "ozone" not in by_var


def test_no_alert_when_clean():
    assert AlertEngine().detect_alerts({"pm2_5": 5.0, "temperature_2m": 20.0}) == []
