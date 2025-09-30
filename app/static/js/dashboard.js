// Dashboard JavaScript for Video Downloader
class VideoDownloader {
    constructor() {
        this.currentVideoInfo = null;
        this.currentToken = null;
        this.isDownloading = false;
        this.trimmerElements = null;
        this.trimmerEventsBound = false;
        this.minTrimGap = 1;
        
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
            // Get user info from the dedicated endpoint
            const response = await fetch('/api/user/info', {
                headers: {
                    'Authorization': `Bearer ${this.currentToken}`
                }
            });
            
            if (response.ok) {
                const userInfo = await response.json();
                document.getElementById('username').textContent = userInfo.username || 'User';
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
        
        // Initialize video trimmer
        this.initializeTrimmer(videoInfo.duration);
        
        // Show preview and enable download
        preview.classList.add('active');

        if (downloadBtn) {
            downloadBtn.disabled = false;
        }

        if (downloadBtnText) {
            downloadBtnText.textContent = 'Download Now';
        }
        
        // Scroll to preview
        preview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    formatDuration(seconds) {
        if (seconds === 'N/A') return '--:--';

        const numericSeconds = Number(seconds);
        if (!Number.isFinite(numericSeconds) || numericSeconds < 0) {
            return '0:00';
        }

        const totalSeconds = Math.round(numericSeconds);
        const hours = Math.floor(totalSeconds / 3600);
        const mins = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;

        if (hours > 0) {
            return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }

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
        const trimmerValues = this.getTrimmerValues();
        const startTime = trimmerValues.startTime;
        const endTime = trimmerValues.endTime;
        const downloadBtn = document.getElementById('downloadBtn');
        const downloadBtnText = document.getElementById('downloadBtnText');

        this.isDownloading = true;
        this.showProgress();

        if (downloadBtn) {
            downloadBtn.disabled = true;
        }

        if (downloadBtnText) {
            downloadBtnText.textContent = 'Preparing download...';
        }
        
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

            if (downloadBtn) {
                downloadBtn.disabled = !this.currentVideoInfo;
            }

            if (downloadBtnText) {
                downloadBtnText.textContent = this.currentVideoInfo ? 'Download Now' : 'Get Video Info First';
            }
        }
    }
    
    showProgress() {
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        progressContainer.classList.add('active');
        progressFill.style.width = '0%';
        progressText.textContent = 'Preparing download...';
        
        // Set up real progress tracking with EventSource
        const progressUrl = `/api/video/progress/${Date.now()}`;
        this.progressEventSource = new EventSource(progressUrl);
        
        this.progressEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Handle different progress statuses
                if (data.status === 'cookie_error') {
                    this.hideProgress();
                    this.showCookieErrorNotification(data.platform, data.message);
                    this.progressEventSource.close();
                    return;
                }
                
                if (data.status === 'error') {
                    this.hideProgress();
                    this.showError(data.message);
                    this.progressEventSource.close();
                    return;
                }
                
                if (data.status === 'finished') {
                    this.hideProgress();
                    this.showSuccess('Download completed successfully!');
                    this.progressEventSource.close();
                    this.loadDownloadHistory();
                    return;
                }
                
                // Update progress
                let progressText = data.message || 'Downloading...';
                if (data.progress !== undefined) {
                    progressFill.style.width = `${data.progress}%`;
                    progressText += ` ${Math.round(data.progress)}%`;
                }
                
                if (data.speed) {
                    progressText += ` (${data.speed})`;
                }
                
                if (data.eta) {
                    progressText += ` - ETA: ${data.eta}`;
                }
                
                document.getElementById('progressText').textContent = progressText;
                
            } catch (error) {
                console.error('Error parsing progress data:', error);
            }
        };
        
