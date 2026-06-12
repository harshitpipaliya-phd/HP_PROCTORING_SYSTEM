# HP Proctoring - AI Worker Dockerfile
# ====================================
# HuggingFace Space compatible container definition.
# Build: docker build -t hp-proctoring-ai-worker -f ai_workers/Dockerfile .
# Run: docker run -p 7860:7860 hp-proctoring-ai-worker

FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# cmake + build tools are required for dlib (face-recognition library)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*
    
# Install Python dependencies
COPY requirements.txt requirements_ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ai_workers/ ./ai_workers/
COPY video_ai/ ./video_ai/
COPY audio_proctoring/ ./audio_proctoring/
COPY core/ ./core/
COPY database/ ./database/

# Expose Gradio port (default HuggingFace Space port)
EXPOSE 7860

# Run the AI worker Gradio app
CMD ["uvicorn", "ai_workers.app:app", "--host", "0.0.0.0", "--port", "7860"]
