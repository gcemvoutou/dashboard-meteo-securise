"""
Module 1 — Client API Open-Meteo et cache SQLite local avec TTL.
"""

import datetime
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import numpy as np
import requests

from src import config

logger = logging.getLogger(__name__)


class APIResponseError(Exception):
    """Réponse API inexploitable (JSON corrompu, clés manquantes, erreur renvoyée par l'API)."""


@dataclass
class FetchResult:
    """Résultat d'une récupération : données + provenance (api, cache ou mock)."""

    data: Dict[str, Any]
    source: str
    error: Optional[str] = field(default=None)

    @property
    def is_simulated(self) -> bool:
        return self.source == "mock"


class WeatherAPIClient:
    """Récupère les données météo et qualité de l'air et gère le cache local."""

    def __init__(
        self,
        db_path: Path = config.CACHE_DB_PATH,
        ttl_minutes: int = config.CACHE_TTL_MINUTES,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.ttl = datetime.timedelta(minutes=ttl_minutes)
        self.session = session or requests.Session()
        self._init_db()

    # ------------------------------------------------------------------ cache
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Connexion SQLite : commit en cas de succès, rollback sinon, et fermeture systématique."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Crée la table de cache si elle n'existe pas."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_cache (
                        key TEXT PRIMARY KEY,
                        response TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
        except sqlite3.Error as exc:
            logger.error("Erreur d'initialisation du cache : %s", exc)

    def _get_cached_data(self, key: str) -> Optional[Dict[str, Any]]:
        """Retourne la réponse en cache si elle est encore valide (TTL) et bien formée."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT response, timestamp FROM api_cache WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as exc:
            logger.warning("Lecture du cache impossible : %s", exc)
            return None

        if not row:
            return None
        response, timestamp_str = row
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
            if datetime.datetime.now(datetime.timezone.utc) - timestamp >= self.ttl:
                return None
            data = json.loads(response)
            self.validate_payload(data)
        except (ValueError, TypeError, APIResponseError) as exc:
            # Entrée corrompue ou altérée : on l'ignore et on la supprime.
            logger.warning("Entrée de cache invalide ignorée (%s) : %s", key, exc)
            self._delete_cached_data(key)
            return None
        logger.info("Cache valide pour %s", key)
        return data

    def _set_cached_data(self, key: str, data: Dict[str, Any]) -> None:
        """Enregistre une réponse validée dans le cache."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_cache (key, response, timestamp) VALUES (?, ?, ?)",
                    (key, json.dumps(data), datetime.datetime.now(datetime.timezone.utc).isoformat()),
                )
        except sqlite3.Error as exc:
            logger.error("Écriture du cache impossible : %s", exc)

    def _delete_cached_data(self, key: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM api_cache WHERE key = ?", (key,))
        except sqlite3.Error as exc:
            logger.error("Suppression du cache impossible : %s", exc)

    # ------------------------------------------------------------- validation
    @staticmethod
    def validate_payload(data: Any) -> None:
        """
        Vérifie la structure de la réponse combinée.
        Lève APIResponseError si une section ou une variable attendue manque.
        """
        if not isinstance(data, dict):
            raise APIResponseError("Réponse non conforme (objet JSON attendu)")
        sections = {
            "weather": ["hourly", "current", "daily"],
            "air_quality": ["hourly", "current"],
        }
        for section, blocks in sections.items():
            part = data.get(section)
            if not isinstance(part, dict):
                raise APIResponseError(f"Section manquante : {section}")
            if part.get("error"):
                raise APIResponseError(f"Erreur API ({section}) : {part.get('reason', 'inconnue')}")
            for block in blocks:
                if not isinstance(part.get(block), dict):
                    raise APIResponseError(f"Bloc manquant : {section}.{block}")

        expected = {
            ("weather", "hourly"): config.WEATHER_VARIABLES,
            ("weather", "daily"): config.DAILY_WEATHER_VARIABLES,
            ("air_quality", "hourly"): config.AIR_VARIABLES,
        }
        for (section, block), variables in expected.items():
            values = data[section][block]
            times = values.get("time")
            if not isinstance(times, list) or not times:
                raise APIResponseError(f"Série temporelle absente : {section}.{block}")
            for var in variables:
                series = values.get(var)
                if not isinstance(series, list) or len(series) != len(times):
                    raise APIResponseError(f"Variable invalide : {section}.{block}.{var}")

    # ------------------------------------------------------------------ fetch
    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Appel HTTP GET avec timeout ; les paramètres sont encodés par requests."""
        response = self.session.get(url, params=params, timeout=config.HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise APIResponseError("JSON corrompu renvoyé par l'API") from exc

    def fetch_weather_and_air_quality(
        self, lat: float, lon: float, mock_mode: bool = False
    ) -> FetchResult:
        """Récupère les données combinées (cache → API → mock en dernier recours)."""
        if not (-90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0):
            raise ValueError("Coordonnées hors limites")

        if mock_mode:
            return FetchResult(self._generate_mock_data(lat, lon), "mock")

        cache_key = f"data_{lat:.4f}_{lon:.4f}"
        cached = self._get_cached_data(cache_key)
        if cached:
            return FetchResult(cached, "cache")

        common = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "past_days": config.PAST_DAYS,
            "forecast_days": config.FORECAST_DAYS,
        }
        weather_params = {
            **common,
            "current": ",".join(config.WEATHER_VARIABLES),
            "hourly": ",".join(config.WEATHER_VARIABLES),
            "daily": ",".join(config.DAILY_WEATHER_VARIABLES),
        }
        air_params = {
            **common,
            "current": ",".join(config.AIR_VARIABLES),
            "hourly": ",".join(config.AIR_VARIABLES),
        }

        try:
            logger.info("Appel des API pour (%.4f, %.4f)", lat, lon)
            combined = {
                "weather": self._request_json(config.WEATHER_API_URL, weather_params),
                "air_quality": self._request_json(config.AIR_QUALITY_API_URL, air_params),
            }
            self.validate_payload(combined)
        except (requests.exceptions.RequestException, APIResponseError) as exc:
            logger.error("Échec de la récupération des données : %s", exc)
            # Repli sur des données simulées, signalées explicitement à l'utilisateur.
            return FetchResult(
                self._generate_mock_data(lat, lon),
                "mock",
                error="Les API sont injoignables ou ont renvoyé une réponse invalide.",
            )

        self._set_cached_data(cache_key, combined)
        return FetchResult(combined, "api")

    # ------------------------------------------------------------------- mock
    @staticmethod
    def _generate_mock_data(lat: float, lon: float) -> Dict[str, Any]:
        """Génère un jeu de données simulé au même format que les réponses Open-Meteo."""
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
        # Graine explicite (coordonnées + heure) : données simulées reproductibles pour une ville et une heure.
        seed = int(abs(lat) * 1000) * 1_000_000 + int(abs(lon) * 1000) + int(now.timestamp() // 3600)
        rng = np.random.default_rng(seed)
        start = now - datetime.timedelta(days=config.PAST_DAYS)
        hours = 24 * (config.PAST_DAYS + config.FORECAST_DAYS)
        times: List[str] = [
            (start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)
        ]
        hour_index = np.arange(hours)
        temp = 18 + 6 * np.sin((hour_index % 24 - 9) / 24 * 2 * np.pi) + rng.normal(0, 1, hours)

        hourly_weather = {
            "time": times,
            "temperature_2m": temp.round(1).tolist(),
            "apparent_temperature": (temp - rng.uniform(0, 3, hours)).round(1).tolist(),
            "relative_humidity_2m": rng.uniform(40, 90, hours).round(0).tolist(),
            "surface_pressure": rng.uniform(1000, 1025, hours).round(1).tolist(),
            "wind_speed_10m": rng.uniform(2, 30, hours).round(1).tolist(),
            "wind_direction_10m": rng.uniform(0, 360, hours).round(0).tolist(),
            "cloud_cover": rng.uniform(0, 100, hours).round(0).tolist(),
            "precipitation": np.clip(rng.normal(0, 0.5, hours), 0, None).round(1).tolist(),
        }
        hourly_air = {
            "time": times,
            "us_aqi": rng.integers(15, 120, hours).tolist(),
            "pm2_5": rng.uniform(5, 35, hours).round(1).tolist(),
            "pm10": rng.uniform(10, 60, hours).round(1).tolist(),
            "nitrogen_dioxide": rng.uniform(10, 55, hours).round(1).tolist(),
            "ozone": rng.uniform(20, 120, hours).round(1).tolist(),
            "carbon_monoxide": rng.uniform(100, 500, hours).round(0).tolist(),
            "sulphur_dioxide": rng.uniform(1, 15, hours).round(1).tolist(),
        }
        days = sorted({t[:10] for t in times})
        daily_temps = {d: [temp[i] for i, t in enumerate(times) if t.startswith(d)] for d in days}
        current_index = times.index(now.strftime("%Y-%m-%dT%H:%M"))

        def current_of(hourly: Dict[str, list]) -> Dict[str, Any]:
            values = {k: v[current_index] for k, v in hourly.items() if k != "time"}
            values["time"] = times[current_index]
            return values

        return {
            "weather": {
                "latitude": lat,
                "longitude": lon,
                "current": current_of(hourly_weather),
                "hourly": hourly_weather,
                "daily": {
                    "time": days,
                    "temperature_2m_max": [round(max(daily_temps[d]), 1) for d in days],
                    "temperature_2m_min": [round(min(daily_temps[d]), 1) for d in days],
                },
            },
            "air_quality": {
                "latitude": lat,
                "longitude": lon,
                "current": current_of(hourly_air),
                "hourly": hourly_air,
            },
        }
