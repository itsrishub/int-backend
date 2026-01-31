from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/generic", tags=["Generic"])


class StartInterviewSession(BaseModel):
    user_id: Optional[str] = None
    interview_type: Optional[str] = None
    start_time: Optional[str] = None


class EndInterviewSession(BaseModel):
    interview_session_id: int
    end_time: Optional[str] = None
    feedback: Optional[str] = None
    score: Optional[int] = None


@router.post("/start_interview_session")
def start_interview_session(session: StartInterviewSession):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        cursor.execute('''
            INSERT INTO interview_sessions (user_id, interview_type, start_time)
            VALUES (%s, %s, %s)
            RETURNING id
        ''', (
            session.user_id,
            session.interview_type,
            session.start_time
        ))
        interview_session_id = cursor.fetchone()['id']
        conn.commit()
        
        return {
            "success": True,
            "message": "Interview session created successfully",
            "id": interview_session_id,
            "interview_type": session.interview_type
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
        
        # Update the session with end_time, feedback, score, duration
        cursor.execute('''
            UPDATE interview_sessions 
            SET end_time = %s, feedback = %s, score = %s, duration = %s
            WHERE id = %s
        ''', (
            end_time_str,
            session.feedback,
            session.score,
            duration,
            session.interview_session_id
        ))
        conn.commit()
        
        return {
            "success": True,
            "message": "Interview session ended successfully",
            "id": session.interview_session_id,
            "duration": duration,
            "feedback": session.feedback,
            "score": session.score
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()