import json
from typing import Optional, List, Dict, Any
from groq import Groq
from core.config import get_settings
from utils.helpers import serialize

settings = get_settings()

CLIENT = Groq(api_key=settings.groq_api_key) if getattr(settings, "groq_api_key", None) else None
MODEL_NAME = "llama-3.3-70b-versatile"


def _call_groq(prompt: str) -> Any:
    """Call Groq and parse JSON response."""
    response = CLIENT.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content)


async def generate_ai_post(location: str, needs: List[Dict[str, Any]], tone: str, ngo_name: str) -> Dict[str, Any]:
    """Generate a social media post using Groq based on area needs."""
    if not CLIENT:
        return {"error": "Groq not configured"}

    prompt = f"""
    Write a social media post for NGO "{ngo_name}" about needs in {location}.

    Predicted Needs:
    {json.dumps(needs[:2], indent=2)}

    Tone: {tone}

    Post should address the top need, call people to action, be {tone} in tone,
    include 3 hashtags, and be 280-400 characters.

    Respond ONLY with a JSON object:
    {{
        "title": "Headline",
        "content": "Post body",
        "hashtags": ["#tag1", "#tag2", "#tag3"],
        "category": "appeal or announcement",
        "best_time_to_post": "morning or afternoon or evening"
    }}
    """

    try:
        return _call_groq(prompt)
    except Exception as e:
        return {"error": str(e)}


async def predict_area_needs(location: str, db=None) -> Dict[str, Any]:
    """
    Predict community needs for a given area using Groq/Llama.
    Optionally enriches with any existing DB problem data.
    """
    if not CLIENT:
        return {"error": "Groq not configured"}

    db_context = ""
    if db is not None:
        try:
            problems = await db.problems.find(
                {"location": {"$regex": location, "$options": "i"}}
            ).sort("created_at", -1).limit(20).to_list(length=20)

            if problems:
                categories = {}
                for p in problems:
                    for t in p.get("types", []):
                        categories[t] = categories.get(t, 0) + 1
                db_context = f"\nKnown reported problems in area: {json.dumps(categories)}"
        except Exception:
            pass

    prompt = f"""
    You are an NGO community analyst. Predict the top community needs for: {location}
    {db_context}

    Consider: healthcare access, education gaps, infrastructure, food security,
    environmental issues, safety, employment, and sanitation.

    Return the top 5 predicted needs ranked by urgency.

    Respond ONLY with a JSON object:
    {{
        "predicted_needs": [
            {{
                "category": "health or education or infrastructure or environment or safety or food or employment or sanitation",
                "urgency": "critical or high or medium",
                "score": 0.95,
                "reason": "Brief explanation why this is a need in this area"
            }}
        ]
    }}
    """

    try:
        result = _call_groq(prompt)
        return {
            "location": location,
            "predicted_needs": result.get("predicted_needs", []),
            "powered_by": "Groq / Llama-3.3-70b",
        }
    except Exception as e:
        return {"error": str(e)}


