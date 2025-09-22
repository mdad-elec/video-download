let token = localStorage.getItem('access_token');
let currentVideoInfo = null;

async function getVideoInfo() {
    const url = document.getElementById('videoUrl').value;
    const platform = document.getElementById('platform').value;
    
    if (!url) {
        alert('Please enter a video URL');
        return;
    }
    
    document.getElementById('progress').style.display = 'block';
    document.getElementById('progressText').textContent = 'Fetching video information...';
    
    try {
        const response = await fetch('/api/video/info', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url, platform })
        });
        
        if (!response.ok) throw new Error('Failed to get video info');
        
        currentVideoInfo = await response.json();
        displayVideoInfo(currentVideoInfo);
        
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        document.getElementById('progress').style.display = 'none';
    }
}

function displayVideoInfo(info) {
    document.getElementById('videoInfo').style.display = 'block';
    
    const details = document.getElementById('videoDetails');
    details.innerHTML = `
        <p><strong>Title:</strong> ${info.title}</p>
        <p><strong>Duration:</strong> ${formatDuration(info.duration)}</p>
        ${info.thumbnail ? `<img src="${info.thumbnail}" style="max-width: 300px;">` : ''}
    `;
    
    // Populate format options
    const formatSelect = document.getElementById('format');
    formatSelect.innerHTML = '';
    
    if (info.formats && info.formats.length > 0) {
        info.formats.forEach(format => {
            const option = document.createElement('option');
            option.value = format.format_id;
            option.textContent = `${format.resolution} - ${format.ext}`;
            formatSelect.appendChild(option);
        });
    } else {
        formatSelect.innerHTML = '<option value="best">Best Quality</option>';
    }
    
    // Set max values for trim inputs
    if (info.duration) {
        document.getElementById('endTime').max = info.duration;
    }
}

async function downloadVideo() {
    const url = document.getElementById('videoUrl').value;
    const platform = document.getElementById('platform').value;
    const format = document.getElementById('format').value;
    const startTime = document.getElementById('startTime').value || null;
    const endTime = document.getElementById('endTime').value || null;
    
    document.getElementById('progress').style.display = 'block';
    document.getElementById('progressText').textContent = 'Processing video...';
    
    try {
        const response = await fetch('/api/video/download', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url,
                platform,
                format_id: format,
                start_time: startTime ? parseFloat(startTime) : null,
                end_time: endTime ? parseFloat(endTime) : null
            })
        });
        
        if (!response.ok) throw new Error('Download failed');
        
        // Get the blob and create download link
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `video_${Date.now()}.mp4`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
        
        // Clear form
        document.getElementById('videoUrl').value = '';
        document.getElementById('videoInfo').style.display = 'none';
        
        // Refresh history
        loadDownloadHistory();
        
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        document.getElementById('progress').style.display = 'none';
    }
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

async function loadDownloadHistory() {
    try {
        const response = await fetch('/api/user/sessions', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const sessions = await response.json();
            const historyDiv = document.getElementById('downloadHistory');
            
            if (sessions.length === 0) {
                historyDiv.innerHTML = '<p>No recent downloads</p>';
            } else {
                historyDiv.innerHTML = sessions.map(session => `
                    <div class="history-item">
                        <span>${new Date(session.created_at).toLocaleString()}</span>
                        <span class="status-${session.status}">${session.status}</span>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
}

// Check authentication on load
window.addEventListener('DOMContentLoaded', () => {
    if (!token) {
        window.location.href = '/login';
    }
    loadDownloadHistory();
});