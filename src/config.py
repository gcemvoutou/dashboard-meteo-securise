"""
Configuration centrale de l'application.

Les paramètres sensibles ou dépendants de l'environnement sont lus depuis
les variables d'environnement (fichier ``.env`` chargé au démarrage, exclu de Git).
"""

import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Lit un entier dans l'environnement et le borne pour éviter une configuration absurde."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DB_PATH = DATA_DIR / "cache.db"
USERS_DB_PATH = DATA_DIR / "users.db"

# Cache API
CACHE_TTL_MINUTES = _env_int("CACHE_TTL_MINUTES", 30, 1, 1440)
HTTP_TIMEOUT_SECONDS = _env_int("HTTP_TIMEOUT_SECONDS", 5, 1, 30)
PAST_DAYS = 7
FORECAST_DAYS = 2

# Authentification
SESSION_TIMEOUT_MINUTES = _env_int("SESSION_TIMEOUT_MINUTES", 30, 1, 480)
MAX_LOGIN_ATTEMPTS = _env_int("MAX_LOGIN_ATTEMPTS", 5, 1, 20)
LOCKOUT_MINUTES = _env_int("LOCKOUT_MINUTES", 15, 1, 1440)
BCRYPT_ROUNDS = _env_int("BCRYPT_ROUNDS", 12, 4, 15)

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

DEFAULT_CITIES: Dict[str, Dict[str, float]] = {
    "Paris": {"lat": 48.8566, "lon": 2.3522},
    "Lyon": {"lat": 45.7640, "lon": 4.8357},
    "Marseille": {"lat": 43.2965, "lon": 5.3698},
    "London": {"lat": 51.5074, "lon": -0.1278},
    "Madrid": {"lat": 40.4168, "lon": -3.7038},
}

# Variables demandées par le cahier des charges
WEATHER_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
    "precipitation",
]
DAILY_WEATHER_VARIABLES = ["temperature_2m_max", "temperature_2m_min"]
AIR_VARIABLES = [
    "us_aqi",
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "carbon_monoxide",
    "sulphur_dioxide",
]

# Seuils d'alerte : valeurs guides OMS 2021 (24 h / 8 h pour O3) en « warning »,
# seuils réglementaires européens en « danger ».
THRESHOLDS: Dict[str, Dict] = {
    "pm2_5": {"label": "PM2.5", "warning": 15.0, "danger": 25.0, "unit": "µg/m³"},
    "pm10": {"label": "PM10", "warning": 45.0, "danger": 50.0, "unit": "µg/m³"},
    "nitrogen_dioxide": {"label": "NO2", "warning": 25.0, "danger": 50.0, "unit": "µg/m³"},
    "ozone": {"label": "O3", "warning": 100.0, "danger": 180.0, "unit": "µg/m³"},
    "temperature_2m": {"label": "Température", "warning": 33.0, "danger": 38.0, "unit": "°C"},
}

LABELS: Dict[str, str] = {
    "temperature_2m": "Température (°C)",
    "apparent_temperature": "Température ressentie (°C)",
    "relative_humidity_2m": "Humidité (%)",
    "surface_pressure": "Pression (hPa)",
    "wind_speed_10m": "Vent (km/h)",
    "wind_direction_10m": "Direction du vent (°)",
    "cloud_cover": "Couverture nuageuse (%)",
    "precipitation": "Précipitations (mm)",
    "us_aqi": "Indice AQI (US)",
    "pm2_5": "PM2.5 (µg/m³)",
    "pm10": "PM10 (µg/m³)",
    "nitrogen_dioxide": "NO2 (µg/m³)",
    "ozone": "O3 (µg/m³)",
    "carbon_monoxide": "CO (µg/m³)",
    "sulphur_dioxide": "SO2 (µg/m³)",
}
