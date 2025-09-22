from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import uuid
from typing import Dict, List
from ..utils.logger import logger

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, List[str]] = {}  # user_id -> [connection_ids]
    
    async def connect(self, websocket: WebSocket, user_id: str):
        connection_id = str(uuid.uuid4())
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for user {user_id}")
        return connection_id
    
    def disconnect(self, connection_id: str, user_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        if user_id in self.user_connections:
            self.user_connections[user_id].remove(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.user_connections:
            for connection_id in self.user_connections[user_id]:
                if connection_id in self.active_connections:
                    try:
                        await self.active_connections[connection_id].send_text(json.dumps(message))
                    except:
                        # Connection might be dead, remove it
                        self.disconnect(connection_id, user_id)
    
    async def broadcast(self, message: dict):
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except:
                # Remove dead connections
                for user_id, connections in self.user_connections.items():
                    if connection_id in connections:
                        self.disconnect(connection_id, user_id)

manager = ConnectionManager()

async def websocket_endpoint(websocket: WebSocket, token: str):
    """WebSocket endpoint for real-time progress updates"""
    # For now, we'll use a simple user ID. In a real app, you'd validate the token
    user_id = f"user_{token[:8]}"  # Simple user identification
    
    try:
        connection_id = await manager.connect(websocket, user_id)
        
        while True:
            try:
                # Wait for messages (keep connection alive)
                data = await websocket.receive_text()
                # Handle any client messages if needed
                try:
                    message = json.loads(data)
                    if message.get('type') == 'ping':
                        await websocket.send_text(json.dumps({'type': 'pong'}))
                except json.JSONDecodeError:
                    pass
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(connection_id, user_id)

# Helper functions for sending progress updates
async def send_progress_update(user_id: str, progress_data: dict):
    """Send progress update to specific user"""
    message = {
        'type': 'progress',
        'data': progress_data,
        'timestamp': asyncio.get_event_loop().time()
    }
    await manager.send_personal_message(message, user_id)

async def send_download_complete(user_id: str, filename: str, filesize: int = None):
    """Send download completion notification"""
    message = {
        'type': 'download_complete',
        'data': {
            'filename': filename,
            'filesize': filesize,
            'message': 'Download completed successfully!'
        },
        'timestamp': asyncio.get_event_loop().time()
    }
    await manager.send_personal_message(message, user_id)

async def send_download_error(user_id: str, error_message: str):
    """Send download error notification"""
    message = {
        'type': 'download_error',
        'data': {
            'error': error_message,
            'message': 'Download failed'
        },
        'timestamp': asyncio.get_event_loop().time()
    }
    await manager.send_personal_message(message, user_id)