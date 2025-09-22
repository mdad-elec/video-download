import asyncio
import os
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class TempFileCleanup:
    """Background service to clean up old temporary files"""
    
    def __init__(self, temp_dir: Path, max_age_seconds: int = 300):
        self.temp_dir = temp_dir
        self.max_age_seconds = max_age_seconds
        self.running = False
    
    async def start(self):
        """Start the cleanup service"""
        self.running = True
        while self.running:
            try:
                await self.cleanup_old_files()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            await asyncio.sleep(60)  # Run every minute
    
    async def cleanup_old_files(self):
        """Remove files older than max_age_seconds"""
        now = datetime.now()
        cutoff_time = now - timedelta(seconds=self.max_age_seconds)
        
        for filepath in self.temp_dir.glob("*"):
            if filepath.is_file():
                file_time = datetime.fromtimestamp(filepath.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        os.unlink(filepath)
                        logger.info(f"Cleaned up old file: {filepath}")
                    except Exception as e:
                        logger.error(f"Failed to delete {filepath}: {e}")
    
    def stop(self):
        """Stop the cleanup service"""
        self.running = False