import sqlite3

import pytest

from src.auth import GENERIC_ERROR, PasswordPolicyError, UserStore, safe_for_log, validate_password_policy

GOOD_PASSWORD = "Tr0ub4dor&Meteo!"


@pytest.fixture
def store(tmp_path):
    s = UserStore(db_path=tmp_path / "users.db", max_attempts=3, lockout_minutes=15)
    s.create_user("alice", GOOD_PASSWORD)
    return s


def test_password_is_hashed(store, tmp_path):
    with sqlite3.connect(tmp_path / "users.db") as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert GOOD_PASSWORD not in stored
    assert stored.startswith("$2")


def test_login_success(store):
    assert store.authenticate("alice", GOOD_PASSWORD).success


def test_same_message_for_unknown_user_and_wrong_password(store):
    wrong = store.authenticate("alice", "mauvais")
    unknown = store.authenticate("bob", "mauvais")
    assert not wrong.success and not unknown.success
    assert wrong.message == unknown.message == GENERIC_ERROR


def test_lockout_after_max_attempts(store):
    for _ in range(3):
        store.authenticate("alice", "mauvais")
    result = store.authenticate("alice", GOOD_PASSWORD)
    assert not result.success and result.locked


def test_unlock(store):
    for _ in range(3):
        store.authenticate("alice", "mauvais")
    store.unlock_user("alice")
    assert store.authenticate("alice", GOOD_PASSWORD).success


def test_sql_injection_attempt_fails(store):
    assert not store.authenticate("alice' OR '1'='1", "x").success
    assert not store.authenticate("alice", "' OR '1'='1").success


@pytest.mark.parametrize("pwd", ["court1!A", "sansmajuscule1!", "SANSMINUSCULE1!", "SansChiffre!!!", "SansSpecial123", "A1!" + "a" * 80])
def test_password_policy_rejects_weak(pwd):
    with pytest.raises(PasswordPolicyError):
        validate_password_policy(pwd)


def test_duplicate_user_rejected(store):
    with pytest.raises(ValueError):
        store.create_user("alice", GOOD_PASSWORD)


def test_invalid_username_rejected(store):
    with pytest.raises(ValueError):
        store.create_user("<script>", GOOD_PASSWORD)


def test_log_injection_neutralised():
    assert "\n" not in safe_for_log("alice\nConnexion réussie : admin")
