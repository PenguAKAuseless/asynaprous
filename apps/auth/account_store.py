"""Account database and password hashing utilities."""

import datetime
import hashlib
import hmac
import os
import sqlite3
import threading

from env_loader import load_dotenv


load_dotenv()


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


DEFAULT_DB_PATH = os.path.join(_project_root(), "db", "asynaprous.sqlite3")


def get_db_path():
    configured = os.environ.get("ASYNAPROUS_DB_PATH", "").strip()
    if not configured:
        return DEFAULT_DB_PATH

    if os.path.isabs(configured):
        return configured

    return os.path.join(_project_root(), configured)


DB_PATH = get_db_path()

# Memory-hard password hashing parameters.
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
PBKDF2_HASH_NAME = "sha512"
PBKDF2_ITERATIONS = 600_000
PBKDF2_DKLEN = 64
SALT_BYTES = 16

DEMO_ACCOUNTS = [
    {
        "username": "admin",
        "role": "administrator",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_ADMIN",
    },
    {
        "username": "user1",
        "role": "member",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_USER1",
    },
    {
        "username": "user2",
        "role": "member",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_USER2",
    },
    {
        "username": "user3",
        "role": "member",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_USER3",
    },
    {
        "username": "user4",
        "role": "member",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_USER4",
    },
    {
        "username": "user5",
        "role": "member",
        "password_env": "ASYNAPROUS_DEMO_PASSWORD_USER5",
    },
]

_db_lock = threading.Lock()
_initialized = False


def _connect():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def _preferred_hash_algorithm():
    if hasattr(hashlib, "scrypt"):
        return "scrypt"
    return "pbkdf2_sha512"


def _hash_password(plain_password, salt_bytes, algorithm):
    pepper = os.environ.get("ASYNAPROUS_AUTH_PEPPER", "")
    password_material = (str(plain_password) + pepper).encode("utf-8")

    if algorithm == "scrypt":
        if not hasattr(hashlib, "scrypt"):
            raise RuntimeError("scrypt is not available in this Python runtime")
        return hashlib.scrypt(
            password_material,
            salt=salt_bytes,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
        )

    if algorithm == "pbkdf2_sha512":
        return hashlib.pbkdf2_hmac(
            PBKDF2_HASH_NAME,
            password_material,
            salt_bytes,
            PBKDF2_ITERATIONS,
            dklen=PBKDF2_DKLEN,
        )

    raise ValueError("Unsupported hash algorithm: {}".format(algorithm))


def hash_password(plain_password):
    """Hash password using the strongest algorithm available in this runtime."""
    salt_bytes = os.urandom(SALT_BYTES)
    algorithm = _preferred_hash_algorithm()
    password_hash = _hash_password(plain_password, salt_bytes, algorithm)
    return salt_bytes.hex(), password_hash.hex(), algorithm


def verify_password(plain_password, salt_hex, password_hash_hex, hash_algorithm):
    """Verify password against stored hash with constant-time comparison."""
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(password_hash_hex)
    except ValueError:
        return False

    try:
        current_hash = _hash_password(plain_password, salt_bytes, hash_algorithm)
    except (RuntimeError, ValueError):
        return False

    return hmac.compare_digest(current_hash, expected_hash)


def _resolve_demo_password(account):
    """Resolve demo account password from environment variables."""
    username = account["username"]
    password_env = account["password_env"]

    env_password = os.environ.get(password_env)
    if env_password:
        return env_password

    raise RuntimeError(
        "{} is required to seed '{}' in accounts table".format(password_env, username)
    )


def initialize_account_store():
    """Create account table and insert demo accounts if missing."""
    global _initialized

    if _initialized:
        return

    with _db_lock:
        if _initialized:
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL,
                hash_algorithm TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        now = datetime.datetime.utcnow().isoformat() + "Z"
        for account in DEMO_ACCOUNTS:
            username = account["username"]
            role = account["role"]

            cur.execute("SELECT username FROM accounts WHERE username = ?", (username,))
            exists = cur.fetchone() is not None
            if exists:
                continue

            password = _resolve_demo_password(account)

            salt_hex, hash_hex, hash_algorithm = hash_password(password)

            cur.execute(
                """
                INSERT INTO accounts (
                    username,
                    password_hash,
                    salt,
                    role,
                    hash_algorithm,
                    created_at,
                    updated_at,
                    is_demo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    username,
                    hash_hex,
                    salt_hex,
                    role,
                    hash_algorithm,
                    now,
                    now,
                ),
            )

        conn.commit()
        conn.close()
        _initialized = True


def reset_account_store_runtime_state():
    """Reset in-memory initialization state to force a fresh setup call."""
    global _initialized

    with _db_lock:
        _initialized = False


def check_credentials_in_db(username, password):
    """Validate username/password against accounts table."""
    if not username or password is None:
        return False

    initialize_account_store()

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT password_hash, salt, hash_algorithm FROM accounts WHERE username = ?",
            (str(username),),
        )
        row = cur.fetchone()
        conn.close()

    if not row:
        return False

    password_hash_hex, salt_hex, hash_algorithm = row
    return verify_password(password, salt_hex, password_hash_hex, hash_algorithm)


def get_demo_account_rows():
    """Return public metadata for demo accounts (without password/hash values)."""
    initialize_account_store()

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, role, hash_algorithm, created_at
            FROM accounts
            WHERE is_demo = 1
            ORDER BY username ASC
            """
        )
        rows = cur.fetchall()
        conn.close()

    env_by_user = {item["username"]: item["password_env"] for item in DEMO_ACCOUNTS}
    result = []
    for row in rows:
        result.append(
            {
                "username": row[0],
                "role": row[1],
                "hash_algorithm": row[2],
                "created_at": row[3],
                "password_env": env_by_user.get(row[0], ""),
            }
        )
    return result
