from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Response, Form, Header, Request, WebSocket
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
from .database.models import create_tables, get_db_session
from .database.auth import DatabaseAuthManager
from .downloaders import YouTubeDownloader, TikTokDownloader, FacebookDownloader, TwitterDownloader
from .utils.cleanup import TempFileCleanup
from .utils.logger import logger
from .utils.video_converter import VideoConverter
from .utils.download_scheduler import DownloadScheduler
from .api.websocket import send_progress_update, send_download_complete, send_download_error, websocket_endpoint

# Initialize database
create_tables()

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

# Setup progress callbacks for downloaders
def setup_progress_callbacks():
    """Setup progress callbacks for all downloaders"""
    for platform, downloader in downloaders.items():
        downloader.set_progress_callback(lambda data: logger.info(f"Progress {platform}: {data}"))

setup_progress_callbacks()

# Database dependency
def get_db():
    """Get database session"""
    return next(get_db_session())

# Auth manager dependency
def get_auth_manager(db=Depends(get_db)):
    """Get auth manager instance"""
    return DatabaseAuthManager(db)

# Global scheduler instance
scheduler = None

def get_scheduler():
    """Get scheduler instance"""
    global scheduler
    return scheduler

@app.on_event("startup")
async def startup_event():
    """Start background services"""
    # Start cleanup service
    asyncio.create_task(cleanup_service.start())
    
    # Initialize and start download scheduler
    global scheduler
    db = next(get_db_session())
    auth_manager = DatabaseAuthManager(db)
    scheduler = DownloadScheduler(db, auth_manager)
    await scheduler.start()
    logger.info("Download scheduler initialized and started")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop background services"""
    global scheduler
    if scheduler:
        await scheduler.stop()
        logger.info("Download scheduler stopped")

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
async def register(
    username: str = Form(), 
    email: str = Form(), 
    password: str = Form(),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """User registration"""
    try:
        # Validate input
        if not username or not email or not password:
            raise HTTPException(status_code=400, detail="All fields are required")
        
        if len(username) < 3 or len(username) > 20:
            raise HTTPException(status_code=400, detail="Username must be between 3 and 20 characters")
        
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
        logger.info(f"Registration attempt for username: {username}")
        
        if auth_manager.register_user(username, email, password):
            logger.info(f"Successfully registered user: {username}")
            return {"message": "User created successfully"}
        else:
            logger.warning(f"Registration failed - username already exists: {username}")
            raise HTTPException(status_code=400, detail="Username already exists")
            
    except ValueError as e:
        logger.warning(f"Invalid registration input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error for {username}: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

@app.post("/token")
async def login(
    username: str = Form(), 
    password: str = Form(),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """User login - OAuth2 compatible endpoint"""
    try:
        # Validate input
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password are required")
        
        logger.info(f"Login attempt for username: {username}")
        
        if auth_manager.verify_user(username, password):
            token = auth_manager.create_token(username)
            logger.info(f"Successful login for user: {username}")
            return {"access_token": token, "token_type": "bearer"}
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except ValueError as e:
        logger.warning(f"Invalid login input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Login error for {username}: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed. Please try again.")

def get_current_user(
    authorization: str = Header(None),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Get current user from token"""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        token = authorization.split(" ")[1]
        if not token:
            raise HTTPException(status_code=401, detail="Invalid token format")
        
        username = auth_manager.verify_token(token)
        
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return username
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")

