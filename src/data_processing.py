"""
Module 2 — Nettoyage des données, statistiques, tendances et indice de confort.
"""

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


class DataProcessor:
    """Transforme les réponses API en DataFrame et calcule les indicateurs métier."""

    @staticmethod
    def process_raw_api_data(raw_data: Dict[str, Any]) -> pd.DataFrame:
        """Fusionne les séries horaires météo et qualité de l'air dans un DataFrame propre."""
        w_hourly = raw_data.get("weather", {}).get("hourly", {})
        a_hourly = raw_data.get("air_quality", {}).get("hourly", {})

        df_weather = pd.DataFrame(w_hourly)
        df_air = pd.DataFrame(a_hourly)
        if df_weather.empty or df_air.empty or "time" not in df_weather or "time" not in df_air:
            return pd.DataFrame()

        df = pd.merge(df_weather, df_air, on="time", how="inner")
        df["datetime"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["datetime"]).drop_duplicates(subset="datetime")
        numeric_cols = [c for c in df.columns if c not in ("time", "datetime")]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        return df.sort_values("datetime").reset_index(drop=True)

    @staticmethod
    def get_current_values(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne les valeurs « actuelles » (bloc current de l'API) météo + air."""
        current: Dict[str, Any] = {}
        current.update(raw_data.get("weather", {}).get("current", {}))
        current.update(raw_data.get("air_quality", {}).get("current", {}))
        return current

    @staticmethod
    def get_today_min_max(raw_data: Dict[str, Any], reference: pd.Timestamp) -> Dict[str, Optional[float]]:
        """Températures min/max du jour de référence (bloc daily)."""
        daily = raw_data.get("weather", {}).get("daily", {})
        day = reference.strftime("%Y-%m-%d")
        try:
            idx = daily["time"].index(day)
            return {"min": daily["temperature_2m_min"][idx], "max": daily["temperature_2m_max"][idx]}
        except (KeyError, ValueError, IndexError):
            return {"min": None, "max": None}

    @staticmethod
    def history_until(df: pd.DataFrame, reference: pd.Timestamp) -> pd.DataFrame:
        """Garde uniquement les données passées (≤ heure de référence), sans les prévisions."""
        return df[df["datetime"] <= reference]

    @staticmethod
    def compute_statistics(df: pd.DataFrame, column: str, hours: int) -> Dict[str, float]:
        """Moyenne, médiane, min et max d'une variable sur les N dernières heures."""
        window = df.tail(hours)[column].dropna()
        if window.empty:
            return {"mean": np.nan, "median": np.nan, "min": np.nan, "max": np.nan}
        return {
            "mean": round(float(window.mean()), 1),
            "median": round(float(window.median()), 1),
            "min": round(float(window.min()), 1),
            "max": round(float(window.max()), 1),
        }

    @staticmethod
    def compute_trend(df: pd.DataFrame, column: str, hours: int) -> Optional[float]:
        """
        Tendance sur une période : valeur la plus récente − valeur d'il y a N heures.
        Retourne None si l'historique est insuffisant.
        """
        series = df[["datetime", column]].dropna()
        if series.empty:
            return None
        latest = series.iloc[-1]
        target = latest["datetime"] - pd.Timedelta(hours=hours)
        past = series[series["datetime"] <= target]
        if past.empty:
            return None
        return round(float(latest[column] - past.iloc[-1][column]), 1)

    @staticmethod
    def calculate_custom_health_index(df: pd.DataFrame) -> pd.Series:
        """
        Score composite Confort/Santé (0-100, plus haut = mieux) combinant
        température ressentie, humidité et pollution (PM2.5 et NO2).
        """
        temp = df["apparent_temperature"]
        humidity = df["relative_humidity_2m"]
        temp_penalty = np.abs(temp - 21.0) * 1.5
        humidity_penalty = np.abs(humidity - 50.0) * 0.3
        pollution_penalty = df["pm2_5"] * 1.2 + df["nitrogen_dioxide"] * 0.3
        score = 100 - (temp_penalty + humidity_penalty + pollution_penalty)
        return score.clip(0, 100).round(1)

    @staticmethod
    def aqi_category(aqi: float) -> str:
        """Catégorie US AQI utilisée pour le code couleur de la carte."""
        if aqi is None or pd.isna(aqi):
            return "Inconnu"
        bounds = [
            (50, "Bon"),
            (100, "Modéré"),
            (150, "Mauvais (sensibles)"),
            (200, "Mauvais"),
            (300, "Très mauvais"),
        ]
        for limit, label in bounds:
            if aqi <= limit:
                return label
        return "Dangereux"
