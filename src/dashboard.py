"""
Module 4 — Interface Streamlit (protégée par authentification).
"""

import datetime
import logging
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import config
from src.alerts import AlertEngine
from src.api_client import FetchResult, WeatherAPIClient
from src.auth import UserStore
from src.data_processing import DataProcessor

logger = logging.getLogger(__name__)

AQI_COLORS = {
    "Bon": "#00e400",
    "Modéré": "#ffff00",
    "Mauvais (sensibles)": "#ff7e00",
    "Mauvais": "#ff0000",
    "Très mauvais": "#8f3f97",
    "Dangereux": "#7e0023",
    "Inconnu": "#9e9e9e",
}
STAT_WINDOWS = [6, 12, 24, 48, 72, 168]


@st.cache_resource
def get_client() -> WeatherAPIClient:
    return WeatherAPIClient()


@st.cache_resource
def get_user_store() -> UserStore:
    return UserStore()


# ---------------------------------------------------------------- authentification
def _logout(reason: Optional[str] = None) -> None:
    user = st.session_state.get("auth_user")
    st.session_state.clear()
    if reason:
        st.session_state["logout_reason"] = reason
    logging.getLogger("auth").info("Déconnexion (%s) : %s", reason or "manuelle", user)


def require_login() -> Optional[str]:
    """Affiche le formulaire de connexion tant que l'utilisateur n'est pas authentifié."""
    state = st.session_state
    now = datetime.datetime.now(datetime.timezone.utc)
    timeout = datetime.timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)

    if state.get("auth_user"):
        if now - state["last_activity"] > timeout:
            _logout("session expirée")
        else:
            state["last_activity"] = now
            return state["auth_user"]

    st.title("🔐 Connexion — Dashboard Météo & Qualité de l'Air")
    if state.get("logout_reason") == "session expirée":
        st.info("Session expirée après inactivité. Se reconnecter.")

    store = get_user_store()
    if not store.has_users():
        st.warning("Aucun compte n'existe. Créer un compte avec : `python -m src.manage_users add <identifiant>`")
        return None

    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("Identifiant", max_chars=32)
        password = st.text_input("Mot de passe", type="password", max_chars=128)
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        result = store.authenticate(username, password)
        if result.success:
            state.clear()  # nouvelle session propre après authentification
            state["auth_user"] = username.strip()
            state["login_time"] = now
            state["last_activity"] = now
            st.rerun()
        else:
            st.error(result.message)
    return None


# ------------------------------------------------------------------------ helpers
def _wind_direction_label(degrees: Optional[float]) -> str:
    if degrees is None or pd.isna(degrees):
        return "—"
    points = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    return points[int((degrees % 360) / 45 + 0.5) % 8]


