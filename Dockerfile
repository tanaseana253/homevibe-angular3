##########################################
# 1️⃣ Frontend build stage
##########################################
FROM node:18-slim AS frontend-build
WORKDIR /frontend
COPY image-search-frontend/package*.json ./
RUN npm ci && npm install -g @angular/cli
COPY image-search-frontend/ ./
RUN ng build --configuration production
# Keep only built files
RUN rm -rf node_modules src /usr/local/lib/node_modules /root/.npm /tmp/*


##########################################
# 2️⃣ Backend runtime stage
##########################################
FROM python:3.10-slim AS backend
WORKDIR /app

# System libs for OpenCV/YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY image-search-backend/requirements.txt .
# ✅ Use smaller torch build
RUN pip install --no-cache-dir torch==2.2.0+cpu torchvision==0.17.0+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy backend code
COPY image-search-backend/ ./image-search-backend/

# Copy static built frontend
COPY --from=frontend-build /frontend/dist/image-search-frontend/ ./image-search-backend/static/

# Final cleanup
RUN rm -rf /root/.cache /tmp/*

ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "image-search-backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
