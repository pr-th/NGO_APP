from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from core.database import get_db
from core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from utils.helpers import new_id, utcnow, serialize

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    aadhaar_id: str
    date_of_birth: str   # ISO date string  e.g. "1995-06-15"
    location: str

class VolunteerRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    aadhaar_id: str
    date_of_birth: str
    location: str

class NGORegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    pan_number: str
    darpan_id: str
    location: str
    logo_url: str = ""
    description: str = ""

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str   # "user" | "volunteer" | "ngo"

class RefreshRequest(BaseModel):
    refresh_token: str

# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_pair(sub: str, role: str):
    data = {"sub": sub, "role": role}
    return {
        "access_token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "token_type": "bearer",
        "role": role,
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register/user", summary="Register as a regular user")
async def register_user(body: UserRegister, db=Depends(get_db)):
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(400, "Email already registered")
    if await db.users.find_one({"aadhaar_id": body.aadhaar_id}):
        raise HTTPException(400, "Aadhaar ID already registered")

    uid = new_id()
    doc = {
        "_id": uid,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "aadhaar_id": body.aadhaar_id,
        "date_of_birth": body.date_of_birth,
        "location": body.location,
        "liked": [],       # list of problem/post IDs
        "disliked": [],
        "created_at": utcnow(),
    }
    await db.users.insert_one(doc)
    return {"message": "User registered", **_token_pair(uid, "user")}


@router.post("/register/volunteer", summary="Register as a volunteer")
async def register_volunteer(body: VolunteerRegister, db=Depends(get_db)):
    if await db.volunteers.find_one({"email": body.email}):
        raise HTTPException(400, "Email already registered")
    if await db.volunteers.find_one({"aadhaar_id": body.aadhaar_id}):
        raise HTTPException(400, "Aadhaar ID already registered")

    uid = new_id()
    doc = {
        "_id": uid,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "aadhaar_id": body.aadhaar_id,
        "date_of_birth": body.date_of_birth,
        "location": body.location,
        "liked": [],
        "disliked": [],
        # Skills assigned only by NGOs
        "skills": [],        # [{"skill": str, "level": int 1-5, "assigned_by_ngo": ngo_id}]
        "current_task": None,
        "previous_tasks": [],
        "created_at": utcnow(),
    }
    await db.volunteers.insert_one(doc)
    return {"message": "Volunteer registered", **_token_pair(uid, "volunteer")}


@router.post("/register/ngo", summary="Register an NGO (PAN + Darpan)")
async def register_ngo(body: NGORegister, db=Depends(get_db)):
    if await db.ngos.find_one({"email": body.email}):
        raise HTTPException(400, "Email already registered")
    if await db.ngos.find_one({"pan_number": body.pan_number}):
        raise HTTPException(400, "PAN number already registered")
    if await db.ngos.find_one({"darpan_id": body.darpan_id}):
        raise HTTPException(400, "Darpan ID already registered")

    uid = new_id()
    doc = {
        "_id": uid,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "pan_number": body.pan_number,
        "darpan_id": body.darpan_id,
        "location": body.location,
        "logo_url": body.logo_url,
        "description": body.description,
        "selected_volunteers": [],   # list of volunteer IDs chosen by this NGO
        "resources": [],             # embedded resource docs
        "created_at": utcnow(),
    }
    await db.ngos.insert_one(doc)
    return {"message": "NGO registered", **_token_pair(uid, "ngo")}


@router.post("/login", summary="Login for any role")
async def login(body: LoginRequest, db=Depends(get_db)):
    collection_map = {"user": db.users, "volunteer": db.volunteers, "ngo": db.ngos}
    if body.role not in collection_map:
        raise HTTPException(400, "role must be 'user', 'volunteer', or 'ngo'")

    col = collection_map[body.role]
    entity = await col.find_one({"email": body.email})
    if not entity or not verify_password(body.password, entity["password_hash"]):
        raise HTTPException(401, "Invalid credentials")

    return _token_pair(entity["_id"], body.role)


@router.post("/refresh", summary="Get a new access token using refresh token")
async def refresh(body: RefreshRequest, db=Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")
    return _token_pair(payload["sub"], payload["role"])
