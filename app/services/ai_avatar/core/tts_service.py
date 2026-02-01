"""Text-to-Speech service using Edge-TTS."""

import asyncio
import base64
import io
import json
import re
from dataclasses import dataclass
from typing import Optional

import edge_tts

from ..config import TTS_VOICE, TTS_RATE, TTS_VOLUME, TTS_PITCH


@dataclass
class WordTiming:
    """Timing information for a single word."""
    word: str
    start: float  # seconds
    end: float  # seconds


@dataclass
class TTSResult:
    """Result from TTS generation."""
    audio_base64: str
    audio_bytes: bytes
    word_timings: list[WordTiming]
    duration: float  # total duration in seconds


class TTSService:
    """Service for generating speech from text using Edge-TTS."""

    # Average speaking rate: ~150 words per minute = 0.4 seconds per word
    AVG_WORD_DURATION = 0.35  # seconds per word (slightly faster for natural speech)
    
    def __init__(
        self,
        voice: str = TTS_VOICE,
        rate: str = TTS_RATE,
        volume: str = TTS_VOLUME,
        pitch: str = TTS_PITCH,
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch

    async def generate_speech(self, text: str) -> TTSResult:
        """
        Generate speech audio from text with word-level timing.
        
        Args:
            text: The text to convert to speech
            
        Returns:
            TTSResult with audio data and word timings
        """
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
        )

        audio_chunks: list[bytes] = []
        sentence_duration: float = 0.0
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                # Edge-TTS provides timing in 100-nanosecond units
                # Convert to seconds
                offset_seconds = chunk["offset"] / 10_000_000
                duration_seconds = chunk["duration"] / 10_000_000
                sentence_duration = offset_seconds + duration_seconds
            elif chunk["type"] == "WordBoundary":
                # Keep support for WordBoundary if edge-tts re-adds it
                pass

        # Combine all audio chunks
        audio_bytes = b"".join(audio_chunks)
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Calculate duration from audio (MP3 at ~32kbps = ~4000 bytes per second)
        # This is a rough estimate; actual duration from sentence boundary is better
        if sentence_duration > 0:
            total_duration = sentence_duration
        else:
            # Fallback: estimate from audio size (MP3 ~128kbps = 16000 bytes/sec)
            total_duration = len(audio_bytes) / 16000

        # Generate estimated word timings for lip-sync
        word_timings = self._estimate_word_timings(text, total_duration)

        return TTSResult(
            audio_base64=audio_base64,
            audio_bytes=audio_bytes,
            word_timings=word_timings,
            duration=round(total_duration, 3),
        )

    def _estimate_word_timings(self, text: str, total_duration: float) -> list[WordTiming]:
        """
        Estimate word-level timings based on text and total duration.
        
        This provides approximate timings for lip-sync animation.
        The timing is proportional to word length.
        """
        # Extract words (keeping punctuation attached for natural pauses)
        words = re.findall(r'\S+', text)
        
        if not words:
            return []
        
        # Calculate total character count (as proxy for duration)
        total_chars = sum(len(w) for w in words)
        
        if total_chars == 0:
            return []
        
        # Distribute duration proportionally to word length
        word_timings: list[WordTiming] = []
        current_time = 0.0
        
        for word in words:
            # Duration proportional to word length
            word_duration = (len(word) / total_chars) * total_duration
            
            # Add small pause after punctuation
            if word[-1] in '.!?':
                word_duration += 0.2  # Pause after sentence
            elif word[-1] in ',;:':
                word_duration += 0.1  # Short pause after comma
            
            word_timings.append(WordTiming(
                word=word,
                start=round(current_time, 3),
                end=round(current_time + word_duration, 3),
            ))
            
            current_time += word_duration
        
        # Normalize to fit within total duration
        if word_timings and current_time > 0:
            scale = total_duration / current_time
            for wt in word_timings:
                wt.start = round(wt.start * scale, 3)
                wt.end = round(wt.end * scale, 3)
        
        return word_timings

    def word_timings_to_dict(self, timings: list[WordTiming]) -> list[dict]:
        """Convert word timings to dictionary format for JSON serialization."""
        return [
            {
                "word": t.word,
                "start": t.start,
                "end": t.end,
            }
            for t in timings
        ]

    async def get_available_voices(self, language: str = "en") -> list[dict]:
        """Get list of available voices for a language."""
        voices = await edge_tts.list_voices()
        return [
            {
                "name": v["ShortName"],
                "gender": v["Gender"],
                "locale": v["Locale"],
            }
            for v in voices
            if v["Locale"].startswith(language)
        ]
