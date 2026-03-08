import sqlite3
import os
import hashlib
import secrets
from typing import Optional
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta

# --- Config (from environment) ---
SECRET_KEY = os.environ.get("NB_SECRET_KEY", "nancy-brain-dev-key")
ALGORITHM = os.environ.get("NB_JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("NB_ACCESS_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.environ.get("NB_REFRESH_EXPIRE_MINUTES", str(60 * 24 * 7)))
DB_PATH = os.environ.get("NB_USERS_DB", "users.db")
API_KEY_PREFIX = "nb_"
API_KEY_BYTES = 32

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def create_refresh_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        return username
    except JWTError:
        return None


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_user_table():
    conn = get_db()
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    )
    """
    )
    conn.commit()
    conn.close()


def create_refresh_table():
    conn = get_db()
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        token TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    conn.commit()
    conn.close()


def create_api_key_table():
    conn = get_db()
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_hash TEXT UNIQUE NOT NULL,
        key_prefix TEXT NOT NULL,
        contact TEXT,
        label TEXT,
        revoked INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP
    )
    """
    )
    conn.commit()
    conn.close()


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _normalize_optional(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    return value or None


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_BYTES)}"


def store_api_key(api_key: str, contact: Optional[str] = None, label: Optional[str] = None):
    key_hash = _hash_api_key(api_key)
    key_prefix = api_key[:8]
    contact = _normalize_optional(contact)
    label = _normalize_optional(label)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO api_keys (key_hash, key_prefix, contact, label) VALUES (?, ?, ?, ?)",
            (key_hash, key_prefix, contact, label),
        )
        conn.commit()
    finally:
        conn.close()


def issue_api_key(contact: Optional[str] = None, label: Optional[str] = None, max_attempts: int = 5) -> str:
    for _ in range(max_attempts):
        api_key = generate_api_key()
        try:
            store_api_key(api_key, contact=contact, label=label)
            return api_key
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Failed to generate a unique API key")


def is_api_key_valid(api_key: str) -> bool:
    if not api_key:
        return False
    key_hash = _hash_api_key(api_key)
    conn = get_db()
    try:
        row = conn.execute("SELECT revoked FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        if not row or row["revoked"] != 0:
            return False
        try:
            conn.execute("UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE key_hash = ?", (key_hash,))
            conn.commit()
        except Exception:
            pass
        return True
    finally:
        conn.close()


def any_api_keys_exist() -> bool:
    conn = get_db()
    try:
        row = conn.execute("SELECT 1 FROM api_keys WHERE revoked = 0 LIMIT 1").fetchone()
        return row is not None
    finally:
        conn.close()


def store_refresh_token(username: str, token: str):
    conn = get_db()
    try:
        conn.execute("INSERT INTO refresh_tokens (username, token) VALUES (?, ?)", (username, token))
        conn.commit()
    finally:
        conn.close()


def revoke_refresh_token(token: str):
    conn = get_db()
    try:
        conn.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def is_refresh_valid(token: str) -> bool:
    conn = get_db()
    try:
        row = conn.execute("SELECT revoked FROM refresh_tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return False
        return row["revoked"] == 0
    finally:
        conn.close()


def get_refresh_owner(token: str):
    """Return the username owning a refresh token, or None if not found."""
    conn = get_db()
    try:
        row = conn.execute("SELECT username FROM refresh_tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        return row["username"]
    finally:
        conn.close()


def get_user(username: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return user


def verify_password(plain_password, hashed_password):
    try:
        # bcrypt has a 72 byte limit. passlib usually handles this but recent versions/backends can be strict.
        # If the password is ridiculously long (like an API key pasted by mistake), it will raise ValueError.
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    username = verify_token(token)
    if not username:
        raise credentials_exception
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user


def add_user(username: str, password: str):
    hashed = pwd_context.hash(password)
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", (username, hashed))
        conn.commit()
    finally:
        conn.close()


def require_auth(current_user=Depends(get_current_user)):
    """Reusable dependency for endpoints that require a valid authenticated user.

    Use in routes as: current_user = Depends(auth.require_auth)
    Returns the user row (sqlite3.Row) on success, raises 401 on failure.

    Example:

    from fastapi import APIRouter, Depends
    from connectors.http_api import auth

    router = APIRouter()

    @router.get("/my-protected")
    def my_protected_route(current_user = Depends(auth.require_auth)):
        return {"user": current_user["username"]}
    """
    return current_user
