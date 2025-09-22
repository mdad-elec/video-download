# Video Downloader

A comprehensive Python-based video downloading platform with advanced features including batch processing, format conversion, and intelligent scheduling. Built with FastAPI, SQLAlchemy, and modern web technologies.

## ✨ Features

### 🎥 Core Downloading
- **Multi-Platform Support**: Download videos from YouTube, TikTok, Facebook, and Twitter
- **Format Options**: Multiple quality and format options for each platform
- **Real-time Progress**: Live download progress updates via WebSocket
- **Error Handling**: Enhanced error messages with platform-specific details

### 🗄️ Database & Authentication
- **User Management**: Complete user registration and authentication system
- **Session Management**: JWT-based authentication with automatic expiration
- **Download History**: Comprehensive download tracking and history
- **User Statistics**: Personal download statistics and platform breakdowns

### 🔄 Batch Processing
- **Batch Downloads**: Add up to 10 videos to download queue simultaneously
- **Priority Queue**: Priority-based download scheduling
- **Queue Management**: Real-time queue status and cancellation support
- **Progress Monitoring**: Live updates for all queued downloads

### 🎬 Format Conversion
- **Multi-Format Support**: Convert to MP4, WebM, AVI, MKV, MOV, FLV, MP3, WAV, AAC
- **Quality Options**: High, Medium, Low, Ultra quality presets
- **Resolution Scaling**: Convert videos to different resolutions (4K to 240p)
- **Audio Extraction**: Extract audio from videos to various audio formats
- **Progress Tracking**: Real-time conversion progress updates

### ⏰ Intelligent Scheduling
- **Automated Processing**: Background scheduler with configurable concurrent downloads
- **Priority Management**: Set download priorities for queue optimization
- **Cancellation Support**: Cancel scheduled downloads before processing
- **Admin Statistics**: Comprehensive system-wide statistics and analytics
- **Auto-Cleanup**: Automatic cleanup of completed downloads and expired sessions

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- FFmpeg (for video conversion)
- Internet connection for video downloading

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Video-Download
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers (for enhanced platform support):**
   ```bash
   playwright install
   ```

4. **Ensure FFmpeg is installed:**
   ```bash
   # On macOS
   brew install ffmpeg
   
   # On Ubuntu/Debian
   sudo apt update
   sudo apt install ffmpeg
   
   # On Windows (using Chocolatey)
   choco install ffmpeg
   ```

### Running the Application

1. **Start the application:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Access the application:**
   - Open your browser and navigate to `http://localhost:8000`
   - Register a new account or login with existing credentials
   - Access the dashboard to start downloading videos

## 📚 API Documentation

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/register` | User registration |
| `POST` | `/token` | User login (JWT token) |
| `GET` | `/api/user/sessions` | Download history |
| `GET` | `/api/user/stats` | User statistics |
| `GET` | `/api/user/download-queue` | User's download queue |

### Video Download Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/video/info` | Get video information |
| `POST` | `/api/video/download` | Download video immediately |
| `POST` | `/api/video/batch-download` | Add multiple videos to queue |
| `POST` | `/api/video/schedule` | Schedule future download |
| `DELETE` | `/api/video/schedule/{id}` | Cancel scheduled download |

### Video Conversion Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/video/convert` | Convert video format |
| `GET` | `/api/video/converter/info` | Get supported formats |

### Scheduler Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/scheduler/status` | Queue status and statistics |
| `GET` | `/api/scheduler/stats` | Admin statistics (admin only) |

## 🎯 Supported Platforms

### YouTube ✅
- Full support with all quality options
- Live streaming support
- Playlist downloading
- Multiple format options

### TikTok ⚠️
- Basic support available
- May require HTTPS deployment due to IP restrictions
- Mobile user agent fallback

### Facebook ✅
- Multiple URL format support
- Enhanced error handling
- Fallback configurations
- Video content validation

### Twitter ✅
- URL normalization for various formats
- Video content detection
- Mobile user agent support
- API Bearer token integration

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Database Configuration
DATABASE_URL=sqlite:///./video_downloader.db

# Application Configuration
APP_NAME=Video Downloader
VERSION=2.0.0
DEBUG=True

# Security Settings
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# File Storage
TEMP_DIR=/tmp/video_downloader
MAX_TEMP_FILE_AGE_SECONDS=3600

