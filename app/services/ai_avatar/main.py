"""
AI Avatar Service - Main Entry Point

This service provides AI-powered avatar functionality for the InterviewAI application.
It generates speech audio with word-level timing for lip-sync animations.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import SERVICE_NAME, API_VERSION, AUDIO_OUTPUT_DIR, DEBUG
from .api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup: Create temp audio directory if needed
    AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🚀 {SERVICE_NAME} v{API_VERSION} starting...")
    print(f"📁 Audio output directory: {AUDIO_OUTPUT_DIR.absolute()}")
    
    yield
    
    # Shutdown: Cleanup
    print(f"👋 {SERVICE_NAME} shutting down...")


# Create FastAPI application
app = FastAPI(
    title="AI Avatar Service",
    description="""
    AI Avatar Service for InterviewAI application.
    
    ## Features
    - Text-to-Speech with professional interviewer voice
    - Word-level timing for lip-sync animations
    - WebSocket-based real-time interview sessions
    - Mock question service for MVP testing
    
    ## WebSocket Protocol
    Connect to `/api/v1/interview/session` for interview sessions.
    
    ### Client Messages:
    - `{"type": "start"}` - Start the interview
    - `{"type": "answer", "data": {"question_id": 1, "answer_text": "..."}}` - Submit answer
    - `{"type": "ping", "data": {"timestamp": 123}}` - Keep-alive ping
    - `{"type": "end"}` - End session
    
    ### Server Messages:
    - `{"type": "session_info", "data": {...}}` - Session created
    - `{"type": "question", "data": {...}}` - Question with audio
    - `{"type": "complete", "data": {...}}` - Interview complete
    - `{"type": "error", "data": {...}}` - Error occurred
    """,
    version=API_VERSION,
    lifespan=lifespan,
    debug=DEBUG,
)

# Configure CORS for frontend access
# Note: allow_origins=["*"] and allow_credentials=True cannot be used together
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False when using wildcard origins
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers in response
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": SERVICE_NAME,
        "version": API_VERSION,
        "status": "running",
        "docs": "/docs",
        "websocket": f"/api/{API_VERSION}/interview/session",
    }


# For running directly with: python -m services.ai_avatar.main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "services.ai_avatar.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
