// MongoDB initialization script for SWA Database
db = db.getSiblingDB('swa_database');

// Create users collection
db.createCollection('users');

// Create indexes for users collection
db.users.createIndex({ "username": 1 }, { unique: true });
db.users.createIndex({ "email": 1 }, { unique: true });
db.users.createIndex({ "id": 1 }, { unique: true });

// Create promo_codes collection
db.createCollection('promo_codes');

// Create indexes for promo_codes collection
db.promo_codes.createIndex({ "code": 1 }, { unique: true });
db.promo_codes.createIndex({ "id": 1 }, { unique: true });

// Create games collection for caching
db.createCollection('games');

// Create indexes for games collection
db.games.createIndex({ "game_id": 1 }, { unique: true });
db.games.createIndex({ "access_type": 1 });

// Create sessions collection for user sessions
db.createCollection('sessions');

// Create indexes for sessions collection
db.sessions.createIndex({ "session_id": 1 }, { unique: true });
db.sessions.createIndex({ "user_id": 1 });
db.sessions.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 });

// Create stats collection for analytics
db.createCollection('stats');

// Create indexes for stats collection
db.stats.createIndex({ "date": 1 });
db.stats.createIndex({ "type": 1 });

// Create devices collection for device management
db.createCollection('devices');

// Create indexes for devices collection
db.devices.createIndex({ "user_id": 1 });
db.devices.createIndex({ "device_id": 1 }, { unique: true });

// Create slots collection for slot management
db.createCollection('slots');

// Create indexes for slots collection
db.slots.createIndex({ "user_id": 1 });
db.slots.createIndex({ "slot_id": 1 }, { unique: true });

print('SWA Database initialized successfully with collections and indexes');

// Insert sample admin user if needed
var adminUser = {
    "id": "admin-user-uuid",
    "username": "admin",
    "email": "admin@swa.local",
    "password": "hashed_password_here", // This should be properly hashed
    "join_date": new Date().toISOString().split('T')[0],
    "status": "Premium",
    "games_count": 0,
    "is_admin": true,
    "premium_expires": null,
    "slots": 5,
    "devices": [],
    "referral_code": "ADMIN123",
    "used_referral": null,
    "total_referrals": 0
};

// Uncomment to insert admin user
// db.users.insertOne(adminUser);
// print('Admin user created');