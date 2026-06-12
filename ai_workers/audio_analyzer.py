"""
ai_workers/audio_analyzer.py
=============================
Audio analysis worker — wraps audio_proctoring.stream.analyze_audio_file
for queue-based execution.
"""

from typing import Dict, Any


def analyze_audio_worker(file_path: str, user_id: str = "api_user") -> Dict[str, Any]:
    """
    Analyze an audio file — callable from Celery task or direct invocation.
    """
    from audio_proctoring.stream import analyze_audio_file
    return analyze_audio_file(file_path, user_id)


def stream_audio_worker(user_id: str, session_id: str, chunk: bytes) -> Dict[str, Any]:
    """
    Process a single PCM audio chunk in real-time streaming mode.
    """
    from audio_proctoring.stream import create_ws_audio_session, close_ws_audio_session
    ws_sess = create_ws_audio_session(user_id=user_id, session_id=session_id)
    try:
        return ws_sess.push_chunk(chunk)
    finally:
        close_ws_audio_session(session_id)
