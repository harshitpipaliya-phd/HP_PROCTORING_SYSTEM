"""
audio_proctoring/trainer.py
==========================
Audio model training script.

Trains a classifier for audio segments:
  - Silence (0)
  - Noise (1)
  - Speech (2)
  - Anomaly (3)
"""

import os
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

# Feature extraction
from audio_proctoring.classifier import extract_features


def train_audio_model(data_dir: str = "data", output_path: str = "models/audio_classifier.pkl"):
    """
    Train audio classifier model.
    
    Args:
        data_dir: Directory containing training data
        output_path: Path to save the trained model
    """
    # This is a placeholder - in production you'd load actual training data
    print("Training audio model...")
    print(f"Data directory: {data_dir}")
    print(f"Output path: {output_path}")
    
    # For demonstration, create synthetic training data
    # In production, replace with actual labeled data
    
    # Generate synthetic features for each class
    n_samples = 1000
    
    # Class 0: Silence (low energy, low spectral features)
    silence_features = np.random.randn(n_samples, 12) * 0.01 + np.array([0.001, 0.1, 100, 500, 0.5, 0.1, 0.05, 0.02, 0.01, 0.5, 0.1, 0.01])
    silence_labels = np.zeros(n_samples)
    
    # Class 1: Noise (moderate energy, varied spectral)
    noise_features = np.random.randn(n_samples, 12) * 0.05 + np.array([0.02, 0.3, 2000, 3000, 0.8, 0.3, 0.15, 0.1, 0.1, 1.5, 0.5, 0.1])
    noise_labels = np.ones(n_samples)
    
    # Class 2: Speech (higher energy, structured spectral)
    speech_features = np.random.randn(n_samples, 12) * 0.03 + np.array([0.08, 0.2, 1500, 2500, 0.6, 0.4, 0.3, 0.2, 0.2, 2.0, 0.8, 0.2])
    speech_labels = np.ones(n_samples) * 2
    
    # Class 3: Anomaly (unusual spectral patterns)
    anomaly_features = np.random.randn(n_samples, 12) * 0.08 + np.array([0.05, 0.5, 4000, 6000, 1.2, 0.6, 0.4, 0.3, 0.5, 3.0, 1.0, 0.5])
    anomaly_labels = np.ones(n_samples) * 3
    
    # Combine
    X = np.vstack([silence_features, noise_features, speech_features, anomaly_features])
    y = np.concatenate([silence_labels, noise_labels, speech_labels, anomaly_labels])
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Train
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    train_score = model.score(X_train, y_train)
    test_score = model.score(X_test, y_test)
    
    print(f"Training accuracy: {train_score:.2%}")
    print(f"Test accuracy: {test_score:.2%}")
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    joblib.dump(model, output_path)
    print(f"Model saved to {output_path}")
    
    # Save metadata
    # BUG FIX: config.py expects "model_meta.json", not "audio_classifier_meta.json"
    meta_path = os.path.join(os.path.dirname(output_path), "model_meta.json")
    import json
    meta = {
        "model_type": "RandomForestClassifier",
        "n_estimators": 100,
        "n_features": 12,
        "classes": ["silence", "noise", "speech", "anomaly"],
        "train_accuracy": train_score,
        "test_accuracy": test_score,
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved to {meta_path}")
    
    return model


if __name__ == "__main__":
    train_audio_model()