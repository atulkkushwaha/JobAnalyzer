import re
import json

# ---- A list of common tech skills to search for in job descriptions ----
# Lowercase, used for case-insensitive matching. Multi-word entries are fine.
TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd",
    "git", "linux", "bash",
    "react", "angular", "vue", "next.js", "node.js", "express",
    "django", "flask", "fastapi", "spring boot", "spring",
    "html", "css", "tailwind", "graphql", "rest api",
    "pandas", "numpy", "pytorch", "tensorflow", "scikit-learn",
    "machine learning", "deep learning", "nlp", "data analysis",
    "microservices", "kafka", "rabbitmq", "elasticsearch",
    "jenkins", "github actions", "agile", "scrum",
    "jira", "unit testing", "junit", "pytest",
]


def find_skills_in_description(job_description, skills_list=TECH_SKILLS):
    """Return the subset of skills_list that appear in job_description.

    Matching is case-insensitive and uses word boundaries so short skills
    (e.g. "go", "c#") don't accidentally match inside other words.
    """
    text = job_description.lower()
    found = []
    for skill in skills_list:
        skill_lower = skill.lower()
        # Escape special regex chars in the skill (e.g. "c++", "ci/cd")
        # and match it as a whole word/phrase within the text.
        pattern = r"(?<![a-z0-9])" + re.escape(skill_lower) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            found.append(skill)
    return found


def compare_skills(job_skills, user_skills_text):
    """Compare skills found in a job description to the user's own skills.

    job_skills: list of skills found via find_skills_in_description()
    user_skills_text: raw string of user's skills (comma or newline separated)

    Returns a dict with: match_score (%), matched (list), missing (list)
    """
    # Split user's free-text skills on commas/newlines, clean them up
    user_skills = {
        s.strip().lower()
        for s in re.split(r"[,\n]", user_skills_text)
        if s.strip()
    }

    matched = [skill for skill in job_skills if skill.lower() in user_skills]
    missing = [skill for skill in job_skills if skill.lower() not in user_skills]

    total = len(job_skills)
    match_score = round((len(matched) / total) * 100, 1) if total > 0 else 0

    return {
        "match_score": match_score,
        "matched": matched,
        "missing": missing,
    }


def _keyword_fallback(job_description, user_skills_text):
    """Run the keyword-based analysis and shape it like the AI result."""
    job_skills = find_skills_in_description(job_description)
    result = compare_skills(job_skills, user_skills_text)
    return {
        "mode": "keyword",
        "match_score": result["match_score"],
        "matched": result["matched"],
        "missing": result["missing"],
        "required_skills": job_skills,
        "summary": None,  # keyword mode doesn't produce a summary
    }


def analyze_with_gemini(job_description, user_skills_text):
    """Analyze a job description using Google Gemini (gemini-2.5-flash).

    Sends the job description + user's skills and asks for a JSON verdict.
    If the API key is missing from st.secrets, or the request/parsing fails
    for any reason, this silently falls back to the keyword-based analyzer
    instead of crashing, and includes a "fallback_reason" explaining why.
    """
    import streamlit as st  # imported here so analyzer.py has no hard Streamlit dependency

    # ---- Look up the API key ----
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = None

    if not api_key:
        result = _keyword_fallback(job_description, user_skills_text)
        result["mode"] = "keyword_fallback"
        result["fallback_reason"] = (
            "No Gemini API key found in st.secrets['GEMINI_API_KEY']. "
            "Fell back to keyword matching."
        )
        return result

    # ---- Try the real Gemini call ----
    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = f"""You are a job description analyzer.
Given a job description and a candidate's list of skills, reply with ONLY a
JSON object (no markdown formatting, no extra commentary) with exactly these keys:
- "required_skills": list of key skills/technologies the job requires
- "matched_skills": the required_skills the candidate already has
- "missing_skills": the required_skills the candidate is missing
- "score": integer 0-100, percentage of required skills the candidate covers
- "summary": a two sentence summary of the candidate's fit for this role

Job description:
{job_description}

Candidate's skills:
{user_skills_text}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        # Strip markdown code fences (```json ... ``` or ``` ... ```) before parsing
        raw_text = response.text.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()

        data = json.loads(cleaned)

        return {
            "mode": "ai_gemini",
            "match_score": data.get("score", 0),
            "matched": data.get("matched_skills", []),
            "missing": data.get("missing_skills", []),
            "required_skills": data.get("required_skills", []),
            "summary": data.get("summary"),
        }

    except Exception as e:
        # Any failure (bad key, network error, malformed JSON, etc.) falls back
        result = _keyword_fallback(job_description, user_skills_text)
        result["mode"] = "keyword_fallback"
        result["fallback_reason"] = f"Gemini request failed ({e}). Fell back to keyword matching."
        return result


def analyze_with_groq(job_description, user_skills_text):
    """Analyze a job description using Groq (model: openai/gpt-oss-20b).

    Uses the OpenAI SDK pointed at Groq's OpenAI-compatible endpoint.
    Sends the job description + user's skills and asks for a JSON verdict.
    If the API key is missing from st.secrets, or the request/parsing fails
    for any reason, this silently falls back to the keyword-based analyzer
    instead of crashing, and includes a "fallback_reason" explaining why.
    """
    import streamlit as st  # imported here so analyzer.py has no hard Streamlit dependency

    # ---- Look up the API key ----
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = None

    if not api_key:
        result = _keyword_fallback(job_description, user_skills_text)
        result["mode"] = "keyword_fallback"
        result["fallback_reason"] = (
            "No Groq API key found in st.secrets['GROQ_API_KEY']. "
            "Fell back to keyword matching."
        )
        return result

    # ---- Try the real Groq call ----
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

        prompt = f"""You are a job description analyzer.
Given a job description and a candidate's list of skills, reply with ONLY a
JSON object (no markdown formatting, no extra commentary) with exactly these keys:
- "required_skills": list of key skills/technologies the job requires
- "matched_skills": the required_skills the candidate already has
- "missing_skills": the required_skills the candidate is missing
- "score": integer 0-100, percentage of required skills the candidate covers
- "summary": a two sentence summary of the candidate's fit for this role

Job description:
{job_description}

Candidate's skills:
{user_skills_text}
"""

        response = client.responses.create(
            input=prompt,
            model="openai/gpt-oss-20b",
        )

        # Strip markdown code fences (```json ... ``` or ``` ... ```) before parsing
        raw_text = response.output_text.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()

        data = json.loads(cleaned)

        return {
            "mode": "ai_groq",
            "match_score": data.get("score", 0),
            "matched": data.get("matched_skills", []),
            "missing": data.get("missing_skills", []),
            "required_skills": data.get("required_skills", []),
            "summary": data.get("summary"),
        }

    except Exception as e:
        # Any failure (bad key, network error, malformed JSON, etc.) falls back
        result = _keyword_fallback(job_description, user_skills_text)
        result["mode"] = "keyword_fallback"
        result["fallback_reason"] = f"Groq request failed ({e}). Fell back to keyword matching."
        return result