@app.post("/api/video/info")
async def get_video_info(
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Get video information without downloading"""
    try:
        data = await request.json()
        url = data.get('url')
        platform = data.get('platform')
        
        if not url or not platform:
            raise HTTPException(status_code=400, detail="URL and platform required")
        
        if platform not in downloaders:
            raise HTTPException(status_code=400, detail="Unsupported platform")
        
        logger.info(f"User {current_user} requesting video info for {url} on {platform}")
        
        downloader = downloaders[platform]
        info = await downloader.get_video_info(url)
        
        logger.info(f"Successfully retrieved video info for {url}")
        return info
        
    except ValueError as e:
        logger.warning(f"Invalid input for video info: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"Network error fetching video info: {str(e)}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Please try again.")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error getting video info: {error_msg}")
        
        # Provide more user-friendly error messages
        if "Could not fetch" in error_msg and "after multiple attempts" in error_msg:
            detail = f"Unable to retrieve video information from {platform}. This may be due to platform restrictions or the video being private/unavailable."
        elif "No video content found" in error_msg:
            detail = "This URL doesn't contain any video content or the video is no longer available."
        elif "IP address" in error_msg and "blocked" in error_msg:
            detail = "Access to this platform is currently restricted due to network limitations."
        else:
            detail = "Failed to get video information. Please try again."
        
        raise HTTPException(status_code=500, detail=detail)

@app.post("/api/video/download")
async def download_video(
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Download and stream video to user"""
    video_path = None
    try:
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
        
        logger.info(f"User {current_user} downloading video from {url} on {platform}")
        
        # Track download
        auth_manager.track_download(current_user, url, platform)
        
        downloader = downloaders[platform]
        
        # Set up progress callback for this user session
        user_id = f"user_{current_user}"
        
        def progress_callback(progress_data):
            asyncio.create_task(send_progress_update(user_id, progress_data))
        
        downloader.set_progress_callback(progress_callback)
        
        # Download video
        video_path = await downloader.download(
            url=url,
            format_id=format_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # Reset callback
        downloader.set_progress_callback(lambda data: logger.info(f"Progress {platform}: {data}"))
        
        logger.info(f"Successfully downloaded video to {video_path}")
        
        # Stream file and delete after
        async def iterfile():
            try:
                async with aiofiles.open(video_path, 'rb') as file:
                    while chunk := await file.read(1024 * 1024):  # 1MB chunks
                        yield chunk
            except Exception as e:
                logger.error(f"Error streaming video: {str(e)}")
            finally:
                # Delete file after streaming
                try:
                    if video_path and os.path.exists(video_path):
                        os.unlink(video_path)
                        logger.info(f"Cleaned up temporary file: {video_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup file {video_path}: {str(e)}")
        
        return StreamingResponse(
            iterfile(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=video_{uuid.uuid4().hex[:8]}.mp4"
            }
        )
        
    except ValueError as e:
        logger.warning(f"Invalid input for video download: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"Network error downloading video: {str(e)}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Please try again.")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error downloading video: {error_msg}")
        
        # Cleanup any temporary files
        if video_path and os.path.exists(video_path):
            try:
                os.unlink(video_path)
            except:
                pass
        
        # Provide more user-friendly error messages
        if "Could not download" in error_msg and "after multiple attempts" in error_msg:
            detail = f"Unable to download video from {platform}. This may be due to platform restrictions or the video being private/unavailable."
        elif "No video content found" in error_msg:
            detail = "This URL doesn't contain any video content or the video is no longer available."
        elif "IP address" in error_msg and "blocked" in error_msg:
            detail = "Access to this platform is currently restricted due to network limitations."
        else:
            detail = "Download failed. Please try again."
        
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/user/sessions")
async def get_user_sessions(
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Get user's download history"""
    try:
        logger.info(f"User {current_user} requesting download history")
        
        downloads = auth_manager.get_user_downloads(current_user)
        
        # Format for frontend
        sessions = []
        for idx, download in enumerate(downloads[-10:]):  # Last 10 downloads
            try:
                sessions.append({
                    'id': idx,
                    'created_at': download['download_time'],
                    'status': download['status'],
                    'url': download['url'],
                    'title': download.get('title', 'Unknown'),
                    'platform': download.get('platform', 'unknown')
                })
            except KeyError as e:
                logger.warning(f"Invalid download entry format: {str(e)}")
                continue
        
        logger.info(f"Retrieved {len(sessions)} download sessions for user {current_user}")
        return sessions
        
    except Exception as e:
        logger.error(f"Error retrieving sessions for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve download history")

@app.post("/api/video/batch-download")
async def batch_download(
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Add multiple videos to download queue"""
    try:
        data = await request.json()
        videos = data.get('videos', [])
        
        if not videos:
            raise HTTPException(status_code=400, detail="No videos provided")
        
        if len(videos) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 videos per batch")
        
        logger.info(f"User {current_user} adding {len(videos)} videos to batch download")
        
        added_count = 0
        for video in videos:
            url = video.get('url')
            platform = video.get('platform')
            format_id = video.get('format_id', 'best')
            
            if not url or not platform:
                logger.warning(f"Skipping invalid video: {video}")
                continue
            
            if platform not in downloaders:
                logger.warning(f"Skipping unsupported platform: {platform}")
                continue
            
            try:
                queue_id = auth_manager.add_to_download_queue(
                    username=current_user,
                    url=url,
                    platform=platform,
                    format_id=format_id
                )
                added_count += 1
                logger.info(f"Added video to queue: {queue_id}")
                
            except Exception as e:
                logger.error(f"Failed to add video to queue: {str(e)}")
        
        logger.info(f"Successfully added {added_count} videos to download queue for user {current_user}")
        
        return {
            "message": f"Added {added_count} videos to download queue",
            "total": added_count
        }
        
    except ValueError as e:
        logger.warning(f"Invalid batch download input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch download error for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Batch download failed. Please try again.")

@app.get("/api/user/download-queue")
async def get_download_queue(
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Get user's download queue"""
    try:
        logger.info(f"User {current_user} requesting download queue")
        
        queue = auth_manager.get_download_queue(username=current_user)
        
        logger.info(f"Retrieved {len(queue)} items from download queue for user {current_user}")
        return queue
        
    except Exception as e:
        logger.error(f"Error retrieving download queue for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve download queue")

@app.get("/api/user/stats")
async def get_user_stats(
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Get user download statistics"""
    try:
        logger.info(f"User {current_user} requesting download stats")
        
        stats = auth_manager.get_user_stats(current_user)
        
        logger.info(f"Retrieved stats for user {current_user}")
        return stats
        
    except Exception as e:
        logger.error(f"Error retrieving stats for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user statistics")

@app.post("/api/video/convert")
async def convert_video(
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager)
):
    """Convert downloaded video to different format"""
    video_path = None
    converted_path = None
    try:
        data = await request.json()
        url = data.get('url')
        platform = data.get('platform')
        format_id = data.get('format_id', 'best')
        output_format = data.get('output_format', 'mp4')
        quality = data.get('quality', 'medium')
        resolution = data.get('resolution')
        
        if not url or not platform:
            raise HTTPException(status_code=400, detail="URL and platform required")
        
        if platform not in downloaders:
            raise HTTPException(status_code=400, detail="Unsupported platform")
        
        logger.info(f"User {current_user} converting video from {url} on {platform} to {output_format}")
        
        downloader = downloaders[platform]
        
        # Download video first
        video_path = await downloader.download(url, format_id)
        
        # Set up conversion
        converter = VideoConverter()
        import tempfile
        converted_file = tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False)
        converted_file.close()
        converted_path = Path(converted_file.name)
        
        # Progress callback for conversion
        user_id = f"user_{current_user}"
        def conversion_progress(progress_data):
            asyncio.create_task(send_progress_update(user_id, progress_data))
        
        # Convert video
        result_path = await converter.convert_video(
            input_path=video_path,
            output_path=converted_path,
            output_format=output_format,
            quality=quality,
            resolution=resolution,
            progress_callback=conversion_progress
        )
        
        # Track conversion
        auth_manager.track_download(
            username=current_user,
            url=url,
            platform=platform,
            title=f"Converted to {output_format}",
            format_id=f"{format_id}->{output_format}",
            status="completed"
        )
        
        # Stream converted file and delete after
        async def iterfile():
            try:
                async with aiofiles.open(result_path, 'rb') as file:
                    while chunk := await file.read(1024 * 1024):  # 1MB chunks
                        yield chunk
            except Exception as e:
                logger.error(f"Error streaming converted video: {str(e)}")
            finally:
                # Delete files after streaming
                try:
                    if video_path and video_path.exists():
                        video_path.unlink()
                    if result_path and result_path.exists():
                        result_path.unlink()
                    logger.info(f"Cleaned up conversion files")
                except Exception as e:
                    logger.warning(f"Failed to cleanup conversion files: {str(e)}")
        
        return StreamingResponse(
            iterfile(),
            media_type=f"video/{output_format}",
            headers={
                "Content-Disposition": f"attachment; filename=video_{uuid.uuid4().hex[:8]}.{output_format}"
            }
        )
        
    except ValueError as e:
        logger.warning(f"Invalid conversion input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Video conversion error: {str(e)}")
        
        # Cleanup any temporary files
        for path in [video_path, converted_path]:
            if path and path.exists():
                try:
                    path.unlink()
                except:
                    pass
        
        raise HTTPException(status_code=500, detail="Video conversion failed. Please try again.")

@app.get("/api/video/converter/info")
async def get_converter_info():
    """Get video conversion information"""
    converter = VideoConverter()
    
    return {
        "supported_formats": converter.get_supported_formats(),
        "quality_presets": converter.get_quality_presets(),
        "resolution_presets": converter.get_resolution_presets()
    }

@app.post("/api/video/schedule")
async def schedule_download(
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager),
    scheduler: DownloadScheduler = Depends(get_scheduler)
):
    """Schedule a download for future processing"""
    try:
        data = await request.json()
        url = data.get('url')
        platform = data.get('platform')
        format_id = data.get('format_id', 'best')
        priority = data.get('priority', 0)
        
        if not url or not platform:
            raise HTTPException(status_code=400, detail="URL and platform required")
        
        if platform not in downloaders:
            raise HTTPException(status_code=400, detail="Unsupported platform")
        
        logger.info(f"User {current_user} scheduling download: {url}")
        
        # Schedule download
        queue_id = scheduler.schedule_download(
            username=current_user,
            url=url,
            platform=platform,
            format_id=format_id,
            priority=priority
        )
        
        logger.info(f"Scheduled download {queue_id} for user {current_user}")
        
        return {
            "message": "Download scheduled successfully",
            "queue_id": queue_id,
            "url": url,
            "platform": platform
        }
        
    except ValueError as e:
        logger.warning(f"Invalid schedule input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Schedule download error for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to schedule download. Please try again.")

@app.delete("/api/video/schedule/{queue_id}")
async def cancel_scheduled_download(
    queue_id: int,
    current_user: str = Depends(get_current_user),
    scheduler: DownloadScheduler = Depends(get_scheduler)
):
    """Cancel a scheduled download"""
    try:
        logger.info(f"User {current_user} cancelling download {queue_id}")
        
        success = scheduler.cancel_download(queue_id, current_user)
        
        if success:
            logger.info(f"Cancelled download {queue_id} for user {current_user}")
            return {"message": "Download cancelled successfully"}
        else:
            logger.warning(f"Failed to cancel download {queue_id} for user {current_user}")
            raise HTTPException(status_code=404, detail="Download not found or cannot be cancelled")
        
    except Exception as e:
        logger.error(f"Cancel download error for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel download. Please try again.")

@app.get("/api/scheduler/status")
async def get_scheduler_status(
    current_user: str = Depends(get_current_user),
    scheduler: DownloadScheduler = Depends(get_scheduler)
):
    """Get download scheduler status"""
    try:
        logger.info(f"User {current_user} requesting scheduler status")
        
        status = scheduler.get_queue_status(username=current_user)
        
        logger.info(f"Retrieved scheduler status for user {current_user}")
        return status
        
    except Exception as e:
        logger.error(f"Error getting scheduler status for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve scheduler status")

@app.get("/api/scheduler/stats")
async def get_scheduler_stats(
    current_user: str = Depends(get_current_user),
    auth_manager: DatabaseAuthManager = Depends(get_auth_manager),
    scheduler: DownloadScheduler = Depends(get_scheduler)
):
    """Get detailed scheduler statistics (admin only)"""
    try:
        # Check if user is admin
        user = auth_manager.get_user_by_username(current_user)
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        logger.info(f"Admin {current_user} requesting scheduler stats")
        
        stats = scheduler.get_scheduler_stats()
        
        logger.info(f"Retrieved scheduler stats for admin {current_user}")
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scheduler stats for admin {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve scheduler statistics")

@app.websocket("/ws")
async def websocket_route(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time updates"""
    await websocket_endpoint(websocket, token or "anonymous")