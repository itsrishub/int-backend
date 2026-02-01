"""Pydantic schemas for API request/response models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# WebSocket Message Types
# ============================================================================

class WSMessageType(str, Enum):
    """Types of WebSocket messages."""
    # Client -> Server
    START = "start"
    ANSWER = "answer"
    PING = "ping"
    END = "end"
    
    # Server -> Client
    QUESTION = "question"
    COMPLETE = "complete"
    ERROR = "error"
    PONG = "pong"
    SESSION_INFO = "session_info"


# ============================================================================
# Client -> Server Messages
# ============================================================================

class StartInterviewRequest(BaseModel):
    """Request to start an interview."""
    interview_type: str = Field(default="general", description="Type of interview")


class AnswerRequest(BaseModel):
    """User's answer to a question."""
    question_id: int = Field(..., description="ID of the question being answered")
    answer_text: str = Field(..., description="User's answer text")


class WSClientMessage(BaseModel):
    """Wrapper for all client WebSocket messages."""
    type: WSMessageType
    data: Optional[dict] = None


# ============================================================================
# Server -> Client Messages
# ============================================================================

class WordTiming(BaseModel):
    """Timing information for lip-sync."""
    word: str
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")


class AvatarMode(str, Enum):
    """Avatar rendering mode."""
    VIDEO = "video"  # Full video avatar from D-ID
    AUDIO_ONLY = "audio_only"  # Audio with static image (fallback)


class QuestionResponse(BaseModel):
    """Question data sent to client."""
    question_id: int
    question_text: str
    question_type: str
    
    # Avatar mode
    avatar_mode: AvatarMode = Field(
        default=AvatarMode.AUDIO_ONLY,
        description="Avatar rendering mode: 'video' or 'audio_only'"
    )
    
    # Video avatar (when avatar_mode is VIDEO)
    video_url: Optional[str] = Field(
        default=None,
        description="URL to the avatar video (MP4) - present when avatar_mode is 'video'"
    )
    
    # Idle video (for looping during wait states)
    idle_video_url: Optional[str] = Field(
        default=None,
        description="URL to short idle/nodding video for smoother UX between questions"
    )
    
    # Audio (always present)
    audio_base64: str = Field(..., description="Base64 encoded MP3 audio")
    audio_duration: float = Field(..., description="Audio duration in seconds")
    
    # Lip-sync timing (for audio_only mode)
    word_timings: list[WordTiming] = Field(
        default_factory=list,
        description="Word-level timing for lip-sync (used in audio_only mode)"
    )
    
    # Static avatar image (for audio_only mode)
    avatar_image_url: Optional[str] = Field(
        default=None,
        description="URL to static avatar image (used in audio_only mode)"
    )
    
    # Progress
    current_question: int
    total_questions: int
    
    # Latency metrics (for debugging/monitoring)
    latency_ms: Optional[float] = Field(
        default=None,
        description="Total video generation latency in milliseconds"
    )


class InterviewCompleteResponse(BaseModel):
    """Sent when interview is complete."""
    message: str
    questions_answered: int
    session_summary: Optional[dict] = None


class SessionInfoResponse(BaseModel):
    """Session information."""
    session_id: str
    state: str
    total_questions: int


class ErrorResponse(BaseModel):
    """Error message."""
    code: str
    message: str
    details: Optional[dict] = None


class WSServerMessage(BaseModel):
    """Wrapper for all server WebSocket messages."""
    type: WSMessageType
    data: dict


# ============================================================================
# HTTP API Schemas
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str


class VoiceInfo(BaseModel):
    """Information about an available TTS voice."""
    name: str
    gender: str
    locale: str


class VoicesResponse(BaseModel):
    """List of available voices."""
    voices: list[VoiceInfo]
