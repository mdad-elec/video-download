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