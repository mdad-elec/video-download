import yt_dlp
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class FacebookDownloader(BaseDownloader):
    
    def _extract_facebook_url(self, url: str) -> str:
        """Extract proper Facebook URL from various formats"""
        # Handle facebook.com/watch/ URLs
        if 'facebook.com/watch/' in url:
            match = re.search(r'facebook\.com/watch/.*[/?&]v=(\d+)', url)
            if match:
                return f'https://www.facebook.com/watch/?v={match.group(1)}'
        
        # Handle facebook.com/videos/ URLs
        if 'facebook.com/videos/' in url:
            # Extract video ID from path
            match = re.search(r'facebook\.com/videos/([^/?&]+)', url)
            if match:
                return f'https://www.facebook.com/video.php?v={match.group(1)}'
        
        # Handle fb.watch URLs
        if 'fb.watch/' in url:
            return url
        
        # Default: return original URL
        return url
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get Facebook video metadata"""
        # Clean and normalize URL
        clean_url = self._extract_facebook_url(url)
        
        # Try multiple configurations for Facebook
        configs = [
            # Basic config
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            },
            # Config with headers
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            },
            # Config with different extractor
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'extractor_args': {
                    'facebook': {
                        'player': 'imp',
                    }
                }
            }
        ]
        
        loop = asyncio.get_event_loop()
        
        for i, config in enumerate(configs):
            try:
                def extract_info():
                    with yt_dlp.YoutubeDL(config) as ydl:
                        return ydl.extract_info(clean_url, download=False)
                
                info = await loop.run_in_executor(None, extract_info)
                
                return {
                    'title': info.get('title', info.get('description', 'Facebook Video')),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', ''),
                    'view_count': info.get('view_count', 0),
                    'formats': self._get_available_formats(info),
                    'platform': 'facebook'
                }
                
            except Exception as e:
                if i == len(configs) - 1:  # Last attempt
                    raise Exception(f"Could not fetch Facebook video info after multiple attempts: {str(e)}")
                continue
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download Facebook video"""
        
        # Clean and normalize URL
        clean_url = self._extract_facebook_url(url)
        
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        # Try multiple download configurations
        download_configs = [
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
            },
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            }
        ]
        
        loop = asyncio.get_event_loop()
        
        # Try different configurations until one works
        last_error = None
        for config in download_configs:
            try:
                if start_time is not None or end_time is not None:
                    # Download full video first
                    temp_full = self.create_temp_file()
                    config['outtmpl'] = str(Path(temp_full.name).parent / f"{Path(temp_full.name).stem}.%(ext)s")
            
                    def download_video():
                        with yt_dlp.YoutubeDL(config) as ydl:
                            ydl.download([clean_url])
                            # Find actual file
                            stem = Path(temp_full.name).stem
                            for ext in ['.mp4', '.webm', '.mkv']:
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
                        with yt_dlp.YoutubeDL(config) as ydl:
                            ydl.download([clean_url])
                            stem = output_path.stem
                            for ext in ['.mp4', '.webm', '.mkv']:
                                potential_file = output_path.parent / f"{stem}.{ext}"
                                if potential_file.exists():
                                    return potential_file
                            return output_path
                    
                    return await loop.run_in_executor(None, download_video)
                    
            except Exception as e:
                last_error = e
                continue
        
        # If all configurations failed, raise the last error
        if last_error:
            raise Exception(f"Could not download Facebook video after multiple attempts: {str(last_error)}")
    
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