# Scheduler Settings
MAX_CONCURRENT_DOWNLOADS=3
CLEANUP_INTERVAL_HOURS=1
```

### Scheduler Configuration

The download scheduler can be configured through the application:

- **Concurrent Downloads**: Maximum simultaneous downloads (default: 3)
- **Cleanup Interval**: Automatic cleanup frequency (default: 1 hour)
- **Queue Priority**: Priority-based processing order
- **Retry Logic**: Automatic retry for failed downloads

## 🎬 Format Conversion Options

### Video Formats
- **MP4**: H.264/AVC with AAC audio (recommended)
- **WebM**: VP9 video with Opus audio
- **AVI**: H.264 video with MP3 audio
- **MKV**: H.264 video with AAC audio
- **MOV**: H.264 video with AAC audio
- **FLV**: H.264 video with AAC audio

### Audio Formats
- **MP3**: High-quality audio compression
- **WAV**: Uncompressed audio
- **AAC**: Advanced Audio Coding

### Quality Presets
- **High**: Best quality (larger file size)
- **Medium**: Good quality (balanced)
- **Low**: Lower quality (smaller file size)
- **Ultra**: Lowest quality (fastest conversion)

### Resolution Options
- 4K Ultra HD (3840x2160)
- 1440p QHD (2560x1440)
- 1080p Full HD (1920x1080)
- 720p HD (1280x720)
- 480p SD (854x480)
- 360p (640x360)
- 240p (426x240)

## 🏗️ Architecture

### Backend Technologies
- **FastAPI**: Modern, fast web framework
- **SQLAlchemy**: Database ORM with SQLite
- **yt-dlp**: Video downloading backend
- **FFmpeg**: Video processing and conversion
- **WebSocket**: Real-time progress updates

### Database Schema
- **Users**: User accounts and authentication
- **Sessions**: Active user sessions
- **Downloads**: Download history and tracking
- **VideoFormats**: Supported format configurations
- **DownloadQueue**: Scheduled and queued downloads

### Background Services
- **Download Scheduler**: Automated queue processing
- **Cleanup Service**: Temporary file management
- **Session Manager**: Authentication and session handling
- **Progress Monitor**: Real-time progress tracking

## 🛠️ Development

### Project Structure
```
Video-Download/
├── app/
│   ├── database/          # Database models and auth
│   ├── downloaders/       # Platform-specific downloaders
│   ├── utils/            # Utility functions
│   ├── api/              # API endpoints and WebSocket
│   ├── static/           # Static files (CSS, JS)
│   ├── templates/        # HTML templates
│   └── main.py           # Main application
├── requirements.txt      # Python dependencies
├── README.md            # This file
└── .env                 # Environment variables
```

### Running Tests
```bash
# Run database tests
python -c "from app.database.models import create_tables; create_tables()"

# Test authentication
python -c "from app.database.auth import DatabaseAuthManager; print('Auth system ready')"

# Test video converter
python -c "from app.utils.video_converter import VideoConverter; print('Converter ready')"
```

## 🔒 Security Features

- **Password Hashing**: bcrypt for secure password storage
- **JWT Authentication**: Secure token-based authentication
- **Session Management**: Automatic session expiration
- **Input Validation**: Comprehensive input sanitization
- **Rate Limiting**: Protection against abuse
- **File Cleanup**: Automatic temporary file removal

## 📊 Monitoring & Statistics

### User Statistics
- Total downloads count
- Platform usage breakdown
- Download history with metadata
- File size statistics

### Admin Statistics
- System-wide download metrics
- Platform performance analytics
- User activity monitoring
- Queue efficiency metrics

## 🐛 Troubleshooting

### Common Issues

1. **FFmpeg not found**: Ensure FFmpeg is installed and in PATH
2. **Database errors**: Check database file permissions
3. **Platform restrictions**: Some platforms may require HTTPS deployment
4. **Rate limiting**: Implement delays between bulk downloads

### Platform-Specific Issues

- **YouTube**: Generally reliable with all formats
- **TikTok**: May require HTTPS deployment or proxy
- **Facebook**: Parsing errors may occur with API changes
- **Twitter**: Video content detection may fail for some tweets

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.

## 🔗 Related Projects

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloading backend
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [FFmpeg](https://ffmpeg.org/) - Video processing

---

**Note**: This application is for educational and personal use. Please respect the terms of service of the platforms from which you download content and ensure you have the right to download and use the videos.