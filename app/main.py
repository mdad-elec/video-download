from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Response, Form, Header, Request
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uuid
import asyncio
import os
from typing import Optional
import aiofiles
import json

from .config import settings
from .simple_auth import auth_manager
from .downloaders import YouTubeDownloader, TikTokDownloader, FacebookDownloader, TwitterDownloader
from .utils.cleanup import TempFileCleanup

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Initialize cleanup service
cleanup_service = TempFileCleanup(settings.TEMP_DIR, settings.MAX_TEMP_FILE_AGE_SECONDS)

# Platform downloaders
downloaders = {
    'youtube': YouTubeDownloader(),
    'tiktok': TikTokDownloader(),
    'facebook': FacebookDownloader(),
    'twitter': TwitterDownloader(),
}

@app.on_event("startup")
async def startup_event():
    """Start background cleanup"""
    asyncio.create_task(cleanup_service.start())

@app.get("/")
async def root():
    """Redirect to login"""
    return RedirectResponse(url="/login")

@app.get("/login")
async def login_page(request: Request):
    """Render login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register")
async def register_page(request: Request):
    """Render registration page"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Render dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/register")
async def register(username: str = Form(), email: str = Form(), password: str = Form()):
    """User registration"""
    if auth_manager.register_user(username, email, password):
        return {"message": "User created successfully"}
    else:
        raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/token")
async def login(username: str = Form(), password: str = Form()):
    """User login - OAuth2 compatible endpoint"""
    if auth_manager.verify_user(username, password):
        token = auth_manager.create_token(username)
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

def get_current_user(authorization: str = Header(None)):
    """Get current user from token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    username = auth_manager.verify_token(token)
    
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return username

@app.post("/api/video/info")
async def get_video_info(
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Get video information without downloading"""
    data = await request.json()
    url = data.get('url')
    platform = data.get('platform')
    
    if not url or not platform:
        raise HTTPException(status_code=400, detail="URL and platform required")
    
    if platform not in downloaders:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    
    try:
        downloader = downloaders[platform]
        info = await downloader.get_video_info(url)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video/download")
async def download_video(
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Download and stream video to user"""
    data = await request.json()
    url = data.get('url')
    platform = data.get('platform')
    format_id = data.get('format_id', 'best')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    
    if not url or not platform:
        raise HTTPException(status_code=400, detail="URL and platform required")
    
    if platform not in downloaders:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    
    # Track download
    auth_manager.track_download(current_user, url)
    
    try:
        downloader = downloaders[platform]
        
        # Download video
        video_path = await downloader.download(
            url=url,
            format_id=format_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # Stream file and delete after
        async def iterfile():
            async with aiofiles.open(video_path, 'rb') as file:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    yield chunk
            
            # Delete file after streaming
            try:
                os.unlink(video_path)
            except:
                pass
        
        return StreamingResponse(
            iterfile(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=video_{uuid.uuid4().hex[:8]}.mp4"
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/sessions")
async def get_user_sessions(current_user: str = Depends(get_current_user)):
    """Get user's download history"""
    downloads = auth_manager.get_user_downloads(current_user)
    
    # Format for frontend
    sessions = []
    for idx, download in enumerate(downloads[-10:]):  # Last 10 downloads
        sessions.append({
            'id': idx,
            'created_at': download['timestamp'],
            'status': 'completed',
            'url': download['url']
        })
    
    return sessions