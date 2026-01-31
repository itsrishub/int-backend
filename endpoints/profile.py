from fastapi import APIRouter, HTTPException
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("/{user_id}")
def get_profile(user_id: int):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return dict(user)


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