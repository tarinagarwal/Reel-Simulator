# app.py
import os
import uuid
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import DOWNLOAD_DIR, DEFAULT_COLOR1, DEFAULT_COLOR2, DEFAULT_PLATFORM
from utils import time_to_seconds
from services import format_text_with_groq, get_video_info, create_template_video
from services.video import download_video as dl_video, extract_preview_frame

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the frontend HTML"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/upload-bg")
async def upload_background(file: UploadFile = File(...)):
    """Upload a background image"""
    file_id = str(uuid.uuid4())
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
    filepath = os.path.join(DOWNLOAD_DIR, f"bg_{file_id}.{ext}")
    
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"id": f"bg_{file_id}.{ext}"}


@app.get("/info")
def video_info(url: str):
    """Fetch video metadata without downloading"""
    try:
        return get_video_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/prepare")
def prepare_video(
    url: str,
    start_time: str = Query(default="00:00:00"),
    end_time: str = Query(default=None)
):
    """Download video and extract preview frame for cropping"""
    file_id = str(uuid.uuid4())
    raw_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_raw.mp4")
    preview_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_preview.jpg")
    
    start_sec = time_to_seconds(start_time)
    end_sec = time_to_seconds(end_time)
    
    try:
        # Download video
        info = dl_video(url, raw_file, start_sec, end_sec)
        title = info.get("title", "video")
        
        # Find downloaded file
        actual_file = raw_file.replace('.mp4', f'.{info.get("ext", "mp4")}')
        if not os.path.exists(actual_file):
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(f"{file_id}_raw"):
                    actual_file = os.path.join(DOWNLOAD_DIR, f)
                    break
        
        # Extract preview frame and get dimensions
        width, height = extract_preview_frame(actual_file, preview_file)
        
        return {
            "video_id": file_id,
            "title": title,
            "preview": f"{file_id}_preview.jpg",
            "width": width,
            "height": height
        }
    except Exception as e:
        # Cleanup on error
        for f in [raw_file, preview_file]:
            if os.path.exists(f):
                os.remove(f)
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/download")
async def download_video(
    url: str = Query(default=None),
    video_id: str = Query(default=None),
    start_time: str = Query(default="00:00:00"),
    end_time: str = Query(default=None),
    overlay_text: str = Query(default=""),
    username: str = Query(default=""),
    platform: str = Query(default=DEFAULT_PLATFORM),
    color1: str = Query(default=DEFAULT_COLOR1),
    color2: str = Query(default=DEFAULT_COLOR2),
    bg_type: str = Query(default="gradient"),
    bg_image_id: str = Query(default=None),
    gradient_angle: str = Query(default="diagonal-br"),
    crop_x: float = Query(default=0),
    crop_y: float = Query(default=0),
    crop_w: float = Query(default=100),
    crop_h: float = Query(default=100)
):
    """Generate video with template. Use video_id if already prepared, or url to download fresh."""
    
    # Determine file_id and raw_file
    if video_id:
        file_id = video_id
        # Find the prepared video
        raw_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(f"{file_id}_raw"):
                raw_file = os.path.join(DOWNLOAD_DIR, f)
                break
        if not raw_file:
            raise HTTPException(status_code=400, detail="Prepared video not found")
    elif url:
        file_id = str(uuid.uuid4())
        raw_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_raw.mp4")
    else:
        raise HTTPException(status_code=400, detail="Either url or video_id required")
    
    final_file = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")
    start_sec = time_to_seconds(start_time)
    end_sec = time_to_seconds(end_time)
    
    # Crop params as percentages
    crop_params = {"x": crop_x, "y": crop_y, "w": crop_w, "h": crop_h}

    try:
        # Download if not using prepared video
        if not video_id:
            info = dl_video(url, raw_file, start_sec, end_sec)
            title = info.get("title", "video")
            raw_file = raw_file.replace('.mp4', f'.{info.get("ext", "mp4")}')
            if not os.path.exists(raw_file):
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(f"{file_id}_raw"):
                        raw_file = os.path.join(DOWNLOAD_DIR, f)
                        break
        else:
            title = "video"
        
        # Format text with Groq
        groq_result = await format_text_with_groq(overlay_text)
        generated_title = groq_result.get("title", "")
        formatted_body = groq_result.get("body", overlay_text)
        
        # Background image
        bg_image_path = None
        if bg_type == "image" and bg_image_id:
            bg_image_path = os.path.join(DOWNLOAD_DIR, bg_image_id)
        
        # Apply template with crop
        if formatted_body or username:
            create_template_video(
                raw_file, final_file, generated_title, formatted_body, username, platform,
                color1, color2, bg_image_path, gradient_angle, crop_params
            )
            # Cleanup raw and preview
            if os.path.exists(raw_file):
                os.remove(raw_file)
            preview_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_preview.jpg")
            if os.path.exists(preview_file):
                os.remove(preview_file)
            return {"file": f"{file_id}.mp4", "title": title}
        else:
            os.rename(raw_file, final_file)
            return {"file": f"{file_id}.mp4", "title": title}
            
    except Exception as e:
        for f in [raw_file, final_file]:
            if f and os.path.exists(f):
                os.remove(f)
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/file/{name}")
def get_file(name: str):
    """Serve a downloaded file"""
    if ".." in name or "/" in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(DOWNLOAD_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=name)
