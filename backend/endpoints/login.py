from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import base64
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/login", tags=["Login"])


class UserLogin(BaseModel):
    email: Optional[str] = None


@router.post("/")
def login(user: UserLogin):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Insert into users table
        cursor.execute('''
            SELECT * FROM users WHERE email = %s
        ''', (
            user.email,
        ))
        user_id = cursor.fetchone()['id']
        
        conn.commit()
        
        return {
            "success": True,
            "message": "User logged in successfully",
            "user_id": user_id,
        }
    except:
        raise HTTPException(status_code=404, detail="User not found")
