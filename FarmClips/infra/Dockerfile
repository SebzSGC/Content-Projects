FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY packages ./packages
COPY apps/server ./apps/server

RUN pip install --no-cache-dir setuptools \
    fastapi "uvicorn[standard]" pydantic httpx numpy pyarrow soundfile \
    opencv-python-headless mediapipe cryptography Pillow \
    && pip install --no-build-isolation --no-deps \
    -e packages/styles \
    -e packages/editplan \
    -e packages/core \
    -e packages/media \
    -e packages/providers \
    -e packages/tracking \
    -e packages/render-engine \
    -e apps/server

ENV CLIPS_HOST=0.0.0.0
ENV CLIPS_PORT=8790
ENV CLIPS_DATA_DIR=/app/data
EXPOSE 8790

CMD ["python", "-m", "clipsserver.main", "serve"]
