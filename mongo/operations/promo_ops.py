from typing import List, Optional, Dict, Any
from pymongo.errors import DuplicateKeyError
from ..connection import mongo_db
from ..models.promo_code import PromoCode
import logging

logger = logging.getLogger(__name__)

class PromoCodeOperations:
    def __init__(self):
        self.collection = mongo_db.db.promo_codes
    
    def create_promo_code(self, promo: PromoCode) -> bool:
        try:
            self.collection.insert_one(promo.to_dict())
            logger.info(f"Promo code created: {promo.code}")
            return True
        except DuplicateKeyError as e:
            logger.error(f"Promo code creation failed - duplicate code: {e}")
            return False
        except Exception as e:
            logger.error(f"Promo code creation failed: {e}")
            return False
    
    def get_promo_by_code(self, code: str) -> Optional[PromoCode]:
        try:
            data = self.collection.find_one({"code": code})
            return PromoCode.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting promo code {code}: {e}")
            return None
    
    def get_promo_by_id(self, promo_id: str) -> Optional[PromoCode]:
        try:
            data = self.collection.find_one({"id": promo_id})
            return PromoCode.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting promo code by ID {promo_id}: {e}")
            return None
    
    def get_all_promo_codes(self, limit: int = None, skip: int = 0) -> List[PromoCode]:
        try:
            cursor = self.collection.find().skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            promos = []
            for data in cursor:
                promos.append(PromoCode.from_dict(data))
            return promos
        except Exception as e:
            logger.error(f"Error getting all promo codes: {e}")
            return []
    
    def get_promo_codes_by_group(self, group: str) -> List[PromoCode]:
        try:
            cursor = self.collection.find({"group": group})
            promos = []
            for data in cursor:
                promos.append(PromoCode.from_dict(data))
            return promos
        except Exception as e:
            logger.error(f"Error getting promo codes by group {group}: {e}")
            return []
    
    def update_promo_code(self, promo_id: str, updates: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(
                {"id": promo_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating promo code {promo_id}: {e}")
            return False
    
    def delete_promo_code(self, promo_id: str) -> bool:
        try:
            result = self.collection.delete_one({"id": promo_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting promo code {promo_id}: {e}")
            return False
    
    def delete_promo_codes_by_group(self, group: str) -> int:
        try:
            result = self.collection.delete_many({"group": group})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting promo codes by group {group}: {e}")
            return 0
    
    def use_promo_code(self, code: str, user_id: str) -> bool:
        try:
            promo = self.get_promo_by_code(code)
            if not promo or not promo.can_be_used(user_id):
                return False
            
            result = self.collection.update_one(
                {"code": code},
                {
                    "$inc": {"uses_count": 1},
                    "$push": {"used_by": user_id}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error using promo code {code} by user {user_id}: {e}")
            return False
    
    def count_promo_codes(self, filter_dict: Dict[str, Any] = None) -> int:
        try:
            if filter_dict:
                return self.collection.count_documents(filter_dict)
            return self.collection.count_documents({})
        except Exception as e:
            logger.error(f"Error counting promo codes: {e}")
            return 0
    
    def get_user_used_promos(self, user_id: str) -> List[PromoCode]:
        try:
            cursor = self.collection.find({"used_by": user_id})
            promos = []
            for data in cursor:
                promos.append(PromoCode.from_dict(data))
            return promos
        except Exception as e:
            logger.error(f"Error getting used promos for user {user_id}: {e}")
            return []

# Global instance
promo_ops = PromoCodeOperations()