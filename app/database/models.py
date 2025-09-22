from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
from passlib.context import CryptContext

# Database setup
DATABASE_URL = "sqlite:///./video_downloader.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(20), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    downloads = relationship("Download", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    
    def set_password(self, password: str):
        self.hashed_password = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)
    
    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Download(Base):
    __tablename__ = "downloads"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    platform = Column(String(50), nullable=False)
    title = Column(String(500))
    format_id = Column(String(50))
    file_size = Column(Integer)  # in bytes
    status = Column(String(20), default="pending")  # pending, downloading, completed, failed
    error_message = Column(Text)
    download_time = Column(DateTime, default=func.now())
    file_path = Column(String(1000))  # temporary file path
    
    # Relationships
    user = relationship("User", back_populates="downloads")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "url": self.url,
            "platform": self.platform,
            "title": self.title,
            "format_id": self.format_id,
            "file_size": self.file_size,
            "status": self.status,
            "error_message": self.error_message,
            "download_time": self.download_time.isoformat() if self.download_time else None
        }

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active
        }

class VideoFormat(Base):
    __tablename__ = "video_formats"
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)
    format_id = Column(String(50), nullable=False)
    resolution = Column(String(50))
    extension = Column(String(10))
    video_codec = Column(String(50))
    audio_codec = Column(String(50))
    fps = Column(Integer)
    is_preferred = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "platform": self.platform,
            "format_id": self.format_id,
            "resolution": self.resolution,
            "extension": self.extension,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "fps": self.fps,
            "is_preferred": self.is_preferred
        }

class DownloadQueue(Base):
    __tablename__ = "download_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    platform = Column(String(50), nullable=False)
    format_id = Column(String(50), default="best")
    priority = Column(Integer, default=0)  # Higher number = higher priority
    status = Column(String(20), default="queued")  # queued, processing, completed, failed
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    # Relationships
    user = relationship("User")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "url": self.url,
            "platform": self.platform,
            "format_id": self.format_id,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message
        }

# Create indexes for better performance
Index('idx_downloads_user_time', Download.user_id, Download.download_time.desc())
Index('idx_sessions_token_expires', Session.token, Session.expires_at)
Index('idx_queue_user_priority', DownloadQueue.user_id, DownloadQueue.priority.desc())

def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Database dependency for FastAPI
from fastapi import Depends

def get_db_session():
    """Get database session for FastAPI dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()