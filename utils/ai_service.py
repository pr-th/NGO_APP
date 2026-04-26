# ═══════════════════════════════════════════════════════════════════
# ALREADY EXISTS - TOP OF FILE
# ═══════════════════════════════════════════════════════════════════
import json
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from core.config import get_settings
from utils.helpers import serialize
from utils.vertex_ai_models import area_needs_predictor, volunteer_scorer

settings = get_settings()

if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)
    MODEL = genai.GenerativeModel("gemini-1.5-flash")
else:
    MODEL = None

# ✅ ADD THIS NEW FUNCTION (at the end of the file):

async def generate_ai_post(location: str, needs: List[Dict[str, Any]], tone: str, ngo_name: str) -> Dict[str, Any]:
    """
    Generate a complete social media post using Gemini based on area needs.
    
    Args:
        location: Where the post is for
        needs: ML-predicted needs from Vertex AI
        tone: 'urgent', 'inspirational', 'informative'
        ngo_name: Name of NGO
    
    Returns:
        {
            "title": "Post headline",
            "content": "Post body",
            "hashtags": ["#tag1"],
            "category": "appeal|announcement",
            "best_time_to_post": "morning"
        }
    """
    if not MODEL:
        return {"error": "Gemini not configured"}
    
    prompt = f"""
    Write a social media post for NGO "{ngo_name}" about needs in {location}.
    
    Predicted Needs (from AI analysis):
    {json.dumps(needs[:2], indent=2)}
    
    Tone: {tone}
    
    Post should:
    - Address top need
    - Call people to action
    - Be {tone}
    - Include 3 hashtags
    - Be 280-400 characters
    
    RESPOND ONLY IN JSON:
    {{
        "title": "Headline",
        "content": "Post body",
        "hashtags": ["#tag1", "#tag2", "#tag3"],
        "category": "appeal|announcement",
        "best_time_to_post": "morning|afternoon|evening"
    }}
    """
    
    try:
        response = MODEL.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}    