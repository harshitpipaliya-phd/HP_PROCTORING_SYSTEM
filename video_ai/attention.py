"""
video_ai/attention.py
====================
Attention scoring module for HP Proctoring.

Calculates attention score based on:
  - Eye gaze direction
  - Head pose direction
  - Looking away frequency
  - Blink patterns

Returns a composite attention score (0-100) with a label.
"""

from typing import Tuple


def calculate_attention(looking_away: bool, head_direction: str,
                       look_away_frequency: int = 0,
                       ear_avg: float = 0.3,
                       blink_rate: float = 15.0) -> int:
    """
    Calculate attention score (0-100).
    
    Args:
        looking_away: Whether subject is looking away
        head_direction: Current head direction (Center/Left/Right/Up/Down/No Face)
        look_away_frequency: Number of look-aways in last 60 seconds
        ear_avg: Average eye aspect ratio
        blink_rate: Estimated blinks per minute
    
    Returns:
        Attention score (0-100)
    """
    score = 100
    
    # Looking away penalty
    if looking_away:
        score -= 30
    
    # Head not centered penalty
    if head_direction not in ("Center", "No Face"):
        score -= 20
    
    # Frequent look-aways penalty
    if look_away_frequency >= 5:
        score -= 15
    elif look_away_frequency >= 3:
        score -= 8
    
    # Unusual blink rate
    if ear_avg < 0.20:
        # Very low EAR could indicate unusual eye behavior
        score -= 10
    
    # Low blink rate (normal is 15-20 per minute)
    if blink_rate < 5:
        score -= 10
    elif blink_rate > 40:
        score -= 5
    
    return max(0, min(100, score))


def get_attention_label(score: int) -> str:
    """Get attention label based on score."""
    if score >= 80:
        return "FOCUSED"
    elif score >= 60:
        return "ATTENTIVE"
    elif score >= 40:
        return "DISTRACTED"
    elif score >= 20:
        return "UNFOCUSED"
    else:
        return "DISENGAGED"


def get_attention_metrics(eye_result: dict, pose_result: dict) -> Tuple[int, str, dict]:
    """
    Calculate full attention metrics from eye and pose results.
    
    Returns:
        (attention_score, attention_label, metrics_dict)
    """
    looking_away = eye_result.get("looking_away", False)
    gaze_direction = eye_result.get("gaze_direction", "Center")
    head_direction = pose_result.get("direction", "Center")
    look_away_frequency = eye_result.get("look_away_frequency", 0)
    
    ear_left = eye_result.get("ear_left", 0.25)
    ear_right = eye_result.get("ear_right", 0.25)
    ear_avg = (ear_left + ear_right) / 2
    
    score = calculate_attention(
        looking_away=looking_away,
        head_direction=head_direction,
        look_away_frequency=look_away_frequency,
        ear_avg=ear_avg
    )
    
    label = get_attention_label(score)
    
    metrics = {
        "score": score,
        "label": label,
        "looking_away": looking_away,
        "gaze_direction": gaze_direction,
        "head_direction": head_direction,
        "look_away_frequency": look_away_frequency,
        "ear_avg": round(ear_avg, 3),
    }
    
    return score, label, metrics