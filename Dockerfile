##### STEP 1: Build Angular (frontend) #####
FROM node:20-alpine AS frontend
WORKDIR /frontend

# install deps
COPY image-search-frontend/package*.json ./
RUN npm ci

# copy app and build
COPY image-search-frontend/ ./
RUN npm run build -- --configuration production
# output: /frontend/dist/image-search-frontend


##### STEP 2: Build Python (backend) #####
FROM python:3.10-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# system libs needed by opencv etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0  && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python deps first (leverages Docker cache)
COPY image-search-backend/requirements.txt /app/image-search-backend/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/image-search-backend/requirements.txt

# copy backend code
COPY image-search-backend/ /app/image-search-backend/

# copy built Angular into FastAPI static/
COPY --from=frontend /frontend/dist/image-search-frontend/ /app/image-search-backend/static/

# (optional) ship YOLO weights if you want to avoid downloading on boot
# COPY yolov8s.pt /app/image-search-backend/yolov8s.pt

# Render provides $PORT; default to 8000 for local runs
EXPOSE 8000
CMD ["sh", "-c", "uvicorn image-search-backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
