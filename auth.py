import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import jwt
import bcrypt

# Security Constants
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# We use auto_error=False to allow SSE endpoints to gracefully handle missing tokens in header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

USERS_FILE = Path(__file__).parent / "users.json"

class User(BaseModel):
    username: str
    role: str = "user"  # "admin" or "user"

class UserInDB(User):
    hashed_password: str

# ── Password Hashing ────────────────────────────────────────────────────────
def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# ── User Storage ────────────────────────────────────────────────────────────
def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)

def get_user(username: str) -> Optional[UserInDB]:
    users = _load_users()
    if username in users:
        return UserInDB(**users[username])
    return None

def create_user(username: str, password: str, role: str = "user") -> UserInDB:
    users = _load_users()
    if username in users:
        raise ValueError("User already exists")
    
    user_dict = {
        "username": username,
        "role": role,
        "hashed_password": get_password_hash(password)
    }
    users[username] = user_dict
    _save_users(users)
    return UserInDB(**user_dict)

# ── JWT Handling ─────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ── FastAPI Dependencies ──────────────────────────────────────────────────────
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return User(**user.model_dump())

def require_role(required_role: str):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != required_role and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return current_user
    return role_checker
