import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile
import uuid
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class YouTubeDownloader(BaseDownloader):
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get YouTube video metadata"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        loop = asyncio.get_event_loop()
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(None, extract_info)
        
        return {
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'formats': self._get_available_formats(info),
            'platform': 'youtube'
        }
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download YouTube video"""
        
        # Create unique temp file
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path.with_suffix('')),  # Remove suffix, yt-dlp adds it
            'quiet': True,
            'no_warnings': True,
            'no_playlist': True,
        }
        
        # If trimming is needed, we'll post-process
        if start_time is not None or end_time is not None:
            # Download full video first
            temp_full = self.create_temp_file()
            ydl_opts['outtmpl'] = str(Path(temp_full.name).with_suffix(''))
            
            loop = asyncio.get_event_loop()
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the actual downloaded file (yt-dlp may add extension)
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = Path(str(Path(temp_full.name).with_suffix('')) + ext)
                        if potential_file.exists():
                            return potential_file
                    return Path(temp_full.name)
            
            downloaded_file = await loop.run_in_executor(None, download_video)
            
            # Trim the video
            processor = VideoProcessor()
            trimmed_path = await processor.trim_video(
                downloaded_file, 
                output_path,
                start_time, 
                end_time
            )
            
            # Clean up full video immediately
            asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
            
            return trimmed_path
        else:
            # Direct download without trimming
            loop = asyncio.get_event_loop()
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the actual downloaded file
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = Path(str(output_path.with_suffix('')) + ext)
                        if potential_file.exists():
                            return potential_file
                    return output_path
            
            return await loop.run_in_executor(None, download_video)
    
    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats"""
        formats = []
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f.get('resolution', 'Unknown'),
                    'filesize': f.get('filesize', 0),
                    'quality': f.get('quality', 0)
                })
        return sorted(formats, key=lambda x: x.get('quality', 0), reverse=True)