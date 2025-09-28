import yt_dlp
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, Any
from .base import BaseDownloader
from ..config import settings
from ..utils.video_processor import VideoProcessor
from ..utils.logger import logger

class TwitterDownloader(BaseDownloader):
    
    def _extract_tweet_id(self, url: str) -> Optional[str]:
        patterns = [
            r'twitter\.com/.*/status/(\d+)',
            r'x\.com/.*/status/(\d+)',
            r'mobile\.twitter\.com/.*/status/(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _extract_twitter_url(self, url: str) -> str:
        tweet_id = self._extract_tweet_id(url)
        if tweet_id:
            return f'https://twitter.com/i/web/status/{tweet_id}'
        return url
    
    def _select_video_entry(self, info: Optional[Dict[str, Any]], tweet_id: Optional[str] = None):
        """Return a single video entry and its 1-based playlist index."""
        if not info:
            return None, None

        if info.get('_type') == 'playlist':
            entries = info.get('entries') or []
            chosen_entry = None
            chosen_index = None
            for idx, entry in enumerate(entries, start=1):
                candidate, _ = self._select_video_entry(entry, tweet_id)
                if not candidate:
                    continue
                entry_id = entry.get('id') or entry.get('webpage_url_basename')
                if tweet_id and entry_id == tweet_id:
                    return candidate, idx
                if chosen_entry is None:
                    chosen_entry = candidate
                    chosen_index = idx
            return chosen_entry, chosen_index

        formats = info.get('formats') or []
        if any(f.get('vcodec') != 'none' for f in formats):
            return info, None

        if info.get('vcodec') and info.get('vcodec') != 'none':
            return info, None

        return None, None

    def _has_video_content(self, info, tweet_id: Optional[str] = None) -> bool:
        entry, _ = self._select_video_entry(info, tweet_id)
        return entry is not None
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        clean_url = self._extract_twitter_url(url)
        tweet_id = self._extract_tweet_id(url)

        cookie_file = self._get_cookie_file()
        if cookie_file:
            try:
                size = cookie_file.stat().st_size
                logger.info(f"Using configured Twitter cookies file: {cookie_file} (size: {size} bytes)")
            except Exception:
                logger.info(f"Using configured Twitter cookies file: {cookie_file}")

        entry, _, _ = await self._resolve_video_entry(clean_url, tweet_id, cookie_file)

        return {
            'title': entry.get('description', entry.get('title', 'Twitter/X Video')),
            'duration': entry.get('duration', 0),
            'thumbnail': entry.get('thumbnail', ''),
            'uploader': entry.get('uploader', ''),
            'formats': self._get_available_formats(entry),
            'platform': 'twitter'
        }

    async def _resolve_video_entry(self, clean_url: str, tweet_id: Optional[str], cookie_file: Optional[Path]):
        configs = [
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            },
            {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
                }
            },
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

        for i, base_config in enumerate(configs):
            try:
                config = base_config.copy()
                if cookie_file:
                    config['cookiefile'] = str(cookie_file)

                def extract_info():
                    with yt_dlp.YoutubeDL(config) as ydl:
                        return ydl.extract_info(clean_url, download=False)

                info = await loop.run_in_executor(None, extract_info)

                video_entry, playlist_index = self._select_video_entry(info, tweet_id)
                if not video_entry:
                    raise Exception("No video content found in this tweet")

                return video_entry, playlist_index, config

            except Exception as e:
                last_error = e
                if i == len(configs) - 1:
                    if 'No video content found' in str(e) and not cookie_file:
                        raise Exception("Could not fetch Twitter/X video info after multiple attempts: No video content found in this tweet. It may require login. Set TWITTER_COOKIES_FILE and retry.")
                    raise Exception(f"Could not fetch Twitter/X video info after multiple attempts: {str(e)}")
                continue

        raise Exception(f"Could not fetch Twitter/X video info after multiple attempts: {str(last_error)}")
    
    async def download(self, url: str, format_id: str = 'best',
                       start_time: Optional[float] = None, 
                       end_time: Optional[float] = None) -> Path:
        """Download Twitter/X video"""
        clean_url = self._extract_twitter_url(url)
        tweet_id = self._extract_tweet_id(url)

        temp_file = self.create_temp_file()
        output_path = Path(temp_file.name)

        if format_id == 'best':
            format_id = 'bestvideo+bestaudio/best'

        cookie_file = self._get_cookie_file()
        if cookie_file:
            try:
                size = cookie_file.stat().st_size
                logger.info(f"Using configured Twitter cookies file: {cookie_file} (size: {size} bytes)")
            except Exception:
                logger.info(f"Using configured Twitter cookies file: {cookie_file}")

        entry_info, playlist_index, _ = await self._resolve_video_entry(clean_url, tweet_id, cookie_file)
        download_target = (
            entry_info.get('webpage_url') or
            entry_info.get('original_url') or
            entry_info.get('url') or
            clean_url
        )

        download_configs = [
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'retries': 10,
                'fragment_retries': 10,
                'file_access_retries': 10,
                'extractor_retries': 10,
                'sleep_interval': 3,
                'sleep_interval_requests': 3,
                'concurrent_fragment_downloads': 4,
                'timeout': 60,
                'socket_timeout': 60,
                'http_chunk_size': 10485760,
                'buffersize': 1048576,
                'nopart': False,
                'nocheckcertificate': True,
                'noplaylist': True,
            },
            {
                'format': format_id,
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'retries': 10,
                'fragment_retries': 10,
                'file_access_retries': 10,
                'extractor_retries': 10,
                'sleep_interval': 3,
                'sleep_interval_requests': 3,
                'concurrent_fragment_downloads': 4,
                'timeout': 60,
                'socket_timeout': 60,
                'http_chunk_size': 10485760,
                'buffersize': 1048576,
                'nopart': False,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
                },
                'noplaylist': True,
            },
            {
                'format': 'best[ext=mp4]/best',
                'outtmpl': str(output_path.parent / f"{output_path.stem}.%(ext)s"),
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'retries': 10,
                'fragment_retries': 10,
                'file_access_retries': 10,
                'extractor_retries': 10,
                'sleep_interval': 5,
                'sleep_interval_requests': 5,
                'concurrent_fragment_downloads': 2,
                'timeout': 90,
                'socket_timeout': 90,
                'http_chunk_size': 10485760,
                'buffersize': 1048576,
                'nopart': False,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'TwitterAndroid/10.21.1-release.0 (29900000-r-0) OnePlus/ONEPLUS_A5000 Android/9',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                },
                'noplaylist': True,
            }
        ]

        last_error = None
        for base_config in download_configs:
            try:
                config = base_config.copy()
                if cookie_file:
                    config['cookiefile'] = str(cookie_file)
                config.setdefault('noplaylist', True)

                downloaded_file = await self.verify_and_retry_download(download_target, config, max_retries=2)

                if start_time is not None or end_time is not None:
                    processor = VideoProcessor()
                    trimmed_path = await processor.trim_video(
                        downloaded_file,
                        output_path,
                        start_time,
                        end_time
                    )
                    asyncio.create_task(self.cleanup_file(downloaded_file, delay=1))
                    return trimmed_path
                else:
                    return downloaded_file

            except Exception as e:
                last_error = e
                logger.warning(f"Twitter download config failed: {str(e)}")
                continue

        if last_error:
            if 'No video content found' in str(last_error) and not cookie_file:
                raise Exception("Could not download Twitter/X video after multiple configuration attempts: No video content found in this tweet. It may require login. Set TWITTER_COOKIES_FILE and retry.")
            raise Exception(f"Could not download Twitter/X video after multiple configuration attempts: {str(last_error)}")
    
    def _get_available_formats(self, info: Dict) -> list:
        """Extract available formats"""
        formats = []
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none':
                # Safely get quality - ensure it's numeric
                quality = f.get('quality')
                if quality is None:
                    # Estimate quality from height
                    height = f.get('height', 0)
                    quality = height
                
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
                    'resolution': f.get('resolution', f"{f.get('width', '?')}x{f.get('height', '?')}"),
                    'filesize': filesize,
                    'quality': quality
                })
        
        # Remove duplicates and sort safely
        unique_formats = {f['resolution']: f for f in formats}
        return sorted(unique_formats.values(), key=lambda x: int(x.get('quality', 0)), reverse=True)

    def _get_cookie_file(self) -> Optional[Path]:
        cookie_path = settings.TWITTER_COOKIES_FILE
        if cookie_path and cookie_path.exists():
            try:
                size = cookie_path.stat().st_size
                if size > 0:
                    return cookie_path
                logger.warning(f"Configured Twitter cookies file is empty: {cookie_path}")
            except Exception as exc:
                logger.warning(f"Failed to validate Twitter cookies file {cookie_path}: {exc}")
        return None
