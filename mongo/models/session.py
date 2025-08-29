from datetime import datetime, timedelta
import uuid
from typing import Dict, Any

class Session:
    def __init__(self, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        
        self.session_id = data.get('session_id', str(uuid.uuid4()))
        self.user_id = data.get('user_id', '')
        self.device_id = data.get('device_id', '')
        self.created_at = data.get('created_at', datetime.now().isoformat())
        self.expires_at = data.get('expires_at', (datetime.now() + timedelta(days=30)).isoformat())
        self.last_activity = data.get('last_activity', datetime.now().isoformat())
        self.is_active = data.get('is_active', True)
        self.ip_address = data.get('ip_address', '')
        self.user_agent = data.get('user_agent', '')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'last_activity': self.last_activity,
            'is_active': self.is_active,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        return cls(data)
    
    def is_expired(self) -> bool:
        try:
            expires = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            return expires < datetime.now()
        except:
            return True