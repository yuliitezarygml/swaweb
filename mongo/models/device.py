from datetime import datetime
import uuid
from typing import Dict, Any

class Device:
    def __init__(self, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        
        self.device_id = data.get('device_id', str(uuid.uuid4()))
        self.user_id = data.get('user_id', '')
        self.device_name = data.get('device_name', '')
        self.hwid = data.get('hwid', '')
        self.os_info = data.get('os_info', '')
        self.last_login = data.get('last_login', datetime.now().isoformat())
        self.is_primary = data.get('is_primary', False)
        self.is_active = data.get('is_active', True)
        self.created_at = data.get('created_at', datetime.now().isoformat())
        self.ip_address = data.get('ip_address', '')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'device_id': self.device_id,
            'user_id': self.user_id,
            'device_name': self.device_name,
            'hwid': self.hwid,
            'os_info': self.os_info,
            'last_login': self.last_login,
            'is_primary': self.is_primary,
            'is_active': self.is_active,
            'created_at': self.created_at,
            'ip_address': self.ip_address
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Device':
        return cls(data)