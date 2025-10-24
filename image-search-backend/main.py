from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from serpapi import GoogleSearch
from ultralytics import YOLO
from PIL import Image
import os, io, requests, time, uuid, shutil
from dotenv import load_dotenv

# ========= 1) ENV & CONSTANTS =========
load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
IMGBB_KEY = os.getenv("IMGBB_KEY")
BACKEND_URL = os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:8000")

# ========= 2) APP & CORS =========
app = FastAPI(title="Object Detection + Similar Search")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        BACKEND_URL,
        "https://homevibe-angular3.onrender.com",
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= 3) STATIC CROPS (FIRST) =========
CROPS_DIR = "cropped_images"
os.makedirs(CROPS_DIR, exist_ok=True)
app.mount("/cropped_images", StaticFiles(directory=CROPS_DIR), name="cropped")

# ========= 4) MODEL & HEALTH =========
model = YOLO("yolov8n.pt")

@app.get("/health")
def health():
    return {"ok": True}

# ========= 5) API ROUTES =========
def cleanup_old_folders(base_folder: str, max_age: int = 600):
    now = time.time()
    for folder in os.listdir(base_folder):
        folder_path = os.path.join(base_folder, folder)
        if os.path.isdir(folder_path):
            try:
                if now - os.path.getmtime(folder_path) > max_age:
                    shutil.rmtree(folder_path)
            except Exception:
                pass

INTERIOR_CLASSES = {"chair", "couch", "sofa", "table", "lamp", "desk", "mirror", "carpet"}

def iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return inter / float(a1 + a2 - inter)

from fastapi import File, UploadFile

@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    cleanup_old_folders(CROPS_DIR, 600)

    request_id = str(uuid.uuid4())
    folder = os.path.join(CROPS_DIR, request_id)
    os.makedirs(folder, exist_ok=True)

    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results = model.predict(img, conf=0.05, iou=0.3, imgsz=1280, verbose=False)[0]

    # Gather raw detections
    raw = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        class_name = results.names[int(box.cls[0])].lower()
        conf = float(box.conf[0])
        if class_name in INTERIOR_CLASSES:
            raw.append({"box": (x1, y1, x2, y2), "class_name": class_name, "confidence": conf})

    # Extra NMS
    filtered = []
    for det in raw:
        if det["confidence"] < 0.30:
            continue
        keep = True
        for f in filtered:
            if iou(det["box"], f["box"]) > 0.5:
                if det["confidence"] > f["confidence"]:
                    f.update(det)
                keep = False
                break
        if keep:
            filtered.append(det)

    # Save crops
    detections = []
    for i, det in enumerate(filtered):
        x1, y1, x2, y2 = det["box"]
        crop = img.crop((x1, y1, x2, y2))
        name = f"crop_{i}.jpg"
        path = os.path.join(folder, name)
        crop.save(path)
        detections.append({
            "id": i,
            "class_name": det["class_name"],
            "confidence": det["confidence"],
            "crop_url": f"{BACKEND_URL}/cropped_images/{request_id}/{name}",
        })

    return {"detections": detections, "request_id": request_id}

@app.get("/search_similar_crop/{request_id}/{crop_id}")
async def search_similar_crop(request_id: str, crop_id: int):
    crop_path = os.path.join(CROPS_DIR, request_id, f"crop_{crop_id}.jpg")
    if not os.path.exists(crop_path):
        return {"error": "Crop not found"}

    with open(crop_path, "rb") as f:
        upload_res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_KEY},
            files={"image": f}
        ).json()

    if "data" not in upload_res:
        return {"error": "Upload failed", "details": upload_res}

    image_url = upload_res["data"]["url"]

    search = GoogleSearch({
        "engine": "google_lens",
        "api_key": SERPAPI_KEY,
        "url": image_url,
        "hl": "ro",
        "gl": "ro"
    })
    results = search.get_dict()
    matches = [
        {"title": m.get("title", ""), "url": m.get("link", ""), "image": m.get("thumbnail", "")}
        for m in results.get("visual_matches", [])[:6]
    ]
    return {"matches": matches}

# ========= 6) ANGULAR SPA (LAST) =========
dist_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(dist_path, "index.html"))
# (The Angular app will handle routing on the frontend)