import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

# Supabase PostgreSQL credentials from environment variables
DATABASE_URL = os.getenv("POSTGRES_DATABASE_URL")


def get_db_connection():
    """Get a connection to the PostgreSQL database."""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        raise RuntimeError(
            "Missing Supabase database credentials. "
            "Please set SUPABASE_DATABASE_URL or (SUPABASE_DB_HOST, SUPABASE_DB_USER, SUPABASE_DB_PASSWORD) in environment variables."
        )
    return conn


def get_db_cursor(conn):
    """Get a cursor that returns rows as dictionaries."""
    return conn.cursor(cursor_factory=RealDictCursor)


def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            profile_photo TEXT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            primary_role TEXT NOT NULL,
            year_of_exp INTEGER NOT NULL,
            rank INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            role TEXT,
            experience_level TEXT,
            interview_type TEXT,
            status TEXT DEFAULT 'active',
            resume_blob BYTEA,
            job_description TEXT,
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
            id SERIAL PRIMARY KEY,
            session_id INTEGER,
            interview_type TEXT,
            question TEXT,
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            resume_blob BYTEA,
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
    print("Database initialized successfully (PostgreSQL)")


if __name__ == "__main__":
    init_db()
