from typing import List, Optional, Dict, Any
from ..connection import mongo_db
from ..models.game import Game
import logging

logger = logging.getLogger(__name__)

class GameOperations:
    def __init__(self):
        self.collection = mongo_db.db.games
    
    def upsert_game(self, game: Game) -> bool:
        try:
            result = self.collection.update_one(
                {"game_id": game.game_id},
                {"$set": game.to_dict()},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting game {game.game_id}: {e}")
            return False
    
    def upsert_games_bulk(self, games: List[Game]) -> int:
        try:
            operations = []
            for game in games:
                operations.append({
                    "updateOne": {
                        "filter": {"game_id": game.game_id},
                        "update": {"$set": game.to_dict()},
                        "upsert": True
                    }
                })
            
            if operations:
                result = self.collection.bulk_write(operations)
                return result.upserted_count + result.modified_count
            return 0
        except Exception as e:
            logger.error(f"Error bulk upserting games: {e}")
            return 0
    
    def get_game_by_id(self, game_id: str) -> Optional[Game]:
        try:
            data = self.collection.find_one({"game_id": game_id})
            return Game.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting game {game_id}: {e}")
            return None
    
    def get_games_by_access_type(self, access_type: str, limit: int = None, skip: int = 0) -> List[Game]:
        try:
            cursor = self.collection.find({"access_type": access_type}).skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            games = []
            for data in cursor:
                games.append(Game.from_dict(data))
            return games
        except Exception as e:
            logger.error(f"Error getting games by access type {access_type}: {e}")
            return []
    
    def get_all_games(self, limit: int = None, skip: int = 0) -> List[Game]:
        try:
            cursor = self.collection.find().skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            games = []
            for data in cursor:
                games.append(Game.from_dict(data))
            return games
        except Exception as e:
            logger.error(f"Error getting all games: {e}")
            return []
    
    def search_games(self, query: str, access_type: str = None, limit: int = 50) -> List[Game]:
        try:
            filter_dict = {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                    {"developer": {"$regex": query, "$options": "i"}}
                ]
            }
            
            if access_type:
                filter_dict["access_type"] = access_type
            
            cursor = self.collection.find(filter_dict).limit(limit)
            
            games = []
            for data in cursor:
                games.append(Game.from_dict(data))
            return games
        except Exception as e:
            logger.error(f"Error searching games with query '{query}': {e}")
            return []
    
    def count_games(self, access_type: str = None) -> int:
        try:
            filter_dict = {}
            if access_type:
                filter_dict["access_type"] = access_type
            return self.collection.count_documents(filter_dict)
        except Exception as e:
            logger.error(f"Error counting games: {e}")
            return 0
    
    def delete_game(self, game_id: str) -> bool:
        try:
            result = self.collection.delete_one({"game_id": game_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting game {game_id}: {e}")
            return False
    
    def clear_games_by_access_type(self, access_type: str) -> int:
        try:
            result = self.collection.delete_many({"access_type": access_type})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error clearing games by access type {access_type}: {e}")
            return 0
    
    def get_games_stats(self) -> Dict[str, Any]:
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$access_type",
                        "count": {"$sum": 1},
                        "total_size": {"$sum": "$size"}
                    }
                }
            ]
            
            result = list(self.collection.aggregate(pipeline))
            stats = {"free": {"count": 0, "total_size": 0}, "premium": {"count": 0, "total_size": 0}}
            
            for item in result:
                access_type = item["_id"]
                if access_type in stats:
                    stats[access_type] = {
                        "count": item["count"],
                        "total_size": item["total_size"]
                    }
            
            return stats
        except Exception as e:
            logger.error(f"Error getting games stats: {e}")
            return {"free": {"count": 0, "total_size": 0}, "premium": {"count": 0, "total_size": 0}}

# Global instance
game_ops = GameOperations()