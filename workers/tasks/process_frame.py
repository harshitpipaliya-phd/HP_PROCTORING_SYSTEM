"""
workers/tasks/process_frame.py
==============================
Celery task for async frame processing.
"""

from workers.celery_app import task


@task(name="process_frame")
def process_frame_task(frame_b64: str, session_id: str, user_id: str):
    try:
        import base64
        import cv2
        import numpy as np
        from ai_workers.video_analyzer import analyze_frame_worker

        img_bytes = base64.b64decode(frame_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return {"success": False, "error": "Image decode failed"}

        _, result = analyze_frame_worker(image)
        return {"success": True, "session_id": session_id, "data": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
