import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor
from ..utils.logger import logger

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
            # TikTok specific options
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        }
        
        loop = asyncio.get_event_loop()
        
        if start_time is not None or end_time is not None:
            # Download full video first
            temp_full = self.create_temp_file()
            ydl_opts['outtmpl'] = str(Path(temp_full.name).parent / f"{Path(temp_full.name).stem}.%(ext)s")
            
            async def download_video():
                try:
                    # Add progress hook for debugging
                    def debug_hook(d):
                        if d['status'] == 'error':
                            logger.error(f"TikTok download error: {d.get('error', 'Unknown error')}")
                        elif d['status'] == 'finished':
                            logger.info(f"TikTok download finished: {d.get('filename')}")
                        elif d['status'] == 'downloading':
                            logger.info(f"TikTok downloading: {d.get('_percent_str', '0%')} - {d.get('_speed_str', 'N/A')}")
                    
                    ydl_opts['progress_hooks'] = [debug_hook]
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                        # Find actual file - support more file types
                        stem = Path(temp_full.name).stem
                        found_files = []
                        file_extensions = ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.3gp']
                        
                        for ext in file_extensions:
                            potential_file = Path(temp_full.name).parent / f"{stem}.{ext}"
                            if potential_file.exists():
                                # Wait for file to be fully written
                                await self.wait_for_file_write(potential_file)
                                file_size = potential_file.stat().st_size
                                logger.info(f"Found TikTok file: {potential_file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return potential_file
                                else:
                                    logger.warning(f"TikTok file is empty: {potential_file}")
                        
                        # Also check for files with similar names (yt-dlp sometimes adds suffixes)
                        temp_dir = Path(temp_full.name).parent
                        for file in temp_dir.glob(f"{stem}*"):
                            if file.is_file() and any(file.suffix.lower() == ext for ext in file_extensions):
                                # Wait for file to be fully written
                                await self.wait_for_file_write(file)
                                file_size = file.stat().st_size
                                logger.info(f"Found similar TikTok file: {file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return file
                        
                        # List all files in directory for debugging
                        temp_dir = Path(temp_full.name).parent
                        all_files = list(temp_dir.glob("*"))
                        logger.warning(f"All files in TikTok temp directory: {all_files}")
                        
                        # Check for any potential matches
                        for file in all_files:
                            if file.is_file() and stem in file.name:
                                file_size = file.stat().st_size
                                logger.warning(f"TikTok potential match: {file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return file
                        
                        logger.warning(f"No valid TikTok downloaded file found for stem: {stem}")
                        return Path(temp_full.name)
                except Exception as e:
                    logger.error(f"TikTok download failed with exception: {str(e)}")
                    raise
            
            downloaded_file = await download_video()
            
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
            async def download_video():
                try:
                    # Add progress hook for debugging
                    def debug_hook(d):
                        if d['status'] == 'error':
                            logger.error(f"TikTok direct download error: {d.get('error', 'Unknown error')}")
                        elif d['status'] == 'finished':
                            logger.info(f"TikTok direct download finished: {d.get('filename')}")
                        elif d['status'] == 'downloading':
                            logger.info(f"TikTok direct downloading: {d.get('_percent_str', '0%')} - {d.get('_speed_str', 'N/A')}")
                    
                    ydl_opts['progress_hooks'] = [debug_hook]
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                        stem = output_path.stem
                        found_files = []
                        file_extensions = ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.3gp']
                        
                        for ext in file_extensions:
                            potential_file = output_path.parent / f"{stem}.{ext}"
                            if potential_file.exists():
                                # Wait for file to be fully written
                                await self.wait_for_file_write(potential_file)
                                file_size = potential_file.stat().st_size
                                logger.info(f"Found TikTok direct file: {potential_file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return potential_file
                                else:
                                    logger.warning(f"TikTok direct file is empty: {potential_file}")
                        
                        # Also check for files with similar names (yt-dlp sometimes adds suffixes)
                        temp_dir = output_path.parent
                        for file in temp_dir.glob(f"{stem}*"):
                            if file.is_file() and any(file.suffix.lower() == ext for ext in file_extensions):
                                # Wait for file to be fully written
                                await self.wait_for_file_write(file)
                                file_size = file.stat().st_size
                                logger.info(f"Found similar TikTok direct file: {file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return file
                        
                        # Check original output path
                        if output_path.exists():
                            file_size = output_path.stat().st_size
                            logger.info(f"TikTok original output file size: {file_size} bytes")
                            if file_size > 0:
                                return output_path
                        
                        # List all files in directory for debugging
                        temp_dir = output_path.parent
                        all_files = list(temp_dir.glob("*"))
                        logger.warning(f"All files in TikTok direct temp directory: {all_files}")
                        
                        # Check for any potential matches
                        for file in all_files:
                            if file.is_file() and stem in file.name:
                                file_size = file.stat().st_size
                                logger.warning(f"TikTok direct potential match: {file}, size: {file_size} bytes")
                                if file_size > 0:
                                    return file
                        
                        logger.warning(f"No valid TikTok direct downloaded file found for stem: {stem}")
                        logger.warning(f"Files found: {found_files}")
                        return output_path
                except Exception as e:
                    logger.error(f"TikTok direct download failed with exception: {str(e)}")
                    raise
            
            return await download_video()
    
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