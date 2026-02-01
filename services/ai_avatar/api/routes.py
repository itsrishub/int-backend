"""API routes for AI Avatar Service."""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
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
from ..core.question_service import QuestionService, InterviewQuestion
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
question_service = QuestionService()  # Real API integration
avatar_service = AvatarService()

# ============================================================================
# Video Generation Cache (for async polling)
# ============================================================================
# Stores: {generation_id: {status, video_url, error, started_at, question_data}}
video_generation_cache: dict[str, dict] = {}


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
# Async Video Generation (Polling Pattern for Render)
# ============================================================================

async def generate_video_background(generation_id: str, text: str):
    """Background task to generate video and update cache."""
    try:
        logger.info(f"Background video generation started: {generation_id}")
        video_generation_cache[generation_id]["status"] = "processing"
        
        # Generate avatar video
        avatar_result = await avatar_service.generate_avatar_video(text=text)
        
        if avatar_result.success and avatar_result.video_url:
            video_generation_cache[generation_id].update({
                "status": "completed",
                "video_url": avatar_result.video_url,
                "latency_ms": avatar_result.total_time_ms,
                "completed_at": time.time(),
            })
            logger.info(f"Background video completed: {generation_id} -> {avatar_result.video_url}")
        else:
            video_generation_cache[generation_id].update({
                "status": "failed",
                "error": avatar_result.error_message or "Video generation failed",
                "completed_at": time.time(),
            })
            logger.warning(f"Background video failed: {generation_id} -> {avatar_result.error_message}")
    except Exception as e:
        video_generation_cache[generation_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": time.time(),
        })
        logger.error(f"Background video error: {generation_id} -> {e}")


