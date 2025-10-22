from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from serpapi import GoogleSearch
from ultralytics import YOLO
from PIL import Image
import os, io, requests, time, uuid, shutil
from dotenv import load_dotenv
import math

# Load env vars
load_dotenv()
print("DEBUG SERPAPI_KEY:", os.getenv("SERPAPI_KEY"))
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
IMGBB_KEY = os.getenv("IMGBB_KEY")

app = FastAPI(title="Object Detection + Similar Search")

# Allow frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200", 
        "http://127.0.0.1:4200"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve cropped images
CROPS_DIR = "cropped_images"
os.makedirs(CROPS_DIR, exist_ok=True)
app.mount("/cropped_images", StaticFiles(directory=CROPS_DIR), name="cropped")

# Load YOLO model once
model = YOLO("yolov8s.pt")

@app.get("/health")
def health():
    return {"ok": True}


# 🔥 Helper: cleanup old request folders (>10 min old)
def cleanup_old_folders(base_folder: str, max_age: int = 600):
    now = time.time()
    for folder in os.listdir(base_folder):
        folder_path = os.path.join(base_folder, folder)
        if os.path.isdir(folder_path):
            try:
                if now - os.path.getmtime(folder_path) > max_age:
                    shutil.rmtree(folder_path)
                    print(f"🧹 Deleted old folder: {folder_path}")
            except Exception as e:
                print(f"Cleanup failed for {folder_path}: {e}")

# Allowed classes
INTERIOR_CLASSES = {
    "chair", "couch", "sofa", "table",
    "lamp", "desk", "mirror", "carpet"
}

def iou(box1, box2):
    """Compute IoU between two boxes (x1, y1, x2, y2)."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    if inter_area == 0:
        return 0.0

    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    return inter_area / float(box1_area + box2_area - inter_area)


# Detect objects + save crops
@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    # 🔥 Clean old folders before processing
    cleanup_old_folders(CROPS_DIR, 600)

    # ✅ Create a unique subfolder for this request
    request_id = str(uuid.uuid4())
    folder = os.path.join(CROPS_DIR, request_id)
    os.makedirs(folder, exist_ok=True)

    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results = model.predict(img, conf=0.05, iou=0.3, imgsz=1280, verbose=False)[0]

    # --- Collect raw detections first ---
    raw_detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        class_id = int(box.cls[0])
        class_name = results.names[class_id].lower()
        conf = float(box.conf[0])

        # ❌ Skip classes not in our whitelist
        if class_name not in INTERIOR_CLASSES:
            continue

        raw_detections.append({
            "box": (x1, y1, x2, y2),
            "class_name": class_name,
            "confidence": conf
        })

    # --- 🔥 Extra NMS: remove duplicates of same class ---
    # --- 🔥 Extra NMS: remove duplicates of same/overlapping objects ---
    filtered = []
    for det in raw_detections:
        # 🚫 Skip low-confidence detections
        if det["confidence"] < 0.30:  
            continue

        keep = True
        for f in filtered:
            # If same class OR heavy overlap regardless of class
            if iou(det["box"], f["box"]) > 0.5:
                # keep only the one with higher confidence
                if det["confidence"] > f["confidence"]:
                    f.update(det)  # replace weaker one
                keep = False
                break
        if keep:
            filtered.append(det)

    # --- Save crops + return detections ---
    detections = []
    for i, det in enumerate(filtered):
        x1, y1, x2, y2 = det["box"]

        crop = img.crop((x1, y1, x2, y2))
        crop_filename = f"crop_{i}.jpg"
        crop_path = os.path.join(folder, crop_filename)
        crop.save(crop_path)

        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        detections.append({
            "id": i,
            "class_name": det["class_name"],
            "confidence": det["confidence"],
            "crop_url": f"http://127.0.0.1:8000/cropped_images/{request_id}/{crop_filename}",
            "x": center_x,
            "y": center_y
        })

    return {"detections": detections, "request_id": request_id}


# Search similar for a given crop
@app.get("/search_similar_crop/{request_id}/{crop_id}")
async def search_similar_crop(request_id: str, crop_id: int):
    crop_path = os.path.join(CROPS_DIR, request_id, f"crop_{crop_id}.jpg")
    if not os.path.exists(crop_path):
        return {"error": "Crop not found"}

    # Upload crop to imgbb
    with open(crop_path, "rb") as f:
        upload_res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_KEY},
            files={"image": f}
        ).json()

    if "data" not in upload_res:
        return {"error": "Upload failed", "details": upload_res}

    image_url = upload_res["data"]["url"]

    # Search with SerpAPI Google Lens
    search = GoogleSearch({
        "engine": "google_lens",
        "api_key": SERPAPI_KEY,
        "url": image_url,
        "hl": "ro",
        "gl": "ro"
    })

    results = search.get_dict()
    matches = []
    for item in results.get("visual_matches", [])[:6]:
        matches.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "image": item.get("thumbnail", "")
        })

    return {"matches": matches}


# ✅ Serve Angular frontend (for Heroku deployment)
from fastapi.responses import FileResponse

# Serve static Angular files (built version)
app.mount("/static", StaticFiles(directory="image-search-backend/static"), name="static")

@app.get("/")
def serve_frontend():
    index_path = os.path.join("image-search-backend/static/index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not found. Did you build Angular?"}


dist_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(dist_path, "index.html"))