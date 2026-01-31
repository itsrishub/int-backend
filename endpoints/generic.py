from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/generic", tags=["Generic"])


class StartInterviewSession(BaseModel):
    user_id: Optional[str] = None
    start_time: Optional[str] = None
    resume_blob: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    experience: Optional[int] = 0
    job_description: Optional[str] = None


class EndInterviewSession(BaseModel):
    interview_session_id: int
    end_time: Optional[str] = None
    feedback: Optional[str] = None
    score: Optional[int] = None
    status: Optional[str] = "closed"


@router.get("/email/{email}")
def get_user_by_email(email: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return dict(user)


@router.get("/config/{user_id}")
def get_config(user_id: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    cursor.execute("""
        SELECT * FROM interview_sessions 
        WHERE user_id = %s AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    session = cursor.fetchone()
    conn.close()
    
    if session is None:
        return {
            "success": True,
            "has_active_session": False,
            "session_id": None
        }
    
    return {
        "success": True,
        "has_active_session": True,
        "session_id": session["id"]
    }

@router.post("/start_interview_session")
def start_interview_session(session: StartInterviewSession):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        cursor.execute('''
            INSERT INTO interview_sessions (user_id, start_time, status, resume_blob, role, company, experience_level, job_description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            session.user_id,
            session.start_time,
            'active',
            session.resume_blob,
            session.role,
            session.company,
            session.experience,
            session.job_description
        ))
        interview_session_id = cursor.fetchone()['id']
        conn.commit()
        
        return {
            "success": True,
            "message": "Interview session created successfully",
            "session_id": interview_session_id,
            "status": "active"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/end_interview_session")
def end_interview_session(session: EndInterviewSession):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Get the start_time from the session
        cursor.execute("SELECT start_time FROM interview_sessions WHERE id = %s", (session.interview_session_id,))
        row = cursor.fetchone()
        
        if row is None:
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        start_time_str = row["start_time"]
        end_time_str = session.end_time or datetime.now().isoformat()
        
        # Calculate duration in seconds
        duration = None
        if start_time_str:
            try:
                # Handle both datetime object and string
                if isinstance(start_time_str, datetime):
                    start_time = start_time_str
                else:
                    start_time = datetime.fromisoformat(start_time_str)
                end_time = datetime.fromisoformat(end_time_str)
                duration = int((end_time - start_time).total_seconds())
            except:
                pass
        
        # Update the session with end_time, feedback, score, duration, status
        final_status = session.status if session.status in ['closed', 'terminated'] else 'closed'
        cursor.execute('''
            UPDATE interview_sessions 
            SET end_time = %s, feedback = %s, score = %s, duration = %s, status = %s
            WHERE id = %s
        ''', (
            end_time_str,
            session.feedback,
            session.score,
            duration,
            final_status,
            session.interview_session_id
        ))
        conn.commit()
        
        return {
            "success": True,
            "message": "Interview session ended successfully",
            "id": session.interview_session_id,
            "duration": duration,
            "feedback": session.feedback,
            "score": session.score,
            "status": final_status
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()