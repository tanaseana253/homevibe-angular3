# STEP 1: Build Angular
FROM node:18 as frontend-build
WORKDIR /frontend
COPY image-search-frontend/ .
RUN npm install
RUN npm run build -- --configuration production

# STEP 2: Build FastAPI
FROM python:3.10-slim
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential

# Install Python deps
COPY image-search-backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend code
COPY image-search-backend/ /app/image-search-backend/

# Copy Angular build into static folder
COPY --from=frontend-build /frontend/dist/image-search-frontend/ /app/image-search-backend/static/

# Expose port
EXPOSE 8000

# Run FastAPI
CMD ["uvicorn", "image-search-backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
