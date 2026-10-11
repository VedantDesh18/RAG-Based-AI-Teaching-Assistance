FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output for live logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install required system dependencies:
# - ffmpeg (and ffprobe): required for video/audio extraction, chunk splitting, and duration detection
# - nodejs: required by yt-dlp for JavaScript runtime deciphering
# - curl: required for container health checks
# - build-essential: provides gcc/g++ if native extensions need building
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg is properly installed
RUN ffmpeg -version && ffprobe -version

# Copy dependency files first to leverage Docker layer caching
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application source code, migrations, scripts, and default config
COPY videoqa/ ./videoqa/
COPY db/ ./db/
COPY scripts/ ./scripts/
COPY config.yaml ./

# Install package in editable mode so internal package references resolve properly
RUN pip install --no-cache-dir -e .

# Ensure data directory structures exist
RUN mkdir -p data/db data/chroma data/media

# Expose FastAPI backend port
EXPOSE 8000

# Health check to ensure the backend is responsive
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the FastAPI application with uvicorn on 0.0.0.0:8000
CMD ["uvicorn", "videoqa.main:app", "--host", "0.0.0.0", "--port", "8000"]
