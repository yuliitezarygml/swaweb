from datetime import datetime, date
import uuid
from typing import Optional, List, Dict, Any

class User:
    def __init__(self, data: Dict[str, Any] = None, **kwargs):
        if data is None:
            data = {}
        
        # Support both dict and kwargs initialization
        data.update(kwargs)
        
        self.id = data.get('id', str(uuid.uuid4()))
        self.username = data.get('username', '')
        self.email = data.get('email', '')
        self.password = data.get('password', '')
        self.join_date = data.get('join_date', date.today().isoformat())
        self.status = data.get('status', 'Standard')
        self.games_count = data.get('games_count', 0)
        self.is_admin = data.get('is_admin', False)
        self.premium_expires = data.get('premium_expires')
        self.slots = data.get('slots', 1)
        self.devices = data.get('devices', [])
        self.referral_code = data.get('referral_code', '')
        self.used_referral = data.get('used_referral')
        self.total_referrals = data.get('total_referrals', 0)
        self.last_login = data.get('last_login')
        self.last_activity = data.get('last_activity')
        
        # Launcher related fields
        self.launcher_code = data.get('launcher_code')
        self.launcher_connected = data.get('launcher_connected', False)
        self.last_connection = data.get('last_connection')
        self.unique_id = data.get('unique_id')
        self.total_play_time = data.get('total_play_time', '0h 0m')
        self.games_played = data.get('games_played', 0)
        self.achievements = data.get('achievements', 0)
        self.last_session = data.get('last_session')
        self.game_sessions = data.get('game_sessions', [])
        self.friends = data.get('friends', [])
        self.active_devices = data.get('active_devices', [])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'password': self.password,
            'join_date': self.join_date,
            'status': self.status,
            'games_count': self.games_count,
            'is_admin': self.is_admin,
            'premium_expires': self.premium_expires,
            'slots': self.slots,
            'devices': self.devices,
            'referral_code': self.referral_code,
            'used_referral': self.used_referral,
            'total_referrals': self.total_referrals,
            'last_login': self.last_login,
            'last_activity': self.last_activity,
            # Launcher related fields
            'launcher_code': self.launcher_code,
            'launcher_connected': self.launcher_connected,
            'last_connection': self.last_connection,
            'unique_id': self.unique_id,
            'total_play_time': self.total_play_time,
            'games_played': self.games_played,
            'achievements': self.achievements,
            'last_session': self.last_session,
            'game_sessions': self.game_sessions,
            'friends': self.friends,
            'active_devices': self.active_devices
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(data)
    
    def is_premium(self) -> bool:
        if not self.premium_expires:
            return False
        try:
            expires = datetime.strptime(self.premium_expires, '%Y-%m-%d')
            return expires.date() >= date.today()
        except:
            return False
    
    def has_available_slots(self) -> bool:
        return len(self.devices) < self.slots