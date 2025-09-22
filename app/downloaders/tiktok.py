import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class TikTokDownloader(BaseDownloader):
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get TikTok video metadata"""
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
                'title': info.get('description', info.get('title', 'TikTok Video')),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', ''),
                'view_count': info.get('view_count', 0),
                'formats': self._get_available_formats(info),
                'platform': 'tiktok'
            }
        except Exception as e:
            raise Exception(f"Could not fetch TikTok video info: {str(e)}")
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download TikTok video"""
        
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            # TikTok specific options
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        loop = asyncio.get_event_loop()
        
        if start_time is not None or end_time is not None:
            # Download full video first
            temp_full = self.create_temp_file()
            ydl_opts['outtmpl'] = str(Path(temp_full.name).parent / f"{Path(temp_full.name).stem}.%(ext)s")
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find actual file
                    stem = Path(temp_full.name).stem
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = Path(temp_full.name).parent / f"{stem}.{ext}"
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
                    stem = output_path.stem
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = output_path.parent / f"{stem}.{ext}"
                        if potential_file.exists():
                            return potential_file
                    return output_path
            
            return await loop.run_in_executor(None, download_video)
    
    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats"""
        formats = []
        
        # TikTok usually has limited format options
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none':
                resolution = f.get('resolution') or f"{f.get('width', '?')}x{f.get('height', '?')}"
                quality = f.get('quality') or f.get('height', 0)
                
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f.get('ext', 'mp4'),
                    'resolution': resolution,
                    'filesize': f.get('filesize', 0),
                    'quality': quality
                })
        
        # If no formats found, provide default
        if not formats:
            formats = [{
                'format_id': 'best',
                'ext': 'mp4',
                'resolution': 'Best Available',
                'filesize': 0,
                'quality': 1080
            }]
        
        return sorted(formats, key=lambda x: x.get('quality', 0), reverse=True)