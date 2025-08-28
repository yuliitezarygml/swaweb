from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import requests
from datetime import datetime, date, timedelta
import json
from collections import defaultdict
import os
import time
import threading
import atexit
import uuid
import hashlib
import re
from functools import wraps
import random
import string
import sys

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'swa-dev-secret-key-change-in-prod')

# Define custom Jinja2 filters
@app.template_filter('escapejs')
def escapejs_filter(value):
    """Escape characters for use in JavaScript."""
    if isinstance(value, str):
        return value.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
    return value
    
@app.template_filter('to_datetime')
def to_datetime_filter(value):
    """Convert a string date to a datetime object."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None

# User data file
USERS_FILE = 'users.json'

# Promo codes file
PROMO_CODES_FILE = 'promo_codes.json'

# Cache data structures
data_cache = {
    "stats": None,
    "last_stats_update": 0,
    "daily_data": {},  # Cache for daily data {date_str: data}
    "last_daily_update": {},  # Last update for each day {date_str: timestamp}
    "period_data": {
        "7": None,  # Weekly data
        "30": None  # Monthly data
    },
    "last_period_update": {
        "7": 0,
        "30": 0
    },
    "games": {
        "free": None,
        "premium": None
    },
    "last_games_update": {
        "free": 0,
        "premium": 0
    }
}

# Cache update period in seconds
CACHE_LIFETIME = {
    "stats": 300,  # 5 minutes for main statistics
    "daily": 3600,  # 1 hour for daily data
    "period": 7200,  # 2 hours for periods (week/month)
    "games": 3600  # 1 hour for game data
}

# API URLs for games
GAMES_API = {
    "free": "https://swa-recloud.fun/static/games.json",  # Use an alternative working API if available
    "premium": "https://swa-recloud.fun/static/game2.json"  # Use an alternative working API if available
}

# Cache for game data from the external API
games_api_cache = {
    "data": None,
    "last_updated": 0,
    "free_games": None,
    "premium_games": None
}

# Cache lifetime for game data (in seconds)
GAMES_CACHE_LIFETIME = 3600  # 1 hour

# Helper functions for promo codes
def get_promo_codes():
    """Load promo codes from JSON file"""
    if not os.path.exists(PROMO_CODES_FILE):
        with open(PROMO_CODES_FILE, 'w') as f:
            json.dump([], f)
        return []
        
    try:
        with open(PROMO_CODES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_promo_codes(promo_codes):
    """Save promo codes to JSON file"""
    with open(PROMO_CODES_FILE, 'w') as f:
        json.dump(promo_codes, f, indent=4)

def generate_promo_code(length=14):
    """Generate a random promo code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def find_promo_code(code):
    """Find a promo code by its code"""
    promo_codes = get_promo_codes()
    for promo in promo_codes:
        if promo['code'].upper() == code.upper():
            return promo
    return None

