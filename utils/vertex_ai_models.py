"""
ML Models for advanced predictions (without scikit-learn to avoid version conflicts):
- Area needs prediction using pattern analysis
- Volunteer suitability scoring using weighted factors
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.config import get_settings

settings = get_settings()

# Initialize Vertex AI if GCP is configured (optional integration)
VERTEX_AI_AVAILABLE = False
if settings.gcp_project_id:
    try:
        import vertexai
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        VERTEX_AI_AVAILABLE = True
    except Exception as e:
        print(f"Vertex AI initialization note: {e}")


class AreaNeedsPredictor:
    """Predict what categories of needs will emerge in an area using pattern analysis."""
    
    CATEGORIES = ["health", "education", "infrastructure", "environment", "safety", "food"]
    
    def predict_next_needs(self, problems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze historical problems and predict future needs.
        Uses pattern matching, frequency, recency, and urgency signals.
        """
        if not problems or len(problems) < 3:
            return []
        
        predictions = []
        now = datetime.now()
        
        for category in self.CATEGORIES:
            # Count problems in this category
            cat_problems = [p for p in problems if category in p.get("types", [])]
            if not cat_problems:
                continue
            
            count = len(cat_problems)
            avg_importance = sum(p.get("importance", 3) for p in cat_problems) / count
            
            # Recency: how recent are the problems?
            def safe_date_diff(prob):
                created = prob.get("created_at")
                if isinstance(created, datetime):
                    return (now - created).days
                return 999  # If date format unknown, treat as old
            
            days_since_last = min(safe_date_diff(p) for p in cat_problems)
            recency_score = max(0, (30 - days_since_last) / 30.0)  # Recent = higher
            
            # Trend: is it increasing?
            recent_count = len([p for p in cat_problems if safe_date_diff(p) < 14])
            older_count = len([p for p in cat_problems if safe_date_diff(p) >= 14])
            trend_score = (recent_count - older_count) / max(count, 1)
            
            # Composite score
            score = (recency_score * 0.4) + (avg_importance / 5.0 * 0.4) + (trend_score * 0.2)
            score = min(score, 1.0)
            
            if score > 0.25:  # Threshold for inclusion
                urgency = "critical" if score > 0.75 else "high" if score > 0.5 else "medium"
                predictions.append({
                    "category": category,
                    "score": float(round(score, 2)),
                    "urgency": urgency,
                    "reason": f"Based on {count} reports; recent activity strong; avg importance {avg_importance:.1f}/5",
                })
        
        return sorted(predictions, key=lambda x: x["score"], reverse=True)[:5]


class VolunteerSuitabilityScorer:
    """Score how suitable a volunteer is for a specific problem."""
    
    @staticmethod
    def score_volunteer(volunteer: Dict[str, Any], problem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score volunteer suitability 0-1 scale.
        Factors: skill match, skill level, location, experience, availability.
        """
        score_components = {}
        
        # 1. Skill match (0-0.4 weight)
        problem_types = problem.get("types", [])
        volunteer_skills = {s.get("skill", "").lower(): s.get("level", 1) 
                          for s in volunteer.get("skills", [])}
        
        skill_matches = 0
        max_level = 0
        for ptype in problem_types:
            for skill_name, skill_level in volunteer_skills.items():
                # Fuzzy match on skill name
                if ptype.lower() in skill_name or skill_name in ptype.lower():
                    skill_matches += 1
                    max_level = max(max_level, skill_level)
        
        skill_match = min(skill_matches * 0.15, 0.25)
        skill_level = (max_level / 5.0) * 0.15 if max_level > 0 else 0
        score_components["skill"] = skill_match + skill_level
        
        # 2. Location (0-0.3 weight)
        vol_loc = volunteer.get("location", "").lower()
        prob_loc = problem.get("location", "").lower()
        
        if vol_loc == prob_loc:
            location_score = 0.30
        elif vol_loc and prob_loc and any(w in prob_loc for w in vol_loc.split()):
            location_score = 0.20
        else:
            location_score = 0.05
        
        score_components["location"] = location_score
        
        # 3. Experience (0-0.2 weight)
        prev_tasks = volunteer.get("previous_tasks", [])
        completed = len([t for t in prev_tasks if t.get("status") == "completed"])
        score_components["experience"] = min(completed / 10, 0.2)
        
        # 4. Availability (0-0.1 weight)
        has_task = bool(volunteer.get("current_task"))
        score_components["availability"] = 0.1 if not has_task else 0.02
        
        total = sum(score_components.values())
        
        return {
            "volunteer_id": volunteer.get("_id"),
            "volunteer_name": volunteer.get("name"),
            "total_score": min(total, 1.0),
            "components": score_components,
            "reasoning": _generate_reasoning(volunteer, score_components),
        }
    
    @staticmethod
    def rank_volunteers(volunteers: List[Dict[str, Any]], 
                       problem: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rank volunteers for a problem."""
        scorer = VolunteerSuitabilityScorer()
        scores = [scorer.score_volunteer(v, problem) for v in volunteers]
        return sorted(scores, key=lambda x: x["total_score"], reverse=True)


def _generate_reasoning(volunteer: Dict[str, Any], scores: Dict[str, float]) -> str:
    """Generate human-readable reasoning for suitability score."""
    reasons = []
    
    if scores["skill"] > 0.25:
        reasons.append("Strong skill match")
    elif scores["skill"] > 0.10:
        reasons.append("Some relevant skills")
    
    if scores["location"] > 0.25:
        reasons.append("Located in area")
    elif scores["location"] > 0.05:
        reasons.append("Nearby")
    
    if scores["experience"] > 0.1:
        reasons.append(f"Experienced ({int(scores['experience'] * 10)}+ tasks)")
    
    if scores["availability"] > 0.05:
        reasons.append("Available now")
    
    return " • ".join(reasons) if reasons else "Available to assist"


# Initialize singletons
area_needs_predictor = AreaNeedsPredictor()
volunteer_scorer = VolunteerSuitabilityScorer()