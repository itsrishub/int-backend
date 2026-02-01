"""Session manager for interview state management."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from app.shared.utils import generate_session_id, get_timestamp


class SessionState(str, Enum):
    """State of an interview session."""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_ANSWER = "waiting_for_answer"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass
class AnswerRecord:
    """Record of a user's answer."""
    question_id: int
    answer_text: str
    timestamp: str


@dataclass
class InterviewSession:
    """Represents an active interview session."""
    session_id: str
    state: SessionState
    created_at: str
    current_question_id: int = 0
    answers: list[AnswerRecord] = field(default_factory=list)
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = self.created_at


class SessionManager:
    """
    Manages interview sessions and their state.
    
    For MVP, sessions are stored in memory. In production,
    this would use Redis or a database for persistence.
    """

    def __init__(self, session_timeout: int = 1800):
        """
        Initialize the session manager.
        
        Args:
            session_timeout: Session timeout in seconds (default: 30 minutes)
        """
        self._sessions: dict[str, InterviewSession] = {}
        self._session_timeout = session_timeout

    def create_session(self) -> InterviewSession:
        """Create a new interview session."""
        session_id = generate_session_id()
        timestamp = get_timestamp()
        
        session = InterviewSession(
            session_id=session_id,
            state=SessionState.CREATED,
            created_at=timestamp,
            updated_at=timestamp,
        )
        
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def update_session_state(
        self, 
        session_id: str, 
        state: SessionState
    ) -> Optional[InterviewSession]:
        """Update the state of a session."""
        session = self._sessions.get(session_id)
        if session:
            session.state = state
            session.updated_at = get_timestamp()
        return session

    def set_current_question(
        self, 
        session_id: str, 
        question_id: int
    ) -> Optional[InterviewSession]:
        """Set the current question for a session."""
        session = self._sessions.get(session_id)
        if session:
            session.current_question_id = question_id
            session.updated_at = get_timestamp()
        return session

    def record_answer(
        self, 
        session_id: str, 
        question_id: int, 
        answer_text: str
    ) -> Optional[InterviewSession]:
        """Record a user's answer for a question."""
        session = self._sessions.get(session_id)
        if session:
            answer = AnswerRecord(
                question_id=question_id,
                answer_text=answer_text,
                timestamp=get_timestamp(),
            )
            session.answers.append(answer)
            session.updated_at = get_timestamp()
        return session

    def complete_session(self, session_id: str) -> Optional[InterviewSession]:
        """Mark a session as completed."""
        return self.update_session_state(session_id, SessionState.COMPLETED)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def get_session_summary(self, session_id: str) -> Optional[dict]:
        """Get a summary of the session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "questions_answered": len(session.answers),
            "created_at": session.created_at,
            "completed_at": session.updated_at if session.state == SessionState.COMPLETED else None,
        }

    def get_active_sessions_count(self) -> int:
        """Get the count of active sessions."""
        return len([
            s for s in self._sessions.values() 
            if s.state not in [SessionState.COMPLETED, SessionState.EXPIRED]
        ])
