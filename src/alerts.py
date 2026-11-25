"""
Module 3 — Moteur d'alertes basé sur les seuils OMS / réglementaires.
"""

from typing import Any, Dict, List, Mapping

import pandas as pd

from src.config import THRESHOLDS

ALERT_TITLES = {
    "temperature_2m": {"warning": "Vigilance Forte Chaleur", "danger": "Alerte Canicule"},
    "default": {"warning": "Vigilance Pollution", "danger": "Alerte Pic de Pollution"},
}


class AlertEngine:
    """Compare les valeurs actuelles aux seuils et produit des alertes."""

    def __init__(self, thresholds: Mapping[str, Dict[str, Any]] = THRESHOLDS) -> None:
        self.thresholds = thresholds

    def detect_alerts(self, current: Mapping[str, Any]) -> List[Dict[str, str]]:
        """Retourne la liste des alertes (niveau + message) pour les valeurs actuelles."""
        alerts: List[Dict[str, str]] = []
        for variable, rule in self.thresholds.items():
            value = current.get(variable)
            if value is None or pd.isna(value):
                continue
            if value >= rule["danger"]:
                level, seuil = "danger", rule["danger"]
            elif value >= rule["warning"]:
                level, seuil = "warning", rule["warning"]
            else:
                continue
            titles = ALERT_TITLES.get(variable, ALERT_TITLES["default"])
            title = titles[level]
            if variable != "temperature_2m":
                title = f"{title} {rule['label']}"
            alerts.append(
                {
                    "level": level,
                    "variable": variable,
                    "message": f"{title} : {value:.1f} {rule['unit']} (seuil {seuil:g} {rule['unit']})",
                }
            )
        return alerts
