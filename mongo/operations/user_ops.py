from typing import List, Optional, Dict, Any
from pymongo.errors import DuplicateKeyError
from ..connection import mongo_db
from ..models.user import User
import logging

logger = logging.getLogger(__name__)

class UserOperations:
    def __init__(self):
        self.collection = mongo_db.db.users
    
    def create_user(self, user: User) -> bool:
        try:
            self.collection.insert_one(user.to_dict())
            logger.info(f"User created: {user.username}")
            return True
        except DuplicateKeyError as e:
            logger.error(f"User creation failed - duplicate key: {e}")
            return False
        except Exception as e:
            logger.error(f"User creation failed: {e}")
            return False
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        try:
            data = self.collection.find_one({"id": user_id})
            return User.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        try:
            data = self.collection.find_one({"username": username})
            return User.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        try:
            data = self.collection.find_one({"email": email})
            return User.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None
    
    def get_user_by_launcher_code(self, launcher_code: str) -> Optional[User]:
        try:
            data = self.collection.find_one({"launcher_code": launcher_code})
            return User.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting user by launcher code {launcher_code}: {e}")
            return None
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(
                {"id": user_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False
    
    def delete_user(self, user_id: str) -> bool:
        try:
            result = self.collection.delete_one({"id": user_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return False
    
    def get_all_users(self, limit: int = None, skip: int = 0) -> List[User]:
        try:
            cursor = self.collection.find().skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            users = []
            for data in cursor:
                users.append(User.from_dict(data))
            return users
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def count_users(self, filter_dict: Dict[str, Any] = None) -> int:
        try:
            if filter_dict:
                return self.collection.count_documents(filter_dict)
            return self.collection.count_documents({})
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            return 0
    
    def get_users_by_status(self, status: str) -> List[User]:
        try:
            cursor = self.collection.find({"status": status})
            users = []
            for data in cursor:
                users.append(User.from_dict(data))
            return users
        except Exception as e:
            logger.error(f"Error getting users by status {status}: {e}")
            return []
    
    def update_user_last_activity(self, user_id: str, timestamp: str) -> bool:
        return self.update_user(user_id, {"last_activity": timestamp})
    
    def add_device_to_user(self, user_id: str, device_info: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(
                {"id": user_id},
                {"$push": {"devices": device_info}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error adding device to user {user_id}: {e}")
            return False
    
    def remove_device_from_user(self, user_id: str, device_id: str) -> bool:
        try:
            result = self.collection.update_one(
                {"id": user_id},
                {"$pull": {"devices": {"device_id": device_id}}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error removing device from user {user_id}: {e}")
            return False

# Global instance
user_ops = UserOperations()