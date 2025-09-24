import yt_dlp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import random

from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor
from ..config import settings
from ..utils.logger import logger

class YouTubeDownloader(BaseDownloader):
    
    def __init__(self):
        super().__init__()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        ]

    def _locate_cookie_file(self) -> Optional[Path]:
        """Try to locate a usable YouTube cookies file"""
        module_dir = Path(__file__).resolve().parent
        project_root = module_dir.parent.parent

        candidates: List[Path] = []

        if settings.YOUTUBE_COOKIES_FILE:
            candidates.append(Path(settings.YOUTUBE_COOKIES_FILE))

        relative_candidates = [
            Path('www.youtube.com_cookies.txt'),
            Path('./www.youtube.com_cookies.txt'),
        ]

        search_roots = [
            Path.cwd(),
            project_root,
            module_dir,
            Path.home(),
            Path.home() / 'Downloads',
        ]

        for root in search_roots:
            for rel in relative_candidates:
                candidates.append((root / rel).expanduser())

        seen: set[Path] = set()
        for candidate in candidates:
            expanded = candidate.expanduser()
            try:
                resolved = expanded.resolve(strict=False)
            except Exception:
                resolved = expanded

            if resolved in seen:
                continue
            seen.add(resolved)

            if resolved.is_file():
                logger.info(f"Using YouTube cookies file at {resolved}")
                return resolved

        logger.debug("No YouTube cookies file could be located; falling back to anonymous requests.")
        return None
    
    def _get_ydl_configs(self, url: str, cookie_path: Optional[Path]) -> List[Dict[str, Any]]:
        """Generate multiple yt-dlp configurations to try"""
        base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }

        common_opts: Dict[str, Any] = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'sleep_interval_requests': 1,
            'sleep_interval': 1,
            'retries': 3,
            'extractor_retries': 2,
            'file_access_retries': 2,
            'fragment_retries': 2,
            'concurrent_fragment_downloads': 1,
            'noprogress': True,
            'cachedir': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],
                }
            },
        }

        def build_config(format_string: str, user_agent: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            headers = {**base_headers, 'User-Agent': user_agent}
            cfg = dict(common_opts)
            cfg.update({
                'format': format_string,
                'user_agent': user_agent,
                'http_headers': headers,
            })
            if extra:
                cfg.update(extra)
            return cfg

        configs: List[Dict[str, Any]] = []

        if cookie_path:
            configs.append(build_config('best', random.choice(self.user_agents), {
                'cookiefile': str(cookie_path),
            }))

        configs.append(build_config('best', random.choice(self.user_agents)))

        configs.append(build_config('best[height<=720]/best', random.choice(self.user_agents), {
            'sleep_interval_requests': 2,
            'sleep_interval': 2,
        }))

        mobile_ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
        configs.append(build_config('best', mobile_ua, {
            'sleep_interval_requests': 3,
            'sleep_interval': 3,
        }))

        return configs
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get YouTube video metadata with multiple fallback strategies"""
        self.emit_progress({
            'status': 'info',
            'message': 'Fetching video information...',
            'progress': 0
        })
        
        cookie_path = self._locate_cookie_file()
        if not cookie_path:
            self.emit_progress({
                'status': 'warning',
                'message': 'No YouTube cookies configured; continuing without authentication. Some videos may require login.',
                'progress': 5
            })

        configs = self._get_ydl_configs(url, cookie_path)
        config_count = len(configs)
        last_error = None
        
        for i, ydl_opts in enumerate(configs):
            try:
                config_name = "Cookie Authentication" if i == 0 and 'cookiefile' in ydl_opts else f'Configuration {i+1}/{config_count}'
                self.emit_progress({
                    'status': 'info',
                    'message': f'Trying {config_name}...',
                    'progress': 10
                })
                
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
                
            except Exception as e:
                last_error = e
                config_name = "Cookie Authentication" if i == 0 and 'cookiefile' in ydl_opts else f'Configuration {i+1}'
                
                if "Sign in to confirm you're not a bot" in str(e):
                    if i == 0:  # Cookie authentication failed
                        self.emit_progress({
                            'status': 'warning',
                            'message': 'Cookie authentication failed, trying fallback methods...',
                            'progress': 20
                        })
                    else:
                        self.emit_progress({
                            'status': 'warning',
                            'message': f'{config_name} blocked by YouTube, trying next...',
                            'progress': 20 + (i * 20)
                        })
                else:
                    self.emit_progress({
                        'status': 'warning',
                        'message': f'{config_name} failed: {str(e)}',
                        'progress': 20 + (i * 20)
                    })
                
                # Wait before trying next configuration
                if i < len(configs) - 1:
                    await asyncio.sleep(2)
        
        # All configurations failed
        error_msg = "YouTube is requiring authentication or all configurations failed. Please try again later or use a different video platform."
        self.emit_progress({
            'status': 'error',
            'message': error_msg,
            'progress': 0
        })
        raise Exception(error_msg)
    
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
        
        # Use multiple configurations for download as well
        cookie_path = self._locate_cookie_file()
        if not cookie_path:
            self.emit_progress({
                'status': 'warning',
                'message': 'No YouTube cookies configured; attempting download without authentication.',
                'progress': 5
            })

        configs = self._get_ydl_configs(url, cookie_path)
        config_count = len(configs)
        last_error = None

        for i, base_opts in enumerate(configs):
            try:
                config_name = "Cookie Authentication" if i == 0 and 'cookiefile' in base_opts else f'Download Configuration {i+1}/{config_count}'
                self.emit_progress({
                    'status': 'info',
                    'message': f'Trying {config_name}...',
                    'progress': 5
                })
                
                ydl_opts = {
                    **base_opts,
                    'format': self._get_format_string(format_id),
                    'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
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
                        'progress': 10
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
                        start_time, 
                        end_time, 
                        output_path
                    )
                    
                    # Clean up temp file
                    if downloaded_file.exists():
                        downloaded_file.unlink()
                    
                    return trimmed_path
                else:
                    # Direct download
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
                    
                    return await loop.run_in_executor(None, download_video)
                    
            except Exception as e:
                last_error = e
                config_name = "Cookie Authentication" if i == 0 and 'cookiefile' in base_opts else f'Download Configuration {i+1}'
                
                if "Sign in to confirm you're not a bot" in str(e):
                    if i == 0:  # Cookie authentication failed
                        self.emit_progress({
                            'status': 'warning',
                            'message': 'Cookie authentication failed, trying fallback methods...',
                            'progress': 10
                        })
                    else:
                        self.emit_progress({
                            'status': 'warning',
                            'message': f'{config_name} blocked, trying next...',
                            'progress': 10 + (i * 5)
                        })
                else:
                    self.emit_progress({
                        'status': 'warning',
                        'message': f'{config_name} failed: {str(e)}',
                        'progress': 10 + (i * 5)
                    })
                
                # Wait before trying next configuration
                if i < config_count - 1:
                    await asyncio.sleep(2)
        
        # All configurations failed
        error_msg = "YouTube download failed due to authentication or network issues. Please try again later."
        self.emit_progress({
            'status': 'error',
            'message': error_msg,
            'progress': 0
        })
        raise Exception(error_msg)
    
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
