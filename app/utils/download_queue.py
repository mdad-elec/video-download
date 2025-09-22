import asyncio
import uuid
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from ..utils.logger import logger

class DownloadStatus(Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    TRIMMING = "trimming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class DownloadTask:
    id: str
    user_id: str
    url: str
    platform: str
    format_id: str = "best"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    progress_callback: Optional[Callable] = None

class DownloadQueue:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.queue: List[DownloadTask] = []
        self.active: Dict[str, DownloadTask] = {}
        self.completed: Dict[str, DownloadTask] = {}
        self.processing = False
        self._queue_event = asyncio.Event()
    
    async def add_download(self, user_id: str, url: str, platform: str, 
                          format_id: str = "best", start_time: Optional[float] = None,
                          end_time: Optional[float] = None,
                          progress_callback: Optional[Callable] = None) -> str:
        """Add a new download task to the queue"""
        
        task_id = str(uuid.uuid4())
        task = DownloadTask(
            id=task_id,
            user_id=user_id,
            url=url,
            platform=platform,
            format_id=format_id,
            start_time=start_time,
            end_time=end_time,
            progress_callback=progress_callback,
            message="Added to queue"
        )
        
        self.queue.append(task)
        logger.info(f"Added download task {task_id} for user {user_id}: {url}")
        
        # Start processing if not already running
        if not self.processing:
            asyncio.create_task(self._process_queue())
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get task by ID"""
        # Check active tasks
        if task_id in self.active:
            return self.active[task_id]
        
        # Check completed tasks
        if task_id in self.completed:
            return self.completed[task_id]
        
        # Check queue
        for task in self.queue:
            if task.id == task_id:
                return task
        
        return None
    
    def get_user_tasks(self, user_id: str) -> List[DownloadTask]:
        """Get all tasks for a specific user"""
        tasks = []
        
        # Add active tasks
        for task in self.active.values():
            if task.user_id == user_id:
                tasks.append(task)
        
        # Add queued tasks
        for task in self.queue:
            if task.user_id == user_id:
                tasks.append(task)
        
        # Add completed tasks (last 10)
        user_completed = [task for task in self.completed.values() 
                        if task.user_id == user_id]
        tasks.extend(sorted(user_completed, key=lambda x: x.created_at, reverse=True)[:10])
        
        return sorted(tasks, key=lambda x: x.created_at, reverse=True)
    
    def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a download task"""
        # Check if task is in queue
        for i, task in enumerate(self.queue):
            if task.id == task_id and task.user_id == user_id:
                task.status = DownloadStatus.CANCELLED
                task.message = "Cancelled by user"
                self.queue.pop(i)
                self.completed[task_id] = task
                logger.info(f"Cancelled queued task {task_id}")
                return True
        
        # Check if task is active (can't cancel active downloads for now)
        if task_id in self.active:
            task = self.active[task_id]
            if task.user_id == user_id:
                # For now, we can't cancel active downloads easily
                # In a real implementation, you'd need to interrupt the download process
                logger.warning(f"Cannot cancel active task {task_id}")
                return False
        
        return False
    
    async def _process_queue(self):
        """Process the download queue"""
        if self.processing:
            return
        
        self.processing = True
        logger.info("Starting download queue processor")
        
        try:
            while True:
                # Wait for tasks or exit if processing complete
                if not self.queue and not self.active:
                    self._queue_event.clear()
                    await self._queue_event.wait()
                
                # Start new tasks if under concurrency limit
                while (len(self.active) < self.max_concurrent and 
                       self.queue and 
                       self.queue[0].status == DownloadStatus.PENDING):
                    
                    task = self.queue.pop(0)
                    self.active[task.id] = task
                    asyncio.create_task(self._execute_task(task))
                
                # Clean up completed active tasks
                completed_tasks = [
                    task_id for task_id, task in self.active.items()
                    if task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]
                ]
                
                for task_id in completed_tasks:
                    task = self.active.pop(task_id)
                    self.completed[task_id] = task
                    
                    # Keep only last 100 completed tasks
                    if len(self.completed) > 100:
                        oldest = min(self.completed.keys(), 
                                   key=lambda k: self.completed[k].created_at)
                        self.completed.pop(oldest)
                
                # Wait a bit before checking again
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in download queue processor: {e}")
        finally:
            self.processing = False
            logger.info("Download queue processor stopped")
    
    async def _execute_task(self, task: DownloadTask):
        """Execute a single download task"""
        logger.info(f"Starting download task {task.id}: {task.url}")
        
        try:
            task.status = DownloadStatus.PREPARING
            task.started_at = datetime.now()
            task.progress = 0.0
            task.message = "Preparing download..."
            
            # Import here to avoid circular imports
            from ..downloaders import YouTubeDownloader, TikTokDownloader, FacebookDownloader, TwitterDownloader
            
            # Get the appropriate downloader
            downloaders = {
                'youtube': YouTubeDownloader(),
                'tiktok': TikTokDownloader(),
                'facebook': FacebookDownloader(),
                'twitter': TwitterDownloader(),
            }
            
            downloader = downloaders.get(task.platform)
            if not downloader:
                raise ValueError(f"Unsupported platform: {task.platform}")
            
            # Set progress callback
            def progress_callback(progress_data):
                task.progress = progress_data.get('progress', 0.0)
                task.message = progress_data.get('message', task.message)
                
                if task.progress_callback:
                    task.progress_callback({
                        'task_id': task.id,
                        'status': task.status.value,
                        'progress': task.progress,
                        'message': task.message
                    })
            
            downloader.set_progress_callback(progress_callback)
            
            # Get video info first
            task.message = "Fetching video info..."
            video_info = await downloader.get_video_info(task.url)
            
            # Download the video
            task.status = DownloadStatus.DOWNLOADING
            task.message = "Downloading video..."
            
            file_path = await downloader.download(
                url=task.url,
                format_id=task.format_id,
                start_time=task.start_time,
                end_time=task.end_time
            )
            
            # Get file size
            try:
                task.file_size = file_path.stat().st_size
            except:
                pass
            
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            task.message = "Download completed successfully"
            task.file_path = str(file_path)
            task.completed_at = datetime.now()
            
            logger.info(f"Completed download task {task.id}")
            
        except Exception as e:
            task.status = DownloadStatus.FAILED
            task.error = str(e)
            task.message = f"Download failed: {str(e)}"
            task.completed_at = datetime.now()
            
            logger.error(f"Failed download task {task.id}: {e}")
        
        finally:
            # Notify queue processor
            self._queue_event.set()
            
            # Final progress callback
            if task.progress_callback:
                task.progress_callback({
                    'task_id': task.id,
                    'status': task.status.value,
                    'progress': task.progress,
                    'message': task.message,
                    'error': task.error
                })

# Global download queue instance
download_queue = DownloadQueue()