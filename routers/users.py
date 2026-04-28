from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import Optional
from core.database import get_db
from core.security import get_current_user, hash_password, verify_password
from utils.helpers import utcnow, serialize

router = APIRouter(prefix="/users", tags=["Users"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class UserUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    date_of_birth: Optional[str] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class ReactionBody(BaseModel):
    target_id: str          # problem or post ID
    action: str             # "like" | "dislike" | "remove"

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/me", summary="Get current user profile")
async def get_me(current=Depends(get_current_user), db=Depends(get_db)):
    role = current["role"]
    col = {"user": db.users, "volunteer": db.volunteers, "ngo": db.ngos}[role]
    doc = await col.find_one({"_id": current["_id"]})
    if not doc:
        raise HTTPException(404, "Not found")
    doc.pop("password_hash", None)
    return serialize(doc)


@router.put("/me", summary="Update own profile (not skills)")
async def update_me(body: UserUpdate, current=Depends(get_current_user), db=Depends(get_db)):
    role = current["role"]
    if role == "ngo":
        raise HTTPException(403, "Use /ngos/me to update NGO profile")
    col = {"user": db.users, "volunteer": db.volunteers}[role]
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = utcnow()
    await col.update_one({"_id": current["_id"]}, {"$set": update})
    return {"message": "Profile updated"}


@router.put("/me/password", summary="Change password")
async def change_password(body: PasswordChange, current=Depends(get_current_user), db=Depends(get_db)):
    role = current["role"]
    col = {"user": db.users, "volunteer": db.volunteers, "ngo": db.ngos}[role]
    doc = await col.find_one({"_id": current["_id"]})
    if not verify_password(body.old_password, doc["password_hash"]):
        raise HTTPException(400, "Old password incorrect")
    await col.update_one({"_id": current["_id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    return {"message": "Password changed"}


@router.post("/me/react", summary="Like or dislike a problem/post")
async def react(body: ReactionBody, current=Depends(get_current_user), db=Depends(get_db)):
    role = current["role"]
    col = {"user": db.users, "volunteer": db.volunteers}[role]
    uid = current["_id"]

    # Determine which collection the target lives in
    target = await db.problems.find_one({"_id": body.target_id})
    if not target:
        raise HTTPException(404, "Problem not found")

    tid = body.target_id
    if body.action == "like":
        await col.update_one({"_id": uid}, {"$addToSet": {"liked": tid}, "$pull": {"disliked": tid}})
        await db.problems.update_one({"_id": tid}, {"$addToSet": {"likes": uid}, "$pull": {"dislikes": uid}})
    elif body.action == "dislike":
        await col.update_one({"_id": uid}, {"$addToSet": {"disliked": tid}, "$pull": {"liked": tid}})
        await db.problems.update_one({"_id": tid}, {"$addToSet": {"dislikes": uid}, "$pull": {"likes": uid}})
    elif body.action == "remove":
        await col.update_one({"_id": uid}, {"$pull": {"liked": tid, "disliked": tid}})
        await db.problems.update_one({"_id": tid}, {"$pull": {"likes": uid, "dislikes": uid}})
    else:
        raise HTTPException(400, "action must be like | dislike | remove")

    return {"message": "Reaction recorded"}


@router.delete("/me", summary="Delete own account")
async def delete_me(current=Depends(get_current_user), db=Depends(get_db)):
    role = current["role"]
    col = {"user": db.users, "volunteer": db.volunteers, "ngo": db.ngos}[role]
    await col.delete_one({"_id": current["_id"]})
    return {"message": "Account deleted"}


@router.get("/{user_id}", summary="Get any user by ID (public fields)")
async def get_user(user_id: str, db=Depends(get_db)):
    doc = await db.users.find_one({"_id": user_id})
    if not doc:
        doc = await db.volunteers.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(404, "User not found")
    doc.pop("password_hash", None)
    doc.pop("aadhaar_id", None)   # don't expose Aadhaar publicly
    return serialize(doc)
