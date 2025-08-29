from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ..connection import mongo_db
from ..models.session import Session
import logging

logger = logging.getLogger(__name__)

class SessionOperations:
    def __init__(self):
        self.collection = mongo_db.db.sessions
    
    def create_session(self, session: Session) -> bool:
        try:
            self.collection.insert_one(session.to_dict())
            logger.info(f"Session created: {session.session_id}")
            return True
        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            return False
    
    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        try:
            data = self.collection.find_one({"session_id": session_id})
            return Session.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    def get_sessions_by_user(self, user_id: str, active_only: bool = True) -> List[Session]:
        try:
            filter_dict = {"user_id": user_id}
            if active_only:
                filter_dict["is_active"] = True
            
            cursor = self.collection.find(filter_dict)
            sessions = []
            for data in cursor:
                sessions.append(Session.from_dict(data))
            return sessions
        except Exception as e:
            logger.error(f"Error getting sessions for user {user_id}: {e}")
            return []
    
    def update_session_activity(self, session_id: str, timestamp: str = None) -> bool:
        try:
            if not timestamp:
                timestamp = datetime.now().isoformat()
            
            result = self.collection.update_one(
                {"session_id": session_id},
                {"$set": {"last_activity": timestamp}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating session activity {session_id}: {e}")
            return False
    
    def deactivate_session(self, session_id: str) -> bool:
        try:
            result = self.collection.update_one(
                {"session_id": session_id},
                {"$set": {"is_active": False}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deactivating session {session_id}: {e}")
            return False
    
    def deactivate_user_sessions(self, user_id: str, except_session: str = None) -> int:
        try:
            filter_dict = {"user_id": user_id, "is_active": True}
            if except_session:
                filter_dict["session_id"] = {"$ne": except_session}
            
            result = self.collection.update_many(
                filter_dict,
                {"$set": {"is_active": False}}
            )
            return result.modified_count
        except Exception as e:
            logger.error(f"Error deactivating user sessions {user_id}: {e}")
            return 0
    
    def cleanup_expired_sessions(self) -> int:
        try:
            current_time = datetime.now().isoformat()
            result = self.collection.delete_many({
                "$or": [
                    {"expires_at": {"$lt": current_time}},
                    {"is_active": False}
                ]
            })
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0
    
    def delete_session(self, session_id: str) -> bool:
        try:
            result = self.collection.delete_one({"session_id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False

# Global instance
session_ops = SessionOperations()