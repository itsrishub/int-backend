from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db_connection, get_db_cursor
from typing import Optional
import json
import os
import io
import google.generativeai as genai
from PyPDF2 import PdfReader

router = APIRouter(prefix="/api/theai", tags=["AI"])

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(os.getenv("AI_MODEL"))


class AnswerQuestion(BaseModel):
    question_id: int
    answer: str

class AnalyzeResume(BaseModel):
    resume_id: Optional[int] = None
    user_id: Optional[str] = None
    resume_name: Optional[str] = None
    resume_blob: Optional[str] = None


def generate_content(prompt: str) -> str:
    """Generate content using Gemini API."""
    response = model.generate_content(prompt)
    return response.text


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text content from PDF bytes."""
    pdf_file = io.BytesIO(pdf_bytes)
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text.strip()


@router.post("/resume/")
def analyze_resume(analyze_resume: AnalyzeResume):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)

    resume_blob = None
    if analyze_resume.resume_id is not None:
        cursor.execute("SELECT id, resume_blob FROM resumes WHERE id = %s", (analyze_resume.resume_id,))
        resume = cursor.fetchone()
        if resume is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Resume not found for this user")
        resume_blob = resume["resume_blob"]
    else:
        cursor.execute("INSERT INTO resumes (user_id, resume_name, resume_blob) VALUES (%s, %s, %s)", (user_id, analyze_resume.resume_name, analyze_resume.resume_blob))
        resume_blob = analyze_resume.resume_blob
    
    
    if not resume_blob:
        conn.close()
        raise HTTPException(status_code=400, detail="Resume is empty")
    
    # Convert memoryview to bytes if needed
    if isinstance(resume_blob, memoryview):
        resume_bytes = bytes(resume_blob)
    else:
        resume_bytes = resume_blob
    
    # Extract text from PDF
    try:
        resume_text = extract_text_from_pdf(resume_bytes)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
    
    if not resume_text:
        conn.close()
        raise HTTPException(status_code=400, detail="Could not extract text from resume PDF")
    
    # Create prompt for ATS analysis with full resume text
    prompt = f"""Analyze this resume and provide an ATS (Applicant Tracking System) score and feedback.

Resume Content:
{resume_text}

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
        ai_response = generate_content(prompt)
        
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
                analyze_resume.resume_id
            ))
            conn.commit()
        
        conn.close()
        
        return {
            "success": True,
            "resume_id": analyze_resume.resume_id,
            **result
        }
        
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    

# @router.get("/resume/{resume_id}")
# def analyze_resume_with_id(resume_id: int):


@router.get("/gen_ques/{interview_session_id}")
def generate_questions(interview_session_id: int):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Get session details (role, company, experience, job_description, resume_blob)
        cursor.execute("""
            SELECT role, company, experience_level, job_description, resume_blob 
            FROM interview_sessions 
            WHERE id = %s
        """, (interview_session_id,))
        session = cursor.fetchone()
        
        if session is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        # Extract session context
        role = session["role"]
        company = session["company"]
        experience = session["experience_level"]
        job_description = session["job_description"]
        resume_text = ""
        
        # Extract text from resume if present
        if session["resume_blob"]:
            try:
                import base64
                resume_bytes = base64.b64decode(session["resume_blob"])
                resume_text = extract_text_from_pdf(resume_bytes)
            except:
                resume_text = ""
        
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
                INSERT INTO interview_chit_chat (session_id, question)
                VALUES (%s, %s)
                RETURNING id
            """, (interview_session_id, intro_question))
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
        
        # Build context section
        context_parts = []
        if role:
            context_parts.append(f"Role: {role}")
        if company:
            context_parts.append(f"Company: {company}")
        if job_description:
            context_parts.append(f"Job Description: {job_description}")
        if resume_text:
            context_parts.append(f"Candidate Resume:\n{resume_text[:3000]}")
        
        real_context = ""
        if context_parts:
            context_text = "\n".join(context_parts)
            real_context += f"Interview Context:\n{context_text}"
        
        # Build intro sentence dynamically
        intro_part = "You are an expert interviewer conducting an interview"
        if role:
            intro_part += f" for the role of {role}"
        if company:
            intro_part += f" at {company}"
        intro_part += "."

        # Generate next question using Gemini
        prompt = f"""{intro_part}

{real_context}

Conversation history:
{conversation_text}

Rules:
1. Ask a relevant follow-up question based on the candidate's previous answers
2. Questions should be tailored to the role, company, and job requirements
3. Consider the candidate's experience level ({experience} years) when framing questions
4. Add a brief acknowledgment or transition before asking the question
5. Response should ONLY be valid JSON in this exact format:
{{
    "question": "<your next interview question>"
}}

Respond with ONLY the JSON, no additional text."""

        ai_response = generate_content(prompt)
        
        # Parse JSON response
        try:
            result = json.loads(ai_response)
            next_question = result.get("question", "Can you elaborate more on that?")
        except json.JSONDecodeError:
            # If parsing fails, use the raw response or fallback
            next_question = ai_response.strip() if ai_response else "Can you tell me more about your experience?"
        
        # Insert new question into database
        cursor.execute("""
            INSERT INTO interview_chit_chat (session_id, question)
            VALUES (%s, %s)
            RETURNING id
        """, (interview_session_id, next_question))
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


def analyze_interview_performance(history: list, context: dict) -> dict:
    """
    Analyze the full interview session and generate a scorecard.
    """
    try:
        # Build conversation text
        conversation = []
        for qa in history:
            conversation.append(f"Interviewer: {qa['question']}")
            if qa['answer']:
                conversation.append(f"Candidate: {qa['answer']}")
        
        conversation_text = "\n\n".join(conversation)
        
        # Build context text
        context_parts = []
        if context.get('role'):
            context_parts.append(f"Target Role: {context['role']}")
        if context.get('company'):
            context_parts.append(f"Target Company: {context['company']}")
        if context.get('experience_level'):
            context_parts.append(f"Experience Level: {context['experience_level']} years")
        if context.get('job_description'):
            context_parts.append(f"Job Description: {context['job_description']}")
            
        context_text = "\n".join(context_parts)

        prompt = f"""You are an expert technical interviewer and hiring manager. 
Evaluate this interview session based on the conversation history and context provided.

Context:
{context_text}

Interview Transcript:
{conversation_text}

Please provide a comprehensive evaluation in the following JSON format ONLY:
{{
    "score": <integer 0-100 overall score>,
    "strengths": ["<strength1>", "<strength2>", "<strength3>"],
    "area_of_improvement": ["<area1>", "<area2>", "<area3>"]
}}

Scoring Criteria:
- Technical accuracy of answers
- Communication clarity and confidence
- Problem-solving approach
- Relevance to the specific role and experience level

Respond with ONLY the valid JSON, no markdown formatting or extra text.
"""

        ai_response = generate_content(prompt)
        
        try:
            # Clean up potential markdown code blocks if the model adds them
            clean_response = ai_response.replace('```json', '').replace('```', '').strip()
            result = json.loads(clean_response)
            
            # Ensure all keys exist
            return {
                "score": result.get("score", 0),
                "strengths": result.get("strengths", []),
                "area_of_improvement": result.get("area_of_improvement", [])
            }
        except json.JSONDecodeError:
            print(f"Failed to parse AI response: {ai_response}")
            return {
                "score": 0,
                "strengths": [],
                "area_of_improvement": []
            }
            
    except Exception as e:
        print(f"Error in analyze_interview_performance: {e}")
        return {
            "score": 0,
            "strengths": [],
            "area_of_improvement": []
        }