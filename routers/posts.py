from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from core.database import get_db
from core.security import get_current_user, require_volunteer
from utils.helpers import new_id, utcnow, serialize

router = APIRouter(prefix="/problems", tags=["Problems"])

VALID_TYPES = ["infrastructure", "health", "education", "environment", "safety", "other"]

# ── Schemas ───────────────────────────────────────────────────────────────────

class ProblemCreate(BaseModel):
    title: str
    description: str
    importance: int          # 1-5
    types: List[str]
    location: Optional[str] = None
    image_url: Optional[str] = None
    tags: List[str] = []
    content: Optional[str] = None   # optional long-form content like posts had

class ProblemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    importance: Optional[int] = None
    types: Optional[List[str]] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    content: Optional[str] = None

# ── Helpers ───────────────────────────────────────────────────────────────────

async def can_post(current, db) -> bool:
    """NGOs and volunteers can post; selected volunteers have no extra restriction here."""
    if current["role"] in ("ngo", "volunteer"):
        return True
    return False

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", summary="Create a problem")
async def create_problem(body: ProblemCreate, current=Depends(get_current_user), db=Depends(get_db)):
    if not await can_post(current, db):
        raise HTTPException(403, "Only NGOs or volunteers can post problems")
    if not 1 <= body.importance <= 5:
        raise HTTPException(400, "Importance must be 1-5")

    pid = new_id()
    doc = {
        "_id": pid,
        "title": body.title,
        "description": body.description,
        "importance": body.importance,
        "types": body.types,
        "location": body.location,
        "image_url": body.image_url,
        "tags": body.tags,
        "content": body.content,
        "posted_by": current["_id"],
        "poster_role": current["role"],
        "likes": [],
        "dislikes": [],
        "upvote_count": 0,
        "volunteers_on_problem": [],
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    await db.problems.insert_one(doc)
    return serialize(doc)


@router.get("/", summary="List / search problems")
async def list_problems(
    category: Optional[str] = Query(None, description="Filter by type/category"),
    importance: Optional[int] = Query(None, ge=1, le=5),
    location: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date e.g. 2024-01-01"),
    to_date: Optional[str] = Query(None, description="ISO date e.g. 2024-12-31"),
    posted_by: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    skill_level: Optional[int] = Query(None, ge=1, le=5),
    limit: int = Query(20, le=100),
    skip: int = 0,
    db=Depends(get_db),
):
    query: dict = {}
    if category:
        query["types"] = {"$in": [category]}
    if importance is not None:
        query["importance"] = importance
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
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
    if skill or skill_level is not None:
        skill_q = {}
        if skill:
            skill_q["skills.skill"] = {"$regex": skill, "$options": "i"}
        if skill_level:
            skill_q["skills.level"] = skill_level
        vol_ids = await db.volunteers.distinct("_id", skill_q)
        query["posted_by"] = {"$in": vol_ids}

    cursor = db.problems.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [serialize(d) for d in docs]


@router.get("/{problem_id}", summary="Get a problem by ID")
async def get_problem(problem_id: str, db=Depends(get_db)):
    doc = await db.problems.find_one({"_id": problem_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    return serialize(doc)


@router.put("/{problem_id}", summary="Update a problem (poster only)")
async def update_problem(problem_id: str, body: ProblemUpdate, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.problems.find_one({"_id": problem_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    if doc["posted_by"] != current["_id"]:
        raise HTTPException(403, "Only the poster can edit this problem")

    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    if "importance" in update and not 1 <= update["importance"] <= 5:
        raise HTTPException(400, "Importance must be 1-5")
    update["updated_at"] = utcnow()
    await db.problems.update_one({"_id": problem_id}, {"$set": update})
    return {"message": "Problem updated"}


@router.delete("/{problem_id}", summary="Delete a problem (poster or NGO)")
async def delete_problem(problem_id: str, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.problems.find_one({"_id": problem_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    if doc["posted_by"] != current["_id"] and current["role"] != "ngo":
        raise HTTPException(403, "Not authorised")
    await db.problems.delete_one({"_id": problem_id})
    return {"message": "Problem deleted"}


@router.post("/{problem_id}/volunteer", summary="Volunteer joins a problem")
async def join_problem(problem_id: str, volunteer=Depends(require_volunteer), db=Depends(get_db)):
    doc = await db.problems.find_one({"_id": problem_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    await db.problems.update_one({"_id": problem_id}, {"$addToSet": {"volunteers_on_problem": volunteer["_id"]}})
    return {"message": "Joined problem"}


@router.post("/{problem_id}/upvote", summary="Upvote a problem (any authenticated user)")
async def upvote_problem(problem_id: str, current=Depends(get_current_user), db=Depends(get_db)):
    doc = await db.problems.find_one({"_id": problem_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    uid = current["_id"]
    if uid in doc.get("likes", []):
        await db.problems.update_one({"_id": problem_id}, {"$pull": {"likes": uid}, "$inc": {"upvote_count": -1}})
        return {"message": "Upvote removed"}
    await db.problems.update_one(
        {"_id": problem_id},
        {"$addToSet": {"likes": uid}, "$pull": {"dislikes": uid}, "$inc": {"upvote_count": 1}}
    )
    return {"message": "Upvoted"}