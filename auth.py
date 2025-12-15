import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

# Data directory paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)


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


# ==================== Token Storage ====================
# Simple in-memory token storage (could be moved to file/redis later)
active_tokens: dict[str, AuthToken] = {}


# ==================== Helper Functions ====================

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt."""
    salt = "singularity_salt_2024"  # In production, use unique salt per user
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


# ==================== User Storage ====================

def load_users() -> dict[str, dict]:
    """Load users from JSON file."""
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users: dict[str, dict]) -> None:
    """Save users to JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def create_user(username: str, password: str) -> tuple[Optional[User], Optional[str]]:
    """Create a new user. Returns (user, error)."""
    users = load_users()
    
    # Check if username exists
    for user_data in users.values():
        if user_data["username"].lower() == username.lower():
            return None, "Username already exists"
    
    # Create new user
    user_id = secrets.token_urlsafe(16)
    user = User(
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        created_at=datetime.now().isoformat()
    )
    
    users[user_id] = user.model_dump()
    save_users(users)
    
    # Create user's conversation directory
    os.makedirs(os.path.join(CONVERSATIONS_DIR, user_id), exist_ok=True)
    
    return user, None


def authenticate_user(username: str, password: str) -> tuple[Optional[User], Optional[str]]:
    """Authenticate a user. Returns (user, error)."""
    users = load_users()
    password_hash = hash_password(password)
    
    for user_id, user_data in users.items():
        if user_data["username"].lower() == username.lower():
            if user_data["password_hash"] == password_hash:
                return User(**user_data), None
            else:
                return None, "Invalid password"
    
    return None, "User not found"


def create_auth_token(user_id: str) -> AuthToken:
    """Create an authentication token for a user."""
    token = AuthToken(
        user_id=user_id,
        token=generate_token(),
        expires_at=(datetime.now() + timedelta(days=7)).isoformat()
    )
    active_tokens[token.token] = token
    return token


def validate_token(token: str) -> Optional[str]:
    """Validate a token and return user_id if valid."""
    if token not in active_tokens:
        return None
    
    auth_token = active_tokens[token]
    if datetime.fromisoformat(auth_token.expires_at) < datetime.now():
        del active_tokens[token]
        return None
    
    return auth_token.user_id


def invalidate_token(token: str) -> None:
    """Invalidate (logout) a token."""
    if token in active_tokens:
        del active_tokens[token]


def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID."""
    users = load_users()
    if user_id in users:
        return User(**users[user_id])
    return None


# ==================== Conversation Storage ====================

def get_user_conversations_dir(user_id: str) -> str:
    """Get the conversation directory for a user."""
    return os.path.join(CONVERSATIONS_DIR, user_id)


def load_conversation(user_id: str, conversation_id: str) -> Optional[Conversation]:
    """Load a specific conversation."""
    conv_path = os.path.join(get_user_conversations_dir(user_id), f"{conversation_id}.json")
    if not os.path.exists(conv_path):
        return None
    with open(conv_path, "r") as f:
        return Conversation(**json.load(f))


def save_conversation(conversation: Conversation) -> None:
    """Save a conversation to file."""
    conv_dir = get_user_conversations_dir(conversation.user_id)
    os.makedirs(conv_dir, exist_ok=True)
    conv_path = os.path.join(conv_dir, f"{conversation.id}.json")
    with open(conv_path, "w") as f:
        json.dump(conversation.model_dump(), f, indent=2)


def list_user_conversations(user_id: str) -> list[dict]:
    """List all conversations for a user (metadata only, not full messages)."""
    conv_dir = get_user_conversations_dir(user_id)
    if not os.path.exists(conv_dir):
        return []
    
    conversations = []
    for filename in os.listdir(conv_dir):
        if filename.endswith(".json"):
            conv_path = os.path.join(conv_dir, filename)
            with open(conv_path, "r") as f:
                conv_data = json.load(f)
                conversations.append({
                    "id": conv_data["id"],
                    "title": conv_data["title"],
                    "created_at": conv_data["created_at"],
                    "updated_at": conv_data["updated_at"]
                })
    
    # Sort by updated_at descending
    conversations.sort(key=lambda x: x["updated_at"], reverse=True)
    return conversations


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Delete a conversation."""
    conv_path = os.path.join(get_user_conversations_dir(user_id), f"{conversation_id}.json")
    if os.path.exists(conv_path):
        os.remove(conv_path)
        return True
    return False


def create_conversation(user_id: str, title: str = "New Chat") -> Conversation:
    """Create a new conversation for a user."""
    conversation = Conversation(
        id=secrets.token_urlsafe(16),
        user_id=user_id,
        title=title,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        messages=[]
    )
    save_conversation(conversation)
    return conversation
