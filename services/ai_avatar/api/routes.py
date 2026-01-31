"""API routes for AI Avatar Service."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

from ..config import (
    SERVICE_NAME, 
    API_VERSION, 
    AVATAR_MODE, 
    AVATAR_IMAGE_URL,
    STATIC_AVATAR_URL,
    DID_API_KEY,
)
from ..core.tts_service import TTSService
from ..core.session_manager import SessionManager, SessionState
from ..core.avatar_service import (
    AvatarService, 
    DID_PRESENTER_ID,
    DID_PRESENTER_IDLE_VIDEO,
    DID_PRESENTER_IMAGE,
)
from ..mock.question_service import MockQuestionService
from .schemas import (
    WSMessageType,
    QuestionResponse,
    InterviewCompleteResponse,
    SessionInfoResponse,
    ErrorResponse,
    HealthResponse,
    VoicesResponse,
    VoiceInfo,
    WordTiming,
    AvatarMode,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix=f"/api/{API_VERSION}", tags=["AI Avatar"])

# Initialize services (singleton instances)
tts_service = TTSService()
session_manager = SessionManager()
question_service = MockQuestionService()
avatar_service = AvatarService()


# ============================================================================
# HTTP Endpoints
# ============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        version=API_VERSION,
    )


@router.get("/voices", response_model=VoicesResponse)
async def get_available_voices():
    """Get list of available TTS voices."""
    voices = await tts_service.get_available_voices()
    return VoicesResponse(
        voices=[VoiceInfo(**v) for v in voices]
    )


@router.get("/interview/info")
async def get_interview_info():
    """Get information about the interview format."""
    return {
        "total_questions": question_service.get_total_questions(),
        "question_types": ["introduction", "behavioral", "situational", "technical", "closing"],
        "estimated_duration_minutes": 15,
        "avatar_mode": "video" if avatar_service.is_configured else "audio_only",
        "avatar_image_url": AVATAR_IMAGE_URL,
        "presenter_id": DID_PRESENTER_ID,
    }


@router.get("/avatar/status")
async def get_avatar_status():
    """Get D-ID avatar service status and remaining credits."""
    if not avatar_service.is_configured:
        return {
            "configured": False,
            "mode": "audio_only",
            "message": "D-ID API key not configured. Set DID_API_KEY environment variable.",
        }
    
    credits_info = await avatar_service.get_credits_info()
    return {
        "configured": True,
        "mode": "video",
        "credits": credits_info,
    }


# ============================================================================
# WebSocket Interview Session
# ============================================================================

@router.websocket("/interview/session")
async def interview_session(websocket: WebSocket):
    """
    WebSocket endpoint for interview sessions.
    
    Protocol:
    1. Client connects
    2. Server sends session_info (includes avatar_mode)
    3. Client sends {type: "start"} to begin
    4. Server sends first question with video/audio
    5. Client sends {type: "answer", data: {question_id, answer_text}}
    6. Server sends next question (repeat until complete)
    7. Server sends {type: "complete"} when interview ends
    
    Avatar Modes:
    - "video": Full D-ID avatar video with lip-sync
    - "audio_only": Audio + static image + word timings for client-side animation
    """
    await websocket.accept()
    
    # Create a new session
    session = session_manager.create_session()
    question_service.start_session(session.session_id)
    
    # Determine avatar mode based on D-ID configuration
    current_avatar_mode = AvatarMode.VIDEO if avatar_service.is_configured else AvatarMode.AUDIO_ONLY
    
    logger.info(f"New interview session created: {session.session_id} (avatar_mode: {current_avatar_mode.value})")
    
    try:
        # Send session info to client
        await send_message(websocket, WSMessageType.SESSION_INFO, {
            "session_id": session.session_id,
            "state": session.state.value,
            "total_questions": question_service.get_total_questions(),
            "avatar_mode": current_avatar_mode.value,
            "avatar_image_url": AVATAR_IMAGE_URL,
        })
        
        # Main message loop
        while True:
            # Receive message from client
            raw_message = await websocket.receive_text()
            
            try:
                message = json.loads(raw_message)
                msg_type = message.get("type", "").lower()
                msg_data = message.get("data", {})
            except json.JSONDecodeError:
                await send_error(websocket, "INVALID_JSON", "Invalid JSON message")
                continue
            
            # Handle message types
            if msg_type == WSMessageType.START.value:
                await handle_start_interview(websocket, session.session_id, current_avatar_mode)
                
            elif msg_type == WSMessageType.ANSWER.value:
                await handle_answer(
                    websocket, 
                    session.session_id,
                    msg_data.get("question_id"),
                    msg_data.get("answer_text", ""),
                    current_avatar_mode,
                )
                
            elif msg_type == WSMessageType.PING.value:
                await send_message(websocket, WSMessageType.PONG, {"timestamp": msg_data.get("timestamp")})
                
            elif msg_type == WSMessageType.END.value:
                logger.info(f"Client requested end of session: {session.session_id}")
                break
                
            else:
                await send_error(websocket, "UNKNOWN_TYPE", f"Unknown message type: {msg_type}")
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {session.session_id}")
    except Exception as e:
        logger.error(f"Error in session {session.session_id}: {str(e)}")
        await send_error(websocket, "INTERNAL_ERROR", str(e))
    finally:
        # Cleanup
        question_service.end_session(session.session_id)
        session_manager.delete_session(session.session_id)
        logger.info(f"Session cleaned up: {session.session_id}")


async def handle_start_interview(
    websocket: WebSocket, 
    session_id: str,
    avatar_mode: AvatarMode,
):
    """Handle start interview message."""
    session = session_manager.get_session(session_id)
    if not session:
        await send_error(websocket, "SESSION_NOT_FOUND", "Session not found")
        return
    
    # Update session state
    session_manager.update_session_state(session_id, SessionState.IN_PROGRESS)
    
    # Get first question
    await send_next_question(websocket, session_id, avatar_mode)


async def handle_answer(
    websocket: WebSocket, 
    session_id: str, 
    question_id: Optional[int],
    answer_text: str,
    avatar_mode: AvatarMode,
):
    """Handle user's answer and send next question."""
    session = session_manager.get_session(session_id)
    if not session:
        await send_error(websocket, "SESSION_NOT_FOUND", "Session not found")
        return
    
    if question_id is None:
        await send_error(websocket, "MISSING_QUESTION_ID", "question_id is required")
        return
    
    # Record the answer
    session_manager.record_answer(session_id, question_id, answer_text)
    session_manager.update_session_state(session_id, SessionState.PROCESSING)
    
    logger.info(f"Recorded answer for question {question_id} in session {session_id}")
    
    # Check if interview is complete
    if question_service.is_interview_complete(session_id):
        await handle_interview_complete(websocket, session_id)
    else:
        # Send next question
        await send_next_question(websocket, session_id, avatar_mode, previous_answer=answer_text)


