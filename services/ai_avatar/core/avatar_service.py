"""
Avatar Video Generation Service using D-ID API (Clips Endpoint).

D-ID creates realistic talking avatar videos using their Clips API.
Free trial: 5 minutes of video generation.

API Documentation: https://docs.d-id.com/reference/clips-overview
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import aiohttp

from ..config import (
    DID_API_KEY,
    DID_API_URL,
    AVATAR_IMAGE_URL,
    AVATAR_GENERATION_TIMEOUT,
    AVATAR_POLL_INTERVAL,
    DID_TTS_VOICE,
    IDLE_VIDEO_TEXT,
)

logger = logging.getLogger(__name__)

# Cache for idle video URL (generated once, reused)
_idle_video_cache: dict[str, str] = {}

# D-ID Presenter IDs (use Clips API presenters)
# Female presenters with professional appearance
# Format: v2_public_{Name}@{ID}
DID_PRESENTER_ID = "v2_public_Amber@0zSz8kflCN"  # Amber - professional female presenter

# D-ID provided idle video for the presenter (no generation needed!)
DID_PRESENTER_IDLE_VIDEO = (
    "https://clips-presenters.d-id.com/v2/Amber/0zSz8kflCN/OUM7xZOuD5/idle.mp4"
)

# D-ID provided image for the presenter (for audio-only fallback)
DID_PRESENTER_IMAGE = (
    "https://clips-presenters.d-id.com/v2/Amber/0zSz8kflCN/OUM7xZOuD5/image.png"
)


class AvatarStatus(str, Enum):
    """Status of avatar video generation."""
    PENDING = "pending"
    CREATED = "created"
    STARTED = "started"
    DONE = "done"
    ERROR = "error"


@dataclass
class AvatarResult:
    """Result from avatar video generation."""
    success: bool
    video_url: Optional[str] = None
    video_base64: Optional[str] = None
    duration: float = 0.0
    error_message: Optional[str] = None
    clip_id: Optional[str] = None
    # Latency metrics
    creation_time_ms: float = 0.0  # Time to create clip request
    generation_time_ms: float = 0.0  # Time to generate video
    total_time_ms: float = 0.0  # Total time from start to finish


class AvatarMode(str, Enum):
    """Mode of avatar generation."""
    VIDEO = "video"
    AUDIO_ONLY = "audio_only"


class AvatarService:
    """
    Service for generating talking avatar videos using D-ID Clips API.
    
    Flow:
    1. Create a "clip" with presenter_id + text
    2. Poll for completion
    3. Return video URL or base64
    
    Uses the /clips endpoint which works with D-ID's hosted presenters.
    """

    def __init__(self, api_key: Optional[str] = None, presenter_id: Optional[str] = None):
        """
        Initialize the avatar service.
        
        Args:
            api_key: D-ID API key. If not provided, uses environment variable.
            presenter_id: D-ID presenter ID. Uses default female presenter if not provided.
        """
        self.api_key = api_key or DID_API_KEY
        self.api_url = DID_API_URL
        self.presenter_id = presenter_id or DID_PRESENTER_ID
        self.avatar_image_url = AVATAR_IMAGE_URL  # Fallback for audio-only mode
        self._session: Optional[aiohttp.ClientSession] = None
        self._idle_video_url: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        """Check if the service is properly configured with API key."""
        return bool(self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Basic {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_presenters(self) -> list[dict]:
        """Get list of available D-ID presenters."""
        if not self.is_configured:
            return []
        
        try:
            session = await self._get_session()
            async with session.get(f"{self.api_url}/clips/presenters") as response:
                if response.status == 200:
                    data = await response.json()
                    presenters = data.get("presenters", [])
                    logger.info(f"Found {len(presenters)} D-ID presenters")
                    return presenters
                else:
                    error = await response.text()
                    logger.error(f"Failed to get presenters: {response.status} - {error}")
                    return []
        except Exception as e:
            logger.error(f"Error getting presenters: {e}")
            return []

    async def generate_avatar_video(
        self,
        text: str,
        presenter_id: Optional[str] = None,
    ) -> AvatarResult:
        """
        Generate a talking avatar video from text using D-ID Clips API.
        
        Uses D-ID's built-in TTS to generate speech from text.
        
        Args:
            text: The text for the avatar to speak
            presenter_id: D-ID presenter ID (uses default if not provided)
            
        Returns:
            AvatarResult with video URL or error
        """
        total_start = time.perf_counter()
        
        if not self.is_configured:
            return AvatarResult(
                success=False,
                error_message="D-ID API key not configured. Set DID_API_KEY environment variable.",
            )

        presenter = presenter_id or self.presenter_id
        
        try:
            # Step 1: Create the clip with D-ID's TTS
            create_start = time.perf_counter()
            clip_id = await self._create_clip(text, presenter)
            creation_time_ms = (time.perf_counter() - create_start) * 1000
            
            if not clip_id:
                return AvatarResult(
                    success=False,
                    error_message="Failed to create clip request",
                    creation_time_ms=creation_time_ms,
                )

            logger.info(f"Created D-ID clip: {clip_id} (creation: {creation_time_ms:.0f}ms)")

            # Step 2: Poll for completion
            poll_start = time.perf_counter()
            result = await self._poll_for_clip_result(clip_id)
            generation_time_ms = (time.perf_counter() - poll_start) * 1000
            total_time_ms = (time.perf_counter() - total_start) * 1000
            
            # Add latency metrics to result
            result.creation_time_ms = creation_time_ms
            result.generation_time_ms = generation_time_ms
            result.total_time_ms = total_time_ms
            
            logger.info(f"D-ID avatar latency: creation={creation_time_ms:.0f}ms, "
                       f"generation={generation_time_ms:.0f}ms, total={total_time_ms:.0f}ms")
            
            return result

        except asyncio.TimeoutError:
            total_time_ms = (time.perf_counter() - total_start) * 1000
            return AvatarResult(
                success=False,
                error_message="Avatar generation timed out",
                total_time_ms=total_time_ms,
            )
        except Exception as e:
            total_time_ms = (time.perf_counter() - total_start) * 1000
            logger.error(f"Avatar generation error: {str(e)}")
            return AvatarResult(
                success=False,
                error_message=str(e),
                total_time_ms=total_time_ms,
            )

    async def _create_clip(
        self,
        text: str,
        presenter_id: str,
    ) -> Optional[str]:
        """Create a clip request with D-ID Clips API."""
        session = await self._get_session()
        
        # D-ID /clips endpoint with presenter_id and text input
        # Uses D-ID's hosted presenters for reliable video generation
        payload = {
            "presenter_id": presenter_id,
            "script": {
                "type": "text",
                "input": text,
                "provider": {
                    "type": "microsoft",
                    "voice_id": DID_TTS_VOICE,  # Professional female voice
                }
            },
            "config": {
                "result_format": "mp4",
            },
        }

        logger.info(f"Creating D-ID clip with presenter={presenter_id}, voice={DID_TTS_VOICE}, "
                   f"text: '{text[:50]}...'")
        
        try:
            async with session.post(
                f"{self.api_url}/clips",
                json=payload,
            ) as response:
                response_text = await response.text()
                logger.info(f"D-ID Clips API response status: {response.status}")
                
                if response.status in (200, 201):
                    import json
                    data = json.loads(response_text)
                    clip_id = data.get("id")
                    logger.info(f"D-ID clip created successfully: {clip_id}")
                    return clip_id
                else:
                    logger.error(f"D-ID Clips API error: {response.status} - {response_text[:500]}")
                    return None
        except Exception as e:
            logger.error(f"D-ID Clips API request failed: {str(e)}")
            return None

    async def _poll_for_clip_result(self, clip_id: str) -> AvatarResult:
        """Poll D-ID Clips API until video is ready."""
        session = await self._get_session()
        
        timeout = AVATAR_GENERATION_TIMEOUT
        elapsed = 0
        
        while elapsed < timeout:
            async with session.get(f"{self.api_url}/clips/{clip_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    status = data.get("status", "")
                    
                    if status == "done":
                        video_url = data.get("result_url")
                        duration = data.get("duration", 0)
                        
                        logger.info(f"Avatar video ready: {video_url}")
                        
                        return AvatarResult(
                            success=True,
                            video_url=video_url,
                            duration=duration,
                            clip_id=clip_id,
                        )
                    
                    elif status == "error":
                        error = data.get("error", {})
                        error_msg = error.get("description", "Unknown error") if isinstance(error, dict) else str(error)
                        return AvatarResult(
                            success=False,
                            error_message=error_msg,
                            clip_id=clip_id,
                        )
                    
                    # Still processing
                    logger.debug(f"Clip {clip_id} status: {status}")
                
                else:
                    error_text = await response.text()
                    logger.error(f"Poll error: {response.status} - {error_text}")

            await asyncio.sleep(AVATAR_POLL_INTERVAL)
            elapsed += AVATAR_POLL_INTERVAL

        return AvatarResult(
            success=False,
            error_message=f"Timeout after {timeout} seconds",
            clip_id=clip_id,
        )

    async def generate_idle_video(
        self,
        presenter_id: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> AvatarResult:
        """
        Generate a short idle/nodding video for smoother UX.
        
        Creates a short loop of the avatar with minimal movement
        that can be played while waiting for the next question.
        
        The result is cached after first generation.
        
        Args:
            presenter_id: D-ID presenter ID (uses default if not provided)
            force_regenerate: If True, regenerate even if cached
            
        Returns:
            AvatarResult with idle video URL
        """
        global _idle_video_cache
        
        presenter = presenter_id or self.presenter_id
        cache_key = f"idle_{presenter}"
        
        # Return cached idle video if available
        if not force_regenerate and cache_key in _idle_video_cache:
            logger.info("Using cached idle video")
            return AvatarResult(
                success=True,
                video_url=_idle_video_cache[cache_key],
            )
        
        if not self.is_configured:
            return AvatarResult(
                success=False,
                error_message="D-ID API key not configured",
            )
        
        # Generate short idle animation with minimal text
        # D-ID will create subtle lip movement and natural blinking
        idle_text = IDLE_VIDEO_TEXT
        
        logger.info("Generating idle video for avatar...")
        start_time = time.perf_counter()
        
        result = await self.generate_avatar_video(text=idle_text, presenter_id=presenter)
        
        if result.success and result.video_url:
            # Cache the idle video URL
            _idle_video_cache[cache_key] = result.video_url
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.info(f"Idle video generated and cached ({elapsed:.0f}ms): {result.video_url}")
        
        return result
    
    async def get_cached_idle_video(self, presenter_id: Optional[str] = None) -> Optional[str]:
        """Get cached idle video URL if available."""
        presenter = presenter_id or self.presenter_id
        cache_key = f"idle_{presenter}"
        
        # First check cache
        if cache_key in _idle_video_cache:
            return _idle_video_cache[cache_key]
        
        # Use D-ID's built-in idle video for the default presenter (no generation needed!)
        if presenter == DID_PRESENTER_ID:
            return DID_PRESENTER_IDLE_VIDEO
        
        return None
    
    def get_presenter_image(self, presenter_id: Optional[str] = None) -> str:
        """Get the presenter's image URL for audio-only fallback."""
        presenter = presenter_id or self.presenter_id
        
        # Use D-ID's built-in image for the default presenter
        if presenter == DID_PRESENTER_ID:
            return DID_PRESENTER_IMAGE
        
        return self.avatar_image_url

    async def download_video_base64(self, video_url: str) -> Optional[str]:
        """Download video from URL and return as base64."""
        try:
            session = await self._get_session()
            async with session.get(video_url) as response:
                if response.status == 200:
                    video_bytes = await response.read()
                    return base64.b64encode(video_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
        return None

    async def get_credits_info(self) -> dict:
        """Get remaining credits information."""
        if not self.is_configured:
            return {"error": "API key not configured"}
        
        try:
            session = await self._get_session()
            # Try the /credits endpoint first
            async with session.get(f"{self.api_url}/credits") as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 403:
                    # Credits endpoint may not be available on all plans
                    # Return a message instead of error
                    return {"message": "Credits info not available (API limitation)", "status": "active"}
                else:
                    return {"error": f"API error: {response.status}"}
        except Exception as e:
            return {"error": str(e)}
