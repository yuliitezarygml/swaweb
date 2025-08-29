import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDB, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self.connect()
    
    def connect(self):
        try:
            mongodb_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/swa_database')
            self._client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self._client.admin.command('ping')
            
            # Extract database name from URI or use default
            if 'swa_database' in mongodb_uri:
                db_name = 'swa_database'
            else:
                db_name = mongodb_uri.split('/')[-1] if '/' in mongodb_uri else 'swa_database'
            
            self._db = self._client[db_name]
            logger.info(f"Connected to MongoDB: {db_name}")
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise e
    
    @property
    def client(self):
        if self._client is None:
            self.connect()
        return self._client
    
    @property
    def db(self):
        if self._db is None:
            self.connect()
        return self._db
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed")

# Global instance
mongo_db = MongoDB()