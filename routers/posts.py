from fastapi import APIRouter, HTTPException, Depends, Query, File, Form, UploadFile
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from core.database import get_db
from core.security import get_current_user, require_ngo
from utils.helpers import new_id, utcnow, serialize
from utils.gcs_storage import upload_image_and_get_url

router = APIRouter(prefix="/posts", tags=["Posts"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    title: str
    content: str
    category: str = "general"
    image_url: Optional[str] = None
    tags: List[str] = []

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None

# ── Helper: check if current entity can post ──────────────────────────────────

async def can_post(current, db) -> bool:
    """NGOs can always post; selected volunteers can post."""
    if current["role"] == "ngo":
        return True
    if current["role"] == "volunteer":
        # check if any NGO has selected this volunteer
        ngo = await db.ngos.find_one({"selected_volunteers": current["_id"]})
        return ngo is not None
    return False

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", summary="Create a post (NGO or selected volunteer)")
async def create_post(body: PostCreate, current=Depends(get_current_user), db=Depends(get_db)):
    if not await can_post(current, db):
        raise HTTPException(403, "Only NGOs or selected volunteers can post")

    pid = new_id()
    doc = {
        "_id": pid,
        "title": body.title,
        "content": body.content,
        "category": body.category,
        "image_url": body.image_url,
        "tags": body.tags,
        "posted_by": current["_id"],
        "poster_role": current["role"],
        "likes": [],       # user IDs who upvoted
        "dislikes": [],
        "upvote_count": 0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    await db.posts.insert_one(doc)
    return serialize(doc)


@router.post("/with-image", summary="Create a post with an uploaded image file")
async def create_post_with_image(
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form("general"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    image: Optional[UploadFile] = File(None),
    current=Depends(get_current_user),
    db=Depends(get_db),
):
    if not await can_post(current, db):
        raise HTTPException(403, "Only NGOs or selected volunteers can post")

    image_url: Optional[str] = None
    if image is not None:
        image_url = await upload_image_and_get_url(image, owner_id=current["_id"])

    tag_list: List[str] = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    pid = new_id()
    doc = {
        "_id": pid,
        "title": title,
        "content": content,
        "category": category,
        "image_url": image_url,
        "tags": tag_list,
        "posted_by": current["_id"],
        "poster_role": current["role"],
        "likes": [],
        "dislikes": [],
        "upvote_count": 0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    await db.posts.insert_one(doc)
    return serialize(doc)


@router.get("/", summary="List / search posts")
async def list_posts(
    category: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    posted_by: Optional[str] = Query(None, description="Filter by poster ID"),
    tag: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    skip: int = 0,
    db=Depends(get_db),
):
    query: dict = {}
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    if posted_by:
        query["posted_by"] = posted_by
    if tag:
        query["tags"] = {"$in": [tag]}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        if to_date:
            date_q["$lte"] = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
        query["created_at"] = date_q

    cursor = db.posts.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [serialize(d) for d in docs]


@router.get("/{post_id}", summary="Get a post by ID")
async def get_post(post_id: str, db=Depends(get_db)):
    doc = await db.posts.find_one({"_id": post_id})
    if not doc:
        raise HTTPException(404, "Post not found")
    return serialize(doc)


@router.put("/{post_id}", summary="Update a post (poster only)")
async def update_post(post_id: str, body: PostUpdate, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.posts.find_one({"_id": post_id})
    if not doc:
        raise HTTPException(404, "Post not found")
    if doc["posted_by"] != current["_id"]:
        raise HTTPException(403, "Only the poster can edit this post")

    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = utcnow()
    await db.posts.update_one({"_id": post_id}, {"$set": update})
    return {"message": "Post updated"}


@router.delete("/{post_id}", summary="Delete a post (poster or NGO)")
async def delete_post(post_id: str, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.posts.find_one({"_id": post_id})
    if not doc:
        raise HTTPException(404, "Post not found")
    if doc["posted_by"] != current["_id"] and current["role"] != "ngo":
        raise HTTPException(403, "Not authorised")
    await db.posts.delete_one({"_id": post_id})
    return {"message": "Post deleted"}


@router.post("/{post_id}/upvote", summary="Upvote a post (any authenticated user)")
async def upvote_post(post_id: str, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.posts.find_one({"_id": post_id})
    if not doc:
        raise HTTPException(404, "Post not found")
    uid = current["_id"]
    if uid in doc.get("likes", []):
        # Remove upvote (toggle)
        await db.posts.update_one({"_id": post_id}, {"$pull": {"likes": uid}, "$inc": {"upvote_count": -1}})
        return {"message": "Upvote removed"}
    await db.posts.update_one(
        {"_id": post_id},
        {"$addToSet": {"likes": uid}, "$pull": {"dislikes": uid}, "$inc": {"upvote_count": 1}}
    )
    return {"message": "Upvoted"}
