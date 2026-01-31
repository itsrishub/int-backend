"""Configuration settings for AI Avatar Service."""

import os
from pathlib import Path

# Service settings
SERVICE_NAME = "ai-avatar-service"
API_VERSION = "v1"
DEBUG = True

# Audio settings
AUDIO_OUTPUT_DIR = Path("./temp_audio")
AUDIO_FORMAT = "mp3"

# Edge-TTS Voice settings (for audio-only fallback)
# Using a professional female voice that matches the avatar
TTS_VOICE = "en-US-JennyNeural"  # Professional female voice
TTS_RATE = "+0%"  # Normal speaking rate
TTS_VOLUME = "+0%"  # Normal volume
TTS_PITCH = "+0Hz"  # Normal pitch

# Alternative voices (can be configured):
# - en-US-AriaNeural (Female, professional)
# - en-US-DavisNeural (Male, calm/authoritative)
# - en-GB-RyanNeural (British male, professional)
# - en-US-GuyNeural (Male, friendly)

# D-ID TTS Voice (used when D-ID generates video)
DID_TTS_VOICE = "en-US-JennyNeural"  # Must match avatar appearance

# WebSocket settings
WS_HEARTBEAT_INTERVAL = 30  # seconds

# Interview settings
MAX_QUESTIONS_PER_SESSION = 10
SESSION_TIMEOUT = 1800  # 30 minutes

# =============================================================================
# D-ID Avatar Service Settings
# =============================================================================

# D-ID API Configuration
# Get your API key from: https://studio.d-id.com/account
# Set the environment variable: export DID_API_KEY="your_api_key_here"
DID_API_KEY = os.getenv("DID_API_KEY", "")
DID_API_URL = "https://api.d-id.com"

# D-ID Presenter Configuration
# Using D-ID's hosted presenter images with professional framing
# Available presenters: Noelle_f, Amy-jcwCkr1grs, Lisa-Dqjoi0Gg9N, etc.
# See: https://docs.d-id.com/docs/v2-avatars-quickstart
AVATAR_IMAGE_URL = os.getenv(
    "AVATAR_IMAGE_URL",
    # D-ID Default Presenter - Amy (professional female, better framing)
    # Has more professional interview-style positioning
    "https://create-images-results.d-id.com/DefaultPresenters/Amy-jcwCkr1grs/image.png"
)

# Avatar generation settings
AVATAR_GENERATION_TIMEOUT = 120  # seconds (max wait for video generation)
AVATAR_POLL_INTERVAL = 2  # seconds between status checks

# Avatar mode: "video" (D-ID) or "audio_only" (fallback)
# Set to "audio_only" if D-ID credits are exhausted
AVATAR_MODE = os.getenv("AVATAR_MODE", "video")

# Idle video settings (looping nodding/blinking video for smoother UX)
# This will be generated once per session and cached
IDLE_VIDEO_DURATION = 5  # seconds - short loop for idle state
IDLE_VIDEO_TEXT = "..."  # Minimal text to generate idle animation

# =============================================================================
# Fallback Settings (when D-ID is unavailable)
# =============================================================================

# Static avatar image for audio-only mode
STATIC_AVATAR_URL = os.getenv(
    "STATIC_AVATAR_URL",
    AVATAR_IMAGE_URL  # Same as the D-ID avatar image
)

# Cached idle video URL (generated on first use, cached for reuse)
IDLE_VIDEO_CACHE_URL: str | None = None