# Helper functions for user authentication
def get_users():
    """Load users from JSON file"""
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump([], f)
        return []
        
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def has_valid_premium(user):
    """Check if a user has valid premium status"""
    # Admin users always have premium access
    if user.get('is_admin', False):
        return True
    
    # Check if user has Premium status
    if user.get('status') != 'Premium':
        return False
    
    # Check for premium expiration
    if user.get('premium_expires_at'):
        try:
            expires_at = datetime.strptime(user['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expires_at:
                # Premium has expired but not yet revoked by background task
                return False
        except Exception:
            # Error parsing expiration, assume valid to avoid blocking user
            return True
    
    # Premium status is valid
    return True

def is_admin(user):
    """Check if a user has admin privileges"""
    return user.get('is_admin', False)

def save_users(users):
    """Save users to JSON file with error handling and atomic writes"""
    import tempfile
    import shutil
    
    try:
        # Create temporary file in same directory
        temp_file = USERS_FILE + '.tmp'
        
        # Write to temporary file first
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
        
        # Atomic replace - only if write was successful
        shutil.move(temp_file, USERS_FILE)
        
    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        
        # Log error and re-raise
        print(f"Error saving users: {e}")
        raise

def hash_password(password):
    """Hash a password for storing"""
    salt = uuid.uuid4().hex
    return hashlib.sha256(salt.encode() + password.encode()).hexdigest() + ':' + salt

def check_password(hashed_password, user_password):
    """Check hashed password against a provided password"""
    password, salt = hashed_password.split(':')
    return password == hashlib.sha256(salt.encode() + user_password.encode()).hexdigest()

def find_user_by_username(username):
    """Find a user by username"""
    if username is None:
        return None
        
    users = get_users()
    for user in users:
        if user['username'].lower() == username.lower():
            return user
    return None

def find_user_by_email(email):
    """Find a user by email"""
    users = get_users()
    for user in users:
        if user['email'].lower() == email.lower():
            return user
    return None

def find_user_by_id(user_id):
    """Find a user by id"""
    users = get_users()
    for user in users:
        if user['id'] == user_id:
            return user
    return None

def is_valid_username(username):
    """Check if username is valid"""
    return re.match(r'^[a-zA-Z0-9_]{3,20}$', username) is not None

def is_valid_email(email):
    """Check if email is valid"""
    return re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email) is not None

def is_valid_password(password):
    """Check if password is valid (at least 8 characters)"""
    return len(password) >= 8

def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Add admin_required decorator after the login_required decorator
def admin_required(f):
    """Decorator for routes that require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            print(f"[DEBUG] admin_required: user_id not in session, redirecting to login")
            return redirect(url_for('login', next=request.url))
        
        user = find_user_by_id(session['user_id'])
        print(f"[DEBUG] admin_required: user={user}")
        
        if not user:
            print(f"[DEBUG] admin_required: user not found, redirecting to index")
            flash('You do not have access to this page', 'error')
            return redirect(url_for('index'))
            
        is_admin_user = is_admin(user)
        print(f"[DEBUG] admin_required: is_admin={is_admin_user}, user.is_admin={user.get('is_admin')}, user.status={user.get('status')}")
        
        if not is_admin_user:
            print(f"[DEBUG] admin_required: user is not admin, redirecting to index")
            flash('You do not have access to this page', 'error')
            return redirect(url_for('index'))
            
        print(f"[DEBUG] admin_required: user is admin, proceeding to {f.__name__}")
        return f(*args, **kwargs)
    return decorated_function

def generate_launcher_code():
    """Generate a unique launcher connection code"""
    prefix = "SWA2"
    # Generate two blocks of 4 alphanumeric characters
    block1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    block2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{block1}-{block2}"

def generate_unique_id(user_id):
    """Generate a unique identifier for the user in the launcher"""
    return f"SWA-{user_id}"

def find_user_by_launcher_code(code):
    """Find a user by their launcher connection code"""
    users = get_users()
    for user in users:
        if user.get('launcher_code') == code:
            return user
    return None

def add_or_update_device(user_id, device_id, device_name, device_os):
    """Add or update a device for a user"""
    users = get_users()
    for user in users:
        if user['id'] == user_id:
            # Initialize devices list if it doesn't exist
            if 'devices' not in user:
                user['devices'] = []
            
            # Check if device already exists
            device_exists = False
            for device in user.get('devices', []):
                if device['device_id'] == device_id:
                    # Update existing device
                    device['device_name'] = device_name
                    device['device_os'] = device_os
                    device['last_connection'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    device_exists = True
                    break
            
            # Add new device if it doesn't exist
            if not device_exists:
                user['devices'].append({
                    'device_id': device_id,
                    'device_name': device_name,
                    'device_os': device_os,
                    'first_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'last_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            save_users(users)
            return True
    
    return False

def update_user_stats(user_id, game_id, playtime_minutes):
    """Update user stats based on game session data"""
    users = get_users()
    for user in users:
        if user['id'] == user_id:
            # Initialize stats fields if they don't exist
            if 'games_played' not in user:
                user['games_played'] = 0
            if 'total_play_time' not in user:
                user['total_play_time'] = "0h 0m"
            if 'game_sessions' not in user:
                user['game_sessions'] = []
            
            # Update games played count
            game_ids = [session['game_id'] for session in user.get('game_sessions', [])]
            if game_id not in game_ids:
                user['games_played'] += 1
            
            # Update total play time
            current_time = user['total_play_time'].split('h ')
            current_hours = int(current_time[0])
            current_minutes = int(current_time[1].replace('m', ''))
            
            total_minutes = current_hours * 60 + current_minutes + playtime_minutes
            new_hours = total_minutes // 60
            new_minutes = total_minutes % 60
            user['total_play_time'] = f"{new_hours}h {new_minutes}m"
            
            # Get game data for recording session
            games_data = get_games_data(force_update=False)
            game_info = None
            for game in games_data.values():
                if game['id'] == game_id:
                    game_info = game
                    break
            
            # Create session record
            session_record = {
                'game_id': game_id,
                'game_name': game_info['name'] if game_info else f"Game {game_id}",
                'game_image': game_info['image'] if game_info else "",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'duration': f"{playtime_minutes//60}h {playtime_minutes%60}m",
                'date': datetime.now().strftime('%Y-%m-%d')
            }
            
            # Add to game sessions
            user['game_sessions'].append(session_record)
            
            # Update last session
            user['last_session'] = session_record
            
            # Save changes
            save_users(users)
            return True
    
    return False

# User authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if not all([username, email, password, confirm_password]):
            return render_template('register.html', error='All fields are required')
        
        if not is_valid_username(username):
            return render_template('register.html', error='Username must be 3-20 characters and contain only letters, numbers, and underscores')
        
        if not is_valid_email(email):
            return render_template('register.html', error='Invalid email address')
        
        if not is_valid_password(password):
            return render_template('register.html', error='Password must be at least 8 characters')
        
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')
        
        # Check if username or email already exists
        if find_user_by_username(username):
            return render_template('register.html', error='Username already exists')
        
        if find_user_by_email(email):
            return render_template('register.html', error='Email already exists')
        
        # Generate user ID
        user_id = str(uuid.uuid4())
        
        # Create new user - without launcher code for Standard users
        new_user = {
            'id': user_id,
            'username': username,
            'email': email,
            'password': hash_password(password),
            'join_date': datetime.now().strftime('%Y-%m-%d'),
            'status': 'Standard',
            'games_count': 0,
            'is_admin': False,
            'launcher_connected': False,
            'last_connection': None,
            'unique_id': generate_unique_id(user_id),
            'total_play_time': '0h 0m',
            'games_played': 0,
            'achievements': 0,
            'last_session': None,
            'game_sessions': [],
            'slots': 0,
            'friends': []
        }
        
        users = get_users()
        users.append(new_user)
        save_users(users)
        
        # Log the user in
        session['user_id'] = new_user['id']
        session['username'] = new_user['username']
        session['is_admin'] = is_admin(new_user)
        
        return redirect(url_for('profile'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Validate input
        if not all([username, password]):
            return render_template('login.html', error='Username and password are required')
        
        # Find user by username
        user = find_user_by_username(username)
        if not user:
            return render_template('login.html', error='Invalid username or password')
        
        # Check password
        if not check_password(user['password'], password):
            return render_template('login.html', error='Invalid username or password')
        
        # Log the user in
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = is_admin(user)
        
        # Redirect to next page if provided
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        
        # If user is admin, redirect to admin panel, otherwise to profile
        if session['is_admin']:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('profile'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout"""
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = find_user_by_id(session['user_id'])
    if not user:
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('is_admin', None)
        return redirect(url_for('login'))
    
    # Check premium expiration for this user instantly
    if user.get('status') == 'Premium' and user.get('premium_expires_at'):
        try:
            expires_at = datetime.strptime(user['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            if now > expires_at:
                # Revert to standard status
                user['status'] = 'Standard'
                del user['premium_expires_at']
                
                # Clear existing slots alignments when premium expires
                if 'friends' in user:
                    users = get_users()
                    for friend_username in list(user.get('friends', [])):
                        for u in users:
                            if u['username'].lower() == friend_username.lower() and u.get('status') == 'Premium (Aligned)' and u.get('aligned_by') == user['username']:
                                # Reset friend's status to Standard
                                u['status'] = 'Standard'
                                if 'aligned_by' in u:
                                    del u['aligned_by']
                                
                                # Add to friend's history
                                if 'premium_history' not in u:
                                    u['premium_history'] = []
                                
                                u['premium_history'].append({
                                    'date': now.strftime('%Y-%m-%d %H:%M:%S'),
                                    'action': 'Premium Status Revoked',
                                    'details': f"Revoked Premium because slot alignment from {user['username']} was removed (premium expired)"
                                })
                    
                    # Clear user's friends list
                    user['friends'] = []
                    
                    # Save changes
                    save_users(users)
                else:
                    # Just save this user's changes
                    users = get_users()
                    for u in users:
                        if u['id'] == user['id']:
                            u['status'] = 'Standard'
                            if 'premium_expires_at' in u:
                                del u['premium_expires_at']
                    save_users(users)
                
                # Fetch updated user data
                user = find_user_by_id(session['user_id'])
        except Exception as e:
            print(f"Error checking premium expiration: {e}")
    
    # Add premium expiration info if available
    premium_expires = None
    if user.get('status') == 'Premium' and user.get('premium_expires_at'):
        try:
            expires_date = datetime.strptime(user['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            
            days_remaining = (expires_date - now).days
            if days_remaining >= 0:
                premium_expires = {
                    'date': expires_date.strftime('%Y-%m-%d'),
                    'days_remaining': days_remaining
                }
        except Exception as e:
            print(f"Error parsing premium expiration: {e}")
    
    # Process slots information for UI display
    slots_info = []
    available_slots = 0
    if user.get('slots_info'):
        now = datetime.now()
        
        # Get list of assigned users from friends list
        assigned_users = user.get('friends', [])
        assigned_count = len(assigned_users)
        
        for i, slot in enumerate(user['slots_info']):
            # Check if slot is expired
            if slot.get('expires_at'):
                try:
                    expires_at = datetime.strptime(slot['expires_at'], '%Y-%m-%d %H:%M:%S')
                    if now > expires_at:
                        continue  # Skip expired slots
                except Exception as e:
                    print(f"Error parsing slot expiration: {e}")
                    # If there's an error parsing the date, assume it's valid
            
            slot_data = {'id': slot.get('id')}
            
            # Add expiration info if available
            if slot.get('expires_at'):
                try:
                    expires_date = datetime.strptime(slot['expires_at'], '%Y-%m-%d %H:%M:%S')
                    days_remaining = (expires_date - now).days
                    
                    # Only show valid expiration dates (not expired)
                    if days_remaining >= 0:
                        slot_data['expires'] = {
                            'date': expires_date.strftime('%Y-%m-%d'),
                            'days_remaining': days_remaining
                        }
                except Exception as e:
                    print(f"Error parsing slot expiration: {e}")
            else:
                # Explicitly mark as permanent only if not expired
                slot_data['permanent'] = True
            
            # Add source and created_at information
            if slot.get('source'):
                slot_data['source'] = slot.get('source')
            if slot.get('created_at'):
                slot_data['created_at'] = slot.get('created_at')
            
            # Add assigned user if available for this slot
            if i < len(assigned_users):
                username = assigned_users[i]
                slot_data['assigned_to'] = username
                
                # Get the user's status
                assigned_user = find_user_by_username(username)
                if assigned_user:
                    slot_data['assigned_user_status'] = assigned_user.get('status')
                    
                    # Add alignment details
                    alignment_info = {}
                    if 'premium_history' in user:
                        # Find the alignment history for this user
                        alignment_entries = [
                            entry for entry in user['premium_history'] 
                            if entry.get('action') == 'Slot Assigned' and username in entry.get('details', '')
                        ]
                        if alignment_entries:
                            # Get the most recent alignment entry
                            latest_entry = max(alignment_entries, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S'))
                            alignment_info['aligned_at'] = latest_entry['date']
                            alignment_info['aligned_for_days'] = (now - datetime.strptime(latest_entry['date'], '%Y-%m-%d %H:%M:%S')).days
                            
                            # Get previous alignments history
                            if len(alignment_entries) > 1:
                                alignment_info['alignment_count'] = len(alignment_entries)
                                alignment_info['first_aligned_at'] = min(alignment_entries, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S'))['date']
                                
                    slot_data['alignment_info'] = alignment_info
            else:
                # This slot is available
                available_slots += 1
            
            slots_info.append(slot_data)
    
    # Process expired slots for history display
    expired_slots_info = []
    if user.get('expired_slots'):
        for slot in user.get('expired_slots', []):
            expired_slot_data = {
                'id': slot.get('id'),
                'expired_at': slot.get('expired_at'),
                'created_at': slot.get('created_at'),
                'source': slot.get('source', 'Unknown')
            }
            
            # Add assigned user if available
            if 'assigned_to' in slot:
                assigned_to = slot.get('assigned_to')
                if assigned_to is not None:
                    expired_slot_data['assigned_to'] = assigned_to
                    
                    # Get user info if available
                    assigned_user = find_user_by_username(assigned_to)
                    if assigned_user:
                        expired_slot_data['assigned_user_status'] = assigned_user.get('status')
            
            expired_slots_info.append(expired_slot_data)
        
        # Sort expired slots by expiration date (newest first)
        expired_slots_info = sorted(
            expired_slots_info,
            key=lambda x: datetime.strptime(x['expired_at'], '%Y-%m-%d %H:%M:%S') if x.get('expired_at') else datetime.now(),
            reverse=True
        )
    
    # Prepare premium history for display
    premium_history = []
    if user.get('premium_history'):
        # Limit to the most recent 10 entries
        premium_history = sorted(
            user['premium_history'], 
            key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S'), 
            reverse=True
        )[:10]
    
    # Update the slots count based on valid slots
    users = get_users()
    for u in users:
        if u['id'] == user['id']:
            u['slots'] = len(slots_info)
            save_users(users)
            break
    
    return render_template('profile.html', 
                          user=user, 
                          premium_expires=premium_expires, 
                          slots_info=slots_info,
                          premium_history=premium_history,
                          expired_slots_info=expired_slots_info,
                          available_slots=available_slots
                         )

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    user = find_user_by_id(session['user_id'])
    if not user:
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('is_admin', None)
        return redirect(url_for('login'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    
    # Validate input
    if not all([username, email]):
        return render_template('profile.html', user=user, message='All fields are required', message_type='error')
    
    if not is_valid_username(username):
        return render_template('profile.html', user=user, message='Username must be 3-20 characters and contain only letters, numbers, and underscores', message_type='error')
    
    if not is_valid_email(email):
        return render_template('profile.html', user=user, message='Invalid email address', message_type='error')
    
    # Check if username or email already exists (excluding current user)
    existing_username = find_user_by_username(username)
    if existing_username and existing_username['id'] != user['id']:
        return render_template('profile.html', user=user, message='Username already exists', message_type='error')
    
    existing_email = find_user_by_email(email)
    if existing_email and existing_email['id'] != user['id']:
        return render_template('profile.html', user=user, message='Email already exists', message_type='error')
    
    # Update user
    users = get_users()
    for u in users:
        if u['id'] == user['id']:
            is_admin_before = u.get('is_admin', False)  # Save admin status before update
            u['username'] = username
            u['email'] = email
            
            # Make sure admin status doesn't change when updating profile
            u['is_admin'] = is_admin_before
            
            # Update session if username changed
            if username != session['username']:
                session['username'] = username
            
            # If user lost premium, clear slots
            if u.get('status') != 'Premium':
                if 'friends' in u and u['friends']:
                    # Remove aligned premium from all friends
                    for friend_username in u['friends']:
                        for f in users:
                            if f['username'].lower() == friend_username.lower() and f.get('status') == 'Premium (Aligned)':
                                f['status'] = 'Standard'
                    u['friends'] = []
            
            # Save changes
            save_users(users)
            
            # Return updated user
            return render_template('profile.html', user=u, message='Profile updated successfully', message_type='success')
    
    return render_template('profile.html', user=user, message='Error updating profile', message_type='error')

@app.route('/profile/password', methods=['POST'])
@login_required
def update_password():
    """Update user password"""
    user = find_user_by_id(session['user_id'])
    if not user:
        session.pop('user_id', None)
        session.pop('username', None)
        return redirect(url_for('login'))
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Validate input
    if not all([current_password, new_password, confirm_password]):
        return render_template('profile.html', user=user, message='All fields are required', message_type='error')
    
    # Check current password
    if not check_password(user['password'], current_password):
        return render_template('profile.html', user=user, message='Current password is incorrect', message_type='error')
    
    if not is_valid_password(new_password):
        return render_template('profile.html', user=user, message='Password must be at least 8 characters', message_type='error')
    
    if new_password != confirm_password:
        return render_template('profile.html', user=user, message='Passwords do not match', message_type='error')
    
    # Update password
    users = get_users()
    for u in users:
        if u['id'] == user['id']:
            u['password'] = hash_password(new_password)
            
            # Save changes
            save_users(users)
            
            # Return updated user
            return render_template('profile.html', user=u, message='Password updated successfully', message_type='success')
    
    return render_template('profile.html', user=user, message='Error updating password', message_type='error')

@app.route('/profile/regenerate-code', methods=['POST'])
@login_required
def regenerate_launcher_code():
    """Regenerate a user's launcher connection code"""
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Generate a new code
    new_code = generate_launcher_code()
    
    # Update user
    users = get_users()
    for u in users:
        if u['id'] == user['id']:
            u['launcher_code'] = new_code
            u['launcher_connected'] = False
            u['last_connection'] = None
            
            # Mark all active devices as disconnected with the force_disconnect flag
            if 'active_devices' in u:
                for device in u['active_devices']:
                    device['disconnected'] = True
                    device['force_disconnect'] = True
                    device['code_changed'] = True  # New flag to track code changes
            
            # Clear devices array
            if 'devices' in u:
                u['devices'] = []
                
            break
    
    save_users(users)
    
    return jsonify({'success': True, 'new_code': new_code})

@app.route('/profile/redeem-code', methods=['POST'])
@login_required
def redeem_promo_code():
    """Redeem a promo code for the current user"""
    code = request.form.get('promo_code', '').strip()
    
    if not code:
        flash('Please enter a promo code', 'error')
        return redirect(url_for('profile'))
    
    # Find promo code
    promo = find_promo_code(code)
    if not promo:
        flash('Promo code not found or already used', 'error')
        return redirect(url_for('profile'))
    
    # Check if code is expired
    if promo.get('expires_at'):
        try:
            expires_at = datetime.strptime(promo['expires_at'], '%Y-%m-%d')
            if expires_at < datetime.now():
                flash('Promo code has expired', 'error')
                return redirect(url_for('profile'))
        except:
            pass  # Ignore parse errors
    
    # Check if code has reached its usage limit
    if promo.get('uses_limit') > 0 and promo.get('uses_count', 0) >= promo['uses_limit']:
        flash('Promo code has reached its usage limit', 'error')
        return redirect(url_for('profile'))
    
    # Check if user already redeemed this code
    user_id = session['user_id']
    if user_id in promo.get('redeemed_by', []):
        flash('You have already used this promo code', 'error')
        return redirect(url_for('profile'))
    
    # Apply promo code benefits
    users = get_users()
    for user in users:
        if user['id'] == user_id:
            # Record redemption timestamp and details for history
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            redemption_details = {
                'promo_code': code,
                'timestamp': timestamp,
                'gave_premium': promo.get('gives_premium', False),
                'premium_duration': promo.get('premium_duration', 7),
                'gave_slots': promo.get('slots', 0),
                'slots_duration': promo.get('slots_duration', 3)
            }
            
            # Initialize premium history if it doesn't exist
            if 'premium_history' not in user:
                user['premium_history'] = []
                
            # Apply premium status if code gives it
            if promo.get('gives_premium', False):
                user['status'] = 'Premium'
                
                # Set premium source information
                user['premium_source'] = f"Promo Code: {code}"
                
                # Set premium expiration based on duration
                premium_duration = promo.get('premium_duration', 7)  # Default to permanent
                
                # Убедимся, что premium_duration - это число
                if isinstance(premium_duration, str):
                    premium_duration = int(premium_duration)
                
                # Calculate expiration date based on duration value
                if premium_duration < 7:  # Only set expiration if not permanent
                    premium_expiry = None
                    
                    if premium_duration == 1:  # 1 day
                        premium_expiry = datetime.now() + timedelta(days=1)
                    elif premium_duration == 2:  # 7 days
                        premium_expiry = datetime.now() + timedelta(days=7)
                    elif premium_duration == 3:  # 1 month
                        premium_expiry = datetime.now() + timedelta(days=30)
                    elif premium_duration == 4:  # 3 months
                        premium_expiry = datetime.now() + timedelta(days=90)
                    elif premium_duration == 5:  # 6 months
                        premium_expiry = datetime.now() + timedelta(days=180)
                    elif premium_duration == 6:  # 1 year
                        premium_expiry = datetime.now() + timedelta(days=365)
                    
                    if premium_expiry:
                        user['premium_expires_at'] = premium_expiry.strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Add premium activation to history
                        user['premium_history'].append({
                            'date': timestamp,
                            'action': 'Premium Activated',
                            'details': f"Activated via promo code '{code}'. Expires on {premium_expiry.strftime('%Y-%m-%d %H:%M:%S')}"
                        })
                else:
                    # Remove any existing expiration for permanent premium
                    if 'premium_expires_at' in user:
                        del user['premium_expires_at']
                    
                    # Add permanent premium activation to history
                    user['premium_history'].append({
                        'date': timestamp,
                        'action': 'Premium Activated',
                        'details': f"Activated via promo code '{code}'. Never expires."
                    })
                
            # Add slots with duration
            if promo.get('slots', 0) > 0:
                slots_count = promo.get('slots', 0)
                slots_duration_str = promo.get('slots_duration', '3')  # Default to 1 month (3)
                
                try:
                    slots_duration = int(slots_duration_str)
                except (ValueError, TypeError):
                    slots_duration = 3 # fallback to 1 month

                # Calculate expiration date based on duration value
                slots_expiry = None
                if slots_duration == 1:  # 1 day
                    slots_expiry = datetime.now() + timedelta(days=1)
                elif slots_duration == 2:  # 7 days
                    slots_expiry = datetime.now() + timedelta(days=7)
                elif slots_duration == 3:  # 1 month
                    slots_expiry = datetime.now() + timedelta(days=30)
                elif slots_duration == 4:  # 3 months
                    slots_expiry = datetime.now() + timedelta(days=90)
                elif slots_duration == 5:  # 6 months
                    slots_expiry = datetime.now() + timedelta(days=180)
                elif slots_duration == 6:  # 1 year
                    slots_expiry = datetime.now() + timedelta(days=365)
                elif slots_duration == 7:  # permanent
                    slots_expiry = None
                
                # Initialize slots structure if it doesn't exist
                if not user.get('slots_info'):
                    user['slots_info'] = []
                
                # Add the slots activation to history
                if slots_expiry:
                    user['premium_history'].append({
                        'date': timestamp,
                        'action': f"{slots_count} Slots Added",
                        'details': f"Added via promo code '{code}'. Expires on {slots_expiry.strftime('%Y-%m-%d %H:%M:%S')}"
                    })
                else:
                    user['premium_history'].append({
                        'date': timestamp,
                        'action': f"{slots_count} Slots Added",
                        'details': f"Added via promo code '{code}'. Never expires."
                    })
                
                # Add the new slots with expiration
                for _ in range(slots_count):
                    slot_info = {
                        'id': str(uuid.uuid4()),
                        'source': f"Promo code: {code}",
                        'created_at': timestamp,
                        'users_history': [],
                        'assigned_to': None,
                        'last_update': timestamp
                    }
                    
                    if slots_expiry:
                        slot_info['expires_at'] = slots_expiry.strftime('%Y-%m-%d %H:%M:%S')
                    
                    user['slots_info'].append(slot_info)
                
                # Filter out expired slots and create valid_slots list
                valid_slots = []
                now = datetime.now()
                for slot in user['slots_info']:
                    if slot.get('expires_at'):
                        try:
                            expires_at = datetime.strptime(slot['expires_at'], '%Y-%m-%d %H:%M:%S')
                            if now > expires_at:
                                continue  # Skip expired slots
                        except Exception as e:
                            print(f"Error parsing slot expiration: {e}")
                    valid_slots.append(slot)
                
                # Update slots_info
                if len(valid_slots) != len(user['slots_info']):
                    user['slots_info'] = valid_slots
                    
                # Update the slots count instead of removing it
                user['slots'] = len(valid_slots)
            
            break
    
    # Update promo code usage
    promo_codes = get_promo_codes()
    for p in promo_codes:
        if p['id'] == promo['id']:
            # Increment usage counter
            p['uses_count'] = p.get('uses_count', 0) + 1
            
            # Add user to redeemed list
            if 'redeemed_by' not in p:
                p['redeemed_by'] = []
            
            # Get user details to store in promo code
            current_user = find_user_by_id(user_id)
            user_data = {
                'id': user_id,
                'username': current_user.get('username', ''),
                'redeemed_at': timestamp,
                'premium_given': promo.get('gives_premium', False),
                'slots_given': promo.get('slots', 0)
            }
            
            p['redeemed_by'].append(user_data)
            break
    
    # Save changes
    save_users(users)
    save_promo_codes(promo_codes)
    
    flash('Promo code activated successfully!', 'success')
    return redirect(url_for('profile'))

def get_stats(force_update=False):
    try:
        # Fetch online users
        online_response = requests.get('http://api.swa-recloud.fun/api/v3/info/online')
        online_data = online_response.json() if online_response.status_code == 200 else {'total_online': 0}
        
        # Fetch user statistics
        users_response = requests.get('http://api.swa-recloud.fun/api/v3/info/users')
        users_data = users_response.json() if users_response.status_code == 200 else {
            'daily': {'unique_visits': 0},
            'total': {'unique_visits': 0}
        }
        
        return {
            'daily_users': users_data.get('daily', {}).get('unique_visits', 0),
            'total_users': users_data.get('total', {}).get('unique_visits', 0),
            'online_users': online_data.get('total_online', 0)
        }
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return {
            'daily_users': 0,
            'total_users': 0,
            'online_users': 0
        }

def get_games_data(access="free", force_update=False):
    """Fetch and cache game data from external API for both free and premium games"""
    current_time = time.time()
    
    # Check if cache needs to be updated
    if (data_cache["games"][access] is None or 
            current_time - data_cache["last_games_update"][access] > CACHE_LIFETIME["games"] or 
            force_update):
        try:
            # Use a background thread for updating so we don't block the user
            threading.Thread(target=update_games_data, args=(access,), daemon=True).start()
            
            # If first time loading and no cache, use synchronous request with short timeout
            if data_cache["games"][access] is None:
                try:
                    response = requests.get(GAMES_API[access], timeout=3)
                    if response.ok:
                        data_cache["games"][access] = response.json()
                        data_cache["last_games_update"][access] = current_time
                        print(f"[{datetime.now()}] Initialized {access} games data")
                    else:
                        # If API fails, try to load from local backup file
                        data_cache["games"][access] = load_games_from_backup(access)
                except Exception:
                    # If request fails, try to load from backup without waiting
                    data_cache["games"][access] = load_games_from_backup(access)
        except Exception as e:
            print(f"[{datetime.now()}] Error fetching {access} games data: {e}")
            # Try to load from backup file
            data_cache["games"][access] = load_games_from_backup(access)
    
    # Return cached data or empty dict if cache is still empty
    return data_cache["games"][access] or {}

def update_games_data(access):
    """Update games data in background thread"""
    try:
        current_time = time.time()
        
        # Skip external API calls entirely
        print(f"[{datetime.now()}] Using local game data for {access} games")
        
        # Load from backup file
        games_data = load_games_from_backup(access)
        
        # If no backup exists, create one with sample data
        if not games_data:
            if access == "free":
                games_data = create_sample_free_games()
            else:
                games_data = create_sample_premium_games()
            
            # Save to backup file
            save_games_to_backup(access, games_data)
        
        # Update cache
        data_cache["games"][access] = games_data
        data_cache["last_games_update"][access] = current_time
        
        print(f"[{datetime.now()}] Background update completed for {access} games data")
    except Exception as e:
        print(f"[{datetime.now()}] Error in background update for {access} games: {e}")

def save_games_to_backup(access, data):
    """Save games data to a backup file"""
    backup_file = f"games_{access}_backup.json"
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[{datetime.now()}] Error saving games backup: {e}")

def load_games_from_backup(access):
    """Load games data from backup file"""
    backup_file = f"games_{access}_backup.json"
    try:
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[{datetime.now()}] Error loading games backup: {e}")
    
    # If backup loading fails, return empty dict
    return {}

def get_game_added_stats(date_str=None, force_update=False):
    """Get game added stats for a specific date"""
    # Get data for today if date_str is not provided
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # Check if the cache needs to be updated for this date
    if (date_str not in data_cache["daily_data"] or 
            date_str not in data_cache["last_daily_update"] or
            time.time() - data_cache["last_daily_update"].get(date_str, 0) > CACHE_LIFETIME["daily"] or
            force_update):
        try:
            # Get data from the server or use demo data if in demo mode
            daily_data = get_game_data(date_str)
            data_cache["daily_data"][date_str] = daily_data
            data_cache["last_daily_update"][date_str] = time.time()
            print(f"[{datetime.now()}] Data updated for date: {date_str}")
        except Exception as e:
            print(f"[{datetime.now()}] Error getting data for date {date_str}: {e}")
            if date_str not in data_cache["daily_data"]:
                data_cache["daily_data"][date_str] = {}
    
    # Return data from cache or default values
    return data_cache["daily_data"].get(date_str, {})

def get_game_added_stats_period(days=7, force_update=False):
    """Get game added stats for a period of days"""
    days_str = str(days)
    
    # Check if the cache needs to be updated for this period
    if (data_cache["period_data"][days_str] is None or
            time.time() - data_cache["last_period_update"][days_str] > CACHE_LIFETIME["period"] or
            force_update):
        
        # Initialize result structure
        result = {'days': []}
        
        # Load data for each day in the period
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            day_stats = get_game_added_stats(date_str, force_update=(i == 0))  # Force update only today's data
            result['days'].append(day_stats)
    
    # Return cached data or default values
    return data_cache["period_data"][days_str] or {
        "total_games_added": 0,
        "average_games_per_day": 0,
        "peak_hour": "N/A",
        "peak_hour_raw": None,
        "trend": "N/A"
    }

def get_games_data_old():
    """Fetch detailed game data from API"""
    try:
        # Use the actual API endpoint for games
        url = 'https://api.printedwaste.com/gfk/info/all'
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('success'):
            return data.get('data', {})
        return {}
    except Exception as e:
        print(f"Error fetching game data: {e}")
        # Return sample data for demonstration if API fails
        try:
            with open('sample_game_data.json', 'r') as f:
                data = json.load(f)
                return data.get('data', {})
        except Exception as file_error:
            print(f"Error loading sample data: {file_error}")
            return {}

def get_game_data(date=None):
    """Fetch game data from API for specific date or use today's date (for game stats)"""
    try:
        # The current endpoint is returning HTML instead of JSON
        # Let's modify to use local data directly instead of trying external API
        
        print(f"Fetching data for date: {date or 'latest'}")
        
        # Skip API call entirely and use sample data
        return load_sample_data(date)
            
    except Exception as e:
        print(f"Error fetching game data: {e}")
        return load_sample_data(date)

def load_sample_data(date=None):
    """Load sample data as fallback"""
    try:
        # Check if sample data exists, create default if not
        if not os.path.exists('sample_data.json'):
            create_default_sample_data()
        
        with open('sample_data.json', 'r') as f:
            data = json.load(f)
            
            # If a specific date was requested, update the date in the sample data
            if date:
                data["date"] = date
                
            return data
    except Exception as file_error:
        print(f"Error loading sample data: {file_error}")
        # Return minimal fallback data structure if everything fails
        return {
            "date": date or datetime.now().strftime('%Y-%m-%d'),
            "games_added": 0,
            "details": []
        }

def create_default_sample_data():
    """Create a default sample data file if it doesn't exist"""
    sample_data = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "games_added": 25,
        "details": [
            {
                "game_id": "730",
                "user_id": "76561198123456789",
                "timestamp": f"{datetime.now().strftime('%Y-%m-%d')} 08:15:22"
            },
            {
                "game_id": "570",
                "user_id": "76561198987654321",
                "timestamp": f"{datetime.now().strftime('%Y-%m-%d')} 09:23:45"
            }
        ]
    }
    
    with open('sample_data.json', 'w') as f:
        json.dump(sample_data, f, indent=2)

def create_sample_game_data():
    """Create a sample game data file with detailed game info"""
    sample_data = {
        "success": True,
        "data": {
            "10": {
                "id": "10",
                "name": "Counter-Strike",
                "image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/10/capsule_231x87.jpg?t=1729702322",
                "release_date": "1 Nov, 2000",
                "developers": ["Valve"],
                "platforms": {
                    "windows": True,
                    "mac": True,
                    "linux": True
                },
                "categories": [
                    {"id": 1, "description": "Multi-player"},
                    {"id": 49, "description": "PvP"}
                ],
                "genres": [
                    {"id": "1", "description": "Action"}
                ],
                "recommendations": {"total": 155801},
                "metacritic": {"score": 88},
                "publishers": ["Valve"],
                "is_free": False,
                "price_overview": {
                    "currency": "EUR",
                    "final_formatted": "8,19€"
                },
                "last_update": "2025-01-01",
                "added_at": "2025-01-01",
                "access": "free"
            },
            "70": {
                "id": "70",
                "name": "Half-Life",
                "image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/70/capsule_231x87.jpg",
                "release_date": "19 Nov, 1998",
                "developers": ["Valve"],
                "platforms": {
                    "windows": True,
                    "mac": True,
                    "linux": True
                },
                "categories": [
                    {"id": 2, "description": "Single-player"},
                    {"id": 1, "description": "Multi-player"}
                ],
                "genres": [
                    {"id": "1", "description": "Action"}
                ],
                "recommendations": {"total": 125478},
                "metacritic": {"score": 96},
                "publishers": ["Valve"],
                "is_free": False,
                "price_overview": {
                    "currency": "EUR",
                    "final_formatted": "8,19€"
                },
                "last_update": "2025-01-01",
                "added_at": "2025-01-01",
                "access": "free"
            }
        }
    }
    
    with open('sample_game_data.json', 'w') as f:
        json.dump(sample_data, f, indent=2)

def process_game_data(data):
    """Process raw game data for display (for game stats)"""
    # Sort games by timestamp in descending order (newest first)
    games = sorted(data.get('details', []), key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Get the date from the data
    date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%B %d, %Y')
    except:
        formatted_date = "Today"
    
    # Get unique users count
    unique_users = len(set(game.get('user_id', '') for game in games))
    
    # Process each game
    processed_games = []
    for game in games:
        # Format timestamp
        try:
            timestamp_obj = datetime.strptime(game.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
            formatted_timestamp = timestamp_obj.strftime('%H:%M:%S')
        except:
            formatted_timestamp = "Unknown"
        
        # Get shortened user ID (first 8 chars)
        short_user_id = game.get('user_id', 'Unknown')[:8]
        
        processed_games.append({
            'game_id': game.get('game_id', 'Unknown'),
            'timestamp': game.get('timestamp', ''),
            'formatted_timestamp': formatted_timestamp,
            'user_id': game.get('user_id', 'Unknown'),
            'short_user_id': short_user_id
        })
    
    # Get the most recent game ID
    most_recent_game = processed_games[0]['game_id'] if processed_games else "N/A"
    
    return {
        'games': processed_games,
        'formatted_date': formatted_date, 
        'games_added': data.get('games_added', 0),
        'unique_users': unique_users,
        'most_recent_game': most_recent_game,
        'date': date_str  # Add the raw date for the date picker
    }

def analyze_hourly_data(game_data):
    """Analyze game data to find hourly distribution and most active hour"""
    hourly_counts = defaultdict(int)
    
    # Обработка случая, когда game_data равен None или details отсутствует
    if not game_data or 'details' not in game_data:
        return {
            "hourly_distribution": {},
            "most_active_hour": "N/A",
            "most_active_hour_raw": None
        }
    
    for game in game_data.get('details', []):
        try:
            timestamp = datetime.strptime(game.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
            hour = timestamp.hour
            hourly_counts[hour] += 1
        except:
            continue
    
    # Find most active hour
    most_active_hour = None
    max_count = 0
    
    for hour, count in hourly_counts.items():
        if count > max_count:
            max_count = count
            most_active_hour = hour
    
    # Format for display
    if most_active_hour is not None:
        hour_start = most_active_hour
        hour_end = (most_active_hour + 1) % 24
        
        # Convert to 12-hour format with AM/PM
        hour_start_12 = hour_start if hour_start <= 12 else hour_start - 12
        hour_start_12 = 12 if hour_start_12 == 0 else hour_start_12
        
        hour_end_12 = hour_end if hour_end <= 12 else hour_end - 12
        hour_end_12 = 12 if hour_end_12 == 0 else hour_end_12
        
        am_pm_start = "AM" if hour_start < 12 else "PM"
        am_pm_end = "AM" if hour_end < 12 else "PM"
        
        most_active_formatted = f"{hour_start_12} {am_pm_start}-{hour_end_12} {am_pm_end}"
    else:
        most_active_formatted = "N/A"
    
    return {
        "hourly_distribution": dict(hourly_counts),
        "most_active_hour": most_active_formatted,
        "most_active_hour_raw": most_active_hour
    }

def check_expired_premium_and_slots():
    """Check and revoke expired premium status and slots"""
    try:
        users = get_users()
        now = datetime.now()
        updated = False
        
        for user in users:
            user_updated = False
            
            # Check premium expiration
            if user.get('status') == 'Premium' and user.get('premium_expires_at'):
                try:
                    expires_at = datetime.strptime(user['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
                    if now > expires_at:
                        # Update user status and handle all related changes
                        update_user_status_to_standard(user, "Premium subscription expired.")
                        user_updated = True
                        print(f"[{now}] Revoked expired premium status for user {user['username']}")
                except Exception as e:
                    print(f"[{now}] Error processing premium expiration for {user.get('username')}: {e}")
            
            # Rest of the function remains the same...
            if user_updated:
                updated = True
        
        if updated:
            save_users(users)
            print(f"[{now}] Updated users after checking expirations")
    
    except Exception as e:
        print(f"[{now}] Error in check_expired_premium_and_slots: {e}")

def update_cache_periodically():
    """Update cache at regular intervals"""
    last_stats_refresh = 0
    last_games_refresh = 0
    stats_refresh_interval = 300  # 5 minutes
    games_refresh_interval = 3600  # 1 hour
    
    while True:
        try:
            current_time = time.time()
            
            # Check for expired premium status and slots more frequently
            check_expired_premium_and_slots()
            print(f"[{datetime.now()}] Checked for expired premium subscriptions and slots")
            
            # Update stats more frequently (every 5 minutes)
            if current_time - last_stats_refresh >= stats_refresh_interval:
                get_stats(force_update=True)
                last_stats_refresh = current_time
                print(f"[{datetime.now()}] Statistics refreshed from API")
            
            # Update games data every hour
            if current_time - last_games_refresh >= games_refresh_interval:
                fetch_and_process_games(force_update=True)
                last_games_refresh = current_time
                print(f"[{datetime.now()}] Games data refreshed from API")
            
            # Sleep for a shorter time for premium checks (every 5 minutes)
            time.sleep(300)  # 5 minutes
            
            # Update period stats
            get_game_added_stats_period(7, force_update=True)
            get_game_added_stats_period(30, force_update=True)
            
            print(f"[{datetime.now()}] All cache updated in background thread")
        except Exception as e:
            print(f"[{datetime.now()}] Error in background cache update: {e}")
        
        # Sleep for remaining time to complete the hour
        time.sleep(2700)  # 45 minutes (total cycle: 50 minutes with earlier 5-minute sleep)

# Инициализация кеша при запуске
def init_cache():
    print(f"[{datetime.now()}] Инициализация кеша...")
    try:
        # Force update stats first to ensure we have the latest data
        get_stats(force_update=True)
        
        # Initialize game data from external API
        fetch_and_process_games(force_update=True)
        
        # Create a list of tasks for initialization and start them in separate threads
        # for parallel initialization of different data types
        tasks = [
            # Load data for today
            lambda: get_game_added_stats(datetime.now().strftime('%Y-%m-%d'), force_update=True),
            
            # Load weekly data (with lower priority)
            lambda: get_game_added_stats_period(7, force_update=True),
            
            # Load monthly data (with lower priority)
            lambda: get_game_added_stats_period(30, force_update=True)
        ]
        
        # Start all tasks in parallel
        threads = []
        for task in tasks:
            thread = threading.Thread(target=task)
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Don't wait for threads to complete - they will work in the background
        
        print(f"[{datetime.now()}] Инициализация кеша запущена в фоновом режиме")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка запуска инициализации кеша: {e}")

@app.route('/')
def index():
    stats = get_stats()
    
    # Get today's data
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_data = get_game_added_stats(today_str)
    
    # Get weekly data (7 days)
    week_data = get_game_added_stats_period(7)
    
    # Get monthly data (30 days)
    month_data = get_game_added_stats_period(30)
    
    # Analyze hourly data
    hourly_analysis = analyze_hourly_data(today_data)
    
    # Calculate average games per day - Fixed to handle possible string or empty data
    if week_data and isinstance(week_data, list) and len(week_data) > 0:
        try:
            avg_games = round(sum(day.get("games_added", 0) for day in week_data) / len(week_data))
        except (TypeError, ZeroDivisionError):
            avg_games = 0
    else:
        avg_games = 0
    
    game_stats = {
        "today": today_data,
        "week": week_data,
        "month": month_data,
        "total_games_today": today_data.get("games_added", 0),
        "avg_per_day": avg_games,
        "most_active_hour": hourly_analysis["most_active_hour"]
    }
    
    return render_template('index.html', stats=stats, game_stats=game_stats)

@app.route('/premium')
def premium():
    return render_template('premium.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/gamelist')
def gamelist():
    # This route now only renders the template 
    # The actual game data is loaded via JavaScript from the APIs
    return render_template('gamelist.html')

@app.route('/api/game_stats')
def game_stats_api():
    """API endpoint to get processed game data for charts"""
    date_range = request.args.get('range', '1')
    date = request.args.get('date', None)
    
    if date_range == '1':  # Today/1 day
        # Get hourly data for today or specified date
        data = get_game_added_stats(date)
        
        # Process for chart display
        hourly_data = defaultdict(int)
        
        # Ensure data.details exists
        if data and 'details' in data:
            for game in data.get('details', []):
                try:
                    # Extract hour from timestamp
                    timestamp = datetime.strptime(game.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                    hour = timestamp.hour
                    hourly_data[hour] += 1
                except:
                    continue
        
        # Format for chart
        hours = list(range(24))
        labels = [f"{h}:00" for h in hours]
        counts = [hourly_data.get(hour, 0) for hour in hours]
        
        # Find peak hour
        peak_hour = max(hourly_data.items(), key=lambda x: x[1])[0] if hourly_data else 0
        
        return jsonify({
            'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
            'total_games': data.get('games_added', 0),
            'labels': labels,
            'data': counts,
            'peak_hour': peak_hour
        })
    else:
        # Get multiple days of data
        days = 7 if date_range == '7' else 30
        data = get_game_added_stats_period(days)
        
        # Ensure data exists and is not empty
        if not data:
            data = [
                {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'games_added': 0}
                for i in range(days)
            ]
        
        labels = [datetime.strptime(day.get('date', '2000-01-01'), '%Y-%m-%d').strftime('%b %d') for day in data]
        counts = [day.get('games_added', 0) for day in data]
        
        # Calculate the sum of all games in the period
        total_games = sum(day.get('games_added', 0) for day in data)
        
        return jsonify({
            'labels': labels,
            'data': counts,
            'total_games': total_games
        })

# API endpoint to get games data
@app.route('/api/games/<access>')
def api_games(access):
    """API endpoint to get cached games data"""
    if access not in ["free", "premium"]:
        return jsonify({"error": "Invalid access type. Must be 'free' or 'premium'"}), 400
    
    # Try to fetch and process games if needed
    fetch_and_process_games()
    
    # Return cached data based on access type
    if access == "free":
        # For free access, return only free games
        if games_api_cache["free_games"] is None:
            return jsonify({"error": "No free games data available"}), 500
        return jsonify(games_api_cache["free_games"])
    else:
        # For premium access, return both free and premium games
        if games_api_cache["free_games"] is None or games_api_cache["premium_games"] is None:
            return jsonify({"error": "No games data available"}), 500
        
        # Combine free and premium games
        combined_games = {}
        
        # Add free games
        if games_api_cache["free_games"]:
            combined_games.update(games_api_cache["free_games"])
        
        # Add premium games
        if games_api_cache["premium_games"]:
            combined_games.update(games_api_cache["premium_games"])
        
        return jsonify(combined_games)

@app.route('/api/games/refresh')
@admin_required
def refresh_games_cache():
    """Force refresh the games cache (admin only)"""
    success = fetch_and_process_games(force_update=True)
    
    if success:
        return jsonify({
            "success": True, 
            "message": "Games cache refreshed successfully",
            "free_games_count": len(games_api_cache["free_games"]) if games_api_cache["free_games"] else 0,
            "premium_games_count": len(games_api_cache["premium_games"]) if games_api_cache["premium_games"] else 0
        })
    else:
        return jsonify({"success": False, "error": "Failed to refresh games cache"}), 500

# Add 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('index'))

# Start initial cache initialization and periodic updates
def start_background_tasks():
    # Starting cache initialization in a separate thread to avoid blocking server startup
    init_thread = threading.Thread(target=init_cache, daemon=True)
    init_thread.start()
    
    # Starting periodic updates in a separate thread
    cache_thread = threading.Thread(target=update_cache_periodically, daemon=True)
    cache_thread.start()
    print(f"[{datetime.now()}] Background cache update processes started")

# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard page"""
    # Get basic statistics
    users = get_users()
    free_games = get_games_data("free")
    premium_games = get_games_data("premium")
    
    # Get recent activities (could be stored in a separate file in a real application)
    activities = [
        {
            "icon": "fas fa-user-plus",
            "text": "New user registered: user123",
            "time": "Today, 10:45 AM"
        },
        {
            "icon": "fas fa-gamepad",
            "text": "New game added: Counter-Strike 2",
            "time": "Yesterday, 3:22 PM"
        },
        {
            "icon": "fas fa-crown",
            "text": "User upgraded to Premium: admin",
            "time": "Apr 28, 2025, 9:15 AM"
        }
    ]
    
    # Calculate online users
    online_users = sum(1 for user in users if user.get("launcher_connected", False))
    
    # Calculate premium users
    premium_users = sum(1 for user in users if user.get("status") == "Premium" or user.get("status") == "Premium (Aligned)")
    
    # Count game sessions
    total_game_sessions = sum(len(user.get("game_sessions", [])) for user in users)
    
    # Count new users in the last 24 hours
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    new_users = sum(1 for user in users if datetime.strptime(user.get("join_date", "2000-01-01"), '%Y-%m-%d') >= yesterday)
    
    # Count daily active users (users with a game session in the last 24 hours)
    daily_users = 0
    for user in users:
        has_recent_session = False
        for session in user.get("game_sessions", []):
            try:
                session_time = datetime.strptime(session.get("timestamp", "2000-01-01 00:00:00"), '%Y-%m-%d %H:%M:%S')
                if session_time >= yesterday:
                    has_recent_session = True
                    break
            except:
                continue
        if has_recent_session:
            daily_users += 1
    
    # Prepare stats for the dashboard
    stats = {
        "total_users": len(users),
        "games_count": len(free_games) + len(premium_games),
        "premium_users": premium_users,
        "online_users": online_users,
        "daily_users": daily_users,
        "game_sessions": total_game_sessions,
        "new_users": new_users,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    return render_template('admin/dashboard.html', stats=stats, activities=activities)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin user management page"""
    users = get_users()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/create', methods=['POST'])
@admin_required
def admin_create_user():
    """Create a new user (admin function)"""
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    status = request.form.get('status', 'Standard')
    is_admin = status == 'Admin'
    
    # Validate input
    if not all([username, email, password]):
        return render_template('admin/users.html', users=get_users(), 
                               message='All fields are required', message_type='error')
    
    if not is_valid_username(username):
        return render_template('admin/users.html', users=get_users(), 
                               message='Username must be 3-20 characters and contain only letters, numbers, and underscores', 
                               message_type='error')
    
    if not is_valid_email(email):
        return render_template('admin/users.html', users=get_users(), 
                               message='Invalid email address', message_type='error')
    
    if not is_valid_password(password):
        return render_template('admin/users.html', users=get_users(), 
                               message='Password must be at least 8 characters', message_type='error')
    
    # Check if username or email already exists
    if find_user_by_username(username):
        return render_template('admin/users.html', users=get_users(), 
                               message='Username already exists', message_type='error')
    
    if find_user_by_email(email):
        return render_template('admin/users.html', users=get_users(), 
                               message='Email already exists', message_type='error')
    
    # Generate user ID
    user_id = str(uuid.uuid4())
    
    # Create new user
    new_user = {
        'id': user_id,
        'username': username,
        'email': email,
        'password': hash_password(password),
        'join_date': datetime.now().strftime('%Y-%m-%d'),
        'status': status,
        'games_count': 0,
        'is_admin': is_admin,
        'launcher_connected': False,
        'last_connection': None,
        'unique_id': generate_unique_id(user_id),
        'total_play_time': '0h 0m',
        'games_played': 0,
        'achievements': 0,
        'last_session': None,
        'game_sessions': [],
        'slots': 0,
        'friends': []
    }
    
    # Add launcher code only for Premium or Admin users
    if status == 'Premium' or status == 'Admin':
        new_user['launcher_code'] = generate_launcher_code()
    
    users = get_users()
    users.append(new_user)
    save_users(users)
    
    return render_template('admin/users.html', users=get_users(), 
                           message='User created successfully', message_type='success')

@app.route('/admin/users/update', methods=['POST'])
@admin_required
def admin_update_user():
    """Update a user (admin function)"""
    user_id = request.form.get('user_id')
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    status = request.form.get('status', 'Standard')
    is_admin = 'is_admin' in request.form
    
    # Validate input
    if not all([user_id, username, email]):
        return render_template('admin/users.html', users=get_users(), 
                               message='Required fields missing', message_type='error')
    
    if not is_valid_username(username):
        return render_template('admin/users.html', users=get_users(), 
                               message='Username must be 3-20 characters and contain only letters, numbers, and underscores', 
                               message_type='error')
    
    if not is_valid_email(email):
        return render_template('admin/users.html', users=get_users(), 
                               message='Invalid email address', message_type='error')
    
    # Find user to update
    users = get_users()
    user_to_update = None
    for user in users:
        if user['id'] == user_id:
            user_to_update = user
            break
    
    if not user_to_update:
        return render_template('admin/users.html', users=get_users(), 
                               message='User not found', message_type='error')
    
    # Check if username or email already exists (excluding current user)
    for user in users:
        if user['id'] != user_id:
            if user['username'].lower() == username.lower():
                return render_template('admin/users.html', users=get_users(), 
                                      message='Username already exists', message_type='error')
            if user['email'].lower() == email.lower():
                return render_template('admin/users.html', users=get_users(), 
                                      message='Email already exists', message_type='error')
    
    # Check if status is changing from Premium/Admin to Standard
    if user_to_update.get('status') in ['Premium', 'Admin', 'Premium (Aligned)'] and status == 'Standard':
        update_user_status_to_standard(user_to_update, "Status changed by admin.")
    
    # Check if status is changing to Premium or Admin
    if user_to_update.get('status') == 'Standard' and (status == 'Premium' or status == 'Admin'):
        # Generate new launcher code
        user_to_update['launcher_code'] = generate_launcher_code()
    
    # Update user
    user_to_update['username'] = username
    user_to_update['email'] = email
    user_to_update['status'] = status
    user_to_update['is_admin'] = is_admin
    
    # Update password if provided
    if password:
        user_to_update['password'] = hash_password(password)
    
    save_users(users)
    
    return render_template('admin/users.html', users=get_users(), 
                           message='User updated successfully', message_type='success')

@app.route('/admin/users/delete', methods=['POST'])
@admin_required
def admin_delete_user():
    """Delete a user (admin function)"""
    user_id = request.form.get('user_id')
    
    if not user_id:
        return render_template('admin/users.html', users=get_users(), 
                               message='User ID is required', message_type='error')
    
    # Find user to delete
    user_to_delete = find_user_by_id(user_id)
    if not user_to_delete:
        return render_template('admin/users.html', users=get_users(), 
                               message='User not found', message_type='error')
    
    # Cannot delete an admin user
    if is_admin(user_to_delete):
        return render_template('admin/users.html', users=get_users(), 
                               message='Cannot delete an admin user', message_type='error')
    
    # Delete user
    users = get_users()
    users = [user for user in users if user['id'] != user_id]
    save_users(users)
    
    return render_template('admin/users.html', users=get_users(), 
                           message='User deleted successfully', message_type='success')

@app.route('/admin/games')
@admin_required
def admin_games():
    """Admin games management page"""
    free_games = get_games_data("free")
    premium_games = get_games_data("premium")
    
    # Transform games data into a consistent format for the template
    games = []
    
    for game_id, game_data in free_games.items():
        games.append({
            'id': game_id,
            'name': game_data.get('name', 'Unknown'),
            'image': game_data.get('image', ''),
            'release_date': game_data.get('release_date', 'Unknown'),
            'access': 'free'
        })
    
    for game_id, game_data in premium_games.items():
        games.append({
            'id': game_id,
            'name': game_data.get('name', 'Unknown'),
            'image': game_data.get('image', ''),
            'release_date': game_data.get('release_date', 'Unknown'),
            'access': 'premium'
        })
    
    # Sort games by name
    games.sort(key=lambda x: x['name'])
    
    return render_template('admin/games.html', games=games)

@app.route('/admin/promo-codes')
@admin_required
def admin_promo_codes():
    """Admin promo codes management page"""
    promo_codes = get_promo_codes()
    for p in promo_codes:
        p['uses_count'] = len(p.get('redeemed_by', []))
        if p.get('expires_at'):
            try:
                p['expires_at'] = datetime.strptime(p['expires_at'], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                 try:
                     p['expires_at'] = datetime.strptime(p['expires_at'], '%Y-%m-%d')
                 except (ValueError, TypeError):
                     p['expires_at'] = None

    # Sort by group for Jinja's groupby filter
    promo_codes.sort(key=lambda p: p.get('group', 'default') or 'default')
    return render_template('admin/promo_codes.html', promo_codes=promo_codes)

@app.route('/admin/promo-codes/group/delete', methods=['POST'])
@admin_required
def admin_delete_promo_group():
    """Delete used promo codes in a specific group."""
    group_name = request.form.get('group_name')
    delete_type = request.form.get('delete_type', 'used_only')  # 'all' or 'used_only'
    
    if not group_name:
        flash('Group name is required.', 'error')
        return redirect(url_for('admin_promo_codes'))

    promo_codes = get_promo_codes()
    
    if delete_type == 'all':
        # Старая логика - удаление всей группы
        codes_to_keep = [p for p in promo_codes if p.get('group') != group_name]
        deleted_count = len(promo_codes) - len(codes_to_keep)
        
        if deleted_count == 0:
            flash(f'Group "{group_name}" not found.', 'warning')
        else:
            save_promo_codes(codes_to_keep)
            flash(f'Successfully deleted all {deleted_count} promo codes in group "{group_name}".', 'success')
    else:
        # Новая логика - удаление только использованных промокодов
        original_count = len(promo_codes)
        codes_to_keep = []
        
        for promo in promo_codes:
            # Если промокод не из этой группы или не использован полностью, сохраняем его
            if promo.get('group') != group_name or not (promo.get('uses_limit', 0) > 0 and promo.get('uses_count', 0) >= promo.get('uses_limit', 0)):
                codes_to_keep.append(promo)
        
        deleted_count = original_count - len(codes_to_keep)
        
        if deleted_count == 0:
            flash(f'No used promo codes found in group "{group_name}".', 'warning')
        else:
            save_promo_codes(codes_to_keep)
            flash(f'Successfully deleted {deleted_count} used promo codes in group "{group_name}".', 'success')

    return redirect(url_for('admin_promo_codes'))

@app.route('/admin/promo-codes/create', methods=['POST'])
@admin_required
def admin_create_promo_code():
    try:
        description = request.form.get('description', '')
        uses_limit = int(request.form.get('uses_limit', 1))
        expires_at_date = request.form.get('expires_at')
        expires_at_time = request.form.get('expires_time', '23:59')
        gives_premium = 'gives_premium' in request.form
        premium_duration = request.form.get('premium_duration', '7')
        slots = int(request.form.get('slots', 0))
        slots_duration = request.form.get('slots_duration', '3')
        
        expires_at = None
        if expires_at_date:
            try:
                # Объединяем дату и время
                expires_at_str = f"{expires_at_date} {expires_at_time}:00"
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                flash(f'Invalid expiration date or time format', 'error')
                return redirect(url_for('admin_promo_codes'))
        
        # Get group information
        group = request.form.get('group', 'default')
        if group == 'custom':
            group = request.form.get('custom_group', 'default')
        
        # Generate a unique promo code
        all_promo_codes = get_promo_codes()
        existing_codes = {p['code'] for p in all_promo_codes}
        
        # Try to generate a unique code, up to 10 attempts
        for _ in range(10):
            new_code = generate_promo_code()
            if new_code not in existing_codes:
                break
        else:
            # If we can't generate a unique code after 10 attempts, return an error
            flash('Failed to generate a unique promo code', 'error')
            return redirect(url_for('admin_promo_codes'))
        
        # Get the creator username
        current_user = find_user_by_id(session.get('user_id', ''))
        creator_username = current_user['username'] if current_user else "System"
        
        # Create the new promo code object
        new_promo = {
            'id': str(uuid.uuid4()),
            'code': new_code,
            'description': description,
            'uses_limit': uses_limit,
            'expires_at': expires_at,
            'gives_premium': gives_premium,
            'premium_duration': premium_duration,
            'slots': slots,
            'slots_duration': slots_duration,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': creator_username,
            'redeemed_by': [],
            'group': group  # Add the group field
        }
        
        # Add the new promo code to the list and save
        all_promo_codes.append(new_promo)
        save_promo_codes(all_promo_codes)
        
        flash(f'Promo code {new_code} created successfully', 'success')
        return redirect(url_for('admin_promo_codes'))
    except Exception as e:
        flash(f'Error creating promo code: {str(e)}', 'error')
        return redirect(url_for('admin_promo_codes'))

@app.route('/admin/promo-codes/delete', methods=['POST'])
@admin_required
def admin_delete_promo_code():
    """Delete a promo code (admin function)"""
    promo_id = request.form.get('promo_id')
    
    if not promo_id:
        flash('Promo code ID is required', 'error')
        return redirect(url_for('admin_promo_codes'))
    
    # Delete promo code
    promo_codes = get_promo_codes()
    promo_codes = [promo for promo in promo_codes if promo.get('id') != promo_id]
    save_promo_codes(promo_codes)
    
    flash('Promo code deleted successfully', 'success')
    return redirect(url_for('admin_promo_codes'))

@app.route('/admin/promo-codes/bulk-create', methods=['POST'])
@admin_required
def admin_bulk_create_promo_code():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request'})

    try:
        count = int(data.get('count', 1))
        description = data.get('description', '')
        uses_limit = int(data.get('uses_limit', 1))
        expires_at_date = data.get('expires_at')
        expires_at_time = data.get('expires_time', '23:59')
        gives_premium = data.get('gives_premium', False)
        premium_duration = data.get('premium_duration', '7')
        slots = int(data.get('slots', 0))
        slots_duration = data.get('slots_duration', '3')
        
        expires_at = None
        if expires_at_date:
            try:
                # Объединяем дату и время
                expires_at_str = f"{expires_at_date} {expires_at_time}:00"
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({'success': False, 'error': f'Invalid expiration date or time format'})

        # Get group information
        group = data.get('group', 'default')
        if group == 'custom':
            group = data.get('custom_group', 'default')
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid data types provided.'})

    if not (1 <= count <= 100):
        return jsonify({'success': False, 'error': 'Count must be between 1 and 100.'})

    all_promo_codes = get_promo_codes()
    existing_codes_set = {p['code'] for p in all_promo_codes}
    
    current_user = find_user_by_id(session.get('user_id', ''))
    creator_username = current_user['username'] if current_user else "System"
    
    newly_created_codes = []

    for _ in range(count):
        new_code_str = generate_promo_code()
        while new_code_str in existing_codes_set:
            new_code_str = generate_promo_code()
        existing_codes_set.add(new_code_str)

        new_promo = {
            'id': str(uuid.uuid4()),
            'code': new_code_str,
            'description': description,
            'uses_limit': uses_limit,
            'expires_at': expires_at,
            'gives_premium': gives_premium,
            'premium_duration': premium_duration,
            'slots': slots,
            'slots_duration': slots_duration,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': creator_username,
            'redeemed_by': [],
            'group': group  # Add the group field
        }
        all_promo_codes.append(new_promo)
        newly_created_codes.append(new_code_str)

    save_promo_codes(all_promo_codes)

    return jsonify({'success': True, 'codes': newly_created_codes})

@app.route('/admin/stats')
@admin_required
def admin_stats():
    """Admin statistics page"""
    # Get statistics data
    stats = get_stats()
    
    # Get weekly data
    week_data = get_game_added_stats_period(7)
    
    # Get monthly data
    month_data = get_game_added_stats_period(30)
    
    return render_template('admin/stats.html', stats=stats, week_data=week_data, month_data=month_data)

@app.context_processor
def inject_now():
    """Add current datetime to all templates"""
    return {'now': datetime.now()}

# Add is_admin to all templates
@app.context_processor
def inject_is_admin():
    """Add is_admin flag to all templates"""
    user_id = session.get('user_id')
    print(f"[DEBUG] context_processor: user_id={user_id}")
    
    if user_id:
        user = find_user_by_id(user_id)
        is_admin_value = is_admin(user) if user else False
        print(f"[DEBUG] context_processor: user={user.get('username') if user else None}, is_admin={is_admin_value}")
        return {'is_admin': is_admin_value}
    
    print(f"[DEBUG] context_processor: no user_id, is_admin=False")
    return {'is_admin': False}

# API endpoints for launcher integration
@app.route('/api/launcher/connect', methods=['POST'])
def launcher_connect():
    """Connect a launcher to a user account via connection code"""
    data = request.get_json()
    
    if not data or 'code' not in data:
        return jsonify({'success': False, 'error': 'Invalid request', 'should_disconnect': True})
    
    code = data['code']
    user = find_user_by_launcher_code(code)
    
    if not user:
        return jsonify({'success': False, 'error': 'Invalid connection code', 'should_disconnect': True})
    
    # Check if user has valid premium status
    if user.get('status') not in ['Premium', 'Admin', 'Premium (Aligned)']:
        return jsonify({
            'success': False, 
            'error': 'Premium subscription required',
            'should_disconnect': True,
            'reason': 'no_premium'
        })
    
    # Get device information from request
    device_id = data.get('device_id', f"DEV-{str(uuid.uuid4())[:8]}")
    device_name = data.get('device_name', 'Unknown Device')
    device_os = data.get('device_os', 'Unknown OS')
    
    # Check if this is the primary device or if no primary device is set yet
    users = get_users()
    for u in users:
        if u['id'] == user['id']:
            # If no primary device is set, set this device as primary
            if 'primary_device' not in u:
                u['primary_device'] = {
                    'device_id': device_id,
                    'device_name': device_name,
                    'device_os': device_os,
                    'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                # Check if the connecting device is the primary device
                if u['primary_device']['device_id'] != device_id:
                    return jsonify({
                        'success': False,
                        'error': 'This account can only be accessed from the primary device',
                        'should_disconnect': True,
                        'reason': 'not_primary_device'
                    })
            
            u['launcher_connected'] = True
            u['last_connection'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            u['last_connected_device'] = device_id
            
            # Initialize device arrays if they don't exist
            if 'active_devices' not in u:
                u['active_devices'] = []
            if 'devices' not in u:
                u['devices'] = []
            
            # Update or add device to active_devices
            device_exists = False
            for device in u.get('active_devices', []):
                if device['device_id'] == device_id:
                    device_exists = True
                    device['last_connection'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    device['device_name'] = device_name
                    device['device_os'] = device_os
                    device['disconnected'] = False
                    if 'force_disconnect' in device:
                        del device['force_disconnect']
                    if 'disconnect_reason' in device:
                        del device['disconnect_reason']
                    break
            
            if not device_exists:
                u['active_devices'].append({
                    'device_id': device_id,
                    'device_name': device_name,
                    'device_os': device_os,
                    'first_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'last_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'disconnected': False
                })
            
            # Update or add device to devices list
            device_exists = False
            for device in u.get('devices', []):
                if device['device_id'] == device_id:
                    device_exists = True
                    device['last_connection'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    device['device_name'] = device_name
                    device['device_os'] = device_os
                    break
            
            if not device_exists:
                u['devices'].append({
                    'device_id': device_id,
                    'device_name': device_name,
                    'device_os': device_os,
                    'first_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'last_connection': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            break
    
    save_users(users)
    
    # Determine the status_expires value
    status_expires = "0"  # Default for unlimited premium
    premium_expires_in_days = None
    if user.get('premium_expires_at'):
        status_expires = user['premium_expires_at']
        try:
            expires_at = datetime.strptime(user['premium_expires_at'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            days_left = (expires_at - now).days
            if days_left >= 0:
                premium_expires_in_days = days_left
        except Exception:
            premium_expires_in_days = None

    # Return user information to launcher with status_expires and days left
    return jsonify({
        'success': True,
        'should_disconnect': False,
        'user_id': user['id'],
        'username': user['username'],
        'unique_id': user.get('unique_id') or generate_unique_id(user['id']),
        'status': user['status'],
        'status_expires': status_expires,
        'premium_expires_in_days': premium_expires_in_days
    })

@app.route('/api/slots/add', methods=['POST'])
@login_required
def api_slots_add():
    """Add a friend to a slot by username"""
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        username = data.get('username', '').strip()
    else:
        username = request.form.get('username', '').strip()
        
    if not username:
        return jsonify({'success': False, 'error': 'Username required'})
    
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Calculate available slots from slots_info
    available_slots = 0
    if 'slots_info' in user:
        now = datetime.now()
        assigned_users = user.get('friends', [])
        for i, slot in enumerate(user['slots_info']):
            # Skip already assigned slots
            if i < len(assigned_users):
                continue
                
            # Check if slot is expired
            if slot.get('expires_at'):
                try:
                    expires_at = datetime.strptime(slot['expires_at'], '%Y-%m-%d %H:%M:%S')
                    if now > expires_at:
                        continue  # Skip expired slots
                except Exception:
                    pass  # If date parsing fails, count the slot
            
            # This is a valid available slot
            available_slots += 1
    
    # Check if the current user has available slots
    if available_slots <= 0:
        return jsonify({'success': False, 'error': 'No available slots'})
    
    # Check that user has Premium status specifically (not just slots)
    if user.get('status') != 'Premium':
        return jsonify({'success': False, 'error': 'Only users with active Premium subscription can assign slots. Your slots are reserved until you upgrade to Premium.'})
    
    # Double-check that premium is valid
    if not has_valid_premium(user):
        return jsonify({'success': False, 'error': 'Your Premium subscription has expired or is invalid'})
    
    if username.lower() == user['username'].lower():
        return jsonify({'success': False, 'error': 'Cannot align yourself'})
    
    # Check if already aligned
    if username.lower() in [f.lower() for f in user.get('friends', [])]:
        return jsonify({'success': False, 'error': 'User already aligned'})
    
    # Find friend user
    friend_user = find_user_by_username(username)
    if not friend_user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Add friend
    users = get_users()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for u in users:
        if u['id'] == user['id']:
            if 'friends' not in u:
                u['friends'] = []
            
            # Find first available slot
            available_slot_index = -1
            if 'slots_info' in u:
                now = datetime.now()
                for i, slot in enumerate(u['slots_info']):
                    # Skip already assigned slots
                    if i < len(u['friends']):
                        continue
        
                    # Check if slot is expired
                    if slot.get('expires_at'):
                        try:
                            expires_at = datetime.strptime(slot['expires_at'], '%Y-%m-%d %H:%M:%S')
                            if now > expires_at:
                                continue  # Skip expired slots
                        except Exception:
                            pass  # If date parsing fails, consider it valid
                    
                    # Found an available slot
                    available_slot_index = i
                    break
            
            if available_slot_index < 0:
                return jsonify({'success': False, 'error': 'No available slots'})
            
            # Add user to friends list
            u['friends'].append(friend_user['username'])
            
            # Update slot info with assignment details
            if 'slots_info' in u and available_slot_index < len(u['slots_info']):
                # Update slot with user assignment information
                u['slots_info'][available_slot_index]['assigned_to'] = friend_user['username']
                u['slots_info'][available_slot_index]['last_update'] = timestamp
                
                # Add to users_history
                if 'users_history' not in u['slots_info'][available_slot_index]:
                    u['slots_info'][available_slot_index]['users_history'] = []
                
                u['slots_info'][available_slot_index]['users_history'].append({
                    'username': friend_user['username'],
                    'assigned_at': timestamp,
                    'status': 'active'
                })
            
            # Add to history
            if 'premium_history' not in u:
                u['premium_history'] = []
            
            u['premium_history'].append({
                'date': timestamp,
                'action': 'Slot Assigned',
                'details': f"Assigned slot to user '{username}'"
            })
            
        if u['id'] == friend_user['id']:
            # Mark as aligned premium
            if u.get('status') != 'Premium':
                u['status'] = 'Premium (Aligned)'
                u['aligned_by'] = user['username']
                
                # Add to their history
                if 'premium_history' not in u:
                    u['premium_history'] = []
                
                u['premium_history'].append({
                    'date': timestamp,
                    'action': 'Premium Status Granted',
                    'details': f"Granted Premium via slot alignment from {user['username']}"
                })
    
    save_users(users)
    return jsonify({'success': True})

@app.route('/api/launcher/update-session', methods=['POST'])
def launcher_update_session():
    """Update user's game session data from launcher"""
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'game_id' not in data or 'playtime' not in data:
        return jsonify({'success': False, 'error': 'Invalid request'})
    
    user_id = data['user_id']
    game_id = data['game_id']
    playtime = int(data['playtime'])  # playtime in minutes
    device_id = data.get('device_id', None)  # Optional device ID
    
    
    if not find_user_by_id(user_id):
        return jsonify({'success': False, 'error': 'User not found'})
    
    success = update_user_stats(user_id, game_id, playtime)
    
    # Update device's last connection time if device_id is provided
    if device_id:
        users = get_users()
        for user in users:
            if user['id'] == user_id and 'devices' in user:
                for device in user['devices']:
                    if device['device_id'] == device_id:
                        device['last_connection'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_users(users)
    
    return jsonify({'success': success})

@app.route('/check-expired', methods=['GET'])
def check_expired_endpoint():
    """Temporary endpoint to check for expired premium subscriptions"""
    try:
        check_expired_premium_and_slots()
        return jsonify({'success': True, 'message': 'Checked for expired premium subscriptions'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/slots/align-user', methods=['POST'])
@login_required
def api_slots_align_user():
    """Alias for api_slots_add - compatibility with frontend forms"""
    # If it's a form submission, extract username from form data
    if request.form:
        username = request.form.get('username', '').strip()
        
        # Create a mock JSON request for api_slots_add
        original_get_json = request.get_json
        request.get_json = lambda: {'username': username}
        
        # Call api_slots_add to process the request
        result = api_slots_add()
        
        # Restore original method
        request.get_json = original_get_json
        
        # Always redirect back to profile after form submission
        # This way we don't try to parse the response as JSON
        return redirect(url_for('profile'))
    
    # For API clients, pass through to api_slots_add
    return api_slots_add()

@app.route('/api/slots/remove-user', methods=['POST'])
@login_required
def api_slots_remove_user():
    """Remove a user from a slot"""
    # Get username from JSON or form data
    if request.is_json:
        data = request.get_json()
        username = data.get('username', '').strip()
    else:
        username = request.form.get('username', '').strip()
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'})
    
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Check if username is in user's friends list
    if username not in user.get('friends', []):
        return jsonify({'success': False, 'error': f'User {username} is not aligned to any of your slots'})
    
    # Update user's friends list and slots_info
    users = get_users()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    updated = False
    
    for u in users:
        if u['id'] == user['id']:
            if 'friends' in u:
                # Find the index of the username in the friends list
                try:
                    friend_index = u['friends'].index(username)
                    
                    # Check if this slot has a last_removal_time and if it's been less than 7 days
                    if 'slots_info' in u and friend_index < len(u['slots_info']):
                        slot_info = u['slots_info'][friend_index]
                        
                        # Check if there's a last removal time for this slot
                        if 'last_removal_time' in slot_info:
                            try:
                                last_removal = datetime.strptime(slot_info['last_removal_time'], '%Y-%m-%d %H:%M:%S')
                                now = datetime.now()
                                # Calculate if it's been less than 7 days
                                if (now - last_removal).days < 7:
                                    days_since_removal = (now - last_removal).days
                                    days_until_available = 7 - days_since_removal
                                    return jsonify({
                                        'success': False,
                                        'error': f'Each slot can only be reassigned once per week. Please wait {days_until_available} more day(s) before removing a user from this slot.'
                                    })
                            except (ValueError, KeyError):
                                # If there's an error parsing the date, continue with removal
                                pass
                    
                    # Remove from friends list
                    u['friends'].remove(username)
                    updated = True
                    
                    # Update slot history in slots_info
                    if 'slots_info' in u and friend_index < len(u['slots_info']):
                        slot_info = u['slots_info'][friend_index]
                        
                        # Update slot history
                        if 'users_history' in slot_info:
                            for history_entry in slot_info['users_history']:
                                if history_entry['username'] == username and history_entry['status'] == 'active':
                                    history_entry['status'] = 'removed'
                                    history_entry['removed_at'] = timestamp
                        
                        # Add the removal timestamp to track the 7-day cooldown
                        slot_info['last_removal_time'] = timestamp
                        
                        # Clear assigned_to
                        if 'assigned_to' in slot_info:
                            slot_info['assigned_to'] = None
                    
                    # Add to premium history
                    if 'premium_history' not in u:
                        u['premium_history'] = []
                    
                    u['premium_history'].append({
                        'date': timestamp,
                        'action': 'Slot Freed',
                        'details': f"Removed user '{username}' from slot"
                    })
                except ValueError:
                    # Username not found in friends list
                    return jsonify({'success': False, 'error': f'User {username} is not aligned to any of your slots'})
        
        # Update the removed user's status
        if u['username'] == username and u.get('status') == 'Premium (Aligned)' and u.get('aligned_by') == user['username']:
            # Reset to Standard
            u['status'] = 'Standard'
            if 'aligned_by' in u:
                del u['aligned_by']
            
            # Add to premium history
            if 'premium_history' not in u:
                u['premium_history'] = []
            
            u['premium_history'].append({
                'date': timestamp,
                'action': 'Premium Status Revoked',
                'details': f"Revoked Premium because slot alignment from {user['username']} was removed"
            })
            
            updated = True
    
    if updated:
        save_users(users)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to remove user from slot'})

@app.route('/api/slots/disalign-self', methods=['POST'])
@login_required
def api_slots_disalign_self():
    """Remove yourself from another user's slot alignment"""
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Check if the user is aligned by someone
    aligned_by = user.get('aligned_by')
    if not aligned_by or user.get('status') != 'Premium (Aligned)':
        return jsonify({'success': False, 'error': 'You are not aligned by any user'})
    
    # Find the aligning user
    aligning_user = find_user_by_username(aligned_by)
    if not aligning_user:
        # If aligning user is not found, just update the current user
        users = get_users()
        for u in users:
            if u['id'] == user['id']:
                u['status'] = 'Standard'
                if 'aligned_by' in u:
                    del u['aligned_by']
                
                # Add to premium history
                if 'premium_history' not in u:
                    u['premium_history'] = []
                
                u['premium_history'].append({
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'action': 'Premium Status Revoked',
                    'details': f"You disaligned yourself from {aligned_by}'s slot"
                })
        
        save_users(users)
        return jsonify({'success': True})
    
    # Update both users
    users = get_users()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    updated = False
    
    for u in users:
        # Update current user
        if u['id'] == user['id']:
            u['status'] = 'Standard'
            if 'aligned_by' in u:
                del u['aligned_by']
            
            # Add to premium history
            if 'premium_history' not in u:
                u['premium_history'] = []
            
            u['premium_history'].append({
                'date': timestamp,
                'action': 'Premium Status Revoked',
                'details': f"You disaligned yourself from {aligned_by}'s slot"
            })
            
            updated = True
        
        # Update aligning user
        if u['id'] == aligning_user['id'] and 'friends' in u:
            if user['username'] in u['friends']:
                # Find the slot index
                slot_index = u['friends'].index(user['username'])
                
                # Remove from friends list
                u['friends'].remove(user['username'])
                
                # Update slot info
                if 'slots_info' in u and slot_index < len(u['slots_info']):
                    slot_info = u['slots_info'][slot_index]
                    
                    # Update history
                    if 'users_history' in slot_info:
                        for history_entry in slot_info['users_history']:
                            if history_entry['username'] == user['username'] and history_entry['status'] == 'active':
                                history_entry['status'] = 'self_removed'
                                history_entry['removed_at'] = timestamp
                    
                    # Clear assigned_to
                    if 'assigned_to' in slot_info:
                        slot_info['assigned_to'] = None
                
                # Add to premium history
                if 'premium_history' not in u:
                    u['premium_history'] = []
                
                u['premium_history'].append({
                    'date': timestamp,
                    'action': 'Slot Freed',
                    'details': f"User '{user['username']}' disaligned themselves from your slot"
                })
                
                updated = True
    
    if updated:
        save_users(users)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to disalign from slot'})

@app.route('/api/devices/list')
@login_required
def api_devices_list():
    """Get list of connected devices for current user"""
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Check if user has premium status
    if user.get('status') not in ['Premium', 'Admin', 'Premium (Aligned)']:
        return jsonify({'success': False, 'error': 'Premium subscription required'})
    
    # Get devices from user data
    devices = user.get('devices', [])
    
    # Sort devices by last connection time (most recent first)
    devices.sort(key=lambda x: x.get('last_connection', ''), reverse=True)
    
    # Add 'is_primary' flag to devices
    primary_device_id = None
    if 'primary_device' in user:
        primary_device_id = user['primary_device'].get('device_id')
        
        # Check if primary device is in the devices list, if not add it
        primary_device_exists = any(d['device_id'] == primary_device_id for d in devices)
        if not primary_device_exists:
            # Add primary device to the list if it's not there
            primary_device = user['primary_device'].copy()
            # If last_connection is not set, use registered_at
            if 'last_connection' not in primary_device and 'registered_at' in primary_device:
                primary_device['last_connection'] = primary_device['registered_at']
            # If first_connection is not set, use registered_at
            if 'first_connection' not in primary_device and 'registered_at' in primary_device:
                primary_device['first_connection'] = primary_device['registered_at']
            devices.append(primary_device)
            # Re-sort the list
            devices.sort(key=lambda x: x.get('last_connection', ''), reverse=True)
    
    # Mark active devices
    active_device_ids = set()
    for device in user.get('active_devices', []):
        if not device.get('disconnected', False):
            active_device_ids.add(device.get('device_id'))
    
    # Add status flags
    for device in devices:
        device['is_primary'] = device.get('device_id') == primary_device_id
        device['is_active'] = device.get('device_id') in active_device_ids
    
    return jsonify({
        'success': True,
        'devices': devices,
        'has_primary_device': primary_device_id is not None,
        'primary_device_id': primary_device_id
    })

@app.route('/api/devices/disconnect', methods=['POST'])
@login_required
def api_devices_disconnect():
    """Disconnect a device from user account"""
    data = request.get_json()
    if not data or 'device_id' not in data:
        return jsonify({'success': False, 'error': 'Device ID required'})
    
    device_id = data['device_id']
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Update user's devices
    users = get_users()
    device_found = False
    
    for u in users:
        if u['id'] == user['id']:
            # Remove from devices list
            if 'devices' in u:
                u['devices'] = [d for d in u['devices'] if d.get('device_id') != device_id]
            
            # Mark as disconnected in active_devices
            if 'active_devices' in u:
                for device in u['active_devices']:
                    if device.get('device_id') == device_id:
                        device['disconnected'] = True
                        device['force_disconnect'] = True
                        device_found = True
                        break
            
            # Update connection status if no devices left
            if not any(d for d in u.get('active_devices', []) if not d.get('disconnected')):
                u['launcher_connected'] = False
            
            break
    
    if device_found:
        save_users(users)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Device not found'})

@app.route('/api/launcher/check-status', methods=['POST'])
def launcher_check_status():
    """Check if user still has premium access"""
    data = request.get_json()
    
    if not data or 'user_id' not in data:
        return jsonify({'success': False, 'error': 'Invalid request', 'should_disconnect': True})
    
    user_id = data['user_id']
    user = find_user_by_id(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found', 'should_disconnect': True})
    
    # Check if user still has premium status
    if user.get('status') not in ['Premium', 'Admin', 'Premium (Aligned)']:
        return jsonify({
            'success': False, 
            'error': 'Premium subscription required',
            'should_disconnect': True,
            'reason': 'no_premium'
        })
    
    # Check if user's launcher code is still valid
    if not user.get('launcher_code'):
        return jsonify({
            'success': False,
            'error': 'Invalid launcher code',
            'should_disconnect': True,
            'reason': 'invalid_code'
        })
    
    # Determine the status_expires value
    status_expires = "0"  # Default for unlimited premium
    if user.get('premium_expires_at'):
        status_expires = user['premium_expires_at']
    
    return jsonify({
        'success': True,
        'should_disconnect': False,
        'status': user.get('status'),
        'status_expires': status_expires
    })

def force_disconnect_user_devices(user):
    """Force disconnect all devices for a user"""
    if not user:
        return
    
    # Clear launcher connection status
    user['launcher_connected'] = False
    if 'launcher_code' in user:
        del user['launcher_code']
    
    # Mark all active devices for force disconnect
    if 'active_devices' in user:
        for device in user['active_devices']:
            device['disconnected'] = True
            device['force_disconnect'] = True
            device['disconnect_reason'] = 'premium_lost'
            device['disconnected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Clear devices list
    user['devices'] = []
    user['active_devices'] = []

def update_user_status_to_standard(user, reason=""):
    """Update user status to Standard and handle all related changes"""
    if not user:
        return
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Update status
    user['status'] = 'Standard'
    if 'premium_expires_at' in user:
        del user['premium_expires_at']
    
    # Force disconnect all devices
    force_disconnect_user_devices(user)
    
    # Add to premium history
    if 'premium_history' not in user:
        user['premium_history'] = []
    
    user['premium_history'].append({
        'date': timestamp,
        'action': 'Premium Status Revoked',
        'details': f"Premium status removed. {reason} All devices disconnected."
    })
    
    # Handle aligned users
    if 'friends' in user:
        users = get_users()
        for friend_username in list(user.get('friends', [])):
            for u in users:
                if u['username'] == friend_username and u.get('status') == 'Premium (Aligned)' and u.get('aligned_by') == user['username']:
                    # Reset friend's status and disconnect devices
                    update_user_status_to_standard(u, f"Alignment from {user['username']} was removed.")
        
        # Clear user's friends list
        user['friends'] = []
        save_users(users)

@app.route('/api/devices/reset-primary', methods=['POST'])
@login_required
def api_devices_reset_primary():
    """Reset the primary device binding for the user account"""
    user = find_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Check if user has premium status
    if user.get('status') not in ['Premium', 'Admin', 'Premium (Aligned)']:
        return jsonify({'success': False, 'error': 'Premium subscription required'})
    
    # Check if user has already reset HWID within the last week
    last_reset_time = None
    if 'device_reset_history' in user:
        # Get the most recent reset
        if user['device_reset_history']:
            last_reset = user['device_reset_history'][-1]
            try:
                last_reset_time = datetime.strptime(last_reset['date'], '%Y-%m-%d %H:%M:%S')
                # Check if it's been less than a week
                one_week_ago = datetime.now() - timedelta(days=7)
                if last_reset_time > one_week_ago:
                    days_since_reset = (datetime.now() - last_reset_time).days
                    days_until_available = 7 - days_since_reset
                    return jsonify({
                        'success': False, 
                        'error': f'HWID can only be reset once per week. Please wait {days_until_available} more day(s).'
                    })
            except (ValueError, KeyError):
                # If there's an error parsing the date, continue with the reset
                pass
    
    users = get_users()
    updated = False
    
    for u in users:
        if u['id'] == user['id']:
            # Remove primary device binding
            if 'primary_device' in u:
                # Add to history if we want to keep track
                if 'device_reset_history' not in u:
                    u['device_reset_history'] = []
                
                # Record the reset with timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                u['device_reset_history'].append({
                    'date': timestamp,
                    'device_id': u['primary_device'].get('device_id'),
                    'device_name': u['primary_device'].get('device_name'),
                    'action': 'Device Binding Reset'
                })
                
                # Remove the primary device
                del u['primary_device']
                
                # Also disconnect all existing devices
                if 'active_devices' in u:
                    for device in u['active_devices']:
                        device['disconnected'] = True
                        device['force_disconnect'] = True
                        device['disconnect_reason'] = 'primary_device_reset'
                        device['disconnected_at'] = timestamp
                
                u['launcher_connected'] = False
                updated = True
            break
    
    if updated:
        save_users(users)
        return jsonify({'success': True, 'message': 'Primary device binding has been reset'})
    else:
        return jsonify({'success': False, 'error': 'No primary device to reset'})

@app.route('/api/launcher/check-connection', methods=['POST'])
def launcher_check_connection():
    """Check if device is still connected"""
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'device_id' not in data:
        return jsonify({
            'connected': False, 
            'error': 'Invalid request data',
            'force_disconnect': False
        })
    
    user_id = data['user_id']
    device_id = data['device_id']
    user = find_user_by_id(user_id)
    
    if not user:
        return jsonify({
            'connected': False, 
            'error': 'User not found',
            'force_disconnect': True
        })
    
    # Check if user still has premium status
    if user.get('status') not in ['Premium', 'Admin', 'Premium (Aligned)']:
        return jsonify({
            'connected': False, 
            'error': 'Premium subscription required',
            'force_disconnect': True
        })
    
    # Check if device is in active devices
    device_connected = False
    force_disconnect = False
    
    if 'active_devices' in user:
        for device in user['active_devices']:
            if device.get('device_id') == device_id:
                device_connected = not device.get('disconnected', False)
                force_disconnect = device.get('force_disconnect', False)
                break
    
    # Determine the status_expires value
    status_expires = "0"  # Default for unlimited premium
    if user.get('premium_expires_at'):
        status_expires = user['premium_expires_at']
    
    return jsonify({
        'connected': device_connected,
        'force_disconnect': force_disconnect,
        'status': user.get('status'),
        'status_expires': status_expires
    })

@app.route('/api/user/uniqueid/<path:path>')
def api_user_uniqueid(path):
    """API endpoint to check user premium status by username and unique ID"""
    # Parse username and uniqueid from path
    try:
        username, uniqueid = path.split('&', 1)
    except ValueError:
        return jsonify({'error': 'Invalid request format. Use /api/user/uniqueid/{username}&{uniqueid}'}), 400
    
    # Find user by username
    user = find_user_by_username(username)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Verify that the provided uniqueid matches the one stored for the user
    if not user.get('unique_id') or user.get('unique_id') != uniqueid:
        return jsonify({'error': 'Authentication failed'}), 403
    
    # Check if the user has premium status
    has_premium = user.get('status') in ['Premium', 'Admin', 'Premium (Aligned)']
    
    # Get expiry date if available
    expiry = None
    if has_premium and user.get('premium_expires_at'):
        expiry = user['premium_expires_at'].split(' ')[0]  # Get only the date part
    
    # Return premium status and expiry
    return jsonify({
        'premium': has_premium,
        'expiry': expiry
    })

@app.route('/api/admin/users')
def api_admin_users():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 5))
    status = request.args.get('status')
    q = request.args.get('q', '').lower()

    users = get_users()
    # Фильтрация по статусу
    if status and status != 'all':
        users = [u for u in users if u.get('status', '').lower() == status.lower()]
    # Фильтрация по поиску
    if q:
        users = [u for u in users if q in u.get('username', '').lower() or q in u.get('email', '').lower()]

    total = len(users)
    users_page = users[(page-1)*per_page:page*per_page]
    # Формируем ответ
    result = []
    for u in users_page:
        result.append({
            'id': u['id'],
            'username': u['username'],
            'email': u['email'],
            'status': u['status'],
            'joined': u.get('join_date', '')
        })
    return jsonify({
        'users': result,
        'page': page,
        'perPage': per_page,
        'total': total
    })

@app.route('/api/admin/promo-codes/<promo_id>')
def api_admin_promo_code_details(promo_id):
    promo_codes = get_promo_codes()
    promo = next((p for p in promo_codes if p.get('id') == promo_id), None)
    if not promo:
        return jsonify({'success': False, 'error': 'Promo code not found'}), 404

    # Добавим creator, если нужно (или оставим пустым)
    promo['created_by'] = promo.get('created_by', '')

    return jsonify({'success': True, 'promo': promo})

@app.route('/api/admin/promo-codes/delete', methods=['POST'])
@admin_required
def api_admin_delete_promo_code():
    data = request.get_json()
    promo_id = data.get('promo_id')
    if not promo_id:
        return jsonify({'success': False, 'error': 'No promo_id provided'}), 400
    promo_codes = get_promo_codes()
    promo = next((p for p in promo_codes if str(p.get('id')) == str(promo_id)), None)
    if not promo:
        return jsonify({'success': False, 'error': 'Promo code not found'}), 404
    # Удаляем промокод
    promo_codes = [p for p in promo_codes if str(p.get('id')) != str(promo_id)]
    save_promo_codes(promo_codes)
    return jsonify({'success': True})

def fetch_and_process_games(force_update=False):
    """Fetch games from external API and process them"""
    current_time = time.time()
    
    # Check if cache needs to be updated
    if (games_api_cache["data"] is None or 
            current_time - games_api_cache["last_updated"] > GAMES_CACHE_LIFETIME or
            force_update):
        try:
            print(f"[{datetime.now()}] Fetching games data from external API")
            response = requests.get('http://api.swa-recloud.fun/api/v3/fetch/', timeout=10)
            
            if response.status_code != 200:
                print(f"[{datetime.now()}] External API error: {response.status_code}")
                return False
            
            # Parse the JSON response
            data = response.json()
            
            # Process and categorize games
            free_games = {}
            premium_games = {}
            filtered_count = 0
            
            # Pattern to match placeholder game names
            placeholder_patterns = [
                re.compile(r'^GAME\s+\d+$'),                # "GAME XX"
                re.compile(r'^PLACEHOLDER\s*\d*$', re.I),   # "PLACEHOLDER" or "PLACEHOLDER XX"
                re.compile(r'^TEST\s*\d*$', re.I),          # "TEST" or "TEST XX"
                re.compile(r'^UNTITLED\s*\d*$', re.I),      # "UNTITLED" or "UNTITLED XX"
                re.compile(r'^UNKNOWN\s*\d*$', re.I),       # "UNKNOWN" or "UNKNOWN XX"
                re.compile(r'^UNNAMED\s*\d*$', re.I),       # "UNNAMED" or "UNNAMED XX"
                re.compile(r'^TEMP\s*\d*$', re.I)           # "TEMP" or "TEMP XX"
            ]
            
            for game_id, game_data in data.items():
                # Skip games with no name or placeholder names
                game_name = game_data.get('name', '').strip()
                
                if not game_name:
                    filtered_count += 1
                    continue
                
                # Check against all placeholder patterns
                is_placeholder = False
                for pattern in placeholder_patterns:
                    if pattern.match(game_name):
                        is_placeholder = True
                        filtered_count += 1
                        break
                
                if is_placeholder:
                    continue
                
                # Categorize by access type
                if game_data.get('access') == "1":
                    free_games[game_id] = game_data
                elif game_data.get('access') == "2":
                    premium_games[game_id] = game_data
            
            # Update cache
            games_api_cache["data"] = data  # Keep the original data for reference
            games_api_cache["free_games"] = free_games
            games_api_cache["premium_games"] = premium_games
            games_api_cache["last_updated"] = current_time
            
            print(f"[{datetime.now()}] Games data cached: {len(free_games)} free games, {len(premium_games)} premium games")
            print(f"[{datetime.now()}] Filtered out {filtered_count} games with placeholder names")
            return True
        except Exception as e:
            print(f"[{datetime.now()}] Error fetching game data: {e}")
            return False
    
    return True

@app.route('/api/games/stats')
def api_games_stats():
    """API endpoint to get game statistics"""
    # Try to fetch and process games if needed
    fetch_and_process_games()
    
    # Calculate statistics
    stats = {
        "total_games": 0,
        "free_games": 0,
        "premium_games": 0,
        "genres": {},
        "platforms": {
            "windows": 0,
            "mac": 0,
            "linux": 0
        },
        "recently_added": [],
        "last_updated": games_api_cache["last_updated"]
    }
    
    # Process free games
    if games_api_cache["free_games"]:
        stats["free_games"] = len(games_api_cache["free_games"])
        stats["total_games"] += stats["free_games"]
        
        # Process genre and platform stats
        for game_id, game_data in games_api_cache["free_games"].items():
            # Process genres
            if game_data.get("genres"):
                for genre in game_data["genres"]:
                    genre_name = genre.get("description")
                    if genre_name:
                        if genre_name not in stats["genres"]:
                            stats["genres"][genre_name] = 0
                        stats["genres"][genre_name] += 1
            
            # Process platforms
            if game_data.get("platforms"):
                platforms = game_data["platforms"]
                if platforms.get("windows"):
                    stats["platforms"]["windows"] += 1
                if platforms.get("mac"):
                    stats["platforms"]["mac"] += 1
                if platforms.get("linux"):
                    stats["platforms"]["linux"] += 1
    
    # Process premium games
    if games_api_cache["premium_games"]:
        stats["premium_games"] = len(games_api_cache["premium_games"])
        stats["total_games"] += stats["premium_games"]
        
        # Process genre and platform stats
        for game_id, game_data in games_api_cache["premium_games"].items():
            # Process genres
            if game_data.get("genres"):
                for genre in game_data["genres"]:
                    genre_name = genre.get("description")
                    if genre_name:
                        if genre_name not in stats["genres"]:
                            stats["genres"][genre_name] = 0
                        stats["genres"][genre_name] += 1
            
            # Process platforms
            if game_data.get("platforms"):
                platforms = game_data["platforms"]
                if platforms.get("windows"):
                    stats["platforms"]["windows"] += 1
                if platforms.get("mac"):
                    stats["platforms"]["mac"] += 1
                if platforms.get("linux"):
                    stats["platforms"]["linux"] += 1
    
    # Get recently added games (last 10 from both free and premium)
    all_games = []
    
    if games_api_cache["free_games"]:
        for game_id, game_data in games_api_cache["free_games"].items():
            if game_data.get("added_at"):
                all_games.append({
                    "id": game_id,
                    "name": game_data.get("name", "Unknown"),
                    "added_at": game_data.get("added_at"),
                    "access": "free"
                })
    
    if games_api_cache["premium_games"]:
        for game_id, game_data in games_api_cache["premium_games"].items():
            if game_data.get("added_at"):
                all_games.append({
                    "id": game_id,
                    "name": game_data.get("name", "Unknown"),
                    "added_at": game_data.get("added_at"),
                    "access": "premium"
                })
    
    # Sort by added_at (most recent first) and take top 10
    all_games.sort(key=lambda x: x.get("added_at", ""), reverse=True)
    stats["recently_added"] = all_games[:10]
    
    # Sort genres by count (most popular first)
    stats["genres"] = dict(sorted(stats["genres"].items(), key=lambda item: item[1], reverse=True))
    
    return jsonify(stats)

@app.route('/api/games/search')
def api_games_search():
    """API endpoint to search games"""
    # Get search parameters
    query = request.args.get('q', '').lower()
    access = request.args.get('access', 'all')  # 'all', 'free', or 'premium'
    genre = request.args.get('genre', '')
    limit = min(int(request.args.get('limit', 50)), 100)  # Maximum 100 results
    
    if not query and not genre:
        return jsonify({"error": "Search query or genre filter required"}), 400
    
    # Try to fetch and process games if needed
    fetch_and_process_games()
    
    # Prepare results
    results = []
    
    # Search in free games
    if access in ['all', 'free'] and games_api_cache["free_games"]:
        for game_id, game_data in games_api_cache["free_games"].items():
            # Check if game matches search criteria
            if query and query not in game_data.get("name", "").lower():
                continue
                
            # Check genre filter if provided
            if genre and not any(g.get("description") == genre for g in game_data.get("genres", [])):
                continue
                
            # Add to results
            results.append({
                "id": game_id,
                "name": game_data.get("name", "Unknown"),
                "image": game_data.get("image", ""),
                "release_date": game_data.get("release_date", ""),
                "genres": [g.get("description") for g in game_data.get("genres", [])],
                "access": "free"
            })
    
    # Search in premium games
    if access in ['all', 'premium'] and games_api_cache["premium_games"]:
        for game_id, game_data in games_api_cache["premium_games"].items():
            # Check if game matches search criteria
            if query and query not in game_data.get("name", "").lower():
                continue
                
            # Check genre filter if provided
            if genre and not any(g.get("description") == genre for g in game_data.get("genres", [])):
                continue
                
            # Add to results
            results.append({
                "id": game_id,
                "name": game_data.get("name", "Unknown"),
                "image": game_data.get("image", ""),
                "release_date": game_data.get("release_date", ""),
                "genres": [g.get("description") for g in game_data.get("genres", [])],
                "access": "premium"
            })
    
    # Sort results by name
    results.sort(key=lambda x: x.get("name", ""))
    
    # Limit results
    results = results[:limit]
    
    return jsonify({
        "query": query,
        "access": access,
        "genre": genre,
        "count": len(results),
        "results": results
    })

@app.route('/api/games/detail/<game_id>')
def api_game_detail(game_id):
    """API endpoint to get detailed information about a specific game"""
    # Try to fetch and process games if needed
    fetch_and_process_games()
    
    # Look for the game in both free and premium collections
    game_data = None
    access_type = None
    
    if games_api_cache["free_games"] and game_id in games_api_cache["free_games"]:
        game_data = games_api_cache["free_games"][game_id]
        access_type = "free"
    elif games_api_cache["premium_games"] and game_id in games_api_cache["premium_games"]:
        game_data = games_api_cache["premium_games"][game_id]
        access_type = "premium"
    
    if not game_data:
        return jsonify({"error": f"Game with ID {game_id} not found"}), 404
    
    # Return the game data with access type
    result = dict(game_data)
    result["access_type"] = access_type
    
    return jsonify(result)

def get_promo_code_groups():
    """Get list of all promo code groups"""
    promo_codes = get_promo_codes()
    groups = set()
    
    for promo in promo_codes:
        group = promo.get('group', 'default')
        groups.add(group)
    
    return sorted(list(groups))

@app.template_filter('get_group_color')
def get_group_color(group_name):
    """Get CSS color class for a group"""
    colors = {
        'default': 'secondary',
        'vip': 'primary',            # 1 Month Premium Stock
        'special': 'success',        # 6 Month Premium Stock
        'seasonal': 'info',          # Lifetime Premium Stock
        'partner': 'warning',        # 1 Month Slots Stock
        'custom': 'dark'
    }
    return colors.get(group_name.lower(), 'secondary')

@app.template_filter('get_group_display_name')
def get_group_display_name(group_name):
    """Get display name for a group"""
    display_names = {
        'default': 'Default',
        'vip': '1 Month Premium Stock',
        'special': '6 Month Premium Stock',
        'seasonal': 'Lifetime Premium Stock',
        'partner': '1 Month Slots Stock',
        'custom': 'Custom'
    }
    return display_names.get(group_name.lower(), group_name)

if __name__ == '__main__':
    import sys
    debug = False
    # Определяем debug через аргумент или переменную окружения
    if 'debug' in sys.argv or '--debug' in sys.argv:
        debug = True
    elif hasattr(app, 'debug'):
        debug = app.debug
    # Если debug выключен, инициализируем кеш
    if not debug:
        start_background_tasks()
    # Запускаем приложение
    if debug:
        app.run(host='0.0.0.0', debug=debug, port=5001, use_reloader=True)
    else:
        app.run(host='0.0.0.0', debug=debug, port=5001)
