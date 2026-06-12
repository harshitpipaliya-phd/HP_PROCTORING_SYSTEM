"""
video_ai/frame_utils.py
=======================
Utility functions for frame processing and evidence capture.
"""

import cv2
import numpy as np
import base64
import os
from datetime import datetime
from typing import Dict, Any, Optional


def capture_evidence_frame(frame: np.ndarray, label: str = "violation") -> Dict[str, Any]:
    """
    Capture and encode an evidence frame for violations.
    
    Args:
        frame: The frame to capture
        label: Label for the violation type
        
    Returns:
        dict with image data and metadata
    """
    if frame is None:
        return {}
    
    try:
        # Encode frame to JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
        _, buffer = cv2.imencode('.jpg', frame, encode_params)
        image_bytes = buffer.tobytes()
        
        # Convert to base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"evidence_{label}_{timestamp}.jpg"
        
        output_dir = os.getenv("EVIDENCE_DIR", "static/screenshots")
        os.makedirs(output_dir, exist_ok=True)
        
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "image_b64": image_b64,
            "filename": filename,
            "filepath": filepath,
            "label": label,
            "size_bytes": len(image_bytes)
        }
        
    except Exception as e:
        print(f"[ERROR frame_utils.capture_evidence_frame]: {e}")
        return {}


def decode_base64_image(b64_string: str) -> Optional[np.ndarray]:
    """
    Decode a base64-encoded image string to numpy array.
    
    Args:
        b64_string: Base64 encoded image string
        
    Returns:
        numpy array (BGR) or None if decoding fails
    """
    try:
        img_bytes = base64.b64decode(b64_string)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        print(f"[ERROR frame_utils.decode_base64_image]: {e}")
        return None


def resize_frame(frame: np.ndarray, max_width: int = 1280, max_height: int = 720) -> np.ndarray:
    """Resize frame while maintaining aspect ratio."""
    if frame is None:
        return frame
    
    h, w = frame.shape[:2]
    
    if w > max_width or h > max_height:
        scale = min(max_width / w, max_height / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        frame = cv2.resize(frame, (new_w, new_h))
    
    return frame


def normalize_frame(frame: np.ndarray) -> np.ndarray:
    """Normalize frame values."""
    if frame is None:
        return frame
    
    return frame.astype(np.float32) / 255.0


def draw_text_with_background(frame: np.ndarray, text: str, position: tuple,
                               font=cv2.FONT_HERSHEY_SIMPLEX, font_scale: float = 1.0,
                               text_color=(255, 255, 255), bg_color=(0, 0, 0),
                               thickness: int = 2, padding: int = 5) -> np.ndarray:
    """Draw text with a background rectangle."""
    if frame is None:
        return frame
    
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    
    x, y = position
    cv2.rectangle(frame,
                  (x - padding, y - text_h - padding),
                  (x + text_w + padding, y + baseline + padding),
                  bg_color, -1)
    
    cv2.putText(frame, text, (x, y), font, font_scale, text_color, thickness)
    
    return frame


def create_heatmap(data: np.ndarray, colormap=cv2.COLORMAP_JET) -> np.ndarray:
    """Create a heatmap visualization from a 2D array."""
    if data is None or len(data) == 0:
        return np.zeros((100, 100, 3), dtype=np.uint8)
    
    # Normalize to 0-255
    data_min = np.min(data)
    data_max = np.max(data)
    
    if data_max - data_min > 0:
        normalized = ((data - data_min) / (data_max - data_min) * 255).astype(np.uint8)
    else:
        normalized = np.zeros_like(data, dtype=np.uint8)
    
    # Apply colormap
    heatmap = cv2.applyColorMap(normalized, colormap)
    
    return heatmap


def stack_frames_horizontal(frames: list, target_height: int = 480) -> np.ndarray:
    """Stack multiple frames horizontally with consistent height."""
    if not frames:
        return np.zeros((target_height, 640, 3), dtype=np.uint8)
    
    resized = []
    for frame in frames:
        if frame is None:
            continue
        h, w = frame.shape[:2]
        scale = target_height / h
        new_w = int(w * scale)
        resized.append(cv2.resize(frame, (new_w, target_height)))
    
    if not resized:
        return np.zeros((target_height, 640, 3), dtype=np.uint8)
    
    return np.hstack(resized)


def stack_frames_vertical(frames: list, target_width: int = 640) -> np.ndarray:
    """Stack multiple frames vertically with consistent width."""
    if not frames:
        return np.zeros((480, target_width, 3), dtype=np.uint8)
    
    resized = []
    for frame in frames:
        if frame is None:
            continue
        h, w = frame.shape[:2]
        scale = target_width / w
        new_h = int(h * scale)
        resized.append(cv2.resize(frame, (target_width, new_h)))
    
    if not resized:
        return np.zeros((480, target_width, 3), dtype=np.uint8)
    
    return np.vstack(resized)