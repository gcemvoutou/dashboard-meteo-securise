"""Tests d'interface (Streamlit AppTest) : accès protégé par login."""

import pytest
from streamlit.testing.v1 import AppTest

from src.auth import UserStore

PASSWORD = "Tr0ub4dor&Meteo!"


@pytest.fixture(scope="module", autouse=True)
def account():
    store = UserStore()
    if "testeur" not in store.list_users():
        store.create_user("testeur", PASSWORD)


def _login(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    return at.button[0].click().run()


def test_dashboard_hidden_without_login():
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    assert at.title[0].value.startswith("🔐 Connexion")
    assert not at.tabs  # aucun contenu du dashboard


def test_wrong_password_shows_generic_error():
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    _login(at, "testeur", "mauvais")
    assert at.error[0].value == "Identifiant ou mot de passe incorrect."
    assert not at.tabs


def test_login_then_dashboard_in_mock_mode():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    _login(at, "testeur", PASSWORD)
    at.sidebar.checkbox[0].check().run()
    assert not at.exception
    assert len(at.tabs) == 3
    assert any("simulées" in w.value for w in at.warning)
    labels = [m.label for m in at.metric]
    assert "Score Confort (0-100)" in labels and "Indice AQI (US)" in labels


def test_logout():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    _login(at, "testeur", PASSWORD)
    at.sidebar.checkbox[0].check().run()
    at.sidebar.button[0].click().run()
    assert at.title[0].value.startswith("🔐 Connexion")
