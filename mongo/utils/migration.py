import json
import os
from datetime import datetime
from typing import Dict, List, Any
import logging
from ..connection import mongo_db
from ..operations.user_ops import user_ops
from ..operations.promo_ops import promo_ops
from ..models.user import User
from ..models.promo_code import PromoCode

logger = logging.getLogger(__name__)

class DataMigration:
    def __init__(self):
        self.base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    def migrate_users_from_json(self, json_file: str = None) -> int:
        if not json_file:
            json_file = os.path.join(self.base_path, 'users.json')
        
        if not os.path.exists(json_file):
            logger.warning(f"Users JSON file not found: {json_file}")
            return 0
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
            
            migrated_count = 0
            for user_data in users_data:
                user = User.from_dict(user_data)
                if user_ops.create_user(user):
                    migrated_count += 1
                else:
                    logger.warning(f"Failed to migrate user: {user.username}")
            
            logger.info(f"Migrated {migrated_count} users from JSON")
            return migrated_count
            
        except Exception as e:
            logger.error(f"Error migrating users from JSON: {e}")
            return 0
    
    def migrate_promo_codes_from_json(self, json_file: str = None) -> int:
        if not json_file:
            json_file = os.path.join(self.base_path, 'promo_codes.json')
        
        if not os.path.exists(json_file):
            logger.warning(f"Promo codes JSON file not found: {json_file}")
            return 0
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                promos_data = json.load(f)
            
            migrated_count = 0
            for promo_data in promos_data:
                # Convert old format to new format if needed
                if 'gives_premium' in promo_data:
                    promo_data['gives_premium'] = promo_data['gives_premium'] == 'on'
                
                promo = PromoCode.from_dict(promo_data)
                if promo_ops.create_promo_code(promo):
                    migrated_count += 1
                else:
                    logger.warning(f"Failed to migrate promo code: {promo.code}")
            
            logger.info(f"Migrated {migrated_count} promo codes from JSON")
            return migrated_count
            
        except Exception as e:
            logger.error(f"Error migrating promo codes from JSON: {e}")
            return 0
    
    def export_users_to_json(self, json_file: str = None) -> int:
        if not json_file:
            json_file = os.path.join(self.base_path, 'users_backup.json')
        
        try:
            users = user_ops.get_all_users()
            users_data = [user.to_dict() for user in users]
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(users_data)} users to JSON")
            return len(users_data)
            
        except Exception as e:
            logger.error(f"Error exporting users to JSON: {e}")
            return 0
    
    def export_promo_codes_to_json(self, json_file: str = None) -> int:
        if not json_file:
            json_file = os.path.join(self.base_path, 'promo_codes_backup.json')
        
        try:
            promos = promo_ops.get_all_promo_codes()
            promos_data = [promo.to_dict() for promo in promos]
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(promos_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(promos_data)} promo codes to JSON")
            return len(promos_data)
            
        except Exception as e:
            logger.error(f"Error exporting promo codes to JSON: {e}")
            return 0
    
    def migrate_all_from_json(self) -> Dict[str, int]:
        results = {
            'users': 0,
            'promo_codes': 0
        }
        
        logger.info("Starting migration from JSON files to MongoDB")
        
        results['users'] = self.migrate_users_from_json()
        results['promo_codes'] = self.migrate_promo_codes_from_json()
        
        total = sum(results.values())
        logger.info(f"Migration completed. Total records migrated: {total}")
        
        return results
    
    def backup_all_to_json(self) -> Dict[str, int]:
        results = {
            'users': 0,
            'promo_codes': 0
        }
        
        logger.info("Starting backup from MongoDB to JSON files")
        
        results['users'] = self.export_users_to_json()
        results['promo_codes'] = self.export_promo_codes_to_json()
        
        total = sum(results.values())
        logger.info(f"Backup completed. Total records exported: {total}")
        
        return results
    
    def clear_all_collections(self) -> Dict[str, int]:
        results = {}
        
        try:
            # Clear users
            result = mongo_db.db.users.delete_many({})
            results['users'] = result.deleted_count
            
            # Clear promo codes
            result = mongo_db.db.promo_codes.delete_many({})
            results['promo_codes'] = result.deleted_count
            
            # Clear games
            result = mongo_db.db.games.delete_many({})
            results['games'] = result.deleted_count
            
            # Clear sessions
            result = mongo_db.db.sessions.delete_many({})
            results['sessions'] = result.deleted_count
            
            # Clear devices
            result = mongo_db.db.devices.delete_many({})
            results['devices'] = result.deleted_count
            
            # Clear stats
            result = mongo_db.db.stats.delete_many({})
            results['stats'] = result.deleted_count
            
            logger.info(f"Cleared all collections: {results}")
            
        except Exception as e:
            logger.error(f"Error clearing collections: {e}")
        
        return results

# Global instance
migration = DataMigration()