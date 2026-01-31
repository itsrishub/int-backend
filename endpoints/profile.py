from fastapi import APIRouter, HTTPException
from database import get_db_connection

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("/{user_id}")
def get_profile(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return dict(user)