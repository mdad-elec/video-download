import yt_dlp
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor

class TwitterDownloader(BaseDownloader):
    
    def _extract_twitter_url(self, url: str) -> str:
        """Extract and normalize Twitter/X URL"""
        # Handle various Twitter URL formats
        patterns = [
            r'twitter\.com/.*/status/(\d+)',
            r'x\.com/.*/status/(\d+)',
            r'mobile\.twitter\.com/.*/status/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                tweet_id = match.group(1)
                return f'https://twitter.com/i/web/status/{tweet_id}'
        
        return url
    
    def _has_video_content(self, info) -> bool:
        """Check if the tweet contains video content"""
        if not info:
            return False
        
        # Check if there are any video formats
        formats = info.get('formats', [])
        video_formats = [f for f in formats if f.get('vcodec') != 'none']
        
        # Check for video-specific fields
        has_video_fields = any([
            info.get('duration'),
            info.get('width'),
            info.get('height'),
            len(video_formats) > 0
        ])
        
        return has_video_fields
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get Twitter/X video metadata"""
        # Clean and normalize URL
        clean_url = self._extract_twitter_url(url)
        
        # Try multiple configurations for Twitter
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
                    'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',  # Public guest token
                }
            },
            # Config with mobile user agent
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'TwitterAndroid/10.21.1-release.0 (29900000-r-0) OnePlus/ONEPLUS_A5000 Android/9',
                    'Accept': 'application/json',
                }
            }
        ]
        
        loop = asyncio.get_event_loop()
        last_error = None
        
        for i, config in enumerate(configs):
            try:
                def extract_info():
                    with yt_dlp.YoutubeDL(config) as ydl:
                        return ydl.extract_info(clean_url, download=False)
                
                info = await loop.run_in_executor(None, extract_info)
                
                # Check if tweet actually contains video
                if not self._has_video_content(info):
                    raise Exception("No video content found in this tweet")
                
                return {
                    'title': info.get('description', info.get('title', 'Twitter/X Video')),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', ''),
                    'formats': self._get_available_formats(info),
                    'platform': 'twitter'
                }
                
            except Exception as e:
                last_error = e
                if i == len(configs) - 1:  # Last attempt
                    raise Exception(f"Could not fetch Twitter/X video info after multiple attempts: {str(e)}")
                continue
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download Twitter/X video"""
        
        # Clean and normalize URL
        clean_url = self._extract_twitter_url(url)
        
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        # Twitter videos often have separate audio/video streams
        # Use bestvideo+bestaudio/best to ensure we get complete video
        if format_id == 'best':
            format_id = 'bestvideo+bestaudio/best'
        
        # Try multiple download configurations
        download_configs = [
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',  # Ensure mp4 output
            },
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
                }
            },
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'http_headers': {
                    'User-Agent': 'TwitterAndroid/10.21.1-release.0 (29900000-r-0) OnePlus/ONEPLUS_A5000 Android/9',
                    'Accept': 'application/json',
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
                        with yt_dlp.YoutubeDL(config) as ydl:
                            ydl.download([clean_url])
                            stem = output_path.stem
                            for ext in ['.mp4', '.webm', '.mkv', '.mov']:
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
            raise Exception(f"Could not download Twitter/X video after multiple attempts: {str(last_error)}")
    
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