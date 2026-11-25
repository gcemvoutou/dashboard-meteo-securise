"""
Module d'authentification : stockage des comptes (mots de passe hachés bcrypt),
politique de mot de passe, verrouillage anti-force brute et journalisation.
"""

import datetime
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import bcrypt

from src import config

logger = logging.getLogger("auth")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
BCRYPT_MAX_BYTES = 72
GENERIC_ERROR = "Identifiant ou mot de passe incorrect."
LOCKED_ERROR = "Trop de tentatives. Réessayer plus tard."

# Hash factice : utilisé quand l'utilisateur n'existe pas, pour que le temps de
# réponse soit identique (évite l'énumération des comptes par mesure du temps).
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(rounds=config.BCRYPT_ROUNDS))


class PasswordPolicyError(ValueError):
    """Mot de passe non conforme à la politique."""


@dataclass
class AuthResult:
    success: bool
    message: str = ""
    locked: bool = False


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(moment: datetime.datetime) -> str:
    """Format ISO à longueur fixe : les comparaisons de chaînes en SQL restent chronologiques."""
    return moment.isoformat(timespec="microseconds")


def safe_for_log(value: str) -> str:
    """Neutralise les retours à la ligne pour empêcher l'injection dans les journaux (CWE-117)."""
    return value.replace("\r", "\\r").replace("\n", "\\n")[:64]


def validate_username(username: str) -> None:
    if not USERNAME_PATTERN.fullmatch(username or ""):
        raise ValueError("Identifiant invalide : 3 à 32 caractères parmi lettres, chiffres, . _ -")


def validate_password_policy(password: str) -> None:
    """
    Politique inspirée des recommandations CNIL/ANSSI : 12 caractères minimum,
    majuscule, minuscule, chiffre et caractère spécial. 72 octets maximum (limite bcrypt).
    """
    if len(password) < 12:
        raise PasswordPolicyError("Le mot de passe doit contenir au moins 12 caractères.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise PasswordPolicyError("Le mot de passe ne doit pas dépasser 72 octets.")
    checks = [
        (r"[a-z]", "une minuscule"),
        (r"[A-Z]", "une majuscule"),
        (r"[0-9]", "un chiffre"),
        (r"[^A-Za-z0-9]", "un caractère spécial"),
    ]
    missing = [label for pattern, label in checks if not re.search(pattern, password)]
    if missing:
        raise PasswordPolicyError("Le mot de passe doit contenir " + ", ".join(missing) + ".")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=config.BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except ValueError:
        return False


class UserStore:
    """Comptes utilisateurs et historique des tentatives de connexion (SQLite)."""

    def __init__(
        self,
        db_path: Path = config.USERS_DB_PATH,
        max_attempts: int = config.MAX_LOGIN_ATTEMPTS,
        lockout_minutes: int = config.LOCKOUT_MINUTES,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_attempts = max_attempts
        self.lockout = datetime.timedelta(minutes=lockout_minutes)
        self._init_db()

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
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL
                )
                """
            )

    # ------------------------------------------------------------ gestion
    def has_users(self) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def list_users(self) -> List[str]:
        with self._connect() as conn:
            return [r[0] for r in conn.execute("SELECT username FROM users ORDER BY username")]

    def create_user(self, username: str, password: str) -> None:
        validate_username(username)
        validate_password_policy(password)
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, hash_password(password), _iso(_utcnow())),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Cet identifiant existe déjà.") from exc
        logger.info("Compte créé : %s", safe_for_log(username))

    def delete_user(self, username: str) -> bool:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM users WHERE username = ?", (username,)).rowcount
        return deleted > 0

    def unlock_user(self, username: str) -> None:
        """Débloque un compte en enregistrant une réussite fictive (remet le compteur à zéro)."""
        self._record_attempt(username, success=True)

    # ------------------------------------------------------ authentification
    def _record_attempt(self, username: str, success: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO login_attempts (username, timestamp, success) VALUES (?, ?, ?)",
                (username, _iso(_utcnow()), int(success)),
            )

    def _recent_failures(self, username: str) -> int:
        """Nombre d'échecs dans la fenêtre de verrouillage, depuis la dernière réussite."""
        since = _iso(_utcnow() - self.lockout)
        with self._connect() as conn:
            last_success = conn.execute(
                "SELECT MAX(timestamp) FROM login_attempts WHERE username = ? AND success = 1",
                (username,),
            ).fetchone()[0]
            lower = max(since, last_success) if last_success else since
            return conn.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 0 AND timestamp > ?",
                (username, lower),
            ).fetchone()[0]

    def is_locked(self, username: str) -> bool:
        return self._recent_failures(username) >= self.max_attempts

    def _get_hash(self, username: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
        return row[0] if row else None

    def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Vérifie les identifiants. Même message d'erreur que le compte existe ou non ;
        le verrouillage s'applique aussi aux identifiants inexistants.
        """
        username = (username or "").strip()
        password = password or ""
        log_name = safe_for_log(username)

        if not USERNAME_PATTERN.fullmatch(username):
            bcrypt.checkpw(b"x", _DUMMY_HASH)
            logger.warning("Échec de connexion (identifiant mal formé) : %s", log_name)
            return AuthResult(False, GENERIC_ERROR)

        if self.is_locked(username):
            logger.warning("Connexion refusée (compte verrouillé) : %s", log_name)
            return AuthResult(False, LOCKED_ERROR, locked=True)

        stored_hash = self._get_hash(username)
        if stored_hash is None:
            verify_password(password, _DUMMY_HASH.decode("ascii"))
            valid = False
        else:
            valid = verify_password(password, stored_hash)

        self._record_attempt(username, valid)
        if valid:
            logger.info("Connexion réussie : %s", log_name)
            return AuthResult(True)

        logger.warning("Échec de connexion : %s", log_name)
        if self.is_locked(username):
            logger.warning("Compte verrouillé après %d échecs : %s", self.max_attempts, log_name)
            return AuthResult(False, LOCKED_ERROR, locked=True)
        return AuthResult(False, GENERIC_ERROR)