        this.progressEventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            this.progressEventSource.close();
        };
    }
    
    hideProgress() {
        const progressContainer = document.getElementById('progressContainer');
        progressContainer.classList.remove('active');
        
        if (this.progressEventSource) {
            this.progressEventSource.close();
            this.progressEventSource = null;
        }
    }
    
    clearVideo() {
        const preview = document.getElementById('videoPreview');
        const downloadBtn = document.getElementById('downloadBtn');
        const downloadBtnText = document.getElementById('downloadBtnText');
        
        if (preview) {
            preview.classList.remove('active');
        }

        if (downloadBtn) {
            downloadBtn.disabled = true;
        }

        if (downloadBtnText) {
            downloadBtnText.textContent = 'Get Video Info First';
        }

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
    
    showCookieErrorNotification(platform, message) {
        // Remove existing notifications
        const existing = document.querySelector('.notification');
        if (existing) existing.remove();
        
        const notification = document.createElement('div');
        notification.className = 'notification cookie-error';
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 20px;
            border-radius: 12px;
            background: linear-gradient(135deg, #f59e0b, #ef4444);
            color: white;
            font-weight: 500;
            z-index: 1000;
            animation: slideIn 0.3s ease;
            max-width: 450px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.2);
            border: 2px solid rgba(255,255,255,0.2);
        `;
        
        const platformNames = {
            'youtube': 'YouTube',
            'tiktok': 'TikTok',
            'twitter': 'Twitter/X'
        };
        
        const platformName = platformNames[platform] || platform;
        
        notification.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <i class="fas fa-cookie-bite" style="font-size: 1.2em;"></i>
                    <div>
                        <div style="font-weight: 600; font-size: 1.1em;">🍪 I need cookies!</div>
                        <div style="font-size: 0.9em; opacity: 0.9;">${platformName} cookies are expired</div>
                    </div>
                </div>
                <div style="font-size: 0.85em; line-height: 1.4; opacity: 0.95;">
                    ${message}
                </div>
                <div style="display: flex; gap: 8px; margin-top: 4px;">
                    <button onclick="videoDownloader.showCookieHelp('${platform}')" style="
                        background: rgba(255,255,255,0.2);
                        border: 1px solid rgba(255,255,255,0.3);
                        color: white;
                        padding: 6px 12px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 0.8em;
                        font-weight: 500;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='rgba(255,255,255,0.3)'" 
                       onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                        <i class="fas fa-question-circle"></i> Help
                    </button>
                    <button onclick="videoDownloader.showCookiePaste('${platform}')" style="
                        background: rgba(255,255,255,0.9);
                        border: 1px solid rgba(255,255,255,0.3);
                        color: #ef4444;
                        padding: 6px 12px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 0.8em;
                        font-weight: 600;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='white'" 
                       onmouseout="this.style.background='rgba(255,255,255,0.9)'">
                        <i class="fas fa-paste"></i> Give me cookies
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 15 seconds (longer for cookie notifications)
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }
        }, 15000);
    }
    
    showCookieHelp(platform) {
        // Remove existing cookie modals
        const existingModal = document.querySelector('.cookie-modal');
        if (existingModal) existingModal.remove();
        
        const modal = document.createElement('div');
        modal.className = 'cookie-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 2000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease;
        `;
        
        const platformNames = {
            'youtube': 'YouTube',
            'tiktok': 'TikTok',
            'twitter': 'Twitter/X'
        };
        
        const platformName = platformNames[platform] || platform;
        
        modal.innerHTML = `
            <div style="
                background: white;
                border-radius: 16px;
                padding: 32px;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                animation: slideUp 0.3s ease;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                    <h2 style="margin: 0; color: #1f2937; font-size: 1.5em;">
                        <i class="fas fa-cookie-bite" style="color: #f59e0b; margin-right: 8px;"></i>
                        How to Get ${platformName} Cookies
                    </h2>
                    <button onclick="this.closest('.cookie-modal').remove()" style="
                        background: none;
                        border: none;
                        font-size: 1.5em;
                        cursor: pointer;
                        color: #6b7280;
                        padding: 4px;
                        border-radius: 4px;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#f3f4f6'; this.style.color='#374151'" 
                       onmouseout="this.style.background='none'; this.style.color='#6b7280'">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                
                <div style="color: #4b5563; line-height: 1.6;">
                    <h3 style="color: #1f2937; margin-bottom: 16px;">📖 Step-by-Step Guide</h3>
                    
                    <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                        <strong style="color: #92400e;">⚠️ Important:</strong> You must be logged in to ${platformName} in your browser for this to work!
                    </div>
                    
                    <h4 style="color: #1f2937; margin: 20px 0 12px 0;">For Chrome/Edge:</h4>
                    <ol style="margin-left: 20px; margin-bottom: 20px;">
                        <li>Install the "Get cookies.txt" extension from the Chrome Web Store</li>
                        <li>Go to ${platformName} and make sure you're logged in</li>
                        <li>Click the extension icon in your browser toolbar</li>
                        <li>Click "Export" → "Netscape format"</li>
                        <li>Copy the entire text content</li>
                        <li>Come back here and click "Give me cookies"</li>
                    </ol>
                    
                    <h4 style="color: #1f2937; margin: 20px 0 12px 0;">For Firefox:</h4>
                    <ol style="margin-left: 20px; margin-bottom: 20px;">
                        <li>Install the "cookies.txt" extension from Firefox Add-ons</li>
                        <li>Go to ${platformName} and make sure you're logged in</li>
                        <li>Click the extension icon in your browser toolbar</li>
                        <li>Click "Export" → "As Netscape HTTP Cookie File"</li>
                        <li>Copy the entire text content</li>
                        <li>Come back here and click "Give me cookies"</li>
                    </ol>
                    
                    <div style="background: #dbeafe; border: 1px solid #93c5fd; border-radius: 8px; padding: 16px; margin-top: 20px;">
                        <strong style="color: #1e40af;">💡 Pro Tip:</strong> Cookies typically expire after a few weeks. You'll need to refresh them periodically.
                    </div>
                </div>
                
                <div style="display: flex; gap: 12px; margin-top: 32px; justify-content: flex-end;">
                    <button onclick="videoDownloader.showCookiePaste('${platform}'); this.closest('.cookie-modal').remove();" style="
                        background: #3b82f6;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 500;
                        font-size: 1em;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#2563eb'" 
                       onmouseout="this.style.background='#3b82f6'">
                        <i class="fas fa-paste"></i> Give me cookies
                    </button>
                    <button onclick="this.closest('.cookie-modal').remove()" style="
                        background: #6b7280;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 500;
                        font-size: 1em;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#4b5563'" 
                       onmouseout="this.style.background='#6b7280'">
                        Close
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }
    
    showCookiePaste(platform) {
        // Remove existing cookie modals
        const existingModal = document.querySelector('.cookie-modal');
        if (existingModal) existingModal.remove();
        
        const modal = document.createElement('div');
        modal.className = 'cookie-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 2000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease;
        `;
        
        const platformNames = {
            'youtube': 'YouTube',
            'tiktok': 'TikTok',
            'twitter': 'Twitter/X'
        };
        
        const platformName = platformNames[platform] || platform;
        const cookieFileName = `www.${platformName.toLowerCase().replace('/', '')}.com_cookies.txt`;
        
        modal.innerHTML = `
            <div style="
                background: white;
                border-radius: 16px;
                padding: 32px;
                max-width: 700px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                animation: slideUp 0.3s ease;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                    <h2 style="margin: 0; color: #1f2937; font-size: 1.5em;">
                        <i class="fas fa-paste" style="color: #10b981; margin-right: 8px;"></i>
                        Paste ${platformName} Cookies
                    </h2>
                    <button onclick="this.closest('.cookie-modal').remove()" style="
                        background: none;
                        border: none;
                        font-size: 1.5em;
                        cursor: pointer;
                        color: #6b7280;
                        padding: 4px;
                        border-radius: 4px;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#f3f4f6'; this.style.color='#374151'" 
                       onmouseout="this.style.background='none'; this.style.color='#6b7280'">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                
                <div style="color: #4b5563; line-height: 1.6;">
                    <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                        <strong style="color: #92400e;">📋 Paste your ${platformName} cookies below:</strong>
                        <div style="margin-top: 8px; font-size: 0.9em;">
                            The cookies should be in Netscape format and start with <code># Netscape HTTP Cookie File</code>
                        </div>
                    </div>
                    
                    <textarea id="cookieTextarea" placeholder="Paste your cookies here..." style="
                        width: 100%;
                        height: 300px;
                        border: 2px solid #d1d5db;
                        border-radius: 8px;
                        padding: 16px;
                        font-family: 'Courier New', monospace;
                        font-size: 0.85em;
                        resize: vertical;
                        line-height: 1.4;
                    "></textarea>
                    
                    <div id="cookieValidation" style="margin-top: 12px; font-size: 0.85em; color: #6b7280;"></div>
                    
                    <div style="background: #dbeafe; border: 1px solid #93c5fd; border-radius: 8px; padding: 16px; margin-top: 20px;">
                        <strong style="color: #1e40af;">🔒 Security Note:</strong> Your cookies are stored locally on the server and are only used for video downloads. We do not share or misuse your data.
                    </div>
                </div>
                
                <div style="display: flex; gap: 12px; margin-top: 32px; justify-content: flex-end;">
                    <button onclick="videoDownloader.validateAndSaveCookies('${platform}', '${cookieFileName}')" style="
                        background: #10b981;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 500;
                        font-size: 1em;
                        transition: all 0.2s ease;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    " onmouseover="this.style.background='#059669'" 
                       onmouseout="this.style.background='#10b981'">
                        <i class="fas fa-save"></i>
                        Save Cookies
                    </button>
                    <button onclick="videoDownloader.showCookieHelp('${platform}'); this.closest('.cookie-modal').remove();" style="
                        background: #6b7280;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 500;
                        font-size: 1em;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#4b5563'" 
                       onmouseout="this.style.background='#6b7280'">
                        <i class="fas fa-question-circle"></i>
                        Help
                    </button>
                    <button onclick="this.closest('.cookie-modal').remove()" style="
                        background: #ef4444;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 500;
                        font-size: 1em;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='#dc2626'" 
                       onmouseout="this.style.background='#ef4444'">
                        Cancel
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
        
        // Add real-time validation
        const textarea = modal.querySelector('#cookieTextarea');
        const validation = modal.querySelector('#cookieValidation');
        
        textarea.addEventListener('input', () => {
            const content = textarea.value.trim();
            this.validateCookieFormat(content, platform, validation);
        });
    }
    
    validateCookieFormat(content, platform, validationElement) {
        if (!content) {
            validationElement.innerHTML = '';
            validationElement.style.color = '#6b7280';
            return false;
        }
        
        // Basic validation for Netscape cookie format
        const lines = content.split('\n');
        let validLines = 0;
        let hasHeader = false;
        
        for (let i = 0; i < Math.min(lines.length, 10); i++) {
            const line = lines[i].trim();
            if (line.startsWith('# Netscape HTTP Cookie File')) {
                hasHeader = true;
                continue;
            }
            if (line && !line.startsWith('#')) {
                const parts = line.split('\t');
                if (parts.length >= 7) {
                    validLines++;
                }
            }
        }
        
        if (hasHeader && validLines > 0) {
            validationElement.innerHTML = `✅ Valid cookie format detected (${validLines} cookie${validLines > 1 ? 's' : ''} found)`;
            validationElement.style.color = '#10b981';
            return true;
        } else if (validLines > 0) {
            validationElement.innerHTML = `⚠️ Cookie data found but missing Netscape header. This might still work.`;
            validationElement.style.color = '#f59e0b';
            return true;
        } else {
            validationElement.innerHTML = '❌ No valid cookie data detected. Please check your cookie format.';
            validationElement.style.color = '#ef4444';
            return false;
        }
    }
    
    async validateAndSaveCookies(platform, cookieFileName) {
        const textarea = document.querySelector('#cookieTextarea');
        if (!textarea) return;
        
        const content = textarea.value.trim();
        if (!content) {
            alert('Please paste your cookies first.');
            return;
        }
        
        // Validate format
        const validation = document.querySelector('#cookieValidation');
        if (!this.validateCookieFormat(content, platform, validation)) {
            if (!confirm('The cookie format doesn\'t look right. Save anyway?')) {
                return;
            }
        }
        
        try {
            const response = await fetch('/api/cookies/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.currentToken}`
                },
                body: JSON.stringify({
                    platform: platform,
                    cookieFileName: cookieFileName,
                    cookieContent: content
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // Show success message
                this.showSuccess(`${platform.charAt(0).toUpperCase() + platform.slice(1)} cookies saved successfully! Try downloading again.`);
                
                // Close modal
                const modal = document.querySelector('.cookie-modal');
                if (modal) modal.remove();
                
                // Remove any cookie error notifications
                const notifications = document.querySelectorAll('.notification.cookie-error');
                notifications.forEach(n => n.remove());
            } else {
                this.showError(`Failed to save cookies: ${result.detail || 'Unknown error'}`);
            }
        } catch (error) {
            this.showError(`Error saving cookies: ${error.message}`);
        }
    }
    
    // Video Trimmer Methods
    initializeTrimmer(duration) {
        const parsedDuration = Math.max(0, Number(duration) || 0);

        this.trimmerData = {
            duration: parsedDuration,
            startTime: 0,
            endTime: parsedDuration,
            isDragging: false,
            currentHandle: null
        };

        if (!this.trimmerElements) {
            this.trimmerElements = {
                container: document.querySelector('.video-trimmer'),
                startHandle: document.querySelector('.trimmer-start'),
                endHandle: document.querySelector('.trimmer-end'),
                progress: document.querySelector('.trimmer-progress'),
                startTimeDisplay: document.getElementById('trimStartTime'),
                endTimeDisplay: document.getElementById('trimEndTime')
            };
        }

        if (!this.trimmerEventsBound && this.trimmerElements?.container) {
            this.setupTrimmerEvents();
            this.trimmerEventsBound = true;
        }

        this.updateTrimmerDisplay();
    }
    
    setupTrimmerEvents() {
        const elements = this.trimmerElements;
        if (!elements) return;

        const { container, startHandle, endHandle } = elements;
        if (!container || !startHandle || !endHandle) return;

        const startDrag = (event) => this.startTrimmerDrag(event, 'start');
        const endDrag = (event) => this.startTrimmerDrag(event, 'end');

        startHandle.addEventListener('mousedown', startDrag);
        endHandle.addEventListener('mousedown', endDrag);
        document.addEventListener('mousemove', (event) => this.handleTrimmerDrag(event));
        document.addEventListener('mouseup', () => this.stopTrimmerDrag());

        startHandle.addEventListener('touchstart', startDrag, { passive: false });
        endHandle.addEventListener('touchstart', endDrag, { passive: false });
        document.addEventListener('touchmove', (event) => this.handleTrimmerDrag(event), { passive: false });
        document.addEventListener('touchend', () => this.stopTrimmerDrag());
        document.addEventListener('touchcancel', () => this.stopTrimmerDrag());

        container.addEventListener('click', (event) => {
            const target = event.target;
            if (target === container || target.classList.contains('trimmer-track') || target.classList.contains('trimmer-progress')) {
                this.moveTrimmerHandle(event);
            }
        });
    }
    
    startTrimmerDrag(event, handle) {
        if (!this.trimmerData) return;

        if (event.cancelable) {
            event.preventDefault();
        }

        this.trimmerData.isDragging = true;
        this.trimmerData.currentHandle = handle;
        document.body.style.cursor = 'grabbing';
    }
    
    handleTrimmerDrag(event) {
        if (!this.trimmerData?.isDragging || !this.trimmerData.currentHandle) {
            return;
        }

        const metrics = this.getTrimmerMetrics();
        if (!metrics || metrics.usableWidth === 0) {
            return;
        }

        if (event.cancelable) {
            event.preventDefault();
        }

        const point = event.touches ? event.touches[0] : event;
        if (!point) return;

        let position = point.clientX - metrics.containerRect.left - metrics.handleWidth / 2;
        position = Math.max(0, Math.min(metrics.usableWidth, position));

        const duration = this.trimmerData.duration || 0;
        const time = duration ? (position / metrics.usableWidth) * duration : 0;
        const minGap = this.getTrimGap();

        if (this.trimmerData.currentHandle === 'start') {
            const maxStart = Math.max(0, this.trimmerData.endTime - minGap);
            this.trimmerData.startTime = Math.min(Math.max(0, time), maxStart);
        } else {
            const minEnd = this.trimmerData.startTime + minGap;
            this.trimmerData.endTime = Math.max(minEnd, Math.min(duration, time));
        }

        this.updateTrimmerDisplay();
    }
    
    stopTrimmerDrag() {
        if (!this.trimmerData) return;

        this.trimmerData.isDragging = false;
        this.trimmerData.currentHandle = null;
        document.body.style.cursor = '';
    }
    
    moveTrimmerHandle(event) {
        const metrics = this.getTrimmerMetrics();
        if (!metrics || metrics.usableWidth === 0 || !this.trimmerData) {
            return;
        }

        const position = event.clientX - metrics.containerRect.left - metrics.handleWidth / 2;
        const clamped = Math.max(0, Math.min(metrics.usableWidth, position));
        const duration = this.trimmerData.duration || 0;
        const time = duration ? (clamped / metrics.usableWidth) * duration : 0;
        const minGap = this.getTrimGap();

        const distToStart = Math.abs(time - this.trimmerData.startTime);
        const distToEnd = Math.abs(time - this.trimmerData.endTime);

        if (distToStart < distToEnd) {
            const maxStart = Math.max(0, this.trimmerData.endTime - minGap);
            this.trimmerData.startTime = Math.min(Math.max(0, time), maxStart);
        } else {
            const minEnd = this.trimmerData.startTime + minGap;
            this.trimmerData.endTime = Math.max(minEnd, Math.min(duration, time));
        }

        this.updateTrimmerDisplay();
    }
    
    updateTrimmerDisplay() {
        const metrics = this.getTrimmerMetrics();
        if (!metrics || !this.trimmerData) {
            return;
        }

        const { startHandle, endHandle, progress, startTimeDisplay, endTimeDisplay, handleWidth, usableWidth } = metrics;

        if (usableWidth === 0) {
            requestAnimationFrame(() => this.updateTrimmerDisplay());
            return;
        }

        const duration = this.trimmerData.duration || 0;

        const startTime = Math.max(0, Math.min(this.trimmerData.startTime, duration));
        const endTime = Math.max(startTime, Math.min(this.trimmerData.endTime, duration));

        this.trimmerData.startTime = startTime;
        this.trimmerData.endTime = endTime;

        const startOffset = duration ? (startTime / duration) * usableWidth : 0;
        const endOffset = duration ? (endTime / duration) * usableWidth : 0;

        if (startHandle) {
            startHandle.style.left = `${startOffset}px`;
        }
        if (endHandle) {
            endHandle.style.left = `${endOffset}px`;
        }
        if (progress) {
            progress.style.left = `${startOffset + handleWidth / 2}px`;
            progress.style.width = `${Math.max(0, endOffset - startOffset)}px`;
        }

        if (startTimeDisplay) {
            startTimeDisplay.textContent = this.formatDuration(startTime);
        }
        if (endTimeDisplay) {
            endTimeDisplay.textContent = this.formatDuration(endTime);
        }
    }
    
    getTrimmerValues() {
        if (!this.trimmerData || this.trimmerData.duration === 0) {
            return { startTime: null, endTime: null };
        }

        const { startTime, endTime, duration } = this.trimmerData;
        const trimmed = endTime - startTime;
        const isPartial = startTime > 0 || endTime < duration;

        if (isPartial && trimmed > 0) {
            return {
                startTime: Math.round(startTime),
                endTime: Math.round(endTime)
            };
        }

        return { startTime: null, endTime: null };
    }

    getTrimmerMetrics() {
        const elements = this.trimmerElements;
        if (!elements) return null;

        const { container, startHandle, endHandle, progress, startTimeDisplay, endTimeDisplay } = elements;
        if (!container || !startHandle || !endHandle || !progress || !startTimeDisplay || !endTimeDisplay) {
            return null;
        }

        const containerRect = container.getBoundingClientRect();
        const handleWidth = startHandle.offsetWidth || 1;
        const usableWidth = Math.max(0, containerRect.width - handleWidth);

        return {
            container,
            startHandle,
            endHandle,
            progress,
            startTimeDisplay,
            endTimeDisplay,
            handleWidth,
            usableWidth,
            containerRect
        };
    }

    getTrimGap() {
        if (!this.trimmerData) {
            return 0;
        }

        const duration = this.trimmerData.duration || 0;
        if (duration === 0) {
            return 0;
        }

        return Math.min(this.minTrimGap, duration);
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
