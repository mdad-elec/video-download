import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class FacebookDownloader(BaseDownloader):
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get Facebook video metadata"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'cookiefile': '/tmp/fb_cookies.txt',  # Optional: for private videos
        }
        
        loop = asyncio.get_event_loop()
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        try:
            info = await loop.run_in_executor(None, extract_info)
            
            return {
                'title': info.get('title', 'Facebook Video'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': self._get_available_formats(info),
                'platform': 'facebook'
            }
        except Exception as e:
            raise Exception(f"Could not fetch Facebook video info: {str(e)}")
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download Facebook video"""
        
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path.with_suffix('')),
            'quiet': True,
            'no_warnings': True,
            'no_playlist': True,
            'cookiefile': '/tmp/fb_cookies.txt',  # Optional
        }
        
        loop = asyncio.get_event_loop()
        
        if start_time is not None or end_time is not None:
            # Download full video first
            temp_full = self.create_temp_file()
            ydl_opts['outtmpl'] = str(Path(temp_full.name).with_suffix(''))
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find actual file
                    for ext in ['.mp4', '.webm', '.mkv']:
                        potential_file = Path(str(Path(temp_full.name).with_suffix('')) + ext)
                        if potential_file.exists():
                            return potential_file
                    return Path(temp_full.name)
            
            downloaded_file = await loop.run_in_executor(None, download_video)
            
            # Trim video
            processor = VideoProcessor()
            trimmed_path = await processor.trim_video(
                downloaded_file, 
                output_path,
                start_time, 
                end_time
            )
            
            # Clean up
            asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
            
            return trimmed_path
        else:
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for ext in ['.mp4', '.webm', '.mkv']:
                        potential_file = Path(str(output_path.with_suffix('')) + ext)
                        if potential_file.exists():
                            return potential_file
                    return output_path
            
            return await loop.run_in_executor(None, download_video)
    
    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats"""
        formats = []
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none':
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f.get('ext', 'mp4'),
                    'resolution': f.get('resolution', f.get('height', 'Unknown')),
                    'filesize': f.get('filesize', 0),
                    'quality': f.get('quality', f.get('height', 0))
                })
        return sorted(formats, key=lambda x: x.get('quality', 0), reverse=True)