import sqlite3
import os

# Use /tmp for Vercel serverless (writable but temporary)
DATABASE_NAME = "/tmp/interview_ai.db"


def get_db_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_photo TEXT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            primary_role TEXT,
            year_of_exp INTEGER,
            rank INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            experience_level TEXT,
            interview_type TEXT,
            score INTEGER,
            feedback TEXT,
            duration INTEGER,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_chit_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            interview_type TEXT,
            question TEXT,
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            resume_blob BLOB,
            ats_score INTEGER,
            feedback TEXT,
            strengths TEXT,
            weaknesses TEXT,
            keywords_found TEXT,
            missing_keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully:", DATABASE_NAME)


if __name__ == "__main__":
    init_db()
