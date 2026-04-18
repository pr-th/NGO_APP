from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from core.database import get_db
from core.security import get_current_user, require_ngo
from utils.helpers import new_id, utcnow, serialize

router = APIRouter(prefix="/volunteers", tags=["Volunteers"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class SkillAssign(BaseModel):
    volunteer_id: str
    skill: str
    level: int   # 1-5

class SkillRemove(BaseModel):
    volunteer_id: str
    skill: str

class TaskAssign(BaseModel):
    volunteer_id: str
    title: str
    description: str
    due_date: Optional[str] = None

class TaskComplete(BaseModel):
    volunteer_id: str

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", summary="List volunteers with optional filters")
async def list_volunteers(
    skill: Optional[str] = Query(None),
    skill_level: Optional[int] = Query(None, ge=1, le=5),
    location: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    skip: int = 0,
    db=Depends(get_db),
):
    query = {}
    if skill:
        query["skills.skill"] = {"$regex": skill, "$options": "i"}
    if skill_level is not None:
        query["skills.level"] = skill_level
    if location:
        query["location"] = {"$regex": location, "$options": "i"}

    cursor = db.volunteers.find(query, {"password_hash": 0, "aadhaar_id": 0}).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [serialize(d) for d in docs]


@router.get("/{volunteer_id}", summary="Get volunteer by ID")
async def get_volunteer(volunteer_id: str, db=Depends(get_db)):
    doc = await db.volunteers.find_one({"_id": volunteer_id}, {"password_hash": 0, "aadhaar_id": 0})
    if not doc:
        raise HTTPException(404, "Volunteer not found")
    return serialize(doc)


# ── Skill management (NGO only) ───────────────────────────────────────────────

@router.post("/skills/assign", summary="Assign a skill to a volunteer (NGO only)")
async def assign_skill(body: SkillAssign, ngo=Depends(require_ngo), db=Depends(get_db)):
    if body.level < 1 or body.level > 5:
        raise HTTPException(400, "Level must be 1-5")
    vol = await db.volunteers.find_one({"_id": body.volunteer_id})
    if not vol:
        raise HTTPException(404, "Volunteer not found")

    # Check if volunteer is selected by this NGO
    if body.volunteer_id not in ngo.get("selected_volunteers", []):
        raise HTTPException(403, "Volunteer not selected by your NGO")

    # Update or add skill
    skills: list = vol.get("skills", [])
    existing = next((s for s in skills if s["skill"].lower() == body.skill.lower()), None)
    if existing:
        await db.volunteers.update_one(
            {"_id": body.volunteer_id, "skills.skill": existing["skill"]},
            {"$set": {"skills.$.level": body.level, "skills.$.assigned_by_ngo": ngo["_id"]}}
        )
    else:
        await db.volunteers.update_one(
            {"_id": body.volunteer_id},
            {"$push": {"skills": {"skill": body.skill, "level": body.level, "assigned_by_ngo": ngo["_id"]}}}
        )
    return {"message": "Skill assigned"}


@router.delete("/skills/remove", summary="Remove a skill from a volunteer (NGO only)")
async def remove_skill(body: SkillRemove, ngo=Depends(require_ngo), db=Depends(get_db)):
    if body.volunteer_id not in ngo.get("selected_volunteers", []):
        raise HTTPException(403, "Volunteer not selected by your NGO")
    await db.volunteers.update_one(
        {"_id": body.volunteer_id},
        {"$pull": {"skills": {"assigned_by_ngo": ngo["_id"], "skill": body.skill}}}
    )
    return {"message": "Skill removed"}


# ── Task management (NGO only) ────────────────────────────────────────────────

@router.post("/tasks/assign", summary="Assign a task to a volunteer (NGO only)")
async def assign_task(body: TaskAssign, ngo=Depends(require_ngo), db=Depends(get_db)):
    if body.volunteer_id not in ngo.get("selected_volunteers", []):
        raise HTTPException(403, "Volunteer not selected by your NGO")
    vol = await db.volunteers.find_one({"_id": body.volunteer_id})
    if not vol:
        raise HTTPException(404, "Volunteer not found")

    # Move existing current_task to previous_tasks if exists
    ops = {}
    if vol.get("current_task"):
        ops["$push"] = {"previous_tasks": vol["current_task"]}

    task = {
        "task_id": new_id(),
        "title": body.title,
        "description": body.description,
        "due_date": body.due_date,
        "assigned_by_ngo": ngo["_id"],
        "assigned_at": utcnow().isoformat(),
        "status": "active",
    }
    ops["$set"] = {"current_task": task}
    await db.volunteers.update_one({"_id": body.volunteer_id}, ops)
    return {"message": "Task assigned", "task": task}


@router.post("/tasks/complete", summary="Mark current task as completed (NGO only)")
async def complete_task(body: TaskComplete, ngo=Depends(require_ngo), db=Depends(get_db)):
    vol = await db.volunteers.find_one({"_id": body.volunteer_id})
    if not vol:
        raise HTTPException(404, "Volunteer not found")
    if not vol.get("current_task"):
        raise HTTPException(400, "No current task assigned")

    completed = vol["current_task"]
    completed["status"] = "completed"
    completed["completed_at"] = utcnow().isoformat()

    await db.volunteers.update_one(
        {"_id": body.volunteer_id},
        {"$set": {"current_task": None}, "$push": {"previous_tasks": completed}}
    )
    return {"message": "Task marked complete"}


# ── NGO selects volunteers ────────────────────────────────────────────────────

@router.post("/select/{volunteer_id}", summary="NGO selects a volunteer")
async def select_volunteer(volunteer_id: str, ngo=Depends(require_ngo), db=Depends(get_db)):
    vol = await db.volunteers.find_one({"_id": volunteer_id})
    if not vol:
        raise HTTPException(404, "Volunteer not found")
    await db.ngos.update_one({"_id": ngo["_id"]}, {"$addToSet": {"selected_volunteers": volunteer_id}})
    return {"message": "Volunteer selected"}


@router.delete("/select/{volunteer_id}", summary="NGO deselects a volunteer")
async def deselect_volunteer(volunteer_id: str, ngo=Depends(require_ngo), db=Depends(get_db)):
    await db.ngos.update_one({"_id": ngo["_id"]}, {"$pull": {"selected_volunteers": volunteer_id}})
    return {"message": "Volunteer deselected"}
