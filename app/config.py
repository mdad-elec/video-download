import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Settings:
    APP_NAME = "Video Downloader Service"
    VERSION = "1.0.0"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
    
    # SQLite Database (local file)
    DB_PATH = Path("./data/app.db")
    DB_PATH.parent.mkdir(exist_ok=True)
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    
    # Temp directory
    TEMP_DIR = Path("/tmp/video_downloads")
    TEMP_DIR.mkdir(exist_ok=True)

    # External integrations
    _cookie_path = os.getenv("YOUTUBE_COOKIES_FILE")
    YOUTUBE_COOKIES_FILE = Path(_cookie_path).expanduser() if _cookie_path else None

    _tiktok_cookie_path = os.getenv("TIKTOK_COOKIES_FILE")
    TIKTOK_COOKIES_FILE = Path(_tiktok_cookie_path).expanduser() if _tiktok_cookie_path else None
    
    # Download limits
    MAX_VIDEO_DURATION = 3600  # 1 hour
    MAX_CONCURRENT_DOWNLOADS = 3
    
    # Cleanup settings
    CLEANUP_INTERVAL_SECONDS = 60
    MAX_TEMP_FILE_AGE_SECONDS = 300

settings = Settings()
