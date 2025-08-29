from typing import List, Optional, Dict, Any
from ..connection import mongo_db
from ..models.device import Device
import logging

logger = logging.getLogger(__name__)

class DeviceOperations:
    def __init__(self):
        self.collection = mongo_db.db.devices
    
    def create_device(self, device: Device) -> bool:
        try:
            self.collection.insert_one(device.to_dict())
            logger.info(f"Device created: {device.device_id}")
            return True
        except Exception as e:
            logger.error(f"Device creation failed: {e}")
            return False
    
    def get_device_by_id(self, device_id: str) -> Optional[Device]:
        try:
            data = self.collection.find_one({"device_id": device_id})
            return Device.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting device {device_id}: {e}")
            return None
    
    def get_device_by_hwid(self, hwid: str) -> Optional[Device]:
        try:
            data = self.collection.find_one({"hwid": hwid})
            return Device.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting device by HWID {hwid}: {e}")
            return None
    
    def get_devices_by_user(self, user_id: str, active_only: bool = True) -> List[Device]:
        try:
            filter_dict = {"user_id": user_id}
            if active_only:
                filter_dict["is_active"] = True
            
            cursor = self.collection.find(filter_dict)
            devices = []
            for data in cursor:
                devices.append(Device.from_dict(data))
            return devices
        except Exception as e:
            logger.error(f"Error getting devices for user {user_id}: {e}")
            return []
    
    def get_primary_device(self, user_id: str) -> Optional[Device]:
        try:
            data = self.collection.find_one({"user_id": user_id, "is_primary": True, "is_active": True})
            return Device.from_dict(data) if data else None
        except Exception as e:
            logger.error(f"Error getting primary device for user {user_id}: {e}")
            return None
    
    def update_device(self, device_id: str, updates: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(
                {"device_id": device_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating device {device_id}: {e}")
            return False
    
    def set_primary_device(self, user_id: str, device_id: str) -> bool:
        try:
            # First, unset all primary devices for the user
            self.collection.update_many(
                {"user_id": user_id},
                {"$set": {"is_primary": False}}
            )
            
            # Then set the specified device as primary
            result = self.collection.update_one(
                {"device_id": device_id, "user_id": user_id},
                {"$set": {"is_primary": True}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error setting primary device {device_id} for user {user_id}: {e}")
            return False
    
    def deactivate_device(self, device_id: str) -> bool:
        try:
            result = self.collection.update_one(
                {"device_id": device_id},
                {"$set": {"is_active": False, "is_primary": False}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deactivating device {device_id}: {e}")
            return False
    
    def delete_device(self, device_id: str) -> bool:
        try:
            result = self.collection.delete_one({"device_id": device_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting device {device_id}: {e}")
            return False
    
    def count_user_devices(self, user_id: str, active_only: bool = True) -> int:
        try:
            filter_dict = {"user_id": user_id}
            if active_only:
                filter_dict["is_active"] = True
            return self.collection.count_documents(filter_dict)
        except Exception as e:
            logger.error(f"Error counting devices for user {user_id}: {e}")
            return 0

# Global instance
device_ops = DeviceOperations()