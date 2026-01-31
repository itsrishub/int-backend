from fastapi import APIRouter, HTTPException
from g4f.client import Client
from database import get_db_connection, get_db_cursor
import base64
import json

router = APIRouter(prefix="/api/theai", tags=["AI"])

client = Client()


@router.get("/resume/{user_id}")
def analyze_resume(user_id: int):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    # Get resume blob for the user
    cursor.execute("SELECT id, resume_blob FROM resumes WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
    resume = cursor.fetchone()
    
    if resume is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Resume not found for this user")
    
    resume_id = resume["id"]
    resume_blob = resume["resume_blob"]
    
    # Convert blob to base64 for GPT (it can't read binary directly)
    # PostgreSQL returns memoryview or bytes for BYTEA
    if resume_blob:
        if isinstance(resume_blob, memoryview):
            resume_base64 = base64.b64encode(bytes(resume_blob)).decode('utf-8')
        else:
            resume_base64 = base64.b64encode(resume_blob).decode('utf-8')
    else:
        resume_base64 = None
    
    if not resume_base64:
        conn.close()
        raise HTTPException(status_code=400, detail="Resume is empty")
    
    # Create prompt for ATS analysis
    prompt = f"""Analyze this resume (provided as base64 PDF) and provide an ATS (Applicant Tracking System) score and feedback.

Resume (base64): {resume_base64[:5000]}... (truncated)

Please respond ONLY with valid JSON in this exact format:
{{
    "ats_score": <number 0-100>,
    "feedback": "<detailed feedback string with suggestions for improvement>",
    "strengths": ["<strength1>", "<strength2>"],
    "weaknesses": ["<weakness1>", "<weakness2>"],
    "keywords_found": ["<keyword1>", "<keyword2>"],
    "missing_keywords": ["<keyword1>", "<keyword2>"]
}}

Consider these factors for ATS score:
- Proper formatting and structure
- Relevant keywords for the industry
- Clear section headings
- Quantifiable achievements
- Contact information completeness
- File format compatibility

Respond with ONLY the JSON, no additional text."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            web_search=False
        )
        
        ai_response = response.choices[0].message.content
        
        # Try to parse JSON response
        try:
            result = json.loads(ai_response)
        except json.JSONDecodeError:
            # If parsing fails, return raw response
            result = {
                "ats_score": None,
                "feedback": ai_response,
                "parse_error": True
            }
        
        # Update resume in database with all analysis results
        if result.get("ats_score") is not None:
            cursor.execute('''
                UPDATE resumes 
                SET ats_score = %s, feedback = %s, strengths = %s, weaknesses = %s, keywords_found = %s, missing_keywords = %s
                WHERE id = %s
            ''', (
                result["ats_score"],
                result.get("feedback", ""),
                json.dumps(result.get("strengths", [])),
                json.dumps(result.get("weaknesses", [])),
                json.dumps(result.get("keywords_found", [])),
                json.dumps(result.get("missing_keywords", [])),
                resume_id
            ))
            conn.commit()
        
        conn.close()
        
        return {
            "success": True,
            "user_id": user_id,
            "resume_id": resume_id,
            **result
        }
        
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gen_ques/{interview_session_id}")
def generate_questions(interview_session_id: int):
    pass