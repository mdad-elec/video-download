import yt_dlp
import asyncio
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote

import httpx

from .base import BaseDownloader
from ..utils.video_processor import VideoProcessor
from ..utils.logger import logger

class FacebookDownloader(BaseDownloader):
    
    def _resolve_share_link(self, url: str, depth: int = 0) -> str:
        """Follow Facebook share links to their canonical destination."""
        if depth > 4 or not url:
            return url

        header_sets = [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            {
                # Facebook crawler user-agent often receives canonical URLs without login prompts
                'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        ]

        for headers in header_sets:
            try:
                response = httpx.get(
                    url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=httpx.Timeout(8.0, connect=5.0)
                )
            except Exception as exc:
                logger.debug(f"Failed to resolve Facebook share link {url} with headers {headers.get('User-Agent')}: {exc}")
                continue

            final_url = str(response.url)

            # If Facebook redirected us to login, attempt to extract the intended destination
            if 'facebook.com/login' in final_url:
                parsed = urlsplit(final_url)
                query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))

                next_url = query_params.get('next')
                if next_url:
                    decoded_next = unquote(next_url)
                    logger.info(f"Resolved Facebook share link via login redirect to {decoded_next}")
                    return self._resolve_share_link(decoded_next, depth + 1)

                # Try parsing canonical URL from the login HTML (og:url)
                canonical = self._extract_canonical_from_html(response.text)
                if canonical:
                    logger.info(f"Resolved Facebook share link via canonical meta to {canonical}")
                    return canonical

                # As a final fallback, if story parameters exist build a story URL
                story_fbid = query_params.get('story_fbid')
                page_id = query_params.get('id')
                if story_fbid and page_id:
                    story_url = f'https://www.facebook.com/story.php?story_fbid={story_fbid}&id={page_id}'
                    logger.info(f"Constructed Facebook story URL {story_url} from login redirect parameters")
                    return self._resolve_share_link(story_url, depth + 1)

                continue

            if final_url.rstrip('/') != url.rstrip('/'):
                logger.info(f"Resolved Facebook share link to {final_url}")
            return final_url

        return url

    def _extract_canonical_from_html(self, html: str) -> Optional[str]:
        if not html:
            return None

        # Common canonical markers
        patterns = [
            r"property=['\"]og:url['\"]\s+content=['\"]([^'\"]+)",
            r"<meta\s+content=['\"]([^'\"]+)['\"]\s+property=['\"]al:android:url['\"]",
            r'data-ploi="([^"]+)"'
        ]

        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1)
                if candidate:
                    return candidate
        return None

    def _extract_facebook_url(self, url: str) -> str:
        """Normalize Facebook URLs from various formats (share, watch, videos, etc.)."""
        if not url:
            return url

        clean_url = url.strip()

        # Auto-prefix scheme if missing
        if clean_url.startswith('facebook.com'):
            clean_url = f'https://{clean_url}'

        # Resolve share links that redirect to canonical URLs
        if 'facebook.com/share/' in clean_url:
            clean_url = self._resolve_share_link(clean_url)

        # Ensure we operate on standard host to simplify downstream handling
        clean_url = clean_url.replace('m.facebook.com', 'www.facebook.com')
        clean_url = clean_url.replace('mbasic.facebook.com', 'www.facebook.com')

        # Remove query params that embed duplicate URLs (e.g., rdid)
        try:
            split = urlsplit(clean_url)
            if 'facebook.com' in split.netloc:
                filtered_query = [
                    (key, value)
                    for key, value in parse_qsl(split.query, keep_blank_values=True)
                    if key.lower() not in {'rdid'}
                ]
                clean_url = urlunsplit((
                    split.scheme or 'https',
                    split.netloc,
                    split.path,
                    urlencode(filtered_query, doseq=True),
                    split.fragment
                ))
        except Exception as exc:
            logger.debug(f"Failed to normalize Facebook query string for {clean_url}: {exc}")

        # Handle facebook.com/watch/ URLs
        if 'facebook.com/watch/' in clean_url:
            match = re.search(r'facebook\.com/watch/.*[/?&]v=(\d+)', clean_url)
            if match:
                return f'https://www.facebook.com/watch/?v={match.group(1)}'

        # Handle facebook.com/video(s)/ URLs
        if 'facebook.com/video.php' in clean_url:
            return clean_url

        if 'facebook.com/videos/' in clean_url:
            match = re.search(r'facebook\.com/videos/(\d+)', clean_url)
            if match:
                return f'https://www.facebook.com/video.php?v={match.group(1)}'

        # Handle fb.watch short URLs
        if 'fb.watch/' in clean_url:
            return clean_url

        # Default: return normalized URL
        return clean_url
    
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
        
        # Normalize default format to capture audio + video when possible
        normalized_format = format_id
        if normalized_format == 'best':
            normalized_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'

        # Try multiple download configurations
        download_configs = [
            {
                'format': normalized_format,
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
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            },
            {
                'format': normalized_format,
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
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
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
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
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
                    config = self._apply_common_ydl_options(config)
            
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
                    config = self._apply_common_ydl_options(config)

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

                    # Ensure MP4 compatibility
                    mp4_compatible_path = output_path.parent / f"{output_path.stem}_compatible.mp4"
                    processor = VideoProcessor()
                    final_path = await processor.ensure_mp4_compatibility(downloaded_file, mp4_compatible_path)
                    
                    # Clean up original if different
                    if final_path != downloaded_file:
                        asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
                    
                    return final_path
                    
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
