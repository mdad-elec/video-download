import ffmpeg
import asyncio
from pathlib import Path
from typing import Optional

class VideoProcessor:
    
    async def trim_video(self, input_path: Path, output_path: Path,
                        start_time: Optional[float] = None,
                        end_time: Optional[float] = None) -> Path:
        """Trim video using ffmpeg"""
        
        loop = asyncio.get_event_loop()
        
        def process():
            input_stream = ffmpeg.input(str(input_path))
            
            # Apply trimming
            if start_time is not None and end_time is not None:
                duration = end_time - start_time
                stream = input_stream.trim(start=start_time, duration=duration)
            elif start_time is not None:
                stream = input_stream.trim(start=start_time)
            elif end_time is not None:
                stream = input_stream.trim(end=end_time)
            else:
                stream = input_stream
            
            # Reset timestamps
            stream = stream.setpts('PTS-STARTPTS')
            
            # Output with fast encoding
            stream = ffmpeg.output(
                stream,
                str(output_path),
                codec='copy',  # Copy codec for speed
                avoid_negative_ts='make_zero'
            )
            
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            return output_path
        
        return await loop.run_in_executor(None, process)
    
    async def get_video_duration(self, filepath: Path) -> float:
        """Get video duration in seconds"""
        loop = asyncio.get_event_loop()
        
        def get_duration():
            probe = ffmpeg.probe(str(filepath))
            video_stream = next((stream for stream in probe['streams'] 
                               if stream['codec_type'] == 'video'), None)
            if video_stream:
                return float(video_stream['duration'])
            return 0.0
        
        return await loop.run_in_executor(None, get_duration)
    
    async def ensure_mp4_compatibility(self, input_path: Path, output_path: Path) -> Path:
        """Convert video to MP4 format with standard codecs for maximum compatibility"""
        
        loop = asyncio.get_event_loop()
        
        def convert():
            try:
                # Check if input is already MP4 with compatible codecs
                probe = ffmpeg.probe(str(input_path))
                video_stream = next((stream for stream in probe['streams'] 
                                   if stream['codec_type'] == 'video'), None)
                audio_stream = next((stream for stream in probe['streams'] 
                                   if stream['codec_type'] == 'audio'), None)
                
                # If already MP4 with h264/aac, just copy
                if (input_path.suffix.lower() == '.mp4' and 
                    video_stream and video_stream.get('codec_name') == 'h264' and
                    audio_stream and audio_stream.get('codec_name') == 'aac'):
                    return input_path
                
                # Convert to MP4 with standard codecs
                input_stream = ffmpeg.input(str(input_path))
                
                # Output with H.264 video and AAC audio for maximum compatibility
                stream = ffmpeg.output(
                    input_stream,
                    str(output_path),
                    vcodec='libx264',      # H.264 video codec
                    acodec='aac',          # AAC audio codec
                    movflags='+faststart',  # Enable web streaming
                    preset='fast',         # Balance between speed and quality
                    crf=23,                # Good quality default
                    strict='experimental'   # Allow experimental codecs if needed
                )
                
                ffmpeg.run(stream, overwrite_output=True, quiet=True)
                return output_path
                
            except Exception as e:
                # If conversion fails, try to just copy the streams
                try:
                    input_stream = ffmpeg.input(str(input_path))
                    stream = ffmpeg.output(
                        input_stream,
                        str(output_path),
                        codec='copy',
                        movflags='+faststart'
                    )
                    ffmpeg.run(stream, overwrite_output=True, quiet=True)
                    return output_path
                except:
                    # If all else fails, return original
                    return input_path
        
        return await loop.run_in_executor(None, convert)