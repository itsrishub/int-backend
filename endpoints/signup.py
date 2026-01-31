from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import base64
from database import get_db_connection, get_db_cursor

router = APIRouter(prefix="/api/signup", tags=["Signup"])


class UserSignup(BaseModel):
    user_id: Optional[str] = None
    profile_photo: Optional[str] = None  # base64 string
    full_name: str
    email: str
    primary_role: Optional[str] = None
    year_of_exp: Optional[int] = None
    rank: Optional[int] = None
    resume: Optional[str] = None  # base64 encoded PDF


@router.post("/")
def create_user(user: UserSignup):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        # Insert into users table
        cursor.execute('''
            INSERT INTO users (id, profile_photo, full_name, email, primary_role, year_of_exp, rank)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            user.user_id,
            user.profile_photo,
            user.full_name,
            user.email,
            user.primary_role,
            user.year_of_exp,
            user.rank
        ))
        user_id = cursor.fetchone()['id']
        
        # Insert resume into resumes table if provided
        resume_id = None
        if user.resume:
            # Decode base64 to binary
            resume_blob = base64.b64decode(user.resume)
            cursor.execute('''
                INSERT INTO resumes (user_id, resume_blob)
                VALUES (%s, %s)
                RETURNING id
            ''', (user_id, resume_blob))
            resume_id = cursor.fetchone()['id']
        
        conn.commit()
        
        return {
            "success": True,
            "message": "User created successfully",
            "user_id": user_id,
            "resume_id": resume_id
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.get("/{user_id}")
def get_user(user_id: str):
    conn = get_db_connection()
    cursor = get_db_cursor(conn)
    
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        
        return dict(user)
    finally:
        conn.close()