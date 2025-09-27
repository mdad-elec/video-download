import yt_dlp
import asyncio
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor
from ..utils.logger import logger

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
        temp_file.close()
        output_path = Path(temp_file.name)
        stem = output_path.stem

        # Remove placeholder file so yt-dlp creates the real artifact
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        
        # Try multiple download configurations
        download_configs = [
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
                'retries': 3,
                'fragment_retries': 3,
                'file_access_retries': 3,
                'extractor_retries': 3,
                'sleep_interval': 2,
                'sleep_interval_requests': 2,
                'concurrent_fragment_downloads': 3,
            },
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                'retries': 3,
                'fragment_retries': 3,
                'file_access_retries': 3,
                'extractor_retries': 3,
                'sleep_interval': 2,
                'sleep_interval_requests': 2,
                'concurrent_fragment_downloads': 3,
            },
            {
                'format': 'best[ext=mp4]/best',
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
                },
                'retries': 3,
                'fragment_retries': 3,
                'file_access_retries': 3,
                'extractor_retries': 3,
                'sleep_interval': 3,
                'sleep_interval_requests': 3,
                'concurrent_fragment_downloads': 1,
            }
        ]
        
        loop = asyncio.get_event_loop()
        
        # Try different configurations until one works
        last_error = None
        for raw_config in download_configs:
            config = deepcopy(raw_config)
            config.setdefault('overwrites', True)
            try:
                if start_time is not None or end_time is not None:
                    # Download full video first
                    temp_full = self.create_temp_file()
                    temp_full.close()
                    temp_full_path = Path(temp_full.name)
                    temp_stem = temp_full_path.stem

                    if temp_full_path.exists():
                        try:
                            temp_full_path.unlink()
                        except OSError:
                            pass

                    config['outtmpl'] = str(temp_full_path.parent / f"{temp_stem}.%(ext)s")
            
                    def download_video():
                        try:
                            # Add progress hook for debugging
                            def debug_hook(d):
                                if d['status'] == 'error':
                                    logger.error(f"Facebook download error: {d.get('error', 'Unknown error')}")
                                elif d['status'] == 'finished':
                                    logger.info(f"Facebook download finished: {d.get('filename')}")
                            
                            config['progress_hooks'] = [debug_hook]
                            
                            with yt_dlp.YoutubeDL(config) as ydl:
                                ydl.download([clean_url])
                                # Find actual file
                                found_files = []
                                for ext in ['.mp4', '.webm', '.mkv']:
                                    potential_file = temp_full_path.parent / f"{temp_stem}.{ext}"
                                    if potential_file.exists():
                                        found_files.append(potential_file)
                                        # Verify file has content
                                        file_size = potential_file.stat().st_size
                                        logger.info(f"Found Facebook downloaded file: {potential_file}, size: {file_size} bytes")
                                        if file_size > 1024:
                                            return potential_file
                                        else:
                                            logger.warning(f"Facebook downloaded file is empty: {potential_file}")
                                            try:
                                                potential_file.unlink()
                                            except OSError:
                                                pass
                                
                                # List all files in directory for debugging
                                temp_dir = temp_full_path.parent
                                all_files = list(temp_dir.glob(f"{temp_stem}*"))
                                logger.warning(f"All files in Facebook temp directory: {all_files}")
                                
                                # Check for any potential matches
                                for file in all_files:
                                    if file.is_file():
                                        file_size = file.stat().st_size
                                        logger.warning(f"Facebook potential match: {file}, size: {file_size} bytes")
                                        if file_size > 1024:
                                            return file
                                        try:
                                            file.unlink()
                                        except OSError:
                                            pass
                                
                                # Fallback
                                logger.warning(f"No valid Facebook downloaded file found for stem: {temp_stem}")
                                logger.warning(f"Files found: {found_files}")
                                raise ValueError("Facebook download produced no usable file")
                        except Exception as e:
                            logger.error(f"Facebook download failed with exception: {str(e)}")
                            raise
                    
                    downloaded_file = await loop.run_in_executor(None, download_video)

                    if not downloaded_file.exists():
                        raise ValueError("Facebook download file missing after completion")

                    # Give the filesystem a moment to settle and ensure size is stable
                    previous_size = -1
                    for _ in range(3):
                        current_size = downloaded_file.stat().st_size
                        if current_size == previous_size:
                            break
                        previous_size = current_size
                        time.sleep(0.5)

                    if downloaded_file.stat().st_size <= 1024:
                        raise ValueError("Facebook download resulted in an empty file")
                    
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
                    config['outtmpl'] = str(output_path.parent / f"{stem}.%(ext)s")

                    def download_video():
                        try:
                            # Add progress hook for debugging
                            def debug_hook(d):
                                if d['status'] == 'error':
                                    logger.error(f"Facebook direct download error: {d.get('error', 'Unknown error')}")
                                elif d['status'] == 'finished':
                                    logger.info(f"Facebook direct download finished: {d.get('filename')}")
                            
                            config['progress_hooks'] = [debug_hook]
                            
                            with yt_dlp.YoutubeDL(config) as ydl:
                                ydl.download([clean_url])
                                stem = output_path.stem
                                found_files = []
                                for ext in ['.mp4', '.webm', '.mkv']:
                                    potential_file = output_path.parent / f"{stem}.{ext}"
                                    if potential_file.exists():
                                        found_files.append(potential_file)
                                        # Verify file has content
                                        file_size = potential_file.stat().st_size
                                        logger.info(f"Found Facebook direct downloaded file: {potential_file}, size: {file_size} bytes")
                                        if file_size > 1024:
                                            return potential_file
                                        else:
                                            logger.warning(f"Facebook direct downloaded file is empty: {potential_file}")
                                            try:
                                                potential_file.unlink()
                                            except OSError:
                                                pass
                                
                                # Check original output path
                                if output_path.exists():
                                    file_size = output_path.stat().st_size
                                    logger.info(f"Facebook original output file size: {file_size} bytes")
                                    if file_size > 1024:
                                        return output_path
                                    try:
                                        output_path.unlink()
                                    except OSError:
                                        pass
                                
                                # List all files in directory for debugging
                                temp_dir = output_path.parent
                                all_files = list(temp_dir.glob(f"{stem}*"))
                                logger.warning(f"All files in Facebook direct temp directory: {all_files}")
                                
                                # Check for any potential matches
                                for file in all_files:
                                    if file.is_file():
                                        file_size = file.stat().st_size
                                        logger.warning(f"Facebook direct potential match: {file}, size: {file_size} bytes")
                                        if file_size > 1024:
                                            return file
                                        try:
                                            file.unlink()
                                        except OSError:
                                            pass
                                
                                # Fallback
                                logger.warning(f"No valid Facebook direct downloaded file found for stem: {stem}")
                                logger.warning(f"Files found: {found_files}")
                                raise ValueError("Facebook direct download produced no usable file")
                        except Exception as e:
                            logger.error(f"Facebook direct download failed with exception: {str(e)}")
                            raise
                    
                    downloaded_file = await loop.run_in_executor(None, download_video)

                    if not downloaded_file.exists():
                        raise ValueError("Facebook direct download file missing after completion")

                    previous_size = -1
                    for _ in range(3):
                        current_size = downloaded_file.stat().st_size
                        if current_size == previous_size:
                            break
                        previous_size = current_size
                        time.sleep(0.5)

                    if downloaded_file.stat().st_size <= 1024:
                        raise ValueError("Facebook direct download resulted in an empty file")

                    return downloaded_file
                    
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
