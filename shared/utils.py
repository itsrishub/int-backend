"""Shared utility functions across services."""

import uuid
from datetime import datetime


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"session_{uuid.uuid4().hex[:12]}"


def get_timestamp() -> str:
    """Get current ISO timestamp."""
    return datetime.utcnow().isoformat()
