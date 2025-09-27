import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor
from ..utils.logger import logger

class TikTokDownloader(BaseDownloader):
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get TikTok video metadata"""
        cookie_header = await self._prepare_cookie_header(url)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                'Referer': 'https://www.tiktok.com/',
            }
        }

        if cookie_header:
            ydl_opts['http_headers']['Cookie'] = cookie_header
        
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
        temp_file.close()
        output_path = Path(temp_file.name)

        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass

        cookie_header = await self._prepare_cookie_header(url)

        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
            'quiet': False,  # Enable for better debugging
            'no_warnings': False,
            'retries': 10,  # Increased retries
            'fragment_retries': 10,
            'file_access_retries': 10,
            'extractor_retries': 10,
            'sleep_interval': 3,
            'sleep_interval_requests': 3,
            'concurrent_fragment_downloads': 4,
            'timeout': 60,
            'socket_timeout': 60,
            'http_chunk_size': 10485760,  # 10MB chunks
            'buffersize': 1048576,  # 1MB buffer
            'nopart': False,  # Use partial files
            'nocheckcertificate': True,  # Skip cert validation for some platforms
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                }
            },
            # TikTok specific options with multiple user agents
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
        }

        if cookie_header:
            ydl_opts['http_headers']['Cookie'] = cookie_header
        
        loop = asyncio.get_event_loop()
        
        # Use the robust download method with retry mechanism
        try:
            downloaded_file = await self.verify_and_retry_download(url, ydl_opts, max_retries=3)
            
            if start_time is not None or end_time is not None:
                # Trim video if needed
                processor = VideoProcessor()
                trimmed_path = await processor.trim_video(
                    downloaded_file, 
                    output_path,
                    start_time, 
                    end_time
                )
                
                # Clean up original file
                asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
                
                return trimmed_path
            else:
                # Return the downloaded file directly
                return downloaded_file
                
        except Exception as e:
            logger.error(f"TikTok download failed after all retries: {str(e)}")
            raise

    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats"""
        formats = []
        
        # TikTok usually has limited format options
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none':
                resolution = f.get('resolution') or f"{f.get('width', '?')}x{f.get('height', '?')}"
                
                # Safely get quality - ensure it's numeric
                quality = f.get('quality')
                if quality is None:
                    quality = f.get('height', 0)
                
                # Convert to int if it's a string, or use 0 as fallback
                try:
                    quality = int(quality) if quality is not None else 0
                except (ValueError, TypeError):
                    quality = 0
                
                # Safely get filesize
                filesize = f.get('filesize', 0)
                try:
                    filesize = int(filesize) if filesize is not None else 0
                except (ValueError, TypeError):
                    filesize = 0
                
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f.get('ext', 'mp4'),
                    'resolution': resolution,
                    'filesize': filesize,
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
        
        # Sort by quality (numeric) safely
        return sorted(formats, key=lambda x: int(x.get('quality', 0)), reverse=True)

    async def _prepare_cookie_header(self, url: str) -> Optional[str]:
        """Fetch TikTok page to obtain fresh cookies for yt-dlp."""

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        }

        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                for endpoint in ["https://www.tiktok.com/", url]:
                    try:
                        await client.get(endpoint, headers=headers)
                    except Exception as exc:
                        logger.debug(f"TikTok cookie prefetch failed for {endpoint}: {exc}")
                        continue

                cookie_items = [(name, value) for name, value in client.cookies.items() if value]

                if cookie_items:
                    cookie_header = "; ".join(f"{name}={value}" for name, value in cookie_items)
                    field_names = [name for name, _ in cookie_items]
                    logger.debug(f"Prepared TikTok cookie header with fields: {field_names}")
                    return cookie_header
        except Exception as exc:
            logger.debug(f"TikTok cookie preparation failed: {exc}")

        return None
