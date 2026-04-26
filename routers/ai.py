# ═══════════════════════════════════════════════════════════════════
# ALREADY EXISTS - TOP OF FILE
# ═══════════════════════════════════════════════════════════════════
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from core.database import get_db
from core.security import require_ngo, get_current_user
from utils.ai_service import (
    predict_area_needs,
    recommend_ngo_posts,
    recommend_volunteer_assignments,
    analyze_ngo_dashboard,
)
from utils.helpers import serialize

# ✅ ADD THIS IMPORT:
from utils.vertex_ai_models import area_needs_predictor


# ═══════════════════════════════════════════════════════════════════
# ALREADY EXISTS - SCHEMAS SECTION
# ═══════════════════════════════════════════════════════════════════
class AreaNeedsRequest(BaseModel):
    location: str
    days_back: int = 30

class VolunteerRecommendationRequest(BaseModel):
    problem_id: str

class PostRecommendationRequest(BaseModel):
    focus_areas: Optional[List[str]] = None

# ✅ ADD THESE NEW SCHEMAS:
class PostWriteRequest(BaseModel):
    location: str
    topic: Optional[str] = None
    tone: str = "inspirational"  # "urgent", "informative", "inspirational"


# ═══════════════════════════════════════════════════════════════════
# ALREADY EXISTS - ROUTES SECTION
# ═══════════════════════════════════════════════════════════════════
@router.post("/area-needs", summary="...")
async def get_area_needs(body: AreaNeedsRequest, db=Depends(get_db)):
    ...

@router.post("/ngo-post-recommendations", summary="...")
async def get_post_recommendations(body: PostRecommendationRequest, ngo=Depends(require_ngo), db=Depends(get_db)):
    ...

# ✅ ADD THESE 2 NEW ROUTES (at the end of the file, before last closing):

@router.post("/write-post", summary="AI writes a post based on area needs")
async def ai_write_post(
    body: PostWriteRequest,
    ngo=Depends(require_ngo),
    db=Depends(get_db),
):
    """
    AI analyzes area needs and writes a complete post for NGO to publish.
    """
    if not MODEL:
        raise HTTPException(500, "AI not configured")
    
    # Get area problems
    area_problems = await db.problems.find(
        {"location": {"$regex": body.location, "$options": "i"}}
    ).sort("created_at", -1).limit(50).to_list(length=50)
    
    ml_predictions = area_needs_predictor.predict_next_needs(area_problems)
    
    if not ml_predictions:
        raise HTTPException(400, f"No data for {body.location}")
    
    if body.topic:
        ml_predictions = [p for p in ml_predictions if p["category"] == body.topic]
        if not ml_predictions:
            raise HTTPException(400, f"No {body.topic} needs predicted")
    
    prompt = f"""
    Write an engaging social media post for an NGO about community needs.
    
    Location: {body.location}
    Predicted Needs: {json.dumps(ml_predictions[:2], indent=2)}
    Tone: {body.tone}
    NGO: {ngo.get('name', 'Our NGO')}
    
    Create a post that addresses the needs, calls to action, and is {body.tone} in tone.
    Include 3 hashtags.
    
    RESPOND ONLY IN THIS JSON FORMAT:
    {{
        "title": "Post headline (max 10 words)",
        "content": "Post body (2-3 sentences)",
        "tags": ["tag1", "tag2", "tag3"],
        "category": "appeal|announcement|update",
        "why_this_post": "Why this matters now"
    }}
    """
    
    try:
        response = MODEL.generate_content(prompt)
        result = json.loads(response.text)
        result["location"] = body.location
        result["powered_by"] = "Vertex AI ML + Gemini"
        return result
    except Exception as e:
        raise HTTPException(500, f"AI generation failed: {str(e)}")


@router.get("/area-alert/{location}", summary="Get predicted needs for area (NGOs stay informed)")
async def get_area_alert(location: str, db=Depends(get_db)):
    """
    Returns predicted needs for an area so NGOs know what to address.
    Public endpoint - anyone can check area needs.
    """
    problems = await db.problems.find(
        {"location": {"$regex": location, "$options": "i"}}
    ).sort("created_at", -1).limit(50).to_list(length=50)
    
    if not problems:
        return {
            "location": location,
            "predicted_needs": [],
            "message": "No problems reported yet in this area"
        }
    
    predictions = area_needs_predictor.predict_next_needs(problems)
    
    # Optional: Use Gemini to write summary
    summary = ""
    if MODEL and predictions:
        prompt = f"""
        Write a brief 1-2 sentence summary of community needs for {location}.
        Format: Just text, no JSON.
        
        Needs: {json.dumps(predictions[:3], indent=2)}
        """
        try:
            response = MODEL.generate_content(prompt)
            summary = response.text
        except:
            summary = f"Top priority: {predictions[0]['category']}"
    
    return {
        "location": location,
        "predicted_needs": predictions,
        "summary": summary,
        "recommend_action": f"NGOs should focus on {predictions[0]['category']} if available" if predictions else "No data yet",
        "problems_analyzed": len(problems),
        "powered_by": "Vertex AI ML"
    }