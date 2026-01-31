from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db_connection, get_db_cursor
import base64
import json
import os

# Set writable directory for g4f cache (Vercel only allows /tmp)
os.environ["HOME"] = "/tmp"

from g4f.client import Client

router = APIRouter(prefix="/api/theai", tags=["AI"])

MODEL = os.getenv("AI_MODEL")

client = Client()

class AnswerQuestion(BaseModel):
    question_id: int
    answer: str

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
            model="gpt-4o",
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
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Get interview session details
        cursor.execute("SELECT interview_type FROM interview_sessions WHERE id = %s", (interview_session_id,))
        session = cursor.fetchone()
        
        if session is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        interview_type = session["interview_type"] or "general"
        
        # Get all Q&A history for this session
        cursor.execute("""
            SELECT question, answer FROM interview_chit_chat 
            WHERE session_id = %s 
            ORDER BY created_at ASC
        """, (interview_session_id,))
        history = cursor.fetchall()
        
        # If no history, return hardcoded intro question
        if not history:
            intro_question = "Hello! Tell me about yourself."
            
            # Insert intro question into database
            cursor.execute("""
                INSERT INTO interview_chit_chat (session_id, interview_type, question)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (interview_session_id, interview_type, intro_question))
            question_id = cursor.fetchone()["id"]
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "session_id": interview_session_id,
                "question_id": question_id,
                "question": intro_question,
                "is_first_question": True
            }
        
        # Build conversation history for context
        conversation = []
        for qa in history:
            conversation.append(f"Q: {qa['question']}")
            if qa['answer']:
                conversation.append(f"A: {qa['answer']}")
        
        conversation_text = "\n".join(conversation)
        
        # Generate next question using g4f
        prompt = f"""You are an expert interviewer conducting a {interview_type} interview.

Based on the conversation so far, generate the next interview question.

Conversation history:
{conversation_text}

Rules:
1. Ask a relevant follow-up question based on the candidate's previous answers
2. Keep questions professional and appropriate for a {interview_type} interview
3. Response should ONLY be valid JSON in this exact format:
{{
    "question": "<your next interview question>"
}}

Respond with ONLY the JSON, no additional text."""

        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            web_search=False
        )
        
        ai_response = response.choices[0].message.content
        
        # Parse JSON response
        try:
            result = json.loads(ai_response)
            next_question = result.get("question", "Can you elaborate more on that?")
        except json.JSONDecodeError:
            # If parsing fails, use the raw response or fallback
            next_question = ai_response.strip() if ai_response else "Can you tell me more about your experience?"
        
        # Insert new question into database
        cursor.execute("""
            INSERT INTO interview_chit_chat (session_id, interview_type, question)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (interview_session_id, interview_type, next_question))
        question_id = cursor.fetchone()["id"]
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "session_id": interview_session_id,
            "question_id": question_id,
            "question": next_question,
            "is_first_question": False,
            "questions_asked": len(history) + 1
        }
        
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send_ans/")
def send_answer(answer: AnswerQuestion):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Check if question exists
        cursor.execute("SELECT id FROM interview_chit_chat WHERE id = %s", (answer.question_id,))
        row = cursor.fetchone()
        
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Update the answer
        cursor.execute("""
            UPDATE interview_chit_chat 
            SET answer = %s 
            WHERE id = %s
        """, (answer.answer, answer.question_id))
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "question_id": answer.question_id,
            "message": "Answer saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))