async def recommend_ngo_posts(ngo: Dict[str, Any], db=None, focus_areas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Recommend what posts an NGO should write, using Groq to assess area needs.
    """
    if not CLIENT:
        return [{"error": "Groq not configured"}]

    location = ngo.get("location", "Unknown")
    ngo_name = ngo.get("name", "NGO")
    focus_str = f"Focus only on these categories: {', '.join(focus_areas)}" if focus_areas else ""

    prompt = f"""
    You are advising an NGO called "{ngo_name}" based in {location}.
    {focus_str}

    Recommend 3 social media posts they should publish this week based on
    likely community needs in {location}.

    Respond ONLY with a JSON object:
    {{
        "recommendations": [
            {{
                "category": "health or education or infrastructure or environment or safety or food or employment or sanitation",
                "urgency": "critical or high or medium",
                "suggested_post_type": "appeal or announcement or update",
                "reason": "Why this post matters right now",
                "suggested_title": "A compelling post headline"
            }}
        ]
    }}
    """

    try:
        result = _call_groq(prompt)
        return result.get("recommendations", [])
    except Exception as e:
        return [{"error": str(e)}]


async def recommend_volunteer_assignments(problem_id: str, db) -> List[Dict[str, Any]]:
    """
    Recommend volunteers for a problem. Uses DB volunteer data + Groq for ranking.
    Falls back to ideal volunteer profiles if no volunteers exist in DB.
    """
    from bson import ObjectId

    try:
        problem = await db.problems.find_one({"_id": ObjectId(problem_id)})
    except Exception:
        problem = await db.problems.find_one({"_id": problem_id})

    if not problem:
        return []

    volunteers = await db.volunteers.find({"current_task": None}).to_list(length=100)
    if not volunteers:
        volunteers = await db.volunteers.find({}).to_list(length=100)

    # No volunteers in DB — ask Groq what kind of volunteer would suit this problem
    if not volunteers:
        if not CLIENT:
            return []
        prompt = f"""
        A community problem needs volunteers:
        Title: {problem.get("title", "")}
        Types: {problem.get("types", [])}
        Location: {problem.get("location", "")}
        Description: {problem.get("description", "")}

        Describe the ideal volunteer profiles for this problem.

        Respond ONLY with a JSON object:
        {{
            "ideal_profiles": [
                {{
                    "role": "Role title",
                    "skills_needed": ["skill1", "skill2"],
                    "reason": "Why this role helps"
                }}
            ]
        }}
        """
        try:
            result = _call_groq(prompt)
            return result.get("ideal_profiles", [])
        except Exception as e:
            return [{"error": str(e)}]

    # We have volunteers — use Groq to rank them
    if not CLIENT:
        from utils.vertex_ai_models import volunteer_scorer
        ranked = volunteer_scorer.rank_volunteers(volunteers, problem)
        return serialize(ranked[:5])

    vol_summaries = [
        {
            "id": str(v.get("_id", "")),
            "name": v.get("name", ""),
            "skills": [s.get("skill") for s in v.get("skills", [])],
            "location": v.get("location", ""),
            "completed_tasks": len([t for t in v.get("previous_tasks", []) if t.get("status") == "completed"]),
            "available": v.get("current_task") is None,
        }
        for v in volunteers[:20]
    ]

    prompt = f"""
    Rank these volunteers for a community problem:

    Problem:
    - Title: {problem.get("title", "")}
    - Types: {problem.get("types", [])}
    - Location: {problem.get("location", "")}

    Volunteers:
    {json.dumps(vol_summaries, indent=2)}

    Return top 5 ranked by suitability.

    Respond ONLY with a JSON object:
    {{
        "ranked": [
            {{
                "volunteer_id": "id",
                "volunteer_name": "name",
                "total_score": 0.85,
                "reasoning": "Why this volunteer fits"
            }}
        ]
    }}
    """

    try:
        result = _call_groq(prompt)
        return result.get("ranked", [])
    except Exception as e:
        return [{"error": str(e)}]


async def analyze_ngo_dashboard(ngo: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Generate an AI-powered dashboard summary for an NGO using Groq.
    Uses whatever DB stats are available; Groq fills in area insights.
    """
    if not CLIENT:
        return {"error": "Groq not configured"}

    ngo_id = str(ngo.get("_id", ""))
    location = ngo.get("location", "Unknown")
    ngo_name = ngo.get("name", "NGO")

    total_posts = await db.posts.count_documents({"ngo_id": ngo_id})
    active_problems = await db.problems.count_documents({"status": "open"})
    total_volunteers = await db.volunteers.count_documents({})
    busy_volunteers = await db.volunteers.count_documents({"current_task": {"$ne": None}})

    prompt = f"""
    You are an NGO analyst. Generate a dashboard summary for "{ngo_name}" in {location}.

    Current stats:
    - Posts published: {total_posts}
    - Active problems reported: {active_problems}
    - Volunteers: {total_volunteers} total, {busy_volunteers} currently assigned

    Based on the location "{location}", predict the top 3 community needs
    and give a 2-sentence summary of the NGO situation and what to prioritize.

    Respond ONLY with a JSON object:
    {{
        "summary": "2 sentence overall summary",
        "priority_action": "The single most important thing to do this week",
        "area_predictions": [
            {{
                "category": "category name",
                "urgency": "critical or high or medium",
                "reason": "brief reason"
            }}
        ]
    }}
    """

    try:
        result = _call_groq(prompt)
    except Exception as e:
        result = {"summary": str(e), "priority_action": "", "area_predictions": []}

    predictions = result.get("area_predictions", [])

    return {
        "ngo_name": ngo_name,
        "total_posts": total_posts,
        "active_problems": active_problems,
        "volunteers": {"total": total_volunteers, "assigned": busy_volunteers},
        "top_predicted_need": predictions[0].get("category") if predictions else None,
        "area_predictions": predictions,
        "priority_action": result.get("priority_action", ""),
        "summary": result.get("summary", ""),
        "powered_by": "Groq / Llama-3.3-70b",
    }