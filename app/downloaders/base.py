from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import tempfile
import os
import asyncio
from pathlib import Path

class BaseDownloader(ABC):
    """Base class for all platform downloaders"""
    
    def __init__(self):
        self.temp_dir = Path("/tmp/video_downloads")
        self.temp_dir.mkdir(exist_ok=True)
    
    @abstractmethod
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get video metadata without downloading"""
        pass
    
    @abstractmethod
    async def download(self, url: str, start_time: Optional[float] = None, 
                      end_time: Optional[float] = None) -> Path:
        """Download video and return temporary file path"""
        pass
    
    def create_temp_file(self, suffix=".mp4"):
        """Create a temporary file that will be auto-deleted"""
        return tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=suffix, 
            dir=self.temp_dir
        )
    
    async def cleanup_file(self, filepath: Path, delay: int = 5):
        """Delete file after delay"""
        await asyncio.sleep(delay)
        try:
            if filepath.exists():
                os.unlink(filepath)
        except:
            pass