import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from ..utils.logger import logger

class VideoConverter:
    """Video format conversion utility"""
    
    SUPPORTED_FORMATS = {
        'mp4': {'video_codec': 'libx264', 'audio_codec': 'aac'},
        'webm': {'video_codec': 'libvpx-vp9', 'audio_codec': 'libopus'},
        'avi': {'video_codec': 'libx264', 'audio_codec': 'mp3'},
        'mkv': {'video_codec': 'libx264', 'audio_codec': 'aac'},
        'mov': {'video_codec': 'libx264', 'audio_codec': 'aac'},
        'flv': {'video_codec': 'libx264', 'audio_codec': 'aac'},
        'mp3': {'video_codec': None, 'audio_codec': 'libmp3lame'},  # Audio only
        'wav': {'video_codec': None, 'audio_codec': 'pcm_s16le'},  # Audio only
        'aac': {'video_codec': None, 'audio_codec': 'aac'},  # Audio only
    }
    
    PRESET_QUALITIES = {
        'high': {'crf': 18, 'preset': 'slow'},
        'medium': {'crf': 23, 'preset': 'medium'},
        'low': {'crf': 28, 'preset': 'fast'},
        'ultra': {'crf': 32, 'preset': 'ultrafast'}
    }
    
    def __init__(self):
        self.ffmpeg_path = 'ffmpeg'
    
    async def convert_video(
        self,
        input_path: Path,
        output_path: Path,
        output_format: str = 'mp4',
        quality: str = 'medium',
        resolution: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        progress_callback = None
    ) -> Path:
        """Convert video to different format with optional quality and resolution changes"""
        
        if output_format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported output format: {output_format}")
        
        if quality not in self.PRESET_QUALITIES:
            raise ValueError(f"Unsupported quality: {quality}")
        
        try:
            # Build ffmpeg command
            cmd = [self.ffmpeg_path, '-i', str(input_path)]
            
            # Add input options for trimming
            if start_time is not None:
                cmd.extend(['-ss', str(start_time)])
            if end_time is not None:
                cmd.extend(['-to', str(end_time)])
            
            # Add video codec options
            format_config = self.SUPPORTED_FORMATS[output_format]
            quality_config = self.PRESET_QUALITIES[quality]
            
            if format_config['video_codec']:
                cmd.extend(['-c:v', format_config['video_codec']])
                
                # Add quality options
                if output_format in ['mp4', 'webm', 'avi', 'mkv', 'mov', 'flv']:
                    cmd.extend(['-crf', str(quality_config['crf'])])
                    cmd.extend(['-preset', quality_config['preset']])
                
                # Add resolution scaling
                if resolution:
                    cmd.extend(['-vf', f'scale={resolution}'])
                
                # Add audio codec
                if format_config['audio_codec']:
                    cmd.extend(['-c:a', format_config['audio_codec']])
            else:
                # Audio only conversion
                cmd.extend(['-vn'])  # No video
                cmd.extend(['-c:a', format_config['audio_codec']])
            
            # Add output options
            cmd.extend(['-y', str(output_path)])  # Overwrite output file
            
            logger.info(f"Converting video: {input_path} -> {output_path}")
            logger.info(f"Conversion command: {' '.join(cmd)}")
            
            # Run conversion
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor progress
            if progress_callback:
                await self._monitor_progress(process, progress_callback)
            else:
                await process.wait()
            
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode().strip()
                raise Exception(f"Conversion failed: {error_msg}")
            
            logger.info(f"Video conversion completed: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Video conversion error: {str(e)}")
            raise
    
    async def extract_audio(
        self,
        input_path: Path,
        output_path: Path,
        audio_format: str = 'mp3',
        quality: str = 'medium'
    ) -> Path:
        """Extract audio from video file"""
        
        if audio_format not in ['mp3', 'wav', 'aac']:
            raise ValueError(f"Unsupported audio format: {audio_format}")
        
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', str(input_path),
                '-vn',  # No video
                '-c:a', self.SUPPORTED_FORMATS[audio_format]['audio_codec'],
                '-y',  # Overwrite output file
                str(output_path)
            ]
            
            # Add quality options for MP3
            if audio_format == 'mp3':
                quality_bitrates = {'high': '192k', 'medium': '128k', 'low': '96k', 'ultra': '64k'}
                cmd.extend(['-b:a', quality_bitrates.get(quality, '128k')])
            
            logger.info(f"Extracting audio: {input_path} -> {output_path}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.wait()
            
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode().strip()
                raise Exception(f"Audio extraction failed: {error_msg}")
            
            logger.info(f"Audio extraction completed: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Audio extraction error: {str(e)}")
            raise
    
    async def get_video_info(self, input_path: Path) -> Dict[str, Any]:
        """Get detailed video information using ffprobe"""
        
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(input_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"Failed to get video info")
            
            import json
            info = json.loads(stdout.decode())
            
            # Extract useful information
            video_stream = None
            audio_stream = None
            
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video' and video_stream is None:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and audio_stream is None:
                    audio_stream = stream
            
            result = {
                'format': info.get('format', {}).get('format_name', 'unknown'),
                'duration': float(info.get('format', {}).get('duration', 0)),
                'size': int(info.get('format', {}).get('size', 0)),
                'bit_rate': int(info.get('format', {}).get('bit_rate', 0)),
                'video': {},
                'audio': {}
            }
            
            if video_stream:
                result['video'] = {
                    'codec': video_stream.get('codec_name', 'unknown'),
                    'width': video_stream.get('width', 0),
                    'height': video_stream.get('height', 0),
                    'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                    'bit_rate': int(video_stream.get('bit_rate', 0))
                }
            
            if audio_stream:
                result['audio'] = {
                    'codec': audio_stream.get('codec_name', 'unknown'),
                    'sample_rate': int(audio_stream.get('sample_rate', 0)),
                    'channels': int(audio_stream.get('channels', 0)),
                    'bit_rate': int(audio_stream.get('bit_rate', 0))
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return {}
    
    async def _monitor_progress(self, process, progress_callback):
        """Monitor conversion progress and call callback"""
        total_duration = None
        current_time = 0
        
        while True:
            try:
                # Check if process has finished
                return_code = process.returncode
                if return_code is not None:
                    break
                
                # Read stderr for progress information
                line = await process.stderr.readline()
                if not line:
                    break
                
                line = line.decode().strip()
                if 'Duration' in line and 'start' in line:
                    # Extract duration from ffmpeg output
                    import re
                    duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                    if duration_match:
                        hours, minutes, seconds = duration_match.groups()
                        total_duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                
                elif 'time=' in line and total_duration:
                    # Extract current time from ffmpeg output
                    import re
                    time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                    if time_match:
                        hours, minutes, seconds = time_match.groups()
                        current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                        
                        # Calculate progress percentage
                        if total_duration > 0:
                            progress = min(100, (current_time / total_duration) * 100)
                            progress_callback({
                                'status': 'converting',
                                'progress': progress,
                                'current_time': current_time,
                                'total_time': total_duration
                            })
                
            except Exception as e:
                logger.error(f"Error monitoring progress: {str(e)}")
                break
        
        # Final progress update
        progress_callback({
            'status': 'completed',
            'progress': 100,
            'current_time': current_time,
            'total_time': total_duration
        })
    
    def get_supported_formats(self) -> Dict[str, list]:
        """Get list of supported input and output formats"""
        return {
            'input': ['mp4', 'webm', 'avi', 'mkv', 'mov', 'flv', 'wmv', '3gp'],
            'output': list(self.SUPPORTED_FORMATS.keys()),
            'audio_output': ['mp3', 'wav', 'aac']
        }
    
    def get_quality_presets(self) -> Dict[str, str]:
        """Get available quality presets"""
        return {
            'high': 'Best quality (larger file size)',
            'medium': 'Good quality (balanced)',
            'low': 'Lower quality (smaller file size)',
            'ultra': 'Lowest quality (fastest conversion)'
        }
    
    def get_resolution_presets(self) -> Dict[str, str]:
        """Get common resolution presets"""
        return {
            '3840x2160': '4K Ultra HD',
            '2560x1440': '1440p QHD',
            '1920x1080': '1080p Full HD',
            '1280x720': '720p HD',
            '854x480': '480p SD',
            '640x360': '360p',
            '426x240': '240p'
        }