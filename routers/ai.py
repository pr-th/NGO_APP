import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from core.database import get_db
from core.security import require_ngo, get_current_user
from utils.ai_service import (
    predict_area_needs,
    recommend_ngo_posts,
    recommend_volunteer_assignments,
    analyze_ngo_dashboard,
    generate_ai_post,
)
from utils.helpers import serialize

router = APIRouter(prefix="/ai", tags=["AI"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class AreaNeedsRequest(BaseModel):
    location: str
    days_back: int = 30

class VolunteerRecommendationRequest(BaseModel):
    problem_id: str

class PostRecommendationRequest(BaseModel):
    focus_areas: Optional[List[str]] = None

class PostWriteRequest(BaseModel):
    location: str
    topic: Optional[str] = None
    tone: str = "inspirational"  # "urgent" | "informative" | "inspirational"


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/area-needs", summary="Predict community needs for an area")
async def get_area_needs(body: AreaNeedsRequest, db=Depends(get_db)):
    """
    Uses Gemini to predict the top community needs for a given location.
    Enriches with any existing DB problem data if available.
    """
    result = await predict_area_needs(body.location, db)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.post("/ngo-post-recommendations", summary="Recommend posts for an NGO to publish")
async def get_post_recommendations(
    body: PostRecommendationRequest,
    ngo=Depends(require_ngo),
    db=Depends(get_db),
):
    """
    Recommends 3 posts the NGO should publish this week based on area needs.
    """
    recommendations = await recommend_ngo_posts(ngo, db, body.focus_areas)
    return {"recommendations": recommendations}


@router.post("/write-post", summary="AI writes a ready-to-publish post for the NGO")
async def ai_write_post(
    body: PostWriteRequest,
    ngo=Depends(require_ngo),
    db=Depends(get_db),
):
    """
    Predicts area needs then generates a complete social media post for the NGO.
    """
    # Get needs first
    needs_result = await predict_area_needs(body.location, db)

    if "error" in needs_result:
        raise HTTPException(500, needs_result["error"])

    needs = needs_result.get("predicted_needs", [])

    if not needs:
        raise HTTPException(400, f"Could not determine needs for {body.location}")

    # Filter by topic if specified
    if body.topic:
        needs = [n for n in needs if n.get("category") == body.topic]
        if not needs:
            raise HTTPException(400, f"No '{body.topic}' needs predicted for {body.location}")

    result = await generate_ai_post(
        location=body.location,
        needs=needs,
        tone=body.tone,
        ngo_name=ngo.get("name", "Our NGO"),
    )

    if "error" in result:
        raise HTTPException(500, result["error"])

    result["location"] = body.location
    result["powered_by"] = "Gemini"
    return result


@router.post("/volunteer-recommendations", summary="Recommend volunteers for a problem")
async def get_volunteer_recommendations(
    body: VolunteerRecommendationRequest,
    ngo=Depends(require_ngo),
    db=Depends(get_db),
):
    """
    Ranks available volunteers for a given problem using Gemini.
    Returns ideal profiles if no volunteers are registered yet.
    """
    result = await recommend_volunteer_assignments(body.problem_id, db)
    return {"recommendations": result}


@router.get("/dashboard", summary="AI-powered NGO dashboard summary")
async def get_ngo_dashboard(ngo=Depends(require_ngo), db=Depends(get_db)):
    """
    Returns AI-generated insights: area predictions, volunteer stats, priority action.
    """
    result = await analyze_ngo_dashboard(ngo, db)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.get("/area-alert/{location}", summary="Public: predicted needs for any area")
async def get_area_alert(location: str, db=Depends(get_db)):
    """
    Public endpoint — anyone can check predicted community needs for an area.
    """
    result = await predict_area_needs(location, db)
    if "error" in result:
        raise HTTPException(500, result["error"])

    needs = result.get("predicted_needs", [])
    return {
        "location": location,
        "predicted_needs": needs,
        "recommend_action": (
            f"NGOs should focus on {needs[0]['category']}" if needs else "No data yet"
        ),
        "powered_by": "Gemini",
    }