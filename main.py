"""
InterviewAI Backend Services - Main Entry Point

This is the main entry point for running backend services.
Combines database initialization, user endpoints, and AI Avatar service.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Try to import database module (may not exist in all setups)
try:
    from app.database import init_db
    HAS_DATABASE = True
except ImportError:
    HAS_DATABASE = False

# Import routers
try:
    from app.endpoints import signup_router, profile_router
    HAS_ENDPOINTS = True
except ImportError:
    HAS_ENDPOINTS = False

# Import AI Avatar service
from app.services.ai_avatar.api import router as avatar_router
from app.services.ai_avatar.config import API_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Initialize database on startup if available
    if HAS_DATABASE:
        init_db()
    yield


# Create FastAPI application
app = FastAPI(
    title="InterviewAI Backend",
    description="Backend services for InterviewAI application",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
# Note: allow_origins=["*"] and allow_credentials=True cannot be used together
# For production, specify exact origins or use allow_origin_regex
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False when using wildcard origins
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers in response
)

# Include routers
if HAS_ENDPOINTS:
    app.include_router(signup_router)
    app.include_router(profile_router)

# Include AI Avatar service router
app.include_router(avatar_router)


@app.get("/")
def read_root():
    """Root endpoint."""
    return {
        "message": "Hello from Interview AI API",
        "services": {
            "ai_avatar": f"/api/{API_VERSION}/avatar",
            "docs": "/docs",
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("  InterviewAI Backend Services")
    print("  Starting all services...")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
