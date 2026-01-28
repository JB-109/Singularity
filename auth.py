import json
import hashlib
import secrets
import os
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

from database import get_db

load_dotenv()

# ==================== Models ====================

class User(BaseModel):
    id: str
    username: str
    password_hash: str
    created_at: str


class Conversation(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list


class AuthToken(BaseModel):
    user_id: str
    token: str
    expires_at: str


# ==================== Helper Functions ====================

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt."""
    salt = os.getenv("PASSWORD_SALT", "default_salt_change_me")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


# ==================== User Storage (SQLite) ====================

def create_user(username: str, password: str) -> tuple[Optional[User], Optional[str]]:
    """Create a new user. Returns (user, error)."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,))
        if cursor.fetchone():
            return None, "Username already exists"
        
        # Create new user
        user_id = secrets.token_urlsafe(16)
        now = datetime.now().isoformat()
        password_hash = hash_password(password)
        
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, password_hash, now)
        )
        
        user = User(
            id=user_id,
            username=username,
            password_hash=password_hash,
            created_at=now
        )
        return user, None


def authenticate_user(username: str, password: str) -> tuple[Optional[User], Optional[str]]:
    """Authenticate a user. Returns (user, error)."""
    with get_db() as conn:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        
        cursor.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
            (username,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None, "User not found"
        
        if row["password_hash"] != password_hash:
            return None, "Invalid password"
        
        return User(**dict(row)), None


def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return User(**dict(row))
        return None


# ==================== Token Storage (SQLite) ====================

def create_auth_token(user_id: str) -> AuthToken:
    """Create an authentication token for a user."""
    token = AuthToken(
        user_id=user_id,
        token=generate_token(),
        expires_at=(datetime.now() + timedelta(days=7)).isoformat()
    )
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token.token, token.user_id, token.expires_at)
        )
    
    return token


def validate_token(token: str) -> Optional[str]:
    """Validate a token and return user_id if valid."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tokens WHERE token = ?", (token,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))
            return None
        
        return row["user_id"]


def invalidate_token(token: str) -> None:
    """Invalidate (logout) a token."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))


# ==================== Conversation Storage (SQLite) ====================

def load_conversation(user_id: str, conversation_id: str) -> Optional[Conversation]:
    """Load a specific conversation."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        data = dict(row)
        data["messages"] = json.loads(data["messages"])
        return Conversation(**data)


def save_conversation(conversation: Conversation) -> None:
    """Save a conversation (insert or update)."""
    with get_db() as conn:
        cursor = conn.cursor()
        messages_json = json.dumps(conversation.messages)
        
        cursor.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at, messages)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                updated_at = excluded.updated_at,
                messages = excluded.messages
            """,
            (conversation.id, conversation.user_id, conversation.title,
             conversation.created_at, conversation.updated_at, messages_json)
        )


def list_user_conversations(user_id: str) -> list[dict]:
    """List all conversations for a user (metadata only)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, created_at, updated_at 
            FROM conversations 
            WHERE user_id = ? 
            ORDER BY updated_at DESC
            """,
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Delete a conversation."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        return cursor.rowcount > 0


def create_conversation(user_id: str, title: str = "New Chat") -> Conversation:
    """Create a new conversation for a user."""
    now = datetime.now().isoformat()
    conversation = Conversation(
        id=secrets.token_urlsafe(16),
        user_id=user_id,
        title=title,
        created_at=now,
        updated_at=now,
        messages=[]
    )
    save_conversation(conversation)
    return conversation