@router.post("/interview/{session_id}/question/generate")
async def start_question_generation(session_id: str, background_tasks: BackgroundTasks):
    """
    Start generating the next question with avatar video (async).
    
    Returns immediately with:
    - generation_id: Use to poll for status
    - question data with audio (ready immediately)
    - video_status: "generating"
    
    Client should poll /question/status/{generation_id} for video.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if interview is complete
    if question_service.is_interview_complete(session_id):
        return await get_interview_complete_response(session_id)
    
    # Get next question from real API (async)
    question = await question_service.get_next_question(session_id)
    if question is None:
        return await get_interview_complete_response(session_id)
    
    # Update session
    session_manager.set_current_question(session_id, question.id)
    session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Generate audio immediately (fast - ~1-2 seconds)
    logger.info(f"Generating audio for question {question.id}")
    tts_result = await tts_service.generate_speech(question.text)
    
    # Get progress
    current, total = question_service.get_progress(session_id)
    
    # Get idle video URL
    idle_video_url = await avatar_service.get_cached_idle_video()
    
    # Create generation ID for video polling
    generation_id = f"gen_{uuid.uuid4().hex[:12]}"
    
    # Determine if we should generate video
    should_generate_video = avatar_service.is_configured
    
    if should_generate_video:
        # Store in cache and start background generation
        video_generation_cache[generation_id] = {
            "status": "pending",
            "session_id": session_id,
            "question_id": question.id,
            "started_at": time.time(),
            "video_url": None,
            "error": None,
        }
        
        # Start background video generation
        background_tasks.add_task(generate_video_background, generation_id, question.text)
        video_status = "generating"
    else:
        video_status = "disabled"
    
    return {
        "type": "question",
        "generation_id": generation_id if should_generate_video else None,
        "video_status": video_status,
        "question_id": question.id,
        "question_text": question.text,
        "question_type": question.type.value,
        "avatar_mode": "video" if should_generate_video else "audio_only",
        "video_url": None,  # Will be available via polling
        "idle_video_url": idle_video_url,
        "audio_base64": tts_result.audio_base64,
        "audio_duration": tts_result.duration,
        "word_timings": [
            {"word": wt.word, "start": wt.start, "end": wt.end}
            for wt in tts_result.word_timings
        ],
        "avatar_image_url": DID_PRESENTER_IMAGE,
        "current_question": current,
        "total_questions": total,
    }


@router.get("/interview/video/status/{generation_id}")
async def get_video_status(generation_id: str):
    """
    Poll for video generation status.
    
    Returns:
    - status: "pending" | "processing" | "completed" | "failed"
    - video_url: Available when status is "completed"
    - error: Available when status is "failed"
    - elapsed_seconds: Time since generation started
    """
    if generation_id not in video_generation_cache:
        raise HTTPException(status_code=404, detail="Generation not found")
    
    cache_entry = video_generation_cache[generation_id]
    elapsed = time.time() - cache_entry["started_at"]
    
    response = {
        "generation_id": generation_id,
        "status": cache_entry["status"],
        "elapsed_seconds": round(elapsed, 1),
        "video_url": cache_entry.get("video_url"),
        "error": cache_entry.get("error"),
        "latency_ms": cache_entry.get("latency_ms"),
    }
    
    # Add estimated time remaining for pending/processing
    if cache_entry["status"] in ("pending", "processing"):
        # D-ID typically takes 60-90 seconds
        estimated_remaining = max(0, 75 - elapsed)
        response["estimated_remaining_seconds"] = round(estimated_remaining, 0)
    
    return response


@router.post("/interview/{session_id}/answer/async")
async def submit_answer_async(session_id: str, answer: dict, background_tasks: BackgroundTasks):
    """
    Submit answer and start generating next question (async).
    
    Same as /answer but returns immediately with generation_id.
    Client should poll for video status.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    question_id = answer.get("question_id")
    answer_text = answer.get("answer_text", "")
    
    if question_id is None:
        raise HTTPException(status_code=400, detail="question_id is required")
    
    # Submit answer to real API
    success = await question_service.submit_answer(session_id, question_id, answer_text)
    if not success:
        logger.warning(f"Failed to submit answer for question {question_id}")
        raise HTTPException(status_code=500, detail="Failed to submit answer to question service")
    
    # Record the answer locally
    session_manager.record_answer(session_id, question_id, answer_text)
    session_manager.update_session_state(session_id, SessionState.PROCESSING)
    
    logger.info(f"Async: Recorded answer for question {question_id}")
    
    # Check if interview is complete
    if question_service.is_interview_complete(session_id):
        return await get_interview_complete_response(session_id)
    
    # Get next question from real API (async)
    question = await question_service.get_next_question(session_id, previous_answer=answer_text)
    if question is None:
        return await get_interview_complete_response(session_id)
    
    # Update session
    session_manager.set_current_question(session_id, question.id)
    session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Generate audio immediately (fast - ~1-2 seconds)
    logger.info(f"Generating audio for question {question.id}")
    tts_result = await tts_service.generate_speech(question.text)
    
    # Get progress
    current, total = question_service.get_progress(session_id)
    
    # Get idle video URL
    idle_video_url = await avatar_service.get_cached_idle_video()
    
    # Create generation ID for video polling
    generation_id = f"gen_{uuid.uuid4().hex[:12]}"
    
    # Determine if we should generate video
    should_generate_video = avatar_service.is_configured
    
    if should_generate_video:
        # Store in cache and start background generation
        video_generation_cache[generation_id] = {
            "status": "pending",
            "session_id": session_id,
            "question_id": question.id,
            "started_at": time.time(),
            "video_url": None,
            "error": None,
        }
        
        # Start background video generation
        background_tasks.add_task(generate_video_background, generation_id, question.text)
        video_status = "generating"
    else:
        video_status = "disabled"
    
    return {
        "type": "question",
        "generation_id": generation_id if should_generate_video else None,
        "video_status": video_status,
        "question_id": question.id,
        "question_text": question.text,
        "question_type": question.type.value,
        "avatar_mode": "video" if should_generate_video else "audio_only",
        "video_url": None,  # Will be available via polling
        "idle_video_url": idle_video_url,
        "audio_base64": tts_result.audio_base64,
        "audio_duration": tts_result.duration,
        # Note: word_timings removed from submit answer response
        "avatar_image_url": DID_PRESENTER_IMAGE,
        "current_question": current,
        "total_questions": total,
    }


# ============================================================================
# HTTP Interview Session (REST API - Render Compatible)
# ============================================================================