async def send_next_question(
    websocket: WebSocket, 
    session_id: str,
    avatar_mode: AvatarMode,
    previous_answer: Optional[str] = None,
):
    """Generate and send the next question with video or audio."""
    # Get next question from mock service
    question = question_service.get_next_question(session_id, previous_answer)
    
    if question is None:
        await handle_interview_complete(websocket, session_id)
        return
    
    # Update session
    session_manager.set_current_question(session_id, question.id)
    session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Generate audio with TTS (for fallback/audio-only mode)
    logger.info(f"Generating audio for question {question.id}")
    tts_result = await tts_service.generate_speech(question.text)
    
    # Get progress
    current, total = question_service.get_progress(session_id)
    
    # Initialize response variables
    video_url: Optional[str] = None
    idle_video_url: Optional[str] = None
    latency_ms: Optional[float] = None
    actual_avatar_mode = avatar_mode
    
    # Get presenter's idle video (D-ID provides this - no generation needed!)
    idle_video_url = await avatar_service.get_cached_idle_video()
    
    # Generate avatar video if in video mode
    if avatar_mode == AvatarMode.VIDEO:
        logger.info(f"Generating avatar video for question {question.id}")
        # Pass text to D-ID Clips API (uses presenter_id + TTS)
        avatar_result = await avatar_service.generate_avatar_video(text=question.text)
        
        if avatar_result.success and avatar_result.video_url:
            video_url = avatar_result.video_url
            latency_ms = avatar_result.total_time_ms
            logger.info(f"Avatar video ready: {video_url} (latency: {latency_ms:.0f}ms)")
        else:
            # Fallback to audio_only mode
            logger.warning(f"Avatar generation failed, falling back to audio_only: {avatar_result.error_message}")
            actual_avatar_mode = AvatarMode.AUDIO_ONLY
    
    # Use presenter's image for audio-only fallback
    fallback_image = DID_PRESENTER_IMAGE if actual_avatar_mode == AvatarMode.AUDIO_ONLY else None
    
    # Build response
    response = QuestionResponse(
        question_id=question.id,
        question_text=question.text,
        question_type=question.type.value,
        avatar_mode=actual_avatar_mode,
        video_url=video_url,
        idle_video_url=idle_video_url,
        audio_base64=tts_result.audio_base64,
        audio_duration=tts_result.duration,
        word_timings=[
            WordTiming(word=wt.word, start=wt.start, end=wt.end)
            for wt in tts_result.word_timings
        ] if actual_avatar_mode == AvatarMode.AUDIO_ONLY else [],
        avatar_image_url=fallback_image,
        current_question=current,
        total_questions=total,
        latency_ms=latency_ms,
    )
    
    await send_message(websocket, WSMessageType.QUESTION, response.model_dump())
    logger.info(f"Sent question {question.id} to client (mode: {actual_avatar_mode.value})")


async def handle_interview_complete(websocket: WebSocket, session_id: str):
    """Handle interview completion."""
    session_manager.complete_session(session_id)
    summary = session_manager.get_session_summary(session_id)
    
    response = InterviewCompleteResponse(
        message="Congratulations! You have completed the interview.",
        questions_answered=summary["questions_answered"] if summary else 0,
        session_summary=summary,
    )
    
    await send_message(websocket, WSMessageType.COMPLETE, response.model_dump())
    logger.info(f"Interview completed for session {session_id}")


async def send_message(websocket: WebSocket, msg_type: WSMessageType, data: dict):
    """Send a typed message to the client."""
    await websocket.send_json({
        "type": msg_type.value,
        "data": data,
    })


async def send_error(websocket: WebSocket, code: str, message: str):
    """Send an error message to the client."""
    await send_message(websocket, WSMessageType.ERROR, {
        "code": code,
        "message": message,
    })
