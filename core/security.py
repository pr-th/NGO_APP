from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import get_settings
from core.database import get_db

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ── Token helpers ─────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ── Current-user dependencies ─────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db=Depends(get_db),
):
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    
    role = payload.get("role")
    uid  = payload.get("sub")

    if role == "user":
        entity = await db.users.find_one({"_id": uid})
    elif role == "volunteer":
        entity = await db.volunteers.find_one({"_id": uid})
    elif role == "ngo":
        entity = await db.ngos.find_one({"_id": uid})
    else:
        raise HTTPException(status_code=401, detail="Unknown role")

    if not entity:
        raise HTTPException(status_code=401, detail="Account not found")

    entity["role"] = role
    return entity

async def require_volunteer(current=Depends(get_current_user)):
    if current["role"] not in ("volunteer", "ngo"):
        raise HTTPException(status_code=403, detail="Volunteers only")
    return current

async def require_ngo(current=Depends(get_current_user)):
    if current["role"] != "ngo":
        raise HTTPException(status_code=403, detail="NGO only")
    return current
