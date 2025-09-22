import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from sqlalchemy.orm import Session
from pathlib import Path
import uuid

from ..database.models import DownloadQueue, User
from ..database.auth import DatabaseAuthManager
from ..utils.logger import logger
from ..downloaders import YouTubeDownloader, TikTokDownloader, FacebookDownloader, TwitterDownloader

class DownloadScheduler:
    """Download scheduling and queue management system"""
    
    def __init__(self, db: Session, auth_manager: DatabaseAuthManager):
        self.db = db
        self.auth_manager = auth_manager
        self.downloaders = {
            'youtube': YouTubeDownloader(),
            'tiktok': TikTokDownloader(),
            'facebook': FacebookDownloader(),
            'twitter': TwitterDownloader(),
        }
        self.is_running = False
        self.current_downloads = {}
        self.max_concurrent_downloads = 3
        
    async def start(self):
        """Start the download scheduler"""
        if self.is_running:
            logger.warning("Download scheduler is already running")
            return
        
        self.is_running = True
        logger.info("Download scheduler started")
        
        # Start the main scheduler loop
        asyncio.create_task(self._scheduler_loop())
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_task())
    
    async def stop(self):
        """Stop the download scheduler"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Download scheduler stopping...")
        
        # Cancel all current downloads
        for download_id, task in self.current_downloads.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled download {download_id}")
        
        # Wait for downloads to finish
        if self.current_downloads:
            await asyncio.gather(*self.current_downloads.values(), return_exceptions=True)
        
        logger.info("Download scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.is_running:
            try:
                # Check if we can start new downloads
                available_slots = self.max_concurrent_downloads - len(self.current_downloads)
                
                if available_slots > 0:
                    # Get next downloads from queue
                    next_downloads = self._get_next_downloads(available_slots)
                    
                    for queue_item in next_downloads:
                        # Start download
                        task = asyncio.create_task(self._process_download(queue_item))
                        self.current_downloads[queue_item.id] = task
                        
                        # Update queue status
                        self.auth_manager.update_queue_status(
                            queue_item.id, 
                            "processing"
                        )
                        
                        logger.info(f"Started download {queue_item.id} for user {queue_item.user.username}")
                
                # Clean up completed downloads
                await self._cleanup_completed_downloads()
                
                # Wait before next iteration
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _process_download(self, queue_item: DownloadQueue):
        """Process a single download from the queue"""
        try:
            logger.info(f"Processing download {queue_item.id}: {queue_item.url}")
            
            # Get downloader
            downloader = self.downloaders.get(queue_item.platform)
            if not downloader:
                raise Exception(f"Unsupported platform: {queue_item.platform}")
            
            # Set up progress callback
            user_id = f"user_{queue_item.user.username}_{queue_item.id}"
            def progress_callback(data):
                # Here you could send WebSocket updates or save progress to database
                logger.debug(f"Download {queue_item.id} progress: {data}")
            
            downloader.set_progress_callback(progress_callback)
            
            # Download video
            result_path = await downloader.download(
                url=queue_item.url,
                format_id=queue_item.format_id
            )
            
            # Track successful download
            self.auth_manager.track_download(
                username=queue_item.user.username,
                url=queue_item.url,
                platform=queue_item.platform,
                format_id=queue_item.format_id,
                status="completed"
            )
            
            # Update queue status
            self.auth_manager.update_queue_status(
                queue_item.id, 
                "completed"
            )
            
            logger.info(f"Download {queue_item.id} completed successfully")
            
            # Clean up temporary file
            if result_path and result_path.exists():
                result_path.unlink()
            
        except Exception as e:
            logger.error(f"Download {queue_item.id} failed: {str(e)}")
            
            # Update queue status with error
            self.auth_manager.update_queue_status(
                queue_item.id, 
                "failed",
                str(e)
            )
            
            # Track failed download
            self.auth_manager.track_download(
                username=queue_item.user.username,
                url=queue_item.url,
                platform=queue_item.platform,
                format_id=queue_item.format_id,
                status="failed"
            )
    
    def _get_next_downloads(self, limit: int) -> List[DownloadQueue]:
        """Get next downloads from queue"""
        return self.db.query(DownloadQueue).filter(
            DownloadQueue.status == "queued"
        ).order_by(
            DownloadQueue.priority.desc(),
            DownloadQueue.created_at.asc()
        ).limit(limit).all()
    
    async def _cleanup_completed_downloads(self):
        """Clean up completed downloads from current_downloads dict"""
        completed_ids = []
        
        for download_id, task in self.current_downloads.items():
            if task.done():
                completed_ids.append(download_id)
                
                # Get the result or exception
                try:
                    await task
                except Exception as e:
                    logger.error(f"Download {download_id} completed with error: {str(e)}")
        
        # Remove completed downloads
        for download_id in completed_ids:
            self.current_downloads.pop(download_id, None)
    
    async def _cleanup_task(self):
        """Periodic cleanup task"""
        while self.is_running:
            try:
                # Clean up old completed/failed queue items
                deleted_count = self.auth_manager.cleanup_completed_queue(days_old=7)
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old queue items")
                
                # Clean up expired sessions
                session_count = self.auth_manager.cleanup_expired_sessions()
                
                if session_count > 0:
                    logger.info(f"Cleaned up {session_count} expired sessions")
                
                # Wait before next cleanup
                await asyncio.sleep(3600)  # Clean up every hour
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(3600)
    
    def schedule_download(
        self,
        username: str,
        url: str,
        platform: str,
        format_id: str = "best",
        priority: int = 0,
        scheduled_time: Optional[datetime] = None
    ) -> int:
        """Schedule a download for future processing"""
        
        try:
            # Validate inputs
            if platform not in self.downloaders:
                raise ValueError(f"Unsupported platform: {platform}")
            
            # Get user
            user = self.auth_manager.get_user_by_username(username)
            if not user:
                raise ValueError(f"User not found: {username}")
            
            # Add to queue
            queue_id = self.auth_manager.add_to_download_queue(
                username=username,
                url=url,
                platform=platform,
                format_id=format_id,
                priority=priority
            )
            
            logger.info(f"Scheduled download {queue_id} for user {username}")
            
            # If scheduled time is in the future, you could implement delayed processing
            if scheduled_time and scheduled_time > datetime.utcnow():
                logger.info(f"Download {queue_id} scheduled for {scheduled_time}")
                # Implementation for future scheduling would go here
            
            return queue_id
            
        except Exception as e:
            logger.error(f"Failed to schedule download: {str(e)}")
            raise
    
    def get_queue_status(self, username: str = None) -> Dict:
        """Get current queue status"""
        try:
            # Get queue counts
            total_queue = self.db.query(DownloadQueue).filter(
                DownloadQueue.status == "queued"
            ).count()
            
            processing = self.db.query(DownloadQueue).filter(
                DownloadQueue.status == "processing"
            ).count()
            
            completed_today = self.db.query(DownloadQueue).filter(
                DownloadQueue.status == "completed",
                DownloadQueue.completed_at >= datetime.utcnow().date()
            ).count()
            
            failed_today = self.db.query(DownloadQueue).filter(
                DownloadQueue.status == "failed",
                DownloadQueue.completed_at >= datetime.utcnow().date()
            ).count()
            
            result = {
                "total_in_queue": total_queue,
                "currently_processing": processing,
                "completed_today": completed_today,
                "failed_today": failed_today,
                "concurrent_downloads": len(self.current_downloads),
                "max_concurrent_downloads": self.max_concurrent_downloads,
                "scheduler_running": self.is_running
            }
            
            # Add user-specific stats if username provided
            if username:
                user = self.auth_manager.get_user_by_username(username)
                if user:
                    user_queue = self.db.query(DownloadQueue).filter(
                        DownloadQueue.user_id == user.id,
                        DownloadQueue.status == "queued"
                    ).count()
                    
                    user_processing = self.db.query(DownloadQueue).filter(
                        DownloadQueue.user_id == user.id,
                        DownloadQueue.status == "processing"
                    ).count()
                    
                    result["user_queue"] = user_queue
                    result["user_processing"] = user_processing
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {}
    
    def cancel_download(self, queue_id: int, username: str) -> bool:
        """Cancel a scheduled download"""
        try:
            # Get queue item
            queue_item = self.db.query(DownloadQueue).filter(
                DownloadQueue.id == queue_id
            ).first()
            
            if not queue_item:
                return False
            
            # Check if user owns this download
            if queue_item.user.username != username:
                return False
            
            # If it's currently processing, cancel the task
            if queue_item.status == "processing" and queue_id in self.current_downloads:
                task = self.current_downloads.get(queue_id)
                if task and not task.done():
                    task.cancel()
                
                # Remove from current downloads
                self.current_downloads.pop(queue_id, None)
            
            # Update queue status
            self.auth_manager.update_queue_status(
                queue_id, 
                "failed", 
                "Cancelled by user"
            )
            
            logger.info(f"Cancelled download {queue_id} for user {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling download: {str(e)}")
            return False
    
    def set_concurrent_limit(self, limit: int):
        """Set maximum concurrent downloads"""
        if limit < 1:
            limit = 1
        elif limit > 10:
            limit = 10
        
        self.max_concurrent_downloads = limit
        logger.info(f"Set concurrent download limit to {limit}")
    
    def get_scheduler_stats(self) -> Dict:
        """Get detailed scheduler statistics"""
        try:
            # Get platform statistics
            platform_stats = {}
            for platform in self.downloaders.keys():
                platform_total = self.db.query(DownloadQueue).filter(
                    DownloadQueue.platform == platform
                ).count()
                
                platform_completed = self.db.query(DownloadQueue).filter(
                    DownloadQueue.platform == platform,
                    DownloadQueue.status == "completed"
                ).count()
                
                platform_failed = self.db.query(DownloadQueue).filter(
                    DownloadQueue.platform == platform,
                    DownloadQueue.status == "failed"
                ).count()
                
                platform_stats[platform] = {
                    "total": platform_total,
                    "completed": platform_completed,
                    "failed": platform_failed,
                    "success_rate": (platform_completed / platform_total * 100) if platform_total > 0 else 0
                }
            
            return {
                "platform_stats": platform_stats,
                "current_downloads": len(self.current_downloads),
                "max_concurrent_downloads": self.max_concurrent_downloads,
                "scheduler_running": self.is_running,
                "uptime": "N/A"  # You could track start time for uptime
            }
            
        except Exception as e:
            logger.error(f"Error getting scheduler stats: {str(e)}")
            return {}