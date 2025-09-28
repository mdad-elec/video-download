from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
import tempfile
import os
import asyncio
from pathlib import Path
import yt_dlp
import ffmpeg
from ..utils.logger import logger

class BaseDownloader(ABC):
    """Base class for all platform downloaders"""
    
    def __init__(self):
        self.temp_dir = Path("/tmp/video_downloads")
        self.temp_dir.mkdir(exist_ok=True)
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def set_progress_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set progress callback for real-time updates"""
        self.progress_callback = callback
    
    def emit_progress(self, progress_data: Dict[str, Any]):
        """Emit progress update if callback is set"""
        if self.progress_callback:
            self.progress_callback(progress_data)
    
    @abstractmethod
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get video metadata without downloading"""
        pass
    
    @abstractmethod
    async def download(self, url: str, start_time: Optional[float] = None, 
                      end_time: Optional[float] = None, format_id: str = 'best') -> Path:
        """Download video and return temporary file path"""
        pass
    
    def create_temp_file(self, suffix=".mp4"):
        """Create a temporary file that will be auto-deleted"""
        return tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=suffix, 
            dir=self.temp_dir
        )

    def _apply_common_ydl_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize yt-dlp options for consistent mp4 outputs."""
        opts = options
        opts.setdefault('prefer_ffmpeg', True)
        opts.setdefault('merge_output_format', 'mp4')
        opts.setdefault('format_sort', ['vcodec:h264', 'acodec:m4a', 'br'])

        pp_args = list(opts.get('postprocessor_args', []))
        if '-movflags' not in pp_args:
            pp_args.extend(['-movflags', 'faststart'])
        opts['postprocessor_args'] = pp_args

        postprocessors = opts.setdefault('postprocessors', [])
        if not any(pp.get('key') == 'FFmpegMetadata' for pp in postprocessors):
            postprocessors.append({'key': 'FFmpegMetadata'})

        return opts

    async def _ensure_quicktime_compat(self, filepath: Path) -> Path:
        """Re-encode the file if needed so it plays with QuickTime and keeps audio."""

        loop = asyncio.get_event_loop()

        def convert_if_required() -> Path:
            try:
                probe = ffmpeg.probe(str(filepath))
            except Exception as exc:
                logger.debug(f"ffprobe failed for {filepath}: {exc}")
                return filepath

            format_names = probe.get('format', {}).get('format_name', '')
            format_set = {name.strip() for name in format_names.split(',') if name}
            video_stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video'), {})
            audio_stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'audio'), {})

            video_codec = video_stream.get('codec_name', '')
            audio_codec = audio_stream.get('codec_name', '')
            pix_fmt = video_stream.get('pix_fmt', '')

            container_ok = bool(format_set.intersection({'mp4', 'mov', 'm4a', '3gp', '3g2', 'mj2'}))
            video_ok = video_codec in {'h264', 'avc1'}
            audio_ok = (not audio_stream) or audio_codec in {'aac', 'mp4a'}
            pix_ok = not pix_fmt or pix_fmt in {'yuv420p', 'yuvj420p'}

            if container_ok and video_ok and audio_ok and pix_ok:
                return filepath

            target_path = filepath if filepath.suffix.lower() == '.mp4' else filepath.with_suffix('.mp4')
            temp_output = target_path.parent / f"{target_path.stem}_qt{target_path.suffix}"

            try:
                if temp_output.exists():
                    temp_output.unlink()

                input_stream = ffmpeg.input(str(filepath))
                output_stream = ffmpeg.output(
                    input_stream,
                    str(temp_output),
                    vcodec='libx264',
                    acodec='aac',
                    pix_fmt='yuv420p',
                    movflags='faststart',
                    preset='veryfast',
                    crf=20,
                    audio_bitrate='192k',
                    ar=48000,
                )
                ffmpeg.run(output_stream, overwrite_output=True, quiet=True)

                if target_path.exists() and target_path != filepath:
                    target_path.unlink()

                if target_path == filepath:
                    replacement_path = filepath.with_name(f"{filepath.stem}_orig{filepath.suffix}")
                    filepath.rename(replacement_path)
                    temp_output.rename(target_path)
                    try:
                        replacement_path.unlink()
                    except Exception:
                        pass
                else:
                    temp_output.rename(target_path)
                    if filepath.exists() and filepath != target_path:
                        filepath.unlink()

                logger.info(f"Converted {filepath} to QuickTime-compatible {target_path}")
                return target_path

            except Exception as exc:
                logger.warning(f"Failed to transcode {filepath} for QuickTime compatibility: {exc}")
                if temp_output.exists():
                    try:
                        temp_output.unlink()
                    except Exception:
                        pass
                return filepath

        return await loop.run_in_executor(None, convert_if_required)
    
    async def cleanup_file(self, filepath: Path, delay: int = 5):
        """Delete file after delay"""
        await asyncio.sleep(delay)
        try:
            if filepath.exists():
                os.unlink(filepath)
        except:
            pass
    
    async def wait_for_file_write(self, filepath: Path, max_wait: int = 10) -> bool:
        """Wait for file to be fully written"""
        import time
        
        start_time = time.time()
        last_size = 0
        stable_count = 0
        
        while time.time() - start_time < max_wait:
            try:
                if not filepath.exists():
                    await asyncio.sleep(0.5)
                    continue
                
                current_size = filepath.stat().st_size
                
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 3:  # File size stable for 1.5 seconds
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
                
                await asyncio.sleep(0.5)
            except:
                await asyncio.sleep(0.5)
        
        return False
    
    async def verify_and_retry_download(self, url: str, ydl_opts: dict, max_retries: int = 3) -> Path:
        """Download with verification and automatic retry"""
        import tempfile
        import time

        for attempt in range(max_retries):
            logger.info(f"Download attempt {attempt + 1}/{max_retries} for {url}")
            
            # Create unique temp file for this attempt
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4', dir=self.temp_dir)
            temp_file.close()
            temp_path = Path(temp_file.name)
            stem = temp_path.stem

            # Remove the placeholder file so yt-dlp can create the real one
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            
            # Update output template for this attempt
            attempt_opts = self._apply_common_ydl_options(ydl_opts.copy())
            attempt_opts['outtmpl'] = str(temp_path.parent / f"{stem}.%(ext)s")
            attempt_opts.setdefault('overwrites', True)
            
            try:
                # Download with yt-dlp
                with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                    ydl.download([url])
                
                # Wait for file to be fully written
                await asyncio.sleep(2)  # Initial wait
                
                # Find the actual downloaded file
                downloaded_file = None
                
                # Check for various file extensions
                for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.3gp']:
                    potential_file = temp_path.parent / f"{stem}.{ext}"
                    if potential_file.exists():
                        # Wait and verify file is fully written
                        if await self.wait_for_file_write(potential_file, max_wait=15):
                            file_size = potential_file.stat().st_size
                            if file_size > 1024:  # At least 1KB
                                logger.info(f"Successfully downloaded {file_size} bytes to {potential_file}")
                                downloaded_file = potential_file
                                break
                            else:
                                logger.warning(f"File too small: {file_size} bytes")
                                # Clean up small file
                                try:
                                    potential_file.unlink()
                                except:
                                    pass
                        else:
                            logger.warning(f"File write timeout for {potential_file}")
                
                # Check for similar named files (yt-dlp sometimes adds suffixes)
                if not downloaded_file:
                    temp_dir = temp_path.parent
                    for file in temp_dir.glob(f"{stem}*"):
                        if file.is_file() and any(file.suffix.lower() == ext for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.3gp']):
                            if await self.wait_for_file_write(file, max_wait=15):
                                file_size = file.stat().st_size
                                if file_size > 1024:
                                    logger.info(f"Successfully downloaded {file_size} bytes to {file}")
                                    downloaded_file = file
                                    break
                                else:
                                    logger.warning(f"File too small: {file_size} bytes")
                                    try:
                                        file.unlink()
                                    except:
                                        pass
                
                if downloaded_file:
                    # Final verification
                    await asyncio.sleep(1)
                    final_size = downloaded_file.stat().st_size
                    if final_size > 1024:
                        logger.info(f"Download verification successful: {final_size} bytes")
                        quicktime_safe = await self._ensure_quicktime_compat(downloaded_file)
                        return quicktime_safe
                    else:
                        logger.warning(f"Final verification failed: {final_size} bytes")
                        try:
                            downloaded_file.unlink()
                        except:
                            pass
                else:
                    logger.warning(f"No valid file found after download attempt {attempt + 1}")
                
                # Clean up temp file if it exists
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass
                
                # If this isn't the last attempt, wait before retrying
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # Progressive wait: 5s, 10s, 15s
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                
                # Clean up any temp files
                for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv', '.m4v', '.3gp']:
                    potential_file = temp_path.parent / f"{stem}.{ext}"
                    if potential_file.exists():
                        try:
                            potential_file.unlink()
                        except:
                            pass
                
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
        
        # All attempts failed
        raise Exception(f"Failed to download {url} after {max_retries} attempts")