def _fmt(value, pattern: str = "{:.1f}", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return pattern.format(value) + suffix


def _show_source_banner(result: FetchResult) -> None:
    if result.is_simulated:
        detail = f" {result.error}" if result.error else ""
        st.warning(f"⚠️ Données **simulées** affichées (mode déconnecté).{detail} Ne pas les utiliser comme mesures réelles.")
    else:
        st.caption(f"Source : Open-Meteo ({'cache local' if result.source == 'cache' else 'API en direct'})")


def _build_city_map(client: WeatherAPIClient, mock_mode: bool, selected_city: str):
    rows = []
    for name, coords in config.DEFAULT_CITIES.items():
        res = client.fetch_weather_and_air_quality(coords["lat"], coords["lon"], mock_mode=mock_mode)
        aqi = DataProcessor.get_current_values(res.data).get("us_aqi")
        rows.append(
            {
                "Ville": name,
                "lat": coords["lat"],
                "lon": coords["lon"],
                "AQI": aqi,
                "Catégorie": DataProcessor.aqi_category(aqi),
                "Sélection": 22 if name == selected_city else 14,
            }
        )
    map_df = pd.DataFrame(rows)
    fig = px.scatter_map(
        map_df,
        lat="lat",
        lon="lon",
        hover_name="Ville",
        hover_data={"AQI": True, "Catégorie": True, "lat": False, "lon": False, "Sélection": False},
        color="Catégorie",
        color_discrete_map=AQI_COLORS,
        size="Sélection",
        size_max=22,
        zoom=3.6,
        center={"lat": 46.5, "lon": 2.0},
        height=480,
    )
    fig.update_layout(map_style="open-street-map", margin={"l": 0, "r": 0, "t": 0, "b": 0})
    return fig


# ---------------------------------------------------------------------- dashboard
def render_dashboard(user: str) -> None:
    client = get_client()

    st.sidebar.header("⚙️ Configuration")
    st.sidebar.write(f"Connecté : **{user}**")
    if st.sidebar.button("Se déconnecter"):
        _logout()
        st.rerun()

    selected_city = st.sidebar.selectbox("Ville", list(config.DEFAULT_CITIES.keys()))
    mock_mode = st.sidebar.checkbox("Mode déconnecté (données simulées)", value=False)
    city = config.DEFAULT_CITIES[selected_city]

    with st.spinner(f"Chargement des données pour {selected_city}..."):
        result = client.fetch_weather_and_air_quality(city["lat"], city["lon"], mock_mode=mock_mode)
        df = DataProcessor.process_raw_api_data(result.data)

    st.title("🌤️ Dashboard Météo & Surveillance Qualité de l'Air")
    _show_source_banner(result)
    if df.empty:
        st.error("Impossible d'afficher les données.")
        return

    current = DataProcessor.get_current_values(result.data)
    reference = pd.to_datetime(current.get("time"), errors="coerce")
    if pd.isna(reference):
        reference = df["datetime"].iloc[-1]
    df["health_score"] = DataProcessor.calculate_custom_health_index(df)
    history = DataProcessor.history_until(df, reference)
    current_score = DataProcessor.calculate_custom_health_index(pd.DataFrame([current])).iloc[0]
    min_max = DataProcessor.get_today_min_max(result.data, reference)

    # Filtres
    min_date, max_date = df["datetime"].min().date(), df["datetime"].max().date()
    dates = st.sidebar.date_input(
        "Période affichée",
        value=(max(min_date, reference.date() - datetime.timedelta(days=config.PAST_DAYS)), max_date),
        min_value=min_date,
        max_value=max_date,
    )
    start, end = (dates[0], dates[-1]) if isinstance(dates, (tuple, list)) and dates else (min_date, max_date)
    weather_choices = [v for v in config.WEATHER_VARIABLES if v != "wind_direction_10m"]
    weather_metrics = st.sidebar.multiselect(
        "Métriques météo",
        weather_choices,
        default=["temperature_2m", "apparent_temperature"],
        format_func=lambda v: config.LABELS[v],
    )
    air_metrics = st.sidebar.multiselect(
        "Polluants",
        config.AIR_VARIABLES[1:],
        default=["pm2_5", "pm10", "nitrogen_dioxide", "ozone"],
        format_func=lambda v: config.LABELS[v],
    )
    stat_hours = st.sidebar.select_slider("Fenêtre statistique (heures)", options=STAT_WINDOWS, value=24)

    # Alertes
    alerts = AlertEngine().detect_alerts(current)
    for alert in alerts:
        if alert["level"] == "danger":
            st.error(f"🚨 **DANGER** : {alert['message']}")
        else:
            st.warning(f"⚠️ **ATTENTION** : {alert['message']}")
    if not alerts:
        st.success("✅ Aucune alerte active pour les conditions actuelles.")

    # KPI
    st.markdown(f"#### Conditions actuelles — {selected_city} ({reference:%d/%m/%Y %H:%M})")
    trend_temp = DataProcessor.compute_trend(history, "temperature_2m", 24)
    trend_aqi = DataProcessor.compute_trend(history, "us_aqi", 24)
    c = st.columns(5)
    c[0].metric("Température", _fmt(current.get("temperature_2m"), suffix=" °C"),
                delta=None if trend_temp is None else f"{trend_temp:+.1f} °C / 24 h", delta_color="off")
    c[1].metric("Ressentie", _fmt(current.get("apparent_temperature"), suffix=" °C"))
    c[2].metric("Min / Max du jour", f"{_fmt(min_max['min'])} / {_fmt(min_max['max'])} °C")
    c[3].metric("Humidité", _fmt(current.get("relative_humidity_2m"), "{:.0f}", " %"))
    c[4].metric("Pression", _fmt(current.get("surface_pressure"), "{:.0f}", " hPa"))
    c = st.columns(5)
    c[0].metric("Vent", f"{_fmt(current.get('wind_speed_10m'), suffix=' km/h')} "
                        f"{_wind_direction_label(current.get('wind_direction_10m'))}")
    c[1].metric("Nuages", _fmt(current.get("cloud_cover"), "{:.0f}", " %"))
    c[2].metric("Précipitations", _fmt(current.get("precipitation"), suffix=" mm"))
    c[3].metric("Indice AQI (US)", _fmt(current.get("us_aqi"), "{:.0f}"),
                delta=None if trend_aqi is None else f"{trend_aqi:+.0f} / 24 h", delta_color="inverse")
    c[4].metric("Score Confort (0-100)", _fmt(current_score))
    c = st.columns(6)
    for col, var in zip(c, config.AIR_VARIABLES[1:]):
        col.metric(config.LABELS[var].split(" ")[0], _fmt(current.get(var), suffix=" µg/m³"))

    # Graphiques
    period = df[(df["datetime"].dt.date >= start) & (df["datetime"].dt.date <= end)]
    tab1, tab2, tab3 = st.tabs(["📈 Évolution Météo", "🏭 Qualité de l'Air", "🗺️ Carte Interactive"])

    with tab1:
        if weather_metrics:
            fig = px.line(period, x="datetime", y=weather_metrics,
                          labels={"value": "Valeur", "datetime": "Date/Heure", "variable": "Métrique"},
                          title="Série temporelle météo (historique + prévisions)")
            fig.for_each_trace(lambda t: t.update(name=config.LABELS.get(t.name, t.name)))
            fig.add_vline(x=reference, line_dash="dash", line_color="grey")
            st.plotly_chart(fig, width="stretch")
            st.caption("Trait pointillé : heure actuelle. À droite : prévisions.")
        else:
            st.info("Sélectionner au moins une métrique météo.")

    with tab2:
        if air_metrics:
            fig = px.line(period, x="datetime", y=air_metrics,
                          labels={"value": "µg/m³", "datetime": "Date/Heure", "variable": "Polluant"},
                          title="Concentration des polluants")
            fig.for_each_trace(lambda t: t.update(name=config.LABELS.get(t.name, t.name)))
            fig.add_vline(x=reference, line_dash="dash", line_color="grey")
            st.plotly_chart(fig, width="stretch")

        st.subheader(f"Statistiques sur les {stat_hours} dernières heures et tendances")
        rows = []
        for var in ["us_aqi"] + air_metrics + ["temperature_2m", "health_score"]:
            stats = DataProcessor.compute_statistics(history, var, stat_hours)
            rows.append({
                "Indicateur": config.LABELS.get(var, "Score confort"),
                "Moyenne": stats["mean"], "Médiane": stats["median"],
                "Min": stats["min"], "Max": stats["max"],
                "Tendance 24 h": DataProcessor.compute_trend(history, var, 24),
                "Tendance 7 j": DataProcessor.compute_trend(history, var, 24 * 7),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Tendance = valeur actuelle − valeur d'il y a 24 h (ou 7 jours).")

    with tab3:
        st.subheader("Indice AQI actuel des villes suivies")
        st.plotly_chart(_build_city_map(client, mock_mode, selected_city), width="stretch")


def main() -> None:
    st.set_page_config(page_title="Dashboard Météo & AQI", page_icon="🌤️", layout="wide")
    user = require_login()
    if not user:
        return
    try:
        render_dashboard(user)
    except Exception:  # dernier rempart : pas de trace technique affichée à l'utilisateur
        logger.exception("Erreur inattendue dans le dashboard")
        st.error("Une erreur inattendue est survenue. Réessayer plus tard.")
