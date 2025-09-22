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
        self.emit_progress({
            'status': 'info',
            'message': 'Fetching video information...',
            'progress': 0
        })
        
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
        
        self.emit_progress({
            'status': 'info_complete',
            'message': 'Video information retrieved',
            'progress': 100
        })
        
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
        """Download YouTube video with progress tracking"""
        
        self.emit_progress({
            'status': 'preparing',
            'message': 'Preparing download...',
            'progress': 0
        })
        
        # Create unique temp file
        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)
        
        # Progress hook function
        def progress_hook(d):
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0%')
                speed_str = d.get('_speed_str', 'N/A')
                eta_str = d.get('_eta_str', 'N/A')
                
                # Parse percentage
                try:
                    percent = float(percent_str.replace('%', ''))
                except:
                    percent = 0
                
                self.emit_progress({
                    'status': 'downloading',
                    'progress': percent,
                    'speed': speed_str,
                    'eta': eta_str,
                    'message': f'Downloading... {percent_str}'
                })
            elif d['status'] == 'finished':
                self.emit_progress({
                    'status': 'finished',
                    'progress': 100,
                    'message': 'Download complete'
                })
            elif d['status'] == 'error':
                self.emit_progress({
                    'status': 'error',
                    'progress': 0,
                    'message': f'Download error: {d.get("error", "Unknown error")}'
                })
        
        ydl_opts = {
            'format': self._get_format_string(format_id),
            'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            'no_playlist': True,
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }] if format_id != 'best' else []
        }
        
        # If trimming is needed, we'll post-process
        if start_time is not None or end_time is not None:
            self.emit_progress({
                'status': 'trimming_prep',
                'message': 'Preparing for trimming...',
                'progress': 0
            })
            
            # Download full video first
            temp_full = self.create_temp_file()
            ydl_opts['outtmpl'] = str(Path(temp_full.name).parent / f"{Path(temp_full.name).stem}.%(ext)s")
            
            loop = asyncio.get_event_loop()
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the actual downloaded file (yt-dlp may add extension)
                    stem = Path(temp_full.name).stem
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = Path(temp_full.name).parent / f"{stem}.{ext}"
                        if potential_file.exists():
                            return potential_file
                    return Path(temp_full.name)
            
            downloaded_file = await loop.run_in_executor(None, download_video)
            
            # Trim the video
            self.emit_progress({
                'status': 'trimming',
                'message': 'Trimming video...',
                'progress': 80
            })
            
            processor = VideoProcessor()
            trimmed_path = await processor.trim_video(
                downloaded_file, 
                output_path,
                start_time, 
                end_time
            )
            
            # Clean up full video immediately
            asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
            
            self.emit_progress({
                'status': 'complete',
                'progress': 100,
                'message': 'Download and trimming complete'
            })
            
            return trimmed_path
        else:
            # Direct download without trimming
            loop = asyncio.get_event_loop()
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the actual downloaded file
                    stem = output_path.stem
                    for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                        potential_file = output_path.parent / f"{stem}.{ext}"
                        if potential_file.exists():
                            return potential_file
                    return output_path
            
            result = await loop.run_in_executor(None, download_video)
            
            self.emit_progress({
                'status': 'complete',
                'progress': 100,
                'message': 'Download complete'
            })
            
            return result
    
    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats with better filtering"""
        formats = []
        
        # Add best format option
        formats.append({
            'format_id': 'best',
            'ext': 'mp4',
            'resolution': 'Best Quality',
            'filesize': None,
            'quality': 999,
            'fps': None,
            'vcodec': 'best',
            'acodec': 'best'
        })
        
        # Add specific formats
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                # Calculate file size if not available
                filesize = f.get('filesize') or f.get('filesize_approx')
                
                formats.append({
                    'format_id': f['format_id'],
                    'ext': f.get('ext', 'mp4'),
                    'resolution': f.get('resolution', f.get('format_note', 'Unknown')),
                    'filesize': filesize,
                    'quality': f.get('quality', 0),
                    'fps': f.get('fps'),
                    'vcodec': f.get('vcodec'),
                    'acodec': f.get('acodec'),
                    'height': f.get('height'),
                    'width': f.get('width')
                })
        
        # Sort by quality (height preference) and filter duplicates
        unique_formats = {}
        for fmt in formats:
            key = f"{fmt.get('height', 0)}p_{fmt.get('ext', 'mp4')}"
            if key not in unique_formats or fmt.get('quality', 0) > unique_formats[key].get('quality', 0):
                unique_formats[key] = fmt
        
        # Convert back to list and sort
        sorted_formats = list(unique_formats.values())
        sorted_formats.sort(key=lambda x: (
            0 if x['format_id'] == 'best' else 1,  # Keep 'best' first
            -(x.get('height', 0) or 0),  # Sort by height descending
            -(x.get('quality', 0))  # Then by quality
        ))
        
        return sorted_formats
    
    def _get_format_string(self, format_id: str) -> str:
        """Get yt-dlp format string from format ID"""
        format_map = {
            'best': 'bestvideo+bestaudio/best',
            '137': '137+140',  # 1080p mp4
            '136': '136+140',  # 720p mp4
            '135': '135+140',  # 480p mp4
            '134': '134+140',  # 360p mp4
            '133': '133+140',  # 240p mp4
            '18': '18',        # 360p mp4 (single file)
            '22': '22',        # 720p mp4 (single file)
        }
        
        return format_map.get(format_id, format_id)