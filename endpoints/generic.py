from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db_connection, get_db_cursor
from endpoints.theai import analyze_interview_performance
import json

router = APIRouter(prefix="/api/generic", tags=["Generic"])


class StartInterviewSession(BaseModel):
    user_id: Optional[str] = None
    start_time: Optional[str] = None
    resume_blob: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    experience: Optional[int] = 0
    job_description: Optional[str] = None
    interview_type: Optional[str] = None


class EndInterviewSession(BaseModel):
    interview_session_id: int
    end_time: Optional[str] = None


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

    if session is None:
        conn.close()
        return {
            "success": True,
            "has_active_session": False,
            "session_id": None,
            "last_question_id": None
        }

    cursor.execute("""
        SELECT * FROM interview_chit_chat
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (session["id"],))
    last_question = cursor.fetchone()
    
    conn.close()
    
    return {
        "success": True,
        "has_active_session": True,
        "session_id": session["id"],
        "last_question_id": last_question["id"] if last_question else None
    }

@router.post("/start_interview_session")
def start_interview_session(session: StartInterviewSession):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Terminate any existing active sessions for this user
        cursor.execute("""
            UPDATE interview_sessions 
            SET status = 'terminated' 
            WHERE user_id = %s AND status = 'active'
        """, (session.user_id,))

        cursor.execute("""
            INSERT INTO interview_sessions (user_id, start_time, status, resume_blob, role, company, experience_level, job_description, interview_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            session.user_id,
            session.start_time,
            'active',
            session.resume_blob,
            session.role,
            session.company,
            session.experience,
            session.job_description,
            session.interview_type
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
        cursor.execute("SELECT * FROM interview_sessions WHERE id = %s", (session.interview_session_id,))
        row = cursor.fetchone()
        
        if row is None:
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        start_time_str = row["start_time"]
        target_role = row["role"]
        company = row["company"]
        experience_level = row["experience_level"]
        job_description = row["job_description"]
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
        
        # --- AI Analysis Integration ---
        # 1. Fetch chat history
        cursor.execute("""
            SELECT question, answer FROM interview_chit_chat
            WHERE session_id = %s
            ORDER BY created_at ASC
        """, (session.interview_session_id,))
        history = cursor.fetchall()
        
        # 2. Prepare context
        context = {
            "role": target_role,
            "company": company,
            "experience_level": experience_level,
            "job_description": job_description
        }
        
        # 3. Call AI Analysis
        analysis_result = analyze_interview_performance(history, context)
        
        score = analysis_result["score"]
        # feedback = analysis_result["feedback"]
        strengths = json.dumps(analysis_result["strengths"])
        area_of_improvement = json.dumps(analysis_result["area_of_improvement"])
        
        # Update the session with end_time, feedback, score, duration, status
        final_status = 'closed'
        cursor.execute('''
            UPDATE interview_sessions 
            SET end_time = %s, score = %s, duration = %s, status = %s, strengths = %s, area_of_improvement = %s
            WHERE id = %s
        ''', (
            end_time_str,
            score,
            duration,
            final_status,
            strengths,
            area_of_improvement,
            session.interview_session_id
        ))
        conn.commit()
        
        return {
            "success": True,
            "message": "Interview session ended successfully",
            "id": session.interview_session_id,
            "target_role": target_role,
            "duration": duration,
            "end_time": end_time_str,
            "area_of_improvement": analysis_result["area_of_improvement"],
            "strengths": analysis_result["strengths"],
            "score": score,
            "status": final_status
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/home/{user_id}")
def get_home_data(user_id: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # 1. Best Score & Improvement
        # Get highest score
        cursor.execute("SELECT score FROM interview_sessions WHERE user_id = %s AND status = 'closed' ORDER BY score DESC NULLS LAST LIMIT 1", (user_id,))
        best_row = cursor.fetchone()
        best_score = best_row['score'] if best_row and best_row['score'] else 0
        
        # Calculate improvement (compare average of last 3 sessions vs average of 3 sessions before that)
        cursor.execute("SELECT score FROM interview_sessions WHERE user_id = %s AND status = 'closed' AND score IS NOT NULL ORDER BY created_at DESC LIMIT 6", (user_id,))
        scores = [row['score'] for row in cursor.fetchall()]
        
        improvement = 0
        if len(scores) >= 2:
            current_avg = sum(scores[:3]) / len(scores[:3])
            prev_avg = sum(scores[3:]) / len(scores[3:]) if len(scores) > 3 else (scores[-1] if scores else 0)
            improvement = int(current_avg - prev_avg)

        # 2. Total Sessions
        # This week
        cursor.execute("""
            SELECT COUNT(*) as count FROM interview_sessions 
            WHERE user_id = %s AND created_at >= NOW() - INTERVAL '7 days'
        """, (user_id,))
        week_sessions = cursor.fetchone()['count']
        
        # This month
        cursor.execute("""
            SELECT COUNT(*) as count FROM interview_sessions 
            WHERE user_id = %s AND created_at >= NOW() - INTERVAL '30 days'
        """, (user_id,))
        month_sessions = cursor.fetchone()['count']

        # 3. User Details for Leaderboard
        cursor.execute("SELECT rank, primary_role, year_of_exp FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        rank = user['rank'] if user and user['rank'] else 0
        job_profile = f"{user['primary_role']} {user['year_of_exp']}YOE" if user else "Unknown"
        
        # Calculate top percentage (mock logic - can be real DB calc)
        # Count total users
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total'] or 1
        
        # Determine percentile (lower rank is better)
        top_percentage = int((rank / total_users) * 100) if rank > 0 else 0
        if top_percentage == 0 and rank > 0: top_percentage = 1

        # 4. Session History
        cursor.execute("""
            SELECT score, created_at, company, role, experience_level, interview_type 
            FROM interview_sessions 
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id,))
        history_rows = cursor.fetchall()
        
        session_history = []
        for row in history_rows:
            session_history.append({
                "score_percentage": row['score'] or 0,
                "attempted_date": row['created_at'].isoformat(),
                "company_name": row['company'] or "Practice",
                "context": [row['role'] or "General", f"{row['experience_level'] or 0} YOE"],
                "round_type": row['interview_type']
            })
            
        # Get active session ID if any
        cursor.execute("SELECT id FROM interview_sessions WHERE user_id = %s AND status = 'active' ORDER BY created_at DESC LIMIT 1", (user_id,))
        active_session = cursor.fetchone()
        active_session_id = active_session['id'] if active_session else None
        
        return {
            "success": True,
            "has_active_session": active_session_id is not None,
            "session_id": active_session_id,
            "best_score": {
                "value": best_score,
                "improvement": improvement
            },
            "total_sessions": {
                "week": week_sessions,
                "month": month_sessions
            },
            "recent_leaderboard": {
                "rank": rank,
                "top_percentage": top_percentage,
                "job_profile": job_profile
            },
            "session_history": session_history
        }
    except Exception as e:
        # conn.close() # Avoid double close if reused, but here we can just pass
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



@router.get("/resume_list/{user_id}")
def get_resume_list(user_id: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        cursor.execute("""
            SELECT id, resume_name
            FROM resumes 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        resumes = cursor.fetchall()
        
        resume_list = []
        for resume in resumes:
            resume_list.append({
                "id": resume["id"],
                "resume_name": resume["resume_name"]
            })
            
        return {
            "success": True,
            "resumes": resume_list
        }
    except Exception as e:
        print(f"Error fetching resumes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()