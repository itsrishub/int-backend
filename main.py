"""
InterviewAI Backend Services - Main Entry Point

This is the main entry point for running backend services.
For development, you can run individual services directly.
"""

import uvicorn

# Import the AI Avatar service app
from services.ai_avatar.main import app


if __name__ == "__main__":
    print("=" * 60)
    print("  InterviewAI Backend Services")
    print("  Starting AI Avatar Service...")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
