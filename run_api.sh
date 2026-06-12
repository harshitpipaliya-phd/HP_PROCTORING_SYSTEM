#!/bin/bash
# Run FastAPI backend
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
