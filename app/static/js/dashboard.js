// Dashboard JavaScript for Video Downloader
class VideoDownloader {
    constructor() {
        this.currentVideoInfo = null;
        this.currentToken = null;
        this.isDownloading = false;
        
        this.init();
    }
    
    init() {
        this.checkAuth();
        this.loadUserInfo();
        this.loadDownloadHistory();
        this.setupEventListeners();
        this.startClipboardMonitoring();
    }
    
    checkAuth() {
        const token = localStorage.getItem('access_token');
        if (!token) {
            window.location.href = '/login';
            return;
        }
        this.currentToken = token;
    }
    
    async loadUserInfo() {
        try {
            // Extract username from token (you might want to create a dedicated endpoint for this)
            const response = await fetch('/api/user/sessions', {
                headers: {
                    'Authorization': `Bearer ${this.currentToken}`
                }
            });
            
            if (response.ok) {
                // For now, we'll use a generic username since we don't have a user info endpoint
                document.getElementById('username').textContent = 'User';
            } else {
                this.logout();
            }
        } catch (error) {
            console.error('Error loading user info:', error);
        }
    }
    
    setupEventListeners() {
        // URL input auto-detect platform
        document.getElementById('videoUrl').addEventListener('input', () => {
            this.autoDetectPlatform();
        });
        
        // Enter key support for URL input
        document.getElementById('videoUrl').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.getVideoInfo();
            }
        });
    }
    
    startClipboardMonitoring() {
        // Check clipboard every 2 seconds for URLs
        setInterval(async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (this.isValidURL(text) && !document.getElementById('videoUrl').value) {
                    // Show a subtle notification
                    this.showClipboardNotification(text);
                }
            } catch (error) {
                // Clipboard permission denied, ignore
            }
        }, 2000);
    }
    
    showClipboardNotification(url) {
        // Show a small notification that URL is available in clipboard
        const existingNotification = document.getElementById('clipboard-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        const notification = document.createElement('div');
        notification.id = 'clipboard-notification';
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--primary);
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            z-index: 1000;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease;
        `;
        notification.innerHTML = `
            <i class="fas fa-clipboard"></i> URL in clipboard! Click to paste
        `;
        
        notification.addEventListener('click', () => {
            document.getElementById('videoUrl').value = url;
            this.autoDetectPlatform();
            notification.remove();
        });
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
    
    autoDetectPlatform() {
        const url = document.getElementById('videoUrl').value;
        const platformSelect = document.getElementById('platform');
        
        if (!url) return;
        
        let platform = 'youtube'; // default
        
        if (url.includes('youtube.com') || url.includes('youtu.be')) {
            platform = 'youtube';
        } else if (url.includes('tiktok.com')) {
            platform = 'tiktok';
        } else if (url.includes('facebook.com') || url.includes('fb.watch')) {
            platform = 'facebook';
        } else if (url.includes('twitter.com') || url.includes('x.com')) {
            platform = 'twitter';
        }
        
        platformSelect.value = platform;
    }
    
    isValidURL(url) {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    }
    
    async getVideoInfo() {
        const url = document.getElementById('videoUrl').value.trim();
        const platform = document.getElementById('platform').value;
        
        if (!url) {
            this.showError('Please enter a video URL');
            return;
        }
        
        if (!this.isValidURL(url)) {
            this.showError('Please enter a valid URL');
            return;
        }
        
        const getInfoBtn = document.getElementById('getInfoBtn');
        const originalText = getInfoBtn.innerHTML;
        
        // Show loading state
        getInfoBtn.disabled = true;
        getInfoBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Getting Info...';
        
        try {
            const response = await fetch('/api/video/info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.currentToken}`
                },
                body: JSON.stringify({ url, platform })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to get video info');
            }
            
            const videoInfo = await response.json();
            this.currentVideoInfo = videoInfo;
            this.displayVideoInfo(videoInfo);
            
        } catch (error) {
            this.showError(error.message);
        } finally {
            // Reset button state
            getInfoBtn.disabled = false;
            getInfoBtn.innerHTML = originalText;
        }
    }
    
    displayVideoInfo(videoInfo) {
        const preview = document.getElementById('videoPreview');
        const thumbnail = document.getElementById('videoThumbnail');
        const title = document.getElementById('videoTitle');
        const duration = document.getElementById('videoDuration');
        const platform = document.getElementById('videoPlatform');
        const downloadBtn = document.getElementById('downloadBtn');
        const downloadBtnText = document.getElementById('downloadBtnText');
        
        // Update video info
        thumbnail.src = videoInfo.thumbnail || 'https://via.placeholder.com/120x80';
        title.textContent = videoInfo.title || 'Unknown Title';
        duration.textContent = `Duration: ${this.formatDuration(videoInfo.duration)}`;
        platform.textContent = `Platform: ${this.getPlatformName(videoInfo.platform)}`;
        
        // Update format options if available
        if (videoInfo.formats && videoInfo.formats.length > 0) {
            const formatSelect = document.getElementById('format');
            formatSelect.innerHTML = '';
            
            videoInfo.formats.forEach(format => {
                const option = document.createElement('option');
                option.value = format.format_id;
                option.textContent = `${format.resolution || 'Unknown'} (${format.ext || 'mp4'})`;
                formatSelect.appendChild(option);
            });
        }
        
        // Show preview and enable download
        preview.classList.add('active');
        downloadBtn.disabled = false;
        downloadBtnText.textContent = 'Download Video';
        
        // Scroll to preview
        preview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    formatDuration(seconds) {
        if (!seconds || seconds === 'N/A') return '--:--';
        
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    getPlatformName(platform) {
        const names = {
            'youtube': 'YouTube',
            'tiktok': 'TikTok',
            'facebook': 'Facebook',
            'twitter': 'Twitter/X'
        };
        return names[platform] || platform;
    }
    
    async downloadVideo() {
        if (!this.currentVideoInfo || this.isDownloading) return;
        
        const url = document.getElementById('videoUrl').value.trim();
        const platform = document.getElementById('platform').value;
        const formatId = document.getElementById('format').value;
        const startTime = document.getElementById('startTime').value || null;
        const endTime = document.getElementById('endTime').value || null;
        
        this.isDownloading = true;
        this.showProgress();
        
        try {
            const response = await fetch('/api/video/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.currentToken}`
                },
                body: JSON.stringify({
                    url,
                    platform,
                    format_id: formatId,
                    start_time: startTime,
                    end_time: endTime
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Download failed');
            }
            
            // Get filename from response headers
            const contentDisposition = response.headers.get('content-disposition');
            let filename = `video_${Date.now()}.mp4`;
            
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="(.+)"/);
                if (match) {
                    filename = match[1];
                }
            }
            
            // Download the file
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
            
            this.showSuccess('Download completed successfully!');
            this.loadDownloadHistory();
            
        } catch (error) {
            this.showError(error.message);
        } finally {
            this.isDownloading = false;
            this.hideProgress();
        }
    }
    
    showProgress() {
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        progressContainer.classList.add('active');
        progressFill.style.width = '0%';
        progressText.textContent = 'Preparing download...';
        
        // Simulate progress (you might want to implement real progress tracking)
        let progress = 0;
        const interval = setInterval(() => {
            if (!this.isDownloading) {
                clearInterval(interval);
                return;
            }
            
            progress += Math.random() * 15;
            if (progress > 90) progress = 90;
            
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `Downloading... ${Math.round(progress)}%`;
        }, 500);
    }
    
    hideProgress() {
        const progressContainer = document.getElementById('progressContainer');
        progressContainer.classList.remove('active');
    }
    
    clearVideo() {
        const preview = document.getElementById('videoPreview');
        const downloadBtn = document.getElementById('downloadBtn');
        const downloadBtnText = document.getElementById('downloadBtnText');
        
        preview.classList.remove('active');
        downloadBtn.disabled = true;
        downloadBtnText.textContent = 'Get Video Info First';
        
        this.currentVideoInfo = null;
        document.getElementById('videoUrl').value = '';
    }
    
    async loadDownloadHistory() {
        try {
            const response = await fetch('/api/user/sessions', {
                headers: {
                    'Authorization': `Bearer ${this.currentToken}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to load download history');
            }
            
            const history = await response.json();
            this.displayDownloadHistory(history);
            
        } catch (error) {
            console.error('Error loading download history:', error);
        }
    }
    
    displayDownloadHistory(history) {
        const historyContainer = document.getElementById('downloadHistory');
        
        if (!history || history.length === 0) {
            historyContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-download"></i>
                    <p>No downloads yet. Start by downloading your first video!</p>
                </div>
            `;
            return;
        }
        
        historyContainer.innerHTML = history.map(item => `
            <div class="history-item">
                <div class="history-url" title="${item.url}">
                    <i class="fas fa-link"></i>
                    ${this.truncateUrl(item.url)}
                </div>
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div class="history-date">
                        ${this.formatDate(item.created_at)}
                    </div>
                    <div class="history-status status-completed">
                        <i class="fas fa-check-circle"></i>
                        ${item.status}
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    truncateUrl(url, maxLength = 50) {
        if (url.length <= maxLength) return url;
        return url.substring(0, maxLength) + '...';
    }
    
    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffTime = Math.abs(now - date);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
        return date.toLocaleDateString();
    }
    
    showError(message) {
        this.showNotification(message, 'error');
    }
    
    showSuccess(message) {
        this.showNotification(message, 'success');
    }
    
    showNotification(message, type = 'info') {
        // Remove existing notifications
        const existing = document.querySelector('.notification');
        if (existing) existing.remove();
        
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            animation: slideIn 0.3s ease;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        
        const colors = {
            error: '#ef4444',
            success: '#10b981',
            info: '#3b82f6'
        };
        
        notification.style.background = colors[type] || colors.info;
        notification.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <i class="fas fa-${type === 'error' ? 'exclamation-circle' : type === 'success' ? 'check-circle' : 'info-circle'}"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }
        }, 5000);
    }
    
    logout() {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
    }
}

// Global functions for HTML onclick handlers
let downloader;

window.getVideoInfo = () => downloader.getVideoInfo();
window.downloadVideo = () => downloader.downloadVideo();
window.clearVideo = () => downloader.clearVideo();
window.refreshHistory = () => downloader.loadDownloadHistory();
window.logout = () => downloader.logout();

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    downloader = new VideoDownloader();
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);