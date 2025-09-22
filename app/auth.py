import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

class SimpleAuthManager:
    """Simple file-based authentication manager"""
    
    def __init__(self, data_dir: Path = Path("./data")):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        self.users_file = self.data_dir / "users.json"
        self.sessions_file = self.data_dir / "sessions.json"
        self.downloads_file = self.data_dir / "downloads.json"
        
        # Initialize files if they don't exist
        self._init_files()
    
    def _init_files(self):
        """Initialize data files if they don't exist"""
        for file in [self.users_file, self.sessions_file, self.downloads_file]:
            if not file.exists():
                with open(file, 'w') as f:
                    json.dump({}, f)
    
    def _load_data(self, file: Path) -> Dict:
        """Load data from JSON file"""
        try:
            with open(file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_data(self, file: Path, data: Dict):
        """Save data to JSON file"""
        with open(file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def hash_password(self, password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username: str, email: str, password: str) -> bool:
        """Register a new user"""
        users = self._load_data(self.users_file)
        
        if username in users:
            return False
        
        users[username] = {
            'email': email,
            'password_hash': self.hash_password(password),
            'created_at': datetime.now().isoformat(),
            'is_active': True
        }
        
        self._save_data(self.users_file, users)
        return True
    
    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials"""
        users = self._load_data(self.users_file)
        
        if username not in users:
            return False
        
        user = users[username]
        return user['password_hash'] == self.hash_password(password) and user['is_active']
    
    def create_token(self, username: str) -> str:
        """Create a session token"""
        token = secrets.token_urlsafe(32)
        sessions = self._load_data(self.sessions_file)
        
        sessions[token] = {
            'username': username,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=1)).isoformat()
        }
        
        self._save_data(self.sessions_file, sessions)
        
        # Update last login
        users = self._load_data(self.users_file)
        if username in users:
            users[username]['last_login'] = datetime.now().isoformat()
            self._save_data(self.users_file, users)
        
        return token
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify a session token and return username"""
        sessions = self._load_data(self.sessions_file)
        
        if token not in sessions:
            return None
        
        session = sessions[token]
        expires_at = datetime.fromisoformat(session['expires_at'])
        
        if datetime.now() > expires_at:
            # Token expired, remove it
            del sessions[token]
            self._save_data(self.sessions_file, sessions)
            return None
        
        return session['username']
    
    def track_download(self, username: str, url: str):
        """Track user downloads"""
        downloads = self._load_data(self.downloads_file)
        
        if username not in downloads:
            downloads[username] = []
        
        downloads[username].append({
            'url': url,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 100 downloads per user
        downloads[username] = downloads[username][-100:]
        
        self._save_data(self.downloads_file, downloads)
    
    def get_user_downloads(self, username: str) -> list:
        """Get user's download history"""
        downloads = self._load_data(self.downloads_file)
        return downloads.get(username, [])

# Create a singleton instance
auth_manager = SimpleAuthManager()