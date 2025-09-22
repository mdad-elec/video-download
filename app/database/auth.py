import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from .models import User, Session as SessionModel, Download, VideoFormat, DownloadQueue
from .models import pwd_context

class DatabaseAuthManager:
    """Database-based authentication and session management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def register_user(self, username: str, email: str, password: str) -> bool:
        """Register a new user"""
        try:
            # Check if user already exists
            if self.get_user_by_username(username):
                raise ValueError("Username already exists")
            
            if self.get_user_by_email(email):
                raise ValueError("Email already exists")
            
            # Validate input
            if len(username) < 3 or len(username) > 20:
                raise ValueError("Username must be between 3 and 20 characters")
            
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters")
            
            # Create new user
            user = User(
                username=username,
                email=email
            )
            user.set_password(password)
            
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            
            return True
            
        except ValueError as e:
            raise e
        except Exception as e:
            self.db.rollback()
            raise Exception(f"Failed to register user: {str(e)}")
    
    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials"""
        user = self.get_user_by_username(username)
        if not user or not user.is_active:
            return False
        
        return user.verify_password(password)
    
    def create_token(self, username: str, expires_hours: int = 24) -> str:
        """Create authentication token"""
        user = self.get_user_by_username(username)
        if not user:
            raise ValueError("User not found")
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        
        # Create session record
        session = SessionModel(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours)
        )
        
        # Clean up expired sessions for this user
        self.db.query(SessionModel).filter(
            SessionModel.user_id == user.id,
            SessionModel.expires_at < datetime.utcnow()
        ).delete()
        
        self.db.add(session)
        self.db.commit()
        
        return token
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify authentication token and return username"""
        session = self.db.query(SessionModel).filter(
            SessionModel.token == token,
            SessionModel.is_active == True,
            SessionModel.expires_at > datetime.utcnow()
        ).first()
        
        if not session:
            return None
        
        return session.user.username
    
    def revoke_token(self, token: str) -> bool:
        """Revoke authentication token"""
        session = self.db.query(SessionModel).filter(
            SessionModel.token == token
        ).first()
        
        if session:
            session.is_active = False
            self.db.commit()
            return True
        
        return False
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def track_download(self, username: str, url: str, platform: str, title: str = None, 
                      format_id: str = None, file_size: int = None, status: str = "completed") -> bool:
        """Track user download"""
        user = self.get_user_by_username(username)
        if not user:
            return False
        
        download = Download(
            user_id=user.id,
            url=url,
            platform=platform,
            title=title,
            format_id=format_id,
            file_size=file_size,
            status=status
        )
        
        self.db.add(download)
        self.db.commit()
        
        return True
    
    def get_user_downloads(self, username: str, limit: int = 10) -> List[Dict]:
        """Get user's download history"""
        user = self.get_user_by_username(username)
        if not user:
            return []
        
        downloads = self.db.query(Download).filter(
            Download.user_id == user.id
        ).order_by(Download.download_time.desc()).limit(limit).all()
        
        return [download.to_dict() for download in downloads]
    
    def get_user_stats(self, username: str) -> Dict:
        """Get user download statistics"""
        user = self.get_user_by_username(username)
        if not user:
            return {}
        
        total_downloads = self.db.query(Download).filter(
            Download.user_id == user.id,
            Download.status == "completed"
        ).count()
        
        total_size = self.db.query(Download).filter(
            Download.user_id == user.id,
            Download.status == "completed"
        ).with_entities(Download.file_size).all()
        
        total_bytes = sum(size[0] or 0 for size in total_size)
        
        platform_stats = self.db.query(
            Download.platform,
            self.db.func.count(Download.id).label('count')
        ).filter(
            Download.user_id == user.id,
            Download.status == "completed"
        ).group_by(Download.platform).all()
        
        return {
            "total_downloads": total_downloads,
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "platform_breakdown": {platform: count for platform, count in platform_stats}
        }
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        deleted = self.db.query(SessionModel).filter(
            SessionModel.expires_at < datetime.utcnow()
        ).delete()
        
        self.db.commit()
        return deleted
    
    def get_active_users_count(self) -> int:
        """Get count of active users"""
        return self.db.query(User).filter(User.is_active == True).count()
    
    def get_total_downloads_count(self) -> int:
        """Get total downloads count"""
        return self.db.query(Download).filter(Download.status == "completed").count()
    
    def get_platform_stats(self) -> Dict:
        """Get platform-wide download statistics"""
        platform_stats = self.db.query(
            Download.platform,
            self.db.func.count(Download.id).label('count')
        ).filter(
            Download.status == "completed"
        ).group_by(Download.platform).all()
        
        return {platform: count for platform, count in platform_stats}
    
    def add_to_download_queue(self, username: str, url: str, platform: str, 
                            format_id: str = "best", priority: int = 0) -> int:
        """Add download to queue"""
        user = self.get_user_by_username(username)
        if not user:
            raise ValueError("User not found")
        
        queue_item = DownloadQueue(
            user_id=user.id,
            url=url,
            platform=platform,
            format_id=format_id,
            priority=priority
        )
        
        self.db.add(queue_item)
        self.db.commit()
        self.db.refresh(queue_item)
        
        return queue_item.id
    
    def get_download_queue(self, username: str = None, limit: int = 50) -> List[Dict]:
        """Get download queue"""
        query = self.db.query(DownloadQueue)
        
        if username:
            user = self.get_user_by_username(username)
            if user:
                query = query.filter(DownloadQueue.user_id == user.id)
        
        queue_items = query.order_by(
            DownloadQueue.priority.desc(),
            DownloadQueue.created_at.asc()
        ).limit(limit).all()
        
        return [item.to_dict() for item in queue_items]
    
    def update_queue_status(self, queue_id: int, status: str, error_message: str = None) -> bool:
        """Update queue item status"""
        queue_item = self.db.query(DownloadQueue).filter(
            DownloadQueue.id == queue_id
        ).first()
        
        if not queue_item:
            return False
        
        queue_item.status = status
        
        if status == "processing":
            queue_item.started_at = datetime.utcnow()
        elif status in ["completed", "failed"]:
            queue_item.completed_at = datetime.utcnow()
        
        if error_message:
            queue_item.error_message = error_message
        
        self.db.commit()
        return True
    
    def get_next_queue_item(self) -> Optional[DownloadQueue]:
        """Get next item from download queue"""
        return self.db.query(DownloadQueue).filter(
            DownloadQueue.status == "queued"
        ).order_by(
            DownloadQueue.priority.desc(),
            DownloadQueue.created_at.asc()
        ).first()
    
    def cleanup_completed_queue(self, days_old: int = 7) -> int:
        """Clean up completed queue items older than specified days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        deleted = self.db.query(DownloadQueue).filter(
            DownloadQueue.status.in_(["completed", "failed"]),
            DownloadQueue.completed_at < cutoff_date
        ).delete()
        
        self.db.commit()
        return deleted