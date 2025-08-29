from datetime import datetime, date
import uuid
from typing import Optional, Dict, Any

class PromoCode:
    def __init__(self, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        
        self.id = data.get('id', str(uuid.uuid4()))
        self.code = data.get('code', '')
        self.description = data.get('description', '')
        self.uses_limit = data.get('uses_limit', 1)
        self.uses_count = data.get('uses_count', 0)
        self.expires_at = data.get('expires_at')
        self.gives_premium = data.get('gives_premium', False)
        self.premium_duration = data.get('premium_duration', 0)
        self.slots = data.get('slots', 0)
        self.created_at = data.get('created_at', datetime.now().isoformat())
        self.used_by = data.get('used_by', [])
        self.group = data.get('group', '')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'uses_limit': self.uses_limit,
            'uses_count': self.uses_count,
            'expires_at': self.expires_at,
            'gives_premium': self.gives_premium,
            'premium_duration': self.premium_duration,
            'slots': self.slots,
            'created_at': self.created_at,
            'used_by': self.used_by,
            'group': self.group
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PromoCode':
        return cls(data)
    
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expires = datetime.strptime(self.expires_at, '%Y-%m-%d')
            return expires.date() < date.today()
        except:
            return False
    
    def is_exhausted(self) -> bool:
        return self.uses_count >= self.uses_limit
    
    def can_be_used(self, user_id: str = None) -> bool:
        if self.is_expired() or self.is_exhausted():
            return False
        
        if user_id and user_id in self.used_by:
            return False
        
        return True