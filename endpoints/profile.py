from fastapi import APIRouter, HTTPException
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("/{user_id}")
def get_profile(user_id: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as count FROM interview_sessions WHERE user_id = %s", (user_id,))
    total_sessions = cursor.fetchone()['count']

    cursor.execute("SELECT AVG(score) as avg_score FROM interview_sessions WHERE user_id = %s", (user_id,))
    avg_score = cursor.fetchone()['avg_score']

    cursor.execute("SELECT resume_blob FROM resumes WHERE user_id = %s", (user_id,))
    resume = cursor.fetchone()['resume_blob']
    conn.close()
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user": dict(user),
        "resume": resume
        "total_sessions": total_sessions,
        "best_score": avg_score,
        "avg_score": avg_score
    }


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