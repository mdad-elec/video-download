# Video Downloader

A Python-based application for downloading videos from various platforms using FastAPI and yt-dlp.

## Features

- Download videos from multiple platforms
- RESTful API using FastAPI
- Authentication and authorization
- Database integration with SQLAlchemy
- Support for various video formats

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the Application

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright browsers:**
   ```bash
   playwright install
   ```

3. **Run the application:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access the application:**
   - Open your browser and go to `http://localhost:8000`
   - Register a new account or login with existing credentials
   - Use the dashboard to download videos from supported platforms

### API Endpoints

- `GET /login` - Login page
- `GET /register` - Registration page
- `GET /dashboard` - Main dashboard
- `POST /api/video/info` - Get video information
- `POST /api/video/download` - Download video
- `GET /api/user/sessions` - Get download history

### Supported Platforms

- YouTube
- TikTok
- Facebook
- Twitter

## Dependencies

Key dependencies include:
- FastAPI - Web framework
- yt-dlp - Video downloading
- SQLAlchemy - Database ORM
- Playwright - Browser automation
- ffmpeg - Video processing

## License

This project is open source and available under the MIT License.