@router.post("/interview/start")
async def start_interview(request_data: Optional[dict] = None, background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Start a new interview session and get the first question.
    
    This endpoint combines session creation and first question generation.
    Returns session_id and first question with avatar video/audio.
    
    Optional request body:
    {
        "user_id": "user_123",
        "start_time": "2026-01-31T19:00:00",
        "resume_blob": "",
        "role": "",
        "company": "",
        "experience": 0,
        "job_description": ""
    }
    """
    # Create a new internal session
    session = session_manager.create_session()
    
    # Extract request data or use defaults
    if request_data is None:
        request_data = {}
    
    user_id = request_data.get("user_id", "default_user")
    start_time = request_data.get("start_time")
    resume_blob = request_data.get("resume_blob", "")
    role = request_data.get("role", "")
    company = request_data.get("company", "")
    experience = request_data.get("experience", 0)
    job_description = request_data.get("job_description", "")
    
    # Start session with real API
    try:
        session_info = await question_service.start_session(
            session_id=session.session_id,
            user_id=user_id,
            start_time=start_time,
            resume_blob=resume_blob,
            role=role,
            company=company,
            experience=experience,
            job_description=job_description
        )
        logger.info(f"Started interview session: {session.session_id} -> real_session_id={session_info.session_id}")
    except Exception as e:
        logger.error(f"Failed to start interview session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start interview: {str(e)}")
    
    # Update session state
    session_manager.update_session_state(session.session_id, SessionState.IN_PROGRESS)
    
    # Get first question from real API
    question = await question_service.get_next_question(session.session_id)
    if question is None:
        raise HTTPException(status_code=500, detail="Failed to get first question")
    
    # Update session
    session_manager.set_current_question(session.session_id, question.id)
    session_manager.update_session_state(session.session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Generate audio immediately (fast - ~1-2 seconds)
    logger.info(f"Generating audio for question {question.id}")
    tts_result = await tts_service.generate_speech(question.text)
    
    # Get progress
    current, total = question_service.get_progress(session.session_id)
    
    # Get idle video URL
    idle_video_url = await avatar_service.get_cached_idle_video()
    
    # Create generation ID for video polling
    generation_id = f"gen_{uuid.uuid4().hex[:12]}"
    
    # Determine if we should generate video
    should_generate_video = avatar_service.is_configured
    current_avatar_mode = "video" if should_generate_video else "audio_only"
    
    if should_generate_video:
        # Store in cache and start background generation
        video_generation_cache[generation_id] = {
            "status": "pending",
            "session_id": session.session_id,
            "question_id": question.id,
            "started_at": time.time(),
            "video_url": None,
            "error": None,
        }
        
        # Start background video generation
        background_tasks.add_task(generate_video_background, generation_id, question.text)
        video_status = "generating"
    else:
        video_status = "disabled"
    
    logger.info(f"New HTTP interview session: {session.session_id} (avatar_mode: {current_avatar_mode})")
    
    return {
        "session_id": session.session_id,
        "state": "in_progress",
        "type": "question",
        "generation_id": generation_id if should_generate_video else None,
        "video_status": video_status,
        "question_id": question.id,
        "question_text": question.text,
        "question_type": question.type.value,
        "avatar_mode": current_avatar_mode,
        "video_url": None,  # Will be available via polling
        "idle_video_url": idle_video_url,
        "audio_base64": tts_result.audio_base64,
        "audio_duration": tts_result.duration,
        # "word_timings": [
        #     {"word": wt.word, "start": wt.start, "end": wt.end}
        #     for wt in tts_result.word_timings
        # ],
        "avatar_image_url": DID_PRESENTER_IMAGE,
        "current_question": current,
        "total_questions": total,
    }


@router.get("/interview/{session_id}/question")
async def get_next_question_http(session_id: str):
    """
    Get the next question for the interview session.
    
    First call returns question 1. After submitting an answer,
    call this again to get the next question.
    
    Returns question with avatar video (or audio fallback).
    Note: Video generation takes 30-90 seconds.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if interview is already complete
    if question_service.is_interview_complete(session_id):
        return await get_interview_complete_response(session_id)
    
    # Get next question from real API (async)
    question = await question_service.get_next_question(session_id)
    if question is None:
        return await get_interview_complete_response(session_id)
    
    # Update session
    session_manager.set_current_question(session_id, question.id)
    session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Get avatar mode
    avatar_mode = AvatarMode.VIDEO if avatar_service.is_configured else AvatarMode.AUDIO_ONLY
    
    # Generate question response (without word_timings for submit answer)
    return await generate_question_response(session_id, avatar_mode, question=question, include_word_timings=False)


@router.post("/interview/{session_id}/answer")
async def submit_answer_http(session_id: str, answer: dict):
    """
    Submit an answer to the current question.
    
    Request body:
    {
        "question_id": 1,
        "answer_text": "My answer..."
    }
    
    Returns the next question or completion message.
    Note: Video generation takes 30-90 seconds.
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    question_id = answer.get("question_id")
    answer_text = answer.get("answer_text", "")
    
    if question_id is None:
        raise HTTPException(status_code=400, detail="question_id is required")
    
    # Submit answer to real API
    success = await question_service.submit_answer(session_id, question_id, answer_text)
    if not success:
        logger.warning(f"Failed to submit answer for question {question_id}")
        raise HTTPException(status_code=500, detail="Failed to submit answer to question service")
    
    # Record the answer locally
    session_manager.record_answer(session_id, question_id, answer_text)
    session_manager.update_session_state(session_id, SessionState.PROCESSING)
    
    logger.info(f"HTTP: Recorded answer for question {question_id} in session {session_id}")
    
    # Check if interview is complete
    if question_service.is_interview_complete(session_id):
        return await get_interview_complete_response(session_id)
    
    # Get next question from real API (async)
    question = await question_service.get_next_question(session_id, previous_answer=answer_text)
    if question is None:
        return await get_interview_complete_response(session_id)
    
    # Update session
    session_manager.set_current_question(session_id, question.id)
    session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Get avatar mode
    avatar_mode = AvatarMode.VIDEO if avatar_service.is_configured else AvatarMode.AUDIO_ONLY
    
    # Generate next question response (without word_timings)
    return await generate_question_response(session_id, avatar_mode, question=question, include_word_timings=False)


@router.get("/interview/{session_id}/status")
async def get_session_status(session_id: str):
    """Get the current status of an interview session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    current, total = question_service.get_progress(session_id)
    is_complete = question_service.is_interview_complete(session_id)
    
    return {
        "session_id": session_id,
        "state": session.state.value,
        "current_question": current,
        "total_questions": total,
        "is_complete": is_complete,
        "answers_recorded": len(session.answers) if hasattr(session, 'answers') else 0,
    }


@router.post("/interview/{session_id}")
async def end_interview(session_id: str, request_data: Optional[dict] = None):
    """
    End an interview session and cleanup resources.
    
    Optional request body:
    {
        "end_time": "2026-01-31T20:00:00"  # ISO 8601 format, defaults to current time
    }
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Extract end_time from request or use current time
    end_time = None
    if request_data:
        end_time = request_data.get("end_time")
    
    # Get summary before cleanup
    summary = session_manager.get_session_summary(session_id)
    
    # End session with real API (pass end_time)
    feedback = await question_service.end_session(session_id, end_time=end_time)
    
    # Cleanup local session
    session_manager.delete_session(session_id)
    
    logger.info(f"HTTP: Session ended: {session_id}")
    
    return {
        "message": "Session ended successfully",
        "session_id": session_id,
        "summary": summary,
        "feedback": feedback,  # Include feedback from real API
    }


async def generate_question_response(
    session_id: str,
    avatar_mode: AvatarMode,
    previous_answer: Optional[str] = None,
    question: Optional[InterviewQuestion] = None,
    include_word_timings: bool = True,
) -> dict:
    """
    Generate a question response with avatar video or audio.
    
    Args:
        include_word_timings: Whether to include word_timings in response (default: True)
    """
    # Get next question if not provided
    if question is None:
        question = await question_service.get_next_question(session_id, previous_answer=previous_answer)
        if question is None:
            return await get_interview_complete_response(session_id)
        
        # Update session
        session_manager.set_current_question(session_id, question.id)
        session_manager.update_session_state(session_id, SessionState.WAITING_FOR_ANSWER)
    
    # Generate audio with TTS (for fallback/audio-only mode)
    logger.info(f"HTTP: Generating audio for question {question.id}")
    tts_result = await tts_service.generate_speech(question.text)
    
    # Get progress
    current, total = question_service.get_progress(session_id)
    
    # Initialize response variables
    video_url: Optional[str] = None
    latency_ms: Optional[float] = None
    actual_avatar_mode = avatar_mode
    
    # Get presenter's idle video
    idle_video_url = await avatar_service.get_cached_idle_video()
    
    # Generate avatar video if in video mode
    if avatar_mode == AvatarMode.VIDEO:
        logger.info(f"HTTP: Generating avatar video for question {question.id}")
        avatar_result = await avatar_service.generate_avatar_video(text=question.text)
        
        if avatar_result.success and avatar_result.video_url:
            video_url = avatar_result.video_url
            latency_ms = avatar_result.total_time_ms
            logger.info(f"HTTP: Avatar video ready: {video_url} (latency: {latency_ms:.0f}ms)")
        else:
            logger.warning(f"HTTP: Avatar generation failed: {avatar_result.error_message}")
            actual_avatar_mode = AvatarMode.AUDIO_ONLY
    
    # Use presenter's image for audio-only fallback
    fallback_image = DID_PRESENTER_IMAGE if actual_avatar_mode == AvatarMode.AUDIO_ONLY else None
    
    response = {
        "type": "question",
        "question_id": question.id,
        "question_text": question.text,
        "question_type": question.type.value,
        "avatar_mode": actual_avatar_mode.value,
        "video_url": video_url,
        "idle_video_url": idle_video_url,
        "audio_base64": tts_result.audio_base64,
        "audio_duration": tts_result.duration,
        "avatar_image_url": fallback_image,
        "current_question": current,
        "total_questions": total,
        "latency_ms": latency_ms,
    }
    
    # Only include word_timings if requested
    if include_word_timings:
        response["word_timings"] = [
            {"word": wt.word, "start": wt.start, "end": wt.end}
            for wt in tts_result.word_timings
        ] if actual_avatar_mode == AvatarMode.AUDIO_ONLY else []
    
    return response


async def get_interview_complete_response(session_id: str) -> dict:
    """Generate interview completion response."""
    session_manager.complete_session(session_id)
    summary = session_manager.get_session_summary(session_id)
    
    return {
        "type": "complete",
        "message": "Congratulations! You have completed the interview.",
        "questions_answered": summary["questions_answered"] if summary else 0,
        "session_summary": summary,
    }


# ============================================================================
# WebSocket Interview Session (for local testing)
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
