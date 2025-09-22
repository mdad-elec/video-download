import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class TwitterDownloader(BaseDownloader):
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get Twitter/X video metadata"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        loop = asyncio.get_event_loop()
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        try:
            info = await loop.run_in_executor(None, extract_info)
            
            return {
                'title': info.get('description', info.get('title', 'Twitter/X Video')),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', ''),
                'formats': self._get_available_formats(info),
                'platform': 'twitter'
            }
        except Exception as e:
            raise Exception(f"Could not fetch Twitter/X video info: {str(e)}")
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download Twitter/X video"""
        
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        # Twitter videos often have separate audio/video streams
        # Use bestvideo+bestaudio/best to ensure we get complete video
        if format_id == 'best':
            format_id = 'bestvideo+bestaudio/best'
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path.with_suffix('')),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',  # Ensure mp4 output
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
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
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
            if f.get('vcodec') != 'none':
                quality = f.get('quality')
                if quality is None:
                    # Estimate quality from height
                    height = f.get('height', 0)
                    quality = height
                
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f.get('ext', 'mp4'),
                    'resolution': f.get('resolution', f"{f.get('width', '?')}x{f.get('height', '?')}"),
                    'filesize': f.get('filesize', 0),
                    'quality': quality
                })
        
        # Remove duplicates and sort
        unique_formats = {f['resolution']: f for f in formats}
        return sorted(unique_formats.values(), key=lambda x: x.get('quality', 0), reverse=True)