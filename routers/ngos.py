from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from core.database import get_db
from core.security import get_current_user, require_ngo
from utils.helpers import new_id, utcnow, serialize

router = APIRouter(prefix="/ngos", tags=["NGOs"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class NGOUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None

class ResourceCreate(BaseModel):
    title: str
    description: str = ""
    image_url: str = ""
    category: str = ""

class DonationAdd(BaseModel):
    resource_id: str
    donor_name: str
    donation_type: str    # "money" | "goods" | "service"
    amount: float
    image_proof_url: str = ""
    note: str = ""

class PartnerOrgAdd(BaseModel):
    resource_id: str
    org_name: str
    org_type: str = ""
    contact: str = ""
    image_url: str = ""

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", summary="List all NGOs")
async def list_ngos(
    location: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    skip: int = 0,
    db=Depends(get_db),
):
    query = {}
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    cursor = db.ngos.find(query, {"password_hash": 0, "pan_number": 0, "darpan_id": 0}).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [serialize(d) for d in docs]


@router.get("/me", summary="Get own NGO profile")
async def get_my_ngo(ngo=Depends(require_ngo), db=Depends(get_db)):
    doc = await db.ngos.find_one({"_id": ngo["_id"]}, {"password_hash": 0})
    return serialize(doc)


@router.put("/me", summary="Update NGO profile")
async def update_ngo(body: NGOUpdate, ngo=Depends(require_ngo), db=Depends(get_db)):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = utcnow()
    await db.ngos.update_one({"_id": ngo["_id"]}, {"$set": update})
    return {"message": "NGO updated"}


@router.get("/{ngo_id}", summary="Get NGO by ID")
async def get_ngo(ngo_id: str, db=Depends(get_db)):
    doc = await db.ngos.find_one({"_id": ngo_id}, {"password_hash": 0, "pan_number": 0, "darpan_id": 0})
    if not doc:
        raise HTTPException(404, "NGO not found")
    return serialize(doc)


@router.get("/{ngo_id}/volunteers", summary="Get selected volunteers of an NGO")
async def get_ngo_volunteers(ngo_id: str, db=Depends(get_db)):
    ngo = await db.ngos.find_one({"_id": ngo_id})
    if not ngo:
        raise HTTPException(404, "NGO not found")
    ids = ngo.get("selected_volunteers", [])
    docs = []
    for vid in ids:
        v = await db.volunteers.find_one({"_id": vid}, {"password_hash": 0, "aadhaar_id": 0})
        if v:
            docs.append(serialize(v))
    return docs


# ── Resources ─────────────────────────────────────────────────────────────────

@router.post("/me/resources", summary="Add a resource to NGO")
async def add_resource(body: ResourceCreate, ngo=Depends(require_ngo), db=Depends(get_db)):
    resource = {
        "resource_id": new_id(),
        "title": body.title,
        "description": body.description,
        "image_url": body.image_url,
        "category": body.category,
        "donations": [],
        "partner_organizations": [],
        "created_at": utcnow().isoformat(),
    }
    await db.ngos.update_one({"_id": ngo["_id"]}, {"$push": {"resources": resource}})
    return {"message": "Resource added", "resource": resource}


@router.delete("/me/resources/{resource_id}", summary="Remove a resource")
async def remove_resource(resource_id: str, ngo=Depends(require_ngo), db=Depends(get_db)):
    await db.ngos.update_one(
        {"_id": ngo["_id"]},
        {"$pull": {"resources": {"resource_id": resource_id}}}
    )
    return {"message": "Resource removed"}


# ── Donations ─────────────────────────────────────────────────────────────────

@router.post("/me/donations", summary="Add a donation to a resource")
async def add_donation(body: DonationAdd, ngo=Depends(require_ngo), db=Depends(get_db)):
    doc = await db.ngos.find_one({"_id": ngo["_id"]})
    resources = doc.get("resources", [])
    res = next((r for r in resources if r["resource_id"] == body.resource_id), None)
    if not res:
        raise HTTPException(404, "Resource not found")

    donation = {
        "donation_id": new_id(),
        "donor_name": body.donor_name,
        "donation_type": body.donation_type,
        "amount": body.amount,
        "image_proof_url": body.image_proof_url,
        "note": body.note,
        "recorded_at": utcnow().isoformat(),
    }
    await db.ngos.update_one(
        {"_id": ngo["_id"], "resources.resource_id": body.resource_id},
        {"$push": {"resources.$.donations": donation}}
    )
    return {"message": "Donation recorded", "donation": donation}


# ── Partner organizations ─────────────────────────────────────────────────────

@router.post("/me/partners", summary="Add a partner organization to a resource")
async def add_partner(body: PartnerOrgAdd, ngo=Depends(require_ngo), db=Depends(get_db)):
    partner = {
        "partner_id": new_id(),
        "org_name": body.org_name,
        "org_type": body.org_type,
        "contact": body.contact,
        "image_url": body.image_url,
        "added_at": utcnow().isoformat(),
    }
    await db.ngos.update_one(
        {"_id": ngo["_id"], "resources.resource_id": body.resource_id},
        {"$push": {"resources.$.partner_organizations": partner}}
    )
    return {"message": "Partner added", "partner": partner}
