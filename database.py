import sqlite3
import os
from contextlib import contextmanager

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "singularity.db")

os.makedirs(DATA_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a new database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database tables."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                messages TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Tokens table (persistent sessions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # API requests tracking table (for rate limiting between models)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                utc_date TEXT NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(model, utc_date)
            )
        """)
        
        # User rate limiting table (per-user request timestamps)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                request_time TEXT NOT NULL
            )
        """)
        
        # Index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON tokens(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_requests_date ON api_requests(utc_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_rate_limits_user_id ON user_rate_limits(user_id)")


# ==================== API Request Tracking ====================

from datetime import datetime, timezone

DAILY_LIMIT = 20
MODEL_LITE = "gemini-2.5-flash-lite"
MODEL_MAIN = "gemini-2.5-flash"


def get_utc_date() -> str:
    """Get current UTC date as string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_request_count(model: str, utc_date: str) -> int:
    """Get request count for a model on a specific UTC date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT request_count FROM api_requests WHERE model = ? AND utc_date = ?",
            (model, utc_date)
        )
        row = cursor.fetchone()
        return row["request_count"] if row else 0


def increment_request_count(model: str) -> int:
    """Increment request count for a model. Returns new count."""
    utc_date = get_utc_date()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_requests (model, utc_date, request_count)
            VALUES (?, ?, 1)
            ON CONFLICT(model, utc_date) DO UPDATE SET
                request_count = request_count + 1
            """,
            (model, utc_date)
        )
        cursor.execute(
            "SELECT request_count FROM api_requests WHERE model = ? AND utc_date = ?",
            (model, utc_date)
        )
        return cursor.fetchone()["request_count"]


def get_current_model() -> tuple[str, str]:
    """
    Determine which model to use based on daily limits.
    Returns (model_name, display_name).
    - Start with "lite"
    - Switch to "main" if lite reaches 20
    - Switch back to "lite" if main also reaches 20 (will error but tries)
    """
    utc_date = get_utc_date()
    lite_count = get_request_count(MODEL_LITE, utc_date)
    main_count = get_request_count(MODEL_MAIN, utc_date)
    
    if lite_count < DAILY_LIMIT:
        return MODEL_LITE, "lite"
    elif main_count < DAILY_LIMIT:
        return MODEL_MAIN, "main"
    else:
        # Both exhausted, default to lite (will likely error)
        return MODEL_LITE, "lite"


def get_model_status() -> dict:
    """Get current model status for frontend display."""
    utc_date = get_utc_date()
    model, display = get_current_model()
    lite_count = get_request_count(MODEL_LITE, utc_date)
    main_count = get_request_count(MODEL_MAIN, utc_date)
    return {
        "current_model": display,
        "lite_count": lite_count,
        "main_count": main_count,
        "total_count": lite_count + main_count,
        "daily_limit": DAILY_LIMIT,
        "utc_date": utc_date
    }


# ==================== User Rate Limiting ====================

from datetime import timedelta

RATE_LIMIT_REQUESTS = 4
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_COOLDOWN_SECONDS = 60


def check_user_rate_limit(user_id: str) -> tuple[bool, int]:
    """
    Check if user is rate limited.
    Returns (is_allowed, seconds_until_allowed).
    """
    if not user_id:
        return True, 0
    
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Clean up old entries (older than 2 minutes)
        cleanup_time = (now - timedelta(seconds=120)).isoformat()
        cursor.execute(
            "DELETE FROM user_rate_limits WHERE request_time < ?",
            (cleanup_time,)
        )
        
        # Count requests in the last minute
        cursor.execute(
            """
            SELECT request_time FROM user_rate_limits 
            WHERE user_id = ? AND request_time >= ?
            ORDER BY request_time ASC
            """,
            (user_id, window_start.isoformat())
        )
        requests = cursor.fetchall()
        
        if len(requests) >= RATE_LIMIT_REQUESTS:
            # User is rate limited - calculate when they can try again
            oldest_request = datetime.fromisoformat(requests[0]["request_time"])
            unlock_time = oldest_request + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS + RATE_LIMIT_COOLDOWN_SECONDS)
            seconds_remaining = max(0, int((unlock_time - now).total_seconds()))
            return False, seconds_remaining
        
        return True, 0


def record_user_request(user_id: str) -> None:
    """Record a user request for rate limiting."""
    if not user_id:
        return
    
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_rate_limits (user_id, request_time) VALUES (?, ?)",
            (user_id, now)
        )
