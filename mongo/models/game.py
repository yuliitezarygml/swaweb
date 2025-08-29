from datetime import datetime
from typing import Dict, Any, List

class Game:
    def __init__(self, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        
        self.game_id = data.get('game_id', '')
        self.name = data.get('name', '')
        self.access_type = data.get('access_type', 'free')  # 'free' or 'premium'
        self.icon = data.get('icon', '')
        self.size = data.get('size', 0)
        self.last_updated = data.get('last_updated', datetime.now().isoformat())
        self.categories = data.get('categories', [])
        self.description = data.get('description', '')
        self.developer = data.get('developer', '')
        self.release_date = data.get('release_date', '')
        self.rating = data.get('rating', 0.0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'game_id': self.game_id,
            'name': self.name,
            'access_type': self.access_type,
            'icon': self.icon,
            'size': self.size,
            'last_updated': self.last_updated,
            'categories': self.categories,
            'description': self.description,
            'developer': self.developer,
            'release_date': self.release_date,
            'rating': self.rating
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Game':
        return cls(data)