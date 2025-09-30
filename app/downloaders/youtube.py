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
        import time
        
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
        fresh_cookies = []
        stale_cookies = []
        
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
                try:
                    file_stat = resolved.stat()
                    file_size = file_stat.st_size
                    file_mtime = file_stat.st_mtime
                    current_time = time.time()

                    if file_size <= 100:
                        logger.warning(f"Found YouTube cookies file with insufficient data at {resolved} (size: {file_size} bytes)")
                        continue

                    age_hours = (current_time - file_mtime) / 3600

                    # Treat files updated within 48 hours as fresh. Older ones may still work, so keep as fallback.
                    if age_hours <= 48:
                        fresh_cookies.append(resolved)
                        logger.info(f"Found fresh YouTube cookies file at {resolved} (age: {age_hours:.1f}h, size: {file_size} bytes)")
                    elif age_hours <= 24 * 30:  # allow up to ~30 days as fallback
                        stale_cookies.append(resolved)
                        logger.warning(f"Found stale YouTube cookies file at {resolved} (age: {age_hours:.1f}h). Will use as fallback if no fresh cookies are available.")
                    else:
                        logger.warning(f"Ignoring very old YouTube cookies file at {resolved} (age: {age_hours:.1f}h)")
                except Exception as e:
                    logger.warning(f"Error checking cookies file {resolved}: {e}")

        cookie_pool = fresh_cookies or stale_cookies

        if cookie_pool:
            best_cookie = max(cookie_pool, key=lambda p: p.stat().st_mtime)
            if best_cookie in stale_cookies and not fresh_cookies:
                logger.warning("Using fallback stale YouTube cookies file; consider refreshing cookies soon.")
            logger.info(f"Using YouTube cookies file located at {best_cookie}")
            return best_cookie

        logger.debug("No valid YouTube cookies file could be located; falling back to anonymous requests.")
        return None
    
    def _get_ydl_configs(self, cookie_path: Optional[Path], *, for_info: bool = False) -> List[Dict[str, Any]]:
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
        }

        extractor_fallback = {
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],
                }
            }
        }

        def build_config(format_string: str, user_agent: str, extra: Optional[Dict[str, Any]] = None,
                         *, include_fallback_args: bool = True, set_headers: bool = True) -> Dict[str, Any]:
            cfg = dict(common_opts)
            if include_fallback_args:
                cfg.update(extractor_fallback)

            if set_headers:
                headers = {**base_headers, 'User-Agent': user_agent}
                cfg.update({
                    'user_agent': user_agent,
                    'http_headers': headers,
                })

            if not for_info:
                cfg['format'] = format_string
            else:
                cfg['skip_download'] = True

            if extra:
                cfg.update(extra)

            return cfg

        configs: List[Dict[str, Any]] = []

        if cookie_path:
            # Primary: Cookie-based configuration with optimal settings
            cookie_cfg = dict(common_opts)
            if for_info:
                cookie_cfg['skip_download'] = True
            else:
                cookie_cfg['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
            cookie_cfg.update({
                'cookiefile': str(cookie_path),
                'cookiefile_out': None,
                'nocheckcertificate': True,
                'sleep_interval_requests': 1,
                'sleep_interval': 1,
                'retries': 2,
                'extractor_retries': 2,
            })
            # Use a stable desktop UA that matches typical cookie exports
            cookie_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
            cookie_cfg['user_agent'] = cookie_user_agent
            cookie_cfg['http_headers'] = {**base_headers, 'User-Agent': cookie_user_agent}
            configs.append(cookie_cfg)
            
            # Fallback cookie configuration with different format selection
            cookie_cfg2 = dict(common_opts)
            if for_info:
                cookie_cfg2['skip_download'] = True
            else:
                cookie_cfg2['format'] = 'best[height<=1080]/best'
            cookie_cfg2.update({
                'cookiefile': str(cookie_path),
                'cookiefile_out': None,
                'nocheckcertificate': True,
                'sleep_interval_requests': 2,
                'sleep_interval': 2,
            })
            cookie_cfg2['user_agent'] = cookie_user_agent
            cookie_cfg2['http_headers'] = {**base_headers, 'User-Agent': cookie_user_agent}
            configs.append(cookie_cfg2)

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

        configs = self._get_ydl_configs(cookie_path, for_info=True)
        config_count = len(configs)
        last_error = None
        
        for i, ydl_opts in enumerate(configs):
            try:
                if 'cookiefile' in ydl_opts:
                    if i == 0:
                        config_name = "Cookie Authentication (Primary)"
                        progress_value = 10
                    elif i == 1:
                        config_name = "Cookie Authentication (Fallback)"
                        progress_value = 20
                    else:
                        config_name = f"Cookie Authentication ({i})"
                        progress_value = 10 + (i * 5)
                else:
                    config_name = f'Configuration {i+1}/{config_count}'
                    progress_value = 40 + (i * 10)
                
                self.emit_progress({
                    'status': 'info',
                    'message': f'Trying {config_name}...',
                    'progress': progress_value
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
                    if 'cookiefile' in ydl_opts:
                        if i == 0:
                            self.emit_progress({
                                'status': 'warning',
                                'message': 'Primary cookie authentication failed, trying fallback cookie method...',
                                'progress': 25
                            })
                        elif i == 1:
                            self.emit_progress({
                                'status': 'warning',
                                'message': 'Fallback cookie authentication failed, trying non-cookie methods...',
                                'progress': 35
                            })
                        else:
                            self.emit_progress({
                                'status': 'warning',
                                'message': f'{config_name} blocked by YouTube, trying next...',
                                'progress': 40 + (i * 10)
                            })
                    else:
                        self.emit_progress({
                            'status': 'warning',
                            'message': f'{config_name} blocked by YouTube, trying next...',
                            'progress': 40 + (i * 10)
                        })
                else:
                    self.emit_progress({
                        'status': 'warning',
                        'message': f'{config_name} failed: {str(e)}',
                        'progress': progress_value + 10
                    })
                
                # Wait before trying next configuration
                if i < len(configs) - 1:
                    await asyncio.sleep(2)
        
        # All configurations failed
        # Check if it's specifically a cookie failure
        cookie_failed = False
        for i, config in enumerate(configs):
            if 'cookiefile' in config:
                cookie_failed = True
                break
        
        if cookie_failed:
            error_msg = "YouTube cookies are invalid or expired. Please refresh your cookies to continue downloading."
            self.emit_progress({
                'status': 'cookie_error',
                'message': error_msg,
                'progress': 0,
                'platform': 'youtube'
            })
        else:
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

        configs = self._get_ydl_configs(cookie_path)
        config_count = len(configs)
        last_error = None

        for i, base_opts in enumerate(configs):
            try:
                if 'cookiefile' in base_opts:
                    if i == 0:
                        config_name = "Cookie Authentication (Primary)"
                        progress_value = 5
                    elif i == 1:
                        config_name = "Cookie Authentication (Fallback)"
                        progress_value = 15
                    else:
                        config_name = f"Cookie Authentication ({i})"
                        progress_value = 5 + (i * 5)
                else:
                    config_name = f'Download Configuration {i}/{config_count}'
                    progress_value = 30 + (i * 10)
                
                self.emit_progress({
                    'status': 'info',
                    'message': f'Trying {config_name}...',
                    'progress': progress_value
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
                    }]
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
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                # Add a progress hook to debug the download process
                                def debug_hook(d):
                                    if d['status'] == 'error':
                                        logger.error(f"Download error: {d.get('error', 'Unknown error')}")
                                    elif d['status'] == 'finished':
                                        logger.info(f"Download finished: {d.get('filename')}")
                                
                                ydl_opts['progress_hooks'] = [debug_hook]
                                ydl.download([url])
                                
                                # Find the actual downloaded file (yt-dlp may add extension)
                                stem = Path(temp_full.name).stem
                                found_files = []
                                for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                                    potential_file = Path(temp_full.name).parent / f"{stem}.{ext}"
                                    if potential_file.exists():
                                        found_files.append(potential_file)
                                        # Verify file has content
                                        file_size = potential_file.stat().st_size
                                        logger.info(f"Found downloaded file: {potential_file}, size: {file_size} bytes")
                                        if file_size > 0:
                                            return potential_file
                                        else:
                                            logger.warning(f"Downloaded file is empty: {potential_file}")
                                
                                # If no file found or all are empty, log detailed information
                                logger.warning(f"No valid downloaded file found for stem: {stem}")
                                logger.warning(f"Files found: {found_files}")
                                
                                # List all files in the directory for debugging
                                temp_dir = Path(temp_full.name).parent
                                all_files = list(temp_dir.glob("*"))
                                logger.warning(f"All files in temp directory: {all_files}")
                                
                                # Check if there are any recent files that might be the download
                                for file in all_files:
                                    if file.is_file() and stem in file.name:
                                        file_size = file.stat().st_size
                                        logger.warning(f"Potential match: {file}, size: {file_size} bytes")
                                        if file_size > 0:
                                            return file
                                
                                return Path(temp_full.name)
                        except Exception as e:
                            logger.error(f"Download failed with exception: {str(e)}")
                            raise
                    
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
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                # Add a progress hook to debug the download process
                                def debug_hook(d):
                                    if d['status'] == 'error':
                                        logger.error(f"Download error: {d.get('error', 'Unknown error')}")
                                    elif d['status'] == 'finished':
                                        logger.info(f"Download finished: {d.get('filename')}")
                                
                                ydl_opts['progress_hooks'] = [debug_hook]
                                ydl.download([url])
                                
                                # Find the actual downloaded file
                                stem = output_path.stem
                                found_files = []
                                for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                                    potential_file = output_path.parent / f"{stem}.{ext}"
                                    if potential_file.exists():
                                        found_files.append(potential_file)
                                        # Verify file has content
                                        file_size = potential_file.stat().st_size
                                        logger.info(f"Found downloaded file: {potential_file}, size: {file_size} bytes")
                                        if file_size > 0:
                                            return potential_file
                                        else:
                                            logger.warning(f"Downloaded file is empty: {potential_file}")
                                
                                # If no valid file found, check the original output path
                                if output_path.exists():
                                    file_size = output_path.stat().st_size
                                    logger.info(f"Original output file size: {file_size} bytes")
                                    if file_size > 0:
                                        return output_path
                                
                                # List all files in the directory for debugging
                                temp_dir = output_path.parent
                                all_files = list(temp_dir.glob("*"))
                                logger.warning(f"All files in temp directory: {all_files}")
                                
                                # Check if there are any recent files that might be the download
                                for file in all_files:
                                    if file.is_file() and stem in file.name:
                                        file_size = file.stat().st_size
                                        logger.warning(f"Potential match: {file}, size: {file_size} bytes")
                                        if file_size > 0:
                                            return file
                                
                                # Fallback
                                logger.warning(f"No valid downloaded file found for stem: {stem}")
                                logger.warning(f"Files found: {found_files}")
                                return output_path
                        except Exception as e:
                            logger.error(f"Download failed with exception: {str(e)}")
                            raise
                    
                    downloaded_file = await loop.run_in_executor(None, download_video)
                    
                    # Ensure MP4 compatibility for direct downloads
                    if downloaded_file.exists() and downloaded_file.stat().st_size > 0:
                        mp4_compatible_path = output_path.parent / f"{output_path.stem}_compatible.mp4"
                        processor = VideoProcessor()
                        final_path = await processor.ensure_mp4_compatibility(downloaded_file, mp4_compatible_path)
                        
                        # Clean up original if different
                        if final_path != downloaded_file:
                            asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
                        
                        return final_path
                    
                    return downloaded_file
                    
            except Exception as e:
                last_error = e
                config_name = "Cookie Authentication" if i == 0 and 'cookiefile' in base_opts else f'Download Configuration {i+1}'
                
                if "Sign in to confirm you're not a bot" in str(e):
                    if 'cookiefile' in base_opts:
                        if i == 0:
                            self.emit_progress({
                                'status': 'warning',
                                'message': 'Primary cookie authentication failed, trying fallback cookie method...',
                                'progress': 10
                            })
                        elif i == 1:
                            self.emit_progress({
                                'status': 'warning',
                                'message': 'Fallback cookie authentication failed, trying non-cookie methods...',
                                'progress': 20
                            })
                        else:
                            self.emit_progress({
                                'status': 'warning',
                                'message': f'{config_name} blocked by YouTube, trying next...',
                                'progress': 25 + (i * 5)
                            })
                    else:
                        self.emit_progress({
                            'status': 'warning',
                            'message': f'{config_name} blocked by YouTube, trying next...',
                            'progress': 25 + (i * 5)
                        })
                else:
                    self.emit_progress({
                        'status': 'warning',
                        'message': f'{config_name} failed: {str(e)}',
                        'progress': progress_value + 5
                    })
                
                # Wait before trying next configuration
                if i < config_count - 1:
                    await asyncio.sleep(2)
        
        # All configurations failed
        # Check if it's specifically a cookie failure
        cookie_failed = False
        for i, config in enumerate(configs):
            if 'cookiefile' in config:
                cookie_failed = True
                break
        
        if cookie_failed:
            error_msg = "YouTube cookies are invalid or expired. Please refresh your cookies to continue downloading."
            self.emit_progress({
                'status': 'cookie_error',
                'message': error_msg,
                'progress': 0,
                'platform': 'youtube'
            })
        else:
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
            'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
            '137': '137+140',  # 1080p mp4
            '136': '136+140',  # 720p mp4
            '135': '135+140',  # 480p mp4
            '134': '134+140',  # 360p mp4
            '133': '133+140',  # 240p mp4
            '18': '18',        # 360p mp4 (single file)
            '22': '22',        # 720p mp4 (single file)
        }
        
        return format_map.get(format_id, format_id)
