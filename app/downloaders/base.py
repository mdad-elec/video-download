from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
import tempfile
import os
import asyncio
from pathlib import Path

class BaseDownloader(ABC):
    """Base class for all platform downloaders"""
    
    def __init__(self):
        self.temp_dir = Path("/tmp/video_downloads")
        self.temp_dir.mkdir(exist_ok=True)
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def set_progress_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set progress callback for real-time updates"""
        self.progress_callback = callback
    
    def emit_progress(self, progress_data: Dict[str, Any]):
        """Emit progress update if callback is set"""
        if self.progress_callback:
            self.progress_callback(progress_data)
    
    @abstractmethod
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get video metadata without downloading"""
        pass
    
    @abstractmethod
    async def download(self, url: str, start_time: Optional[float] = None, 
                      end_time: Optional[float] = None, format_id: str = 'best') -> Path:
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