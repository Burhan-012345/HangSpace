from flask import Flask, render_template, request, jsonify, redirect, send_file, send_from_directory, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import os
import shutil
import psutil
from bson import ObjectId
import uuid
from werkzeug.utils import secure_filename
from utils.auth import AuthManager
from utils.database import DatabaseManager
from utils.helpers import JSONEncoder

# Add theme configuration at the top (after imports but before routes)
themes = {
    'default': {
        'name': 'Default',
        'background': 'var(--bg-primary)',
        'primary_color': 'var(--primary)'
    },
    'romantic': {
        'name': 'Romantic',
        'background': 'linear-gradient(135deg, #ffafbd, #ffc3a0)',
        'primary_color': '#ff6b95'
    },
    'dark': {
        'name': 'Dark Mode',
        'background': 'linear-gradient(135deg, #2c3e50, #34495e)',
        'primary_color': '#3498db'
    },
    'nature': {
        'name': 'Nature',
        'background': 'linear-gradient(135deg, #667eea, #764ba2)',
        'primary_color': '#48bb78'
    },
    'ocean': {
        'name': 'Ocean',
        'background': 'linear-gradient(135deg, #4facfe, #00f2fe)',
        'primary_color': '#3182ce'
    },
    'sunset': {
        'name': 'Sunset',
        'background': 'linear-gradient(135deg, #fa709a, #fee140)',
        'primary_color': '#e53e3e'
    }
}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# Add these file upload configurations
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   async_mode='threading',
                   logger=True,
                   engineio_logger=True)

CORS(app)
app.json_encoder = JSONEncoder

# Initialize managers
db_manager = DatabaseManager()
auth_manager = AuthManager()

# Add this at the top of your app.py
_app_initialized = False

@app.before_request
def initialize_app():
    global _app_initialized
    if not _app_initialized:
        # Your initialization code here
        _app_initialized = True

# Add this to your app initialization
def ensure_upload_directories():
    """Create necessary upload directories"""
    directories = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

# Call this when your app starts
ensure_upload_directories()

# ==================== FLASK-ADMIN CONFIGURATION ====================
# Replace your entire Flask-Admin configuration section with this:

from flask_admin import Admin
from flask_admin.contrib.pymongo import ModelView
from flask_admin.base import MenuLink
from flask_admin.form import BaseForm
from wtforms import form, fields, validators
from bson import ObjectId

# Initialize Flask-Admin with custom URL prefix to avoid conflicts
admin = Admin(app, name='HangSpace Admin', template_mode='bootstrap3', url='/admin-panel')

# Base form class for all models
class BaseForm(form.Form):
    pass

# Custom filter base class
class BaseMongoFilter:
    def __init__(self, name, options=None, data_type=None):
        self.name = name
        self.column = name
        self.options = options
        self.data_type = data_type

    def apply(self, query, value):
        return query

    def operation(self):
        return 'equals'

class BooleanFilter(BaseMongoFilter):
    def apply(self, query, value):
        if value == 'true':
            return {self.column: True}
        elif value == 'false':
            return {self.column: False}
        return query

class StringFilter(BaseMongoFilter):
    def apply(self, query, value):
        if value:
            return {self.column: value}
        return query

class AdminModelView(ModelView):
    def is_accessible(self):
        # For development, allow access if user is logged in
        # Remove this in production!
        if 'user_profile_id' not in session:
            print("❌ Admin access denied: No user_profile_id in session")
            return False

        user_profile_id = session['user_profile_id']
        user_profile = db_manager.get_user_profile(user_profile_id)

        if not user_profile:
            print(f"❌ Admin access denied: User profile not found for {user_profile_id}")
            return False

        is_admin = user_profile.get('is_admin', False)
        print(f"🔐 Admin access check for {user_profile['username']}: {is_admin}")

        return is_admin

    def inaccessible_callback(self, name, **kwargs):
        print(f"🔒 Admin inaccessible callback triggered: {name}")
        return redirect(url_for('login'))

    def get_list(self, *args, **kwargs):
        count = self.coll.count_documents({})
        print(f"📊 Admin accessing {self.endpoint}. Total: {count}")
        return super().get_list(*args, **kwargs)

# Updated views with proper configuration
class UserProfileView(AdminModelView):
    column_list = [
        'username', 'display_name', 'status', 'is_online',
        'last_seen', 'created_at', 'is_admin'
    ]
    column_sortable_list = ['username', 'display_name', 'last_seen', 'created_at']
    column_searchable_list = ['username', 'display_name']
    column_labels = {
        'username': 'Username',
        'display_name': 'Display Name',
        'status': 'Status',
        'is_online': 'Online',
        'last_seen': 'Last Seen',
        'created_at': 'Created',
        'is_admin': 'Admin'
    }

    # Form configuration
    form = type('UserProfileForm', (BaseForm,), {
        'username': fields.StringField('Username'),
        'display_name': fields.StringField('Display Name'),
        'status': fields.SelectField('Status', choices=[
            ('online', 'Online'),
            ('offline', 'Offline'),
            ('away', 'Away')
        ]),
        'is_online': fields.BooleanField('Is Online'),
        'is_admin': fields.BooleanField('Is Admin')
    })

class ChatView(AdminModelView):
    column_list = [
        'name', 'is_group', 'participants', 'created_at', 'last_message_at'
    ]
    column_sortable_list = ['name', 'is_group', 'created_at', 'last_message_at']
    column_searchable_list = ['name']
    column_labels = {
        'name': 'Chat Name',
        'is_group': 'Group Chat',
        'participants': 'Participants',
        'created_at': 'Created',
        'last_message_at': 'Last Message'
    }

    form = type('ChatForm', (BaseForm,), {
        'name': fields.StringField('Name'),
        'is_group': fields.BooleanField('Is Group')
    })

class MessageView(AdminModelView):
    column_list = [
        'chat_id', 'sender_id', 'content', 'message_type',
        'timestamp', 'is_edited', 'is_deleted'
    ]
    column_sortable_list = ['timestamp', 'is_edited', 'is_deleted']
    column_searchable_list = ['content']
    column_labels = {
        'chat_id': 'Chat ID',
        'sender_id': 'Sender ID',
        'content': 'Content',
        'message_type': 'Type',
        'timestamp': 'Timestamp',
        'is_edited': 'Edited',
        'is_deleted': 'Deleted'
    }

    form = type('MessageForm', (BaseForm,), {
        'content': fields.TextAreaField('Content'),
        'message_type': fields.SelectField('Message Type', choices=[
            ('text', 'Text'),
            ('file', 'File')
        ]),
        'is_edited': fields.BooleanField('Is Edited'),
        'is_deleted': fields.BooleanField('Is Deleted')
    })

class FriendRequestView(AdminModelView):
    column_list = [
        'from_user_id', 'to_user_id', 'status', 'created_at'
    ]
    column_sortable_list = ['status', 'created_at']
    column_labels = {
        'from_user_id': 'From User',
        'to_user_id': 'To User',
        'status': 'Status',
        'created_at': 'Created'
    }

    form = type('FriendRequestForm', (BaseForm,), {
        'status': fields.SelectField('Status', choices=[
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('declined', 'Declined')
        ])
    })

class NotificationView(AdminModelView):
    column_list = [
        'user_id', 'type', 'message', 'is_read', 'created_at'
    ]
    column_sortable_list = ['type', 'is_read', 'created_at']
    column_searchable_list = ['message', 'type']
    column_labels = {
        'user_id': 'User ID',
        'type': 'Type',
        'message': 'Message',
        'is_read': 'Read',
        'created_at': 'Created'
    }

    form = type('NotificationForm', (BaseForm,), {
        'type': fields.SelectField('Type', choices=[
            ('friend_request', 'Friend Request'),
            ('message', 'Message'),
            ('system', 'System')
        ]),
        'message': fields.StringField('Message'),
        'is_read': fields.BooleanField('Is Read')
    })

# Add views to admin
try:
    admin.add_view(UserProfileView(db_manager.user_profiles, 'User Profiles'))
    admin.add_view(ChatView(db_manager.chats, 'Chats'))
    admin.add_view(MessageView(db_manager.messages, 'Messages'))
    admin.add_view(FriendRequestView(db_manager.friend_requests, 'Friend Requests'))
    admin.add_view(NotificationView(db_manager.notifications, 'Notifications'))

    # Add admin home link
    admin.add_link(MenuLink(name='Back to Site', url='/'))

    print("✅ Flask-Admin configured successfully")
except Exception as e:
    print(f"❌ Error configuring Flask-Admin: {e}")

# Initialize managers
db_manager = DatabaseManager()
auth_manager = AuthManager()

app.config['ALLOWED_EXTENSIONS'] = {
    'images': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'},
    'videos': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'},
    'audio': {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'},
    'documents': {'pdf', 'doc', 'docx', 'txt', 'rtf', 'xls', 'xlsx', 'ppt', 'pptx', 'csv'}
}

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def is_accessible(self):
    if 'user_profile_id' not in session:
        return False

    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    return user_profile and user_profile.get('is_admin', False)

def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()

    # Check all allowed extensions
    all_extensions = set()
    for category in app.config['ALLOWED_EXTENSIONS'].values():
        all_extensions.update(category)

    return ext in all_extensions

def ensure_upload_directories():
    """Create necessary upload directories"""
    directories = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

# Call this function when your app starts
ensure_upload_directories()

def get_file_category(filename):
    """Get file category based on extension"""
    if '.' not in filename:
        return 'other'

    ext = filename.rsplit('.', 1)[1].lower()

    for category, extensions in app.config['ALLOWED_EXTENSIONS'].items():
        if ext in extensions:
            return category

    return 'other'

def save_file(file, user_id):
    """Save file to disk and return file info - with enhanced error handling"""
    if not allowed_file(file.filename):
        raise ValueError('File type not allowed')

    try:
        # Generate unique filename
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

        # Create user-specific directory - use forward slashes for consistency
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id)).replace('\\', '/')
        print(f"📁 Creating directory: {user_upload_dir}")

        os.makedirs(user_upload_dir, exist_ok=True)

        # Verify directory was created
        if not os.path.exists(user_upload_dir):
            raise ValueError(f'Failed to create directory: {user_upload_dir}')

        # Save file - use forward slashes
        file_path = os.path.join(user_upload_dir, unique_filename).replace('\\', '/')
        print(f"📁 Saving file to: {file_path}")

        # Ensure file pointer is at start
        file.seek(0)

        # Read file content and save
        file_content = file.read()
        with open(file_path, 'wb') as f:
            f.write(file_content)

        # Verify file was saved
        if not os.path.exists(file_path):
            raise ValueError('File was not saved successfully')

        # Get file size
        file_size = os.path.getsize(file_path)
        print(f"✅ File saved successfully: {file_size} bytes")

        # Return file info with ISO format datetime strings
        return {
            'original_filename': secure_filename(file.filename),
            'saved_filename': unique_filename,
            'file_path': file_path,
            'file_size': file_size,
            'file_extension': file_ext,
            'file_category': get_file_category(file.filename),
            'uploaded_by': user_id,
            'uploaded_at': datetime.utcnow().isoformat(),  # Convert to ISO string
            'download_url': f"/api/download-file/{user_id}/{unique_filename}",
            'preview_url': f"/api/preview-file/{user_id}/{unique_filename}" if get_file_category(file.filename) == 'images' else None,
            'file_type': get_file_type(file_ext)
        }

    except Exception as e:
        print(f"❌ Error in save_file: {e}")
        import traceback
        traceback.print_exc()
        # Clean up if partial file was created
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise e

@app.context_processor
def utility_processor():
    def get_sender_name(sender_id):
        """Get sender display name for messages"""
        if 'user_profile_id' in session and sender_id == session['user_profile_id']:
            return session.get('display_name', 'You')

        user_profile = db_manager.get_user_profile(sender_id)
        if user_profile:
            return user_profile.get('display_name', user_profile['username'])
        return 'Unknown User'

    return dict(get_sender_name=get_sender_name)

@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard with statistics"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    # Basic admin check - replace with proper admin system
    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile or user_profile.get('username') != 'admin':  # Replace with your admin check
        return redirect(url_for('dashboard'))

    # Get statistics
    total_users = db_manager.user_profiles.count_documents({})
    total_chats = db_manager.chats.count_documents({})
    total_messages = db_manager.messages.count_documents({})
    online_users = db_manager.user_profiles.count_documents({'status': 'online'})

    # Recent activity
    recent_messages = list(db_manager.messages.find()
                          .sort('timestamp', -1)
                          .limit(10))

    recent_users = list(db_manager.user_profiles.find()
                       .sort('created_at', -1)
                       .limit(10))

    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_chats=total_chats,
                         total_messages=total_messages,
                         online_users=online_users,
                         recent_messages=recent_messages,
                         recent_users=recent_users)

@app.route('/admin/cleanup')
def admin_cleanup():
    """Admin cleanup operations"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    # Admin check
    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile or user_profile.get('username') != 'admin':
        return redirect(url_for('dashboard'))

    return render_template('admin/cleanup.html')

@app.route('/admin/cleanup/duplicate-chats', methods=['POST'])
def admin_cleanup_duplicate_chats():
    """Admin endpoint to clean up duplicate chats"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Admin check
    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile or user_profile.get('username') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    duplicates_removed = db_manager.cleanup_duplicate_chats()
    return jsonify({
        'success': True,
        'message': f'Removed {duplicates_removed} duplicate chats'
    })

@app.route('/admin/cleanup/mock-users', methods=['POST'])
def admin_cleanup_mock_users():
    """Admin endpoint to clean up mock users"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Admin check
    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile or user_profile.get('username') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    if hasattr(db_manager, 'cleanup_all_mock_users'):
        removed_count = db_manager.cleanup_all_mock_users()
        return jsonify({
            'success': True,
            'message': f'Removed {removed_count} mock users and their data'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'cleanup_all_mock_users method not available'
        })

@app.route('/admin/cleanup/notifications', methods=['POST'])
def admin_cleanup_notifications():
    """Admin endpoint to clean up old notifications"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Admin check
    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile or user_profile.get('username') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    days_old = request.json.get('days_old', 30)
    cleaned_count = db_manager.cleanup_old_notifications(days_old)

    return jsonify({
        'success': True,
        'message': f'Cleaned up {cleaned_count} notifications older than {days_old} days'
    })

@app.route('/')
def index():
    if 'user_id' in session and 'user_profile_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/auth/google')
def google_auth():
    """Initiate Google OAuth2 flow"""
    return auth_manager.initiate_oauth()

@app.route('/auth/callback')
def auth_callback():
    """Handle Google OAuth2 callback"""
    try:
        user_info = auth_manager.handle_callback(request)
        if not user_info:
            print("❌ No user info returned from auth callback")
            return redirect(url_for('login', error='Authentication failed - no user info'))

        # Store user in database or update existing
        user = db_manager.get_or_create_user(user_info)

        if user is None:
            print("❌ Failed to get or create user in database")
            return redirect(url_for('login', error='Failed to create user account'))

        # Store in session
        session['user_id'] = str(user['_id'])
        session['google_id'] = user_info['sub']
        session.permanent = True

        print(f"✅ User authenticated successfully: {user_info.get('email', 'Unknown')}")
        return redirect(url_for('select_profile'))

    except Exception as e:
        print(f"❌ Auth callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('login', error=f'Authentication error: {str(e)}'))

@app.route('/debug/auth-test')
def debug_auth_test():
    """Test authentication flow"""
    return f"""
    <h1>Auth Debug</h1>
    <p>Session: {dict(session)}</p>
    <p><a href="/auth/google">Test Google Auth</a></p>
    <p><a href="/debug/db-status">Check DB Status</a></p>
    """

@app.route('/debug/clear-session')
def debug_clear_session():
    """Clear session for testing"""
    session.clear()
    return "Session cleared"

@app.route('/select-profile', methods=['GET', 'POST'])
def select_profile():
    """Allow users to select from multiple profiles under one Google account"""
    user_id = session.get('user_id')

    if not user_id:
        print("❌ No user_id in session, redirecting to login")
        return redirect(url_for('login'))

    profiles = db_manager.get_user_profiles(user_id)

    # Handle profile selection (works for both GET and POST)
    if request.method == 'POST':
        profile_id = request.form.get('profile_id')
    else:
        profile_id = request.args.get('profile_id')

    if profile_id:
        profile = db_manager.get_user_profile(profile_id)

        if profile and str(profile['user_id']) == user_id:
            # Set new session data for the selected profile
            session['user_profile_id'] = str(profile['_id'])
            session['username'] = profile['username']
            session['display_name'] = profile.get('display_name', profile['username'])
            session.permanent = True

            print(f"✅ Profile selected: {profile['username']}")

            # Update user status to online
            db_manager.update_user_status(session['user_profile_id'], 'online')

            # Redirect to dashboard after successful profile selection
            return redirect(url_for('dashboard'))
        else:
            return render_template('select_profile.html',
                                 profiles=profiles,
                                 user_id=user_id,
                                 error='Invalid profile selection')

    return render_template('select_profile.html', profiles=profiles, user_id=user_id)

@app.route('/create-profile', methods=['GET', 'POST'])
def create_profile():
    """Create a new user profile under the Google account"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username')
        display_name = request.form.get('display_name')

        if db_manager.is_username_available(username):
            profile = db_manager.create_user_profile(
                session['user_id'],
                username,
                display_name
            )
            session['user_profile_id'] = str(profile['_id'])
            session['username'] = profile['username']
            return redirect(url_for('dashboard'))
        else:
            return render_template('create_profile.html', error='Username not available')

    return render_template('create_profile.html')

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    """Update user profile information"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    updates = {}
    if 'display_name' in data:
        updates['display_name'] = data['display_name'].strip()
    if 'status' in data:
        updates['status'] = data['status'].strip()
    if 'avatar_url' in data:
        updates['avatar_url'] = data['avatar_url'].strip()

    if not updates:
        return jsonify({'success': False, 'error': 'No valid fields to update'})

    result = db_manager.update_user_profile(session['user_profile_id'], updates)
    return jsonify(result)

@app.route('/api/change-username', methods=['POST'])
def change_username():
    """Change username with availability check"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    new_username = data.get('username', '').strip().lower()
    if not new_username:
        return jsonify({'success': False, 'error': 'Username cannot be empty'})

    # Check if username is available
    if not db_manager.is_username_available(new_username):
        return jsonify({'success': False, 'error': 'Username already taken'})

    # Update username
    result = db_manager.update_user_profile(session['user_profile_id'], {'username': new_username})
    if result['success']:
        # Update session username
        session['username'] = new_username

    return jsonify(result)

@app.route('/dashboard')
def dashboard():
    """Main dashboard with friends and chats"""
    if 'user_profile_id' not in session:
        print("No user_profile_id in session, redirecting to login")
        return redirect(url_for('login'))

    user_profile_id = session['user_profile_id']
    user_data = db_manager.get_user_profile(user_profile_id)

    if not user_data:
        print(f"User profile not found: {user_profile_id}")
        session.clear()
        return redirect(url_for('login'))

    print(f"Dashboard loaded for user: {user_data.get('username', 'Unknown')}")

    friends = db_manager.get_friends(user_profile_id)
    pending_requests = db_manager.get_pending_requests(user_profile_id)
    chats = db_manager.get_user_chats(user_profile_id)

    return render_template('dashboard.html',
                         user=user_data,
                         friends=friends,
                         pending_requests=pending_requests,
                         chats=chats)

@app.route('/user/<user_id>')
def view_user_profile(user_id):
    """View a user's profile"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    # Don't allow viewing your own profile through this route
    if user_id == session['user_profile_id']:
        return redirect(url_for('dashboard'))

    user_profile = db_manager.get_user_profile(user_id)
    if not user_profile:
        return render_template('404.html'), 404

    # Check if users are friends
    current_user_friends = db_manager.get_friends(session['user_profile_id'])
    is_friend = any(friend['_id'] == user_id for friend in current_user_friends)

    # Check if there's a pending friend request
    pending_requests = db_manager.get_pending_requests(session['user_profile_id'])
    has_pending_request = any(
        request['from_user']['_id'] == user_id for request in pending_requests
    )

    return render_template('user_profile.html',
                         user=user_profile,
                         is_friend=is_friend,
                         has_pending_request=has_pending_request)

@app.route('/my-profile')
def my_profile():
    """View current user's own profile"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile:
        return redirect(url_for('login'))

    friends = db_manager.get_friends(session['user_profile_id'])

    return render_template('my_profile.html',
                         user=user_profile,
                         friends=friends)

@app.route('/api/send-friend-request', methods=['POST'])
def send_friend_request():
    """Send a friend request to another user"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    target_user_id = data.get('user_id')
    if not target_user_id:
        return jsonify({'error': 'No user_id provided'}), 400

    result = db_manager.send_friend_request(session['user_profile_id'], target_user_id)

    return jsonify(result)

@app.route('/api/respond-friend-request', methods=['POST'])
def respond_friend_request():
    """Accept or decline a friend request"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    request_id = data.get('request_id')
    action = data.get('action')  # 'accept' or 'decline'

    if not request_id or not action:
        return jsonify({'error': 'Missing request_id or action'}), 400

    result = db_manager.respond_friend_request(request_id, action, session['user_profile_id'])

    return jsonify(result)

@app.route('/chat/<chat_id>')
def chat(chat_id):
    """Individual chat page with persistence"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    chat_data = db_manager.get_chat_with_theme(chat_id, session['user_profile_id'])
    if not chat_data:
        return redirect(url_for('dashboard'))

    # Use the new persistent message method
    messages = db_manager.get_chat_messages_with_persistence(chat_id, session['user_profile_id'])
    user_data = db_manager.get_user_profile(session['user_profile_id'])

    # Ensure participants are properly formatted as strings
    if 'participants' in chat_data:
        chat_data['participants'] = [str(pid) for pid in chat_data['participants']]

    return render_template('chat.html',
                         chat=chat_data,
                         messages=messages,
                         user=user_data)

@app.route('/api/chat/<chat_id>/messages')
def get_chat_messages_api(chat_id):
    """API endpoint to get chat messages with persistence"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        limit = request.args.get('limit', 50, type=int)
        messages = db_manager.get_chat_messages_with_persistence(
            chat_id,
            session['user_profile_id'],
            limit
        )

        return jsonify({
            'success': True,
            'messages': messages,
            'count': len(messages)
        })

    except Exception as e:
        print(f"❌ Error getting chat messages API: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create-chat', methods=['POST'])
def create_chat():
    """Create a new chat (individual or group)"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    participant_ids = data.get('participants', [])
    chat_name = data.get('name', '')
    is_group = data.get('is_group', False)

    # Always include current user
    participant_ids.append(session['user_profile_id'])

    chat = db_manager.create_chat(participant_ids, chat_name, is_group)

    return jsonify({'chat_id': str(chat['_id'])})

@app.route('/api/friends')
def get_friends():
    """API endpoint to get friends list"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    friends = db_manager.get_friends(session['user_profile_id'])
    return jsonify({'friends': friends})

@app.route('/api/friends/suggested')
def get_suggested_friends():
    """API endpoint to get suggested friends"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # For now, return empty array - implement suggestion logic later
    return jsonify({'users': []})

@app.route('/api/search')
def global_search():
    """Global search endpoint"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    query = request.args.get('q', '')
    search_type = request.args.get('type', 'users')

    if search_type == 'users':
        results = db_manager.search_users(query, session['user_profile_id'])
        return jsonify({'results': results})
    else:
        # Implement chats and messages search later
        return jsonify({'results': []})

@app.route('/api/remove-friend', methods=['POST'])
def remove_friend():
    """Remove a friend"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    friend_id = data.get('friend_id')
    if not friend_id:
        return jsonify({'error': 'No friend_id provided'}), 400

    result = db_manager.remove_friend(session['user_profile_id'], friend_id)
    return jsonify(result)

@app.route('/edit-profile')
def edit_profile():
    """Edit profile page"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    user_profile = db_manager.get_user_profile(session['user_profile_id'])
    if not user_profile:
        return redirect(url_for('login'))

    return render_template('edit_profile.html', user=user_profile)

@app.route('/api/check-username', methods=['POST'])
def check_username():
    """Check if username is available"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    username = data.get('username', '').strip().lower()
    if not username:
        return jsonify({'available': False, 'error': 'Username cannot be empty'})

    # Check if username is available (excluding current user)
    current_profile = db_manager.get_user_profile(session['user_profile_id'])
    if current_profile and username == current_profile['username']:
        return jsonify({'available': True, 'message': 'This is your current username'})

    available = db_manager.is_username_available(username)
    return jsonify({'available': available})

# Socket.IO Events
connected_clients = {}

@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    client_id = request.sid
    print(f"Client connected: {client_id}")

    if 'user_profile_id' in session:
        user_profile_id = session['user_profile_id']
        connected_clients[client_id] = user_profile_id
        db_manager.update_user_status(user_profile_id, 'online')
        emit('user_online', {'user_id': user_profile_id}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnection"""
    client_id = request.sid
    print(f"Client disconnected: {client_id}")

    if client_id in connected_clients:
        user_profile_id = connected_clients[client_id]
        db_manager.update_user_status(user_profile_id, 'offline')
        emit('user_offline', {'user_id': user_profile_id}, broadcast=True)
        del connected_clients[client_id]

@socketio.on('join_chat')
def handle_join_chat(data):
    """Join a chat room"""
    chat_id = data.get('chat_id')
    if chat_id and 'user_profile_id' in session:
        join_room(chat_id)
        print(f"User {session['user_profile_id']} joined chat: {chat_id}")

@socketio.on('leave_chat')
def handle_leave_chat(data):
    """Leave a chat room"""
    chat_id = data.get('chat_id')
    if chat_id and 'user_profile_id' in session:
        leave_room(chat_id)
        print(f"User {session['user_profile_id']} left chat: {chat_id}")

@socketio.on('send_message')
def handle_send_message(data):
    """Send a message to a chat - with proper notification handling"""
    chat_id = data.get('chat_id')
    message_content = data.get('message')
    message_type = data.get('type', 'text')

    if not chat_id or not message_content:
        print("❌ Missing chat_id or message content")
        return

    if 'user_profile_id' not in session:
        print("❌ User not authenticated")
        return

    try:
        user_profile_id = session['user_profile_id']
        print(f"📨 Sending message from {user_profile_id} to chat {chat_id}: {message_content}")

        # Create the message in database
        message = db_manager.create_message(
            chat_id=chat_id,
            sender_id=user_profile_id,
            content=message_content,
            message_type=message_type
        )

        if message:
            # Get sender info
            sender_profile = db_manager.get_user_profile(user_profile_id)
            sender_username = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'

            # Prepare message data for broadcasting
            message_data = {
                'message_id': str(message['_id']),
                'chat_id': chat_id,
                'sender_id': user_profile_id,
                'sender_username': sender_username,
                'content': message_content,
                'type': message_type,
                'timestamp': message['timestamp'].isoformat()
            }

            print(f"✅ Broadcasting message: {message_data['message_id']}")

            # Get chat info for notifications
            chat = db_manager.get_chat(chat_id, user_profile_id)
            if chat:
                # Create notifications for all other participants
                for participant_id in chat['participants']:
                    participant_id_str = str(participant_id)
                    if participant_id_str != user_profile_id:
                        # Create consolidated notification
                        notification = db_manager.create_consolidated_message_notification(message_data, participant_id_str)

                        if notification:
                            # Emit real-time notification update to the specific user
                            emit('notification_updated', {
                                'type': 'new_message',
                                'notification': notification
                            }, room=participant_id_str)

                            # Also update the badge count in real-time
                            unread_count = db_manager.get_unread_notifications_count(participant_id_str)
                            emit('notification_badge_updated', {
                                'unread_count': unread_count
                            }, room=participant_id_str)

            # Broadcast message to chat room (excluding sender)
            emit('new_message', message_data, room=chat_id, include_self=False)

            # Also send to sender but with a different approach to avoid duplicates
            emit('new_message', message_data, room=request.sid)

        else:
            print("❌ Failed to create message in database")

    except Exception as e:
        print(f"❌ Error sending message: {e}")
        import traceback
        traceback.print_exc()
        emit('message_error', {'error': 'Failed to send message'})

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators"""
    chat_id = data.get('chat_id')
    is_typing = data.get('is_typing')

    if chat_id and 'user_profile_id' in session:
        user_profile = db_manager.get_user_profile(session['user_profile_id'])
        username = user_profile.get('display_name', user_profile['username']) if user_profile else 'Unknown'

        emit('user_typing', {
            'user_id': session.get('user_profile_id'),
            'username': username,
            'is_typing': is_typing
        }, room=chat_id, include_self=False)

@app.route('/logout')
def logout():
    """Logout user and redirect to select profile page"""
    # Store user_id before clearing session so we can redirect to select-profile
    user_id = session.get('user_id')

    # Update user status to offline for current profile
    if 'user_profile_id' in session:
        user_profile_id = session['user_profile_id']
        db_manager.update_user_status(user_profile_id, 'offline')
        print(f"✅ User {user_profile_id} logged out")

    # Clear the session but preserve user_id for select-profile
    session.clear()

    # Set the user_id back in session for select-profile to work
    if user_id:
        session['user_id'] = user_id
        print(f"✅ Preserved user_id {user_id} for profile selection")

    # Redirect to select-profile page
    return redirect(url_for('select_profile'))

@app.route('/admin/cleanup-chats')
def cleanup_chats():
    """Admin route to clean up duplicate chats"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Check if the method exists before calling it
    if hasattr(db_manager, 'cleanup_duplicate_chats'):
        duplicates_removed = db_manager.cleanup_duplicate_chats()
        return jsonify({
            'success': True,
            'message': f'Removed {duplicates_removed} duplicate chats'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'cleanup_duplicate_chats method not available'
        })

@app.route('/api/save-chat-theme', methods=['POST'])
def save_chat_theme():
    """Save chat theme for all participants with enhanced synchronization"""
    if 'user_profile_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'})

        chat_id = data.get('chat_id')
        theme_name = data.get('theme_name')

        if not chat_id or not theme_name:
            return jsonify({'success': False, 'error': 'Missing required fields: chat_id and theme_name'})

        # Validate theme name
        valid_themes = ['default', 'romantic', 'dark', 'nature', 'ocean', 'sunset']
        if theme_name not in valid_themes:
            return jsonify({'success': False, 'error': 'Invalid theme name'})

        # Get the chat
        chat = db_manager.get_chat(chat_id, session['user_profile_id'])
        if not chat:
            return jsonify({'success': False, 'error': 'Chat not found'})

        # Save theme for all participants
        theme_results = []
        for participant_id in chat['participants']:
            result = db_manager.save_chat_theme(participant_id, chat_id, theme_name)
            theme_results.append({
                'participant_id': str(participant_id),
                'success': result['success'],
                'error': result.get('error')
            })

        # Emit socket event to notify all participants with enhanced data
        socketio.emit('theme_updated', {
            'chat_id': chat_id,
            'theme_name': theme_name,
            'updated_by': session['user_profile_id'],
            'updated_at': datetime.utcnow().isoformat(),
            'force_refresh': True,
            'theme_data': themes.get(theme_name, {})
        }, room=chat_id)

        success_count = len([r for r in theme_results if r['success']])

        return jsonify({
            'success': True,
            'message': f'Theme {theme_name} applied to {success_count} participants',
            'results': theme_results
        })

    except Exception as e:
        print(f"❌ Error saving chat theme: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'})

# Add theme configuration at the top of app.py (after imports)
themes = {
    'default': {
        'name': 'Default',
        'background': 'var(--bg-primary)',
        'primary_color': 'var(--primary)'
    },
    'romantic': {
        'name': 'Romantic',
        'background': 'linear-gradient(135deg, #ffafbd, #ffc3a0)',
        'primary_color': '#ff6b95'
    },
    'dark': {
        'name': 'Dark Mode',
        'background': 'linear-gradient(135deg, #2c3e50, #34495e)',
        'primary_color': '#3498db'
    },
    'nature': {
        'name': 'Nature',
        'background': 'linear-gradient(135deg, #667eea, #764ba2)',
        'primary_color': '#48bb78'
    },
    'ocean': {
        'name': 'Ocean',
        'background': 'linear-gradient(135deg, #4facfe, #00f2fe)',
        'primary_color': '#3182ce'
    },
    'sunset': {
        'name': 'Sunset',
        'background': 'linear-gradient(135deg, #fa709a, #fee140)',
        'primary_color': '#e53e3e'
    }
}

@app.route('/api/get-chat-theme', methods=['POST'])
def get_chat_theme():
    """Get chat theme preference for current user"""
    if 'user_profile_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'})

        chat_id = data.get('chat_id')

        if not chat_id:
            return jsonify({'success': False, 'error': 'Missing chat ID'})

        # Get theme for current user in this chat
        theme_preference = db_manager.get_chat_theme(session['user_profile_id'], chat_id)

        if theme_preference:
            return jsonify({
                'success': True,
                'theme_name': theme_preference['theme_name']
            })
        else:
            return jsonify({'success': True, 'theme_name': 'default'})

    except Exception as e:
        print(f"❌ Error getting chat theme: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'})

@app.route('/api/reset-chat-theme', methods=['POST'])
def reset_chat_theme():
    """Reset chat theme to default for all participants"""
    if 'user_profile_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'})

        chat_id = data.get('chat_id')

        if not chat_id:
            return jsonify({'success': False, 'error': 'Missing chat ID'})

        # Get the chat
        chat = db_manager.get_chat(chat_id, session['user_profile_id'])
        if not chat:
            return jsonify({'success': False, 'error': 'Chat not found'})

        # Reset theme for all participants to default
        for participant_id in chat['participants']:
            result = db_manager.delete_chat_theme(participant_id, chat_id)
            if not result['success']:
                print(f"⚠️ Failed to reset theme for participant {participant_id}: {result.get('error')}")

        # Emit socket event to notify all participants
        socketio.emit('theme_updated', {
            'chat_id': chat_id,
            'theme_name': 'default',
            'updated_by': session['user_profile_id']
        }, room=chat_id)

        return jsonify({
            'success': True,
            'message': 'Theme reset to default for all participants'
        })

    except Exception as e:
        print(f"❌ Error resetting chat theme: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'})

@app.route('/api/get-all-chat-themes', methods=['GET'])
def get_all_chat_themes():
    """Get all chat theme preferences for current user"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    themes = db_manager.get_user_chat_themes(session['user_profile_id'])

    return jsonify({
        'success': True,
        'themes': themes
    })

@app.route('/api/get-chat-participant-statuses', methods=['POST'])
def get_chat_participant_statuses():
    """Get online/offline statuses for all participants in a chat"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    chat_id = data.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'Missing chat_id'}), 400

    try:
        # Get chat data
        chat = db_manager.get_chat(chat_id, session['user_profile_id'])
        if not chat:
            return jsonify({'error': 'Chat not found'}), 404

        # Get statuses for all participants
        statuses = []
        for participant in chat['participants']:
            participant_id = str(participant['_id'])

            # Skip current user
            if participant_id == session['user_profile_id']:
                continue

            # Get user status from database
            user_profile = db_manager.get_user_profile(participant_id)
            if user_profile:
                status = user_profile.get('status', 'offline')
                statuses.append({
                    'user_id': participant_id,
                    'status': status,
                    'username': user_profile.get('display_name', user_profile['username'])
                })

        return jsonify({
            'success': True,
            'statuses': statuses
        })

    except Exception as e:
        print(f"❌ Error getting participant statuses: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-user-status', methods=['POST'])
def get_user_status_api():
    """Get user online/offline status"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400

    try:
        status = db_manager.get_user_status(user_id)
        return jsonify({
            'success': True,
            'status': status,
            'user_id': user_id
        })
    except Exception as e:
        print(f"❌ Error getting user status: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Update the socketio connection handler to include initial status sending
@socketio.on('request_initial_statuses')
def handle_request_initial_statuses(data):
    """Send initial statuses when a user joins a chat"""
    chat_id = data.get('chat_id')
    if chat_id and 'user_profile_id' in session:
        try:
            # Get chat data
            chat = db_manager.get_chat(chat_id, session['user_profile_id'])
            if chat:
                # Get statuses for all participants
                statuses = []
                for participant in chat['participants']:
                    participant_id = str(participant['_id'])

                    # Skip current user
                    if participant_id == session['user_profile_id']:
                        continue

                    # Get user status from database
                    user_profile = db_manager.get_user_profile(participant_id)
                    if user_profile:
                        status = user_profile.get('status', 'offline')
                        statuses.append({
                            'user_id': participant_id,
                            'status': status
                        })

                # Send initial statuses to the requesting client
                emit('initial_statuses', {'statuses': statuses}, room=request.sid)
                print(f"✅ Sent initial statuses to user {session['user_profile_id']} for chat {chat_id}")

        except Exception as e:
            print(f"❌ Error sending initial statuses: {e}")

@socketio.on('message_read')
def handle_message_read(data):
    """Handle message read receipt"""
    message_id = data.get('message_id')
    if message_id and 'user_profile_id' in session:
        result = db_manager.mark_message_as_read(message_id, session['user_profile_id'])
        if result['success']:
            # Notify the sender that their message was read
            message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
            if message:
                emit('message_read_receipt', {
                    'message_id': message_id,
                    'reader_id': session['user_profile_id'],
                    'chat_id': str(message['chat_id']),
                    'read_at': datetime.utcnow().isoformat()
                }, room=str(message['sender_id']))

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators with notifications"""
    chat_id = data.get('chat_id')
    is_typing = data.get('is_typing')

    if chat_id and 'user_profile_id' in session:
        user_profile = db_manager.get_user_profile(session['user_profile_id'])
        username = user_profile.get('display_name', user_profile['username']) if user_profile else 'Unknown'

        # Send typing indicator to all other participants
        emit('user_typing', {
            'user_id': session.get('user_profile_id'),
            'username': username,
            'is_typing': is_typing
        }, room=chat_id, include_self=False)

@socketio.on('request_notifications')
def handle_request_notifications():
    """Send current notifications to user when they request"""
    if 'user_profile_id' in session:
        user_id = session['user_profile_id']
        notifications = db_manager.get_user_notifications(user_id, limit=10, unread_only=False)
        unread_count = db_manager.get_unread_notifications_count(user_id)

        emit('notifications_data', {
            'notifications': notifications,
            'unread_count': unread_count
        })

@socketio.on('mark_notification_read')
def handle_mark_notification_read(data):
    """Mark notification as read via socket"""
    if 'user_profile_id' in session:
        notification_id = data.get('notification_id')
        sender_id = data.get('sender_id')

        if notification_id:
            db_manager.mark_notification_as_read(notification_id, session['user_profile_id'])

        # If sender_id is provided, mark all notifications from that sender as read
        if sender_id:
            db_manager.mark_all_message_notifications_as_read(session['user_profile_id'], sender_id)
            # Emit event to remove bell icon for that sender
            emit('notifications_cleared', {
                'sender_id': sender_id,
                'cleared_at': datetime.utcnow().isoformat()
            }, room=session['user_profile_id'])

@socketio.on('mark_all_message_notifications_read')
def handle_mark_all_message_notifications_read(data):
    """Mark all message notifications as read for current user"""
    if 'user_profile_id' in session:
        sender_id = data.get('sender_id')
        cleared_count = db_manager.mark_all_message_notifications_as_read(session['user_profile_id'], sender_id)

        if cleared_count > 0:
            emit('notifications_cleared', {
                'sender_id': sender_id,
                'cleared_count': cleared_count,
                'cleared_at': datetime.utcnow().isoformat()
            }, room=session['user_profile_id'])

@socketio.on('get_unread_message_notifications_count')
def handle_get_unread_message_notifications_count(data):
    """Get count of unread message notifications"""
    if 'user_profile_id' in session:
        sender_id = data.get('sender_id')
        count = db_manager.get_unread_message_notifications_count(session['user_profile_id'], sender_id)

        emit('unread_message_notifications_count', {
            'sender_id': sender_id,
            'count': count
        })

# Add this route to app.py
@app.route('/api/notifications/cleanup-read', methods=['POST'])
def cleanup_read_notifications():
    """Remove all read notifications"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        deleted_count = db_manager.cleanup_read_notifications(session['user_profile_id'])
        return jsonify({
            'success': True,
            'message': f'Removed {deleted_count} read notifications',
            'deleted_count': deleted_count
        })
    except Exception as e:
        print(f"❌ Error cleaning up read notifications: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-group', methods=['POST'])
def delete_group():
    """Delete a group chat"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    chat_id = data.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'Missing chat_id'}), 400

    try:
        # Verify the chat exists and user is a participant
        chat = db_manager.get_chat(chat_id, session['user_profile_id'])
        if not chat:
            return jsonify({'success': False, 'error': 'Group not found'})

        if not chat.get('is_group', False):
            return jsonify({'success': False, 'error': 'Can only delete group chats'})

        # Delete all messages in the group
        db_manager.messages.delete_many({'chat_id': ObjectId(chat_id)})

        # Delete the chat
        result = db_manager.chats.delete_one({'_id': ObjectId(chat_id)})

        # Remove chat reference from all participants
        db_manager.user_profiles.update_many(
            {'chat_ids': chat_id},
            {'$pull': {'chat_ids': chat_id}}
        )

        if result.deleted_count > 0:
            print(f"✅ Group {chat_id} deleted by user {session['user_profile_id']}")
            return jsonify({
                'success': True,
                'message': 'Group deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete group'})

    except Exception as e:
        print(f"❌ Error deleting group: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-group-participants', methods=['POST'])
def get_group_participants():
    """Get group participants for the details modal"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    chat_id = data.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'Missing chat_id'}), 400

    try:
        participants = db_manager.get_group_participants(chat_id)
        return jsonify({
            'success': True,
            'participants': participants
        })
    except Exception as e:
        print(f"❌ Error getting group participants: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/active-senders')
def get_active_message_senders():
    """Get list of senders who have unread message notifications"""
    try:
        user_id = session.get('user_profile_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Not authenticated'})

        senders = db_manager.get_active_message_senders(user_id)
        return jsonify({'success': True, 'senders': senders})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/mark-sender-read', methods=['POST'])
def mark_sender_notifications_read():
    """Mark all notifications from a specific sender as read"""
    try:
        user_id = session.get('user_profile_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Not authenticated'})

        data = request.get_json()
        sender_id = data.get('sender_id')

        count = db_manager.mark_all_message_notifications_as_read(user_id, sender_id)
        return jsonify({'success': True, 'marked_count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications')
def get_notifications():
    """Get user notifications"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    limit = request.args.get('limit', 20, type=int)
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'

    notifications = db_manager.get_user_notifications(session['user_profile_id'], limit, unread_only)
    unread_count = db_manager.get_unread_notifications_count(session['user_profile_id'])

    return jsonify({
        'notifications': notifications,
        'unread_count': unread_count
    })

@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_notification_read():
    """Mark a notification as read"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    notification_id = data.get('notification_id')
    if not notification_id:
        return jsonify({'error': 'Missing notification_id'}), 400

    result = db_manager.mark_notification_as_read(notification_id, session['user_profile_id'])
    return jsonify(result)

@app.route('/api/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    """Mark all notifications as read"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    result = db_manager.mark_all_notifications_as_read(session['user_profile_id'])
    return jsonify(result)

@app.route('/api/notifications/unread-count')
def get_unread_notifications_count():
    """Get unread notifications count"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    count = db_manager.get_unread_notifications_count(session['user_profile_id'])
    return jsonify({'unread_count': count})

@app.route('/api/update-message', methods=['POST'])
def update_message():
    """Update a message"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')
    new_content = data.get('new_content')

    if not message_id or not new_content:
        return jsonify({'error': 'Missing message_id or new_content'}), 400

    result = db_manager.update_message(message_id, session['user_profile_id'], new_content)

    if result['success']:
        # Broadcast the update to all chat participants
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if message:
            socketio.emit('message_updated', {
                'message_id': message_id,
                'chat_id': str(message['chat_id']),
                'new_content': new_content,
                'edited_at': datetime.utcnow().isoformat()
            }, room=str(message['chat_id']))

    return jsonify(result)

@app.route('/api/delete-message', methods=['POST'])
def delete_message():
    """Delete a message"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    result = db_manager.delete_message(message_id, session['user_profile_id'])

    if result['success']:
        # Broadcast the deletion to all chat participants
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if message:
            socketio.emit('message_deleted', {
                'message_id': message_id,
                'chat_id': str(message['chat_id'])
            }, room=str(message['chat_id']))

    return jsonify(result)

@app.route('/api/mark-message-read', methods=['POST'])
def mark_message_read():
    """Mark a message as read"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    result = db_manager.mark_message_as_read(message_id, session['user_profile_id'])
    return jsonify(result)

@app.route('/api/get-unread-count', methods=['POST'])
def get_unread_count():
    """Get unread messages count"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    chat_id = data.get('chat_id') if data else None

    count = db_manager.get_unread_messages_count(session['user_profile_id'], chat_id)
    return jsonify({'unread_count': count})

@socketio.on('send_message')
def handle_send_message(data):
    """Send a message to a chat - with consolidated notifications"""
    chat_id = data.get('chat_id')
    message_content = data.get('message')
    message_type = data.get('type', 'text')

    if not chat_id or not message_content:
        print("❌ Missing chat_id or message content")
        return

    if 'user_profile_id' not in session:
        print("❌ User not authenticated")
        return

    try:
        user_profile_id = session['user_profile_id']
        print(f"📨 Sending message from {user_profile_id} to chat {chat_id}: {message_content}")

        # Create the message in database
        message = db_manager.create_message(
            chat_id=chat_id,
            sender_id=user_profile_id,
            content=message_content,
            message_type=message_type
        )

        if message:
            # Get sender info
            sender_profile = db_manager.get_user_profile(user_profile_id)
            sender_username = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'

            # Prepare message data for broadcasting
            message_data = {
                'message_id': str(message['_id']),
                'chat_id': chat_id,
                'sender_id': user_profile_id,
                'sender_username': sender_username,
                'content': message_content,
                'type': message_type,
                'timestamp': message['timestamp'].isoformat()
            }

            print(f"✅ Broadcasting message: {message_data['message_id']}")

            # Get chat info for notifications
            chat = db_manager.get_chat(chat_id, user_profile_id)
            if chat:
                # Create consolidated notifications for all other participants
                for participant_id in chat['participants']:
                    participant_id_str = str(participant_id)
                    if participant_id_str != user_profile_id:
                        # Use consolidated notification method
                        notification = db_manager.create_consolidated_message_notification(message_data, participant_id_str)

                        # Emit notification update to the specific user
                        emit('notification_updated', {
                            'type': 'new_message',
                            'notification': notification
                        }, room=participant_id_str)

            # Broadcast message to chat room (excluding sender)
            emit('new_message', message_data, room=chat_id, include_self=False)

            # Also send to sender but with a different approach to avoid duplicates
            emit('new_message', message_data, room=request.sid)

        else:
            print("❌ Failed to create message in database")

    except Exception as e:
        print(f"❌ Error sending message: {e}")
        import traceback
        traceback.print_exc()
        emit('message_error', {'error': 'Failed to send message'})

# Add these new routes to app.py
@app.route('/api/get-message/<message_id>')
def get_message(message_id):
    """Get specific message data"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if not message:
            return jsonify({'error': 'Message not found'}), 404

        # Check if user has permission to view this message
        chat = db_manager.chats.find_one({'_id': message['chat_id']})
        if not chat or ObjectId(session['user_profile_id']) not in chat['participants']:
            return jsonify({'error': 'Access denied'}), 403

        message_data = {
            '_id': str(message['_id']),
            'content': message['content'],
            'sender_id': str(message['sender_id']),
            'chat_id': str(message['chat_id']),
            'timestamp': message['timestamp'],
            'is_edited': message.get('is_edited', False),
            'is_deleted': message.get('is_deleted', False)
        }

        return jsonify({'success': True, 'message': message_data})

    except Exception as e:
        print(f"❌ Error getting message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-message-history/<message_id>')
def get_message_history(message_id):
    """Get edit history for a message"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # In a real implementation, you might have a separate collection for message history
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if not message:
            return jsonify({'error': 'Message not found'}), 404

        history = {
            'original_content': message.get('original_content', message['content']),
            'edit_count': message.get('edit_count', 0),
            'last_edited': message.get('edited_at'),
            'edited_by': str(message['sender_id']) if message.get('is_edited') else None
        }

        return jsonify({'success': True, 'history': history})

    except Exception as e:
        print(f"❌ Error getting message history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/create-group-chat', methods=['POST'])
def create_group_chat():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})

    data = request.get_json()
    group_name = data.get('group_name')

    if not group_name:
        return jsonify({'success': False, 'error': 'Group name is required'})

    return jsonify({'success': True, 'message': 'Group chat created'})

@app.route('/start-chat', methods=['POST'])
def start_chat():
    """Start a new chat with a friend"""
    if 'user_profile_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'})

    friend_id = data.get('friend_id')
    if not friend_id:
        return jsonify({'success': False, 'error': 'No friend ID provided'})

    try:
        # Check if users are friends
        current_user_friends = db_manager.get_friends(session['user_profile_id'])
        is_friend = any(friend['_id'] == friend_id for friend in current_user_friends)

        if not is_friend:
            return jsonify({'success': False, 'error': 'You can only start chats with friends'})

        # Create or get existing chat
        chat = db_manager.create_chat([session['user_profile_id'], friend_id], is_group=False)

        if chat:
            return jsonify({
                'success': True,
                'chat_id': chat['_id'],
                'message': 'Chat started successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create chat'})

    except Exception as e:
        print(f"❌ Error starting chat: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Add these new routes to app.py after the existing delete_message route
@app.route('/api/delete-message-for-me', methods=['POST'])
def delete_message_for_me():
    """Delete a message only for the current user"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    result = db_manager.delete_message_for_user(message_id, session['user_profile_id'])

    if result['success']:
        # Notify the user that the message was deleted for them
        emit('message_deleted_for_user', {
            'message_id': message_id,
            'user_id': session['user_profile_id']
        }, room=session['user_profile_id'])

    return jsonify(result)

@app.route('/api/delete-message-for-everyone', methods=['POST'])
def delete_message_for_everyone():
    """Delete a message for all participants"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    result = db_manager.delete_message_for_everyone(message_id, session['user_profile_id'])

    if result['success']:
        # Broadcast the deletion to all chat participants
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if message:
            socketio.emit('message_deleted_for_everyone', {
                'message_id': message_id,
                'chat_id': str(message['chat_id']),
                'deleted_by': session['user_profile_id']
            }, room=str(message['chat_id']))

    return jsonify(result)

@app.route('/learn-more')
def learn_more():
    """Learn more page about HangSpace features"""
    return render_template('service/learn_more.html')

@app.route('/terms')
def terms():
    """Terms of Service page"""
    return render_template('service/terms.html')

@app.route('/privacy')
def privacy():
    """Privacy Policy page"""
    return render_template('service/privacy.html')

@app.route('/admin/cleanup-mock-users')
def cleanup_mock_users():
    """Admin route to clean up mock users"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Check if the method exists
    if hasattr(db_manager, 'cleanup_all_mock_users'):
        removed_count = db_manager.cleanup_all_mock_users()
        return jsonify({
            'success': True,
            'message': f'Removed {removed_count} mock users and their data'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'cleanup_all_mock_users method not available'
        })

@app.route('/api/delete-profile', methods=['POST'])
def delete_profile():
    """Delete user profile and all associated data"""
    if 'user_profile_id' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        user_profile_id = session['user_profile_id']
        user_id = session['user_id']

        print(f"🗑️ Starting profile deletion for user_profile_id: {user_profile_id}, user_id: {user_id}")

        # 1. Remove user from friends lists of all other users
        user_profile = db_manager.user_profiles.find_one({'_id': ObjectId(user_profile_id)})
        if user_profile and 'friends' in user_profile:
            for friend_id in user_profile['friends']:
                db_manager.user_profiles.update_one(
                    {'_id': friend_id},
                    {'$pull': {'friends': ObjectId(user_profile_id)}}
                )
                print(f"✅ Removed user from friend list of {friend_id}")

        # 2. Delete all friend requests involving this user
        friend_requests_deleted = db_manager.friend_requests.delete_many({
            '$or': [
                {'from_user_id': ObjectId(user_profile_id)},
                {'to_user_id': ObjectId(user_profile_id)}
            ]
        })
        print(f"✅ Deleted {friend_requests_deleted.deleted_count} friend requests")

        # 3. Get all chats the user is in
        user_chats = list(db_manager.chats.find({
            'participants': ObjectId(user_profile_id)
        }))
        user_chat_ids = [chat['_id'] for chat in user_chats]

        # 4. For group chats, remove user from participants
        # For individual chats, delete the entire chat
        chats_to_delete = []
        chats_to_update = []

        for chat in user_chats:
            if chat.get('is_group', False):
                # Group chat - remove user from participants
                chats_to_update.append(chat['_id'])
            else:
                # Individual chat - mark for deletion
                chats_to_delete.append(chat['_id'])

        # Update group chats
        if chats_to_update:
            db_manager.chats.update_many(
                {'_id': {'$in': chats_to_update}},
                {'$pull': {'participants': ObjectId(user_profile_id)}}
            )
            print(f"✅ Removed user from {len(chats_to_update)} group chats")

        # Delete individual chats
        if chats_to_delete:
            # Delete messages from these chats
            db_manager.messages.delete_many({
                'chat_id': {'$in': chats_to_delete}
            })
            # Delete the chats themselves
            db_manager.chats.delete_many({
                '_id': {'$in': chats_to_delete}
            })
            print(f"✅ Deleted {len(chats_to_delete)} individual chats and their messages")

        # 5. Delete all messages sent by the user
        user_messages_deleted = db_manager.messages.delete_many({
            'sender_id': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted {user_messages_deleted.deleted_count} messages sent by user")

        # 6. Delete notifications for the user
        notifications_deleted = db_manager.notifications.delete_many({
            'user_id': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted {notifications_deleted.deleted_count} notifications")

        # 7. Delete chat themes for the user
        chat_themes_deleted = db_manager.chat_themes.delete_many({
            'user_profile_id': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted {chat_themes_deleted.deleted_count} chat themes")

        # 8. Delete message edits by the user
        message_edits_deleted = db_manager.message_edits.delete_many({
            'edited_by': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted {message_edits_deleted.deleted_count} message edits")

        # 9. Delete user deleted messages records
        user_deleted_messages_deleted = db_manager.user_deleted_messages.delete_many({
            'user_id': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted {user_deleted_messages_deleted.deleted_count} user deleted messages records")

        # 10. Finally delete the user profile
        profile_deleted = db_manager.user_profiles.delete_one({
            '_id': ObjectId(user_profile_id)
        })
        print(f"✅ Deleted user profile: {profile_deleted.deleted_count} profile")

        # 11. Check if this was the last profile for the user account
        remaining_profiles = db_manager.user_profiles.count_documents({
            'user_id': ObjectId(user_id)
        })

        if remaining_profiles == 0:
            # Delete the user account too
            db_manager.users.delete_one({'_id': ObjectId(user_id)})
            print(f"✅ Deleted user account (no remaining profiles)")

        # Clear the session
        session.clear()

        print("🎉 Profile deletion completed successfully")
        return jsonify({
            'success': True,
            'message': 'Profile deleted successfully'
        })

    except Exception as e:
        print(f"❌ Error deleting profile: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to delete profile: {str(e)}'
        }), 500

@app.route('/api/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    """Subscribe to newsletter"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        # Validate email format
        import re
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400

        # Check if email already exists
        existing_subscriber = db_manager.newsletter_subscriptions.find_one({'email': email})
        if existing_subscriber:
            return jsonify({'success': False, 'error': 'Email already subscribed'}), 400

        # Save to database
        subscriber_data = {
            'email': email,
            'subscribed_at': datetime.utcnow(),
            'active': True,
            'source': 'landing_page'
        }

        result = db_manager.newsletter_subscriptions.insert_one(subscriber_data)

        print(f"✅ New newsletter subscriber: {email}")

        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to newsletter!',
            'subscriber_id': str(result.inserted_id)
        })

    except Exception as e:
        print(f"❌ Error subscribing to newsletter: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/newsletter/unsubscribe', methods=['POST'])
def newsletter_unsubscribe():
    """Unsubscribe from newsletter"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        # Update subscription status
        result = db_manager.newsletter_subscriptions.update_one(
            {'email': email},
            {'$set': {'active': False, 'unsubscribed_at': datetime.utcnow()}}
        )

        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Successfully unsubscribed'})
        else:
            return jsonify({'success': False, 'error': 'Email not found'}), 404

    except Exception as e:
        print(f"❌ Error unsubscribing from newsletter: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    """Handle file uploads with proper error handling and metadata storage"""
    print("📁 File upload endpoint called")

    if 'user_profile_id' not in session:
        print("❌ Unauthorized upload attempt")
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        print("📁 Checking for files in request...")
        print("📁 Request method:", request.method)
        print("📁 Request content type:", request.content_type)
        print("📁 Request files:", dict(request.files))

        if 'file' not in request.files:
            print("❌ No file in request.files")
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        chat_id = request.form.get('chat_id')

        print(f"📁 File info: {file.filename}")
        print(f"📁 File content type: {file.content_type}")
        print(f"📁 Chat ID: {chat_id}")

        if not chat_id:
            print("❌ No chat ID provided")
            return jsonify({'error': 'No chat ID provided'}), 400

        if file.filename == '':
            print("❌ No file selected")
            return jsonify({'error': 'No file selected'}), 400

        # Test basic file operations first
        try:
            file.seek(0, 2)  # Go to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning
            print(f"📁 File size: {file_size} bytes")
        except Exception as e:
            print(f"❌ Error checking file size: {e}")
            return jsonify({'error': 'Invalid file'}), 400

        # Validate file
        if not allowed_file(file.filename):
            print(f"❌ File type not allowed: {file.filename}")
            return jsonify({'error': 'File type not allowed'}), 400

        # Save file to disk
        try:
            print("📁 Starting file save...")
            file_info = save_file(file, session['user_profile_id'])
            print(f"✅ File saved successfully: {file_info}")

        except Exception as e:
            print(f"❌ Error saving file: {e}")
            return jsonify({'error': f'Failed to save file: {str(e)}'}), 500

        # Create message in database with complete file metadata
        try:
            print("📁 Creating message in database...")

            # Complete file metadata with all required fields - CONVERT DATETIME TO STRING
            file_metadata = {
                'original_filename': file_info['original_filename'],
                'saved_filename': file_info['saved_filename'],
                'file_path': file_info['file_path'],
                'file_size': file_info['file_size'],
                'file_extension': file_info['file_extension'],
                'file_category': file_info['file_category'],
                'uploaded_by': session['user_profile_id'],
                'uploaded_at': datetime.utcnow().isoformat(),  # Convert to ISO string
                'download_url': f"/api/download-file/{session['user_profile_id']}/{file_info['saved_filename']}",
                'preview_url': f"/api/preview-file/{session['user_profile_id']}/{file_info['saved_filename']}" if file_info['file_category'] == 'images' else None,
                'file_type': get_file_type(file_info['file_extension'])
            }

            print(f"📁 File metadata prepared: {file_metadata}")

            # Create the message in database
            message = db_manager.create_message(
                chat_id=chat_id,
                sender_id=session['user_profile_id'],
                content=f"📎 {file_info['original_filename']}",
                message_type='file',
                file_metadata=file_metadata
            )

            if message:
                print(f"✅ Message created: {message['_id']}")

                # Get sender info
                sender_profile = db_manager.get_user_profile(session['user_profile_id'])
                sender_username = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'

                # Prepare message data for broadcasting
                message_data = {
                    'message_id': str(message['_id']),
                    'chat_id': chat_id,
                    'sender_id': session['user_profile_id'],
                    'sender_username': sender_username,
                    'content': f"📎 {file_info['original_filename']}",
                    'type': 'file',
                    'timestamp': message['timestamp'].isoformat(),  # Convert to ISO string
                    'file_metadata': file_metadata
                }

                print("📁 Broadcasting message via socket...")

                # Get chat info for notifications
                chat = db_manager.get_chat(chat_id, session['user_profile_id'])
                if chat:
                    # Create consolidated notifications for all other participants
                    for participant_id in chat['participants']:
                        participant_id_str = str(participant_id)
                        if participant_id_str != session['user_profile_id']:
                            # Use consolidated notification method
                            notification = db_manager.create_consolidated_message_notification(message_data, participant_id_str)

                            # Emit notification update to the specific user
                            socketio.emit('notification_updated', {
                                'type': 'new_message',
                                'notification': notification
                            }, room=participant_id_str)

                # Broadcast message to chat room
                socketio.emit('new_message', message_data, room=chat_id)

                print(f"✅ File uploaded and message sent successfully: {file_info['original_filename']}")

                return jsonify({
                    'success': True,
                    'message': 'File uploaded successfully',
                    'file_info': {
                        'original_filename': file_info['original_filename'],
                        'file_size': file_info['file_size'],
                        'file_category': file_info['file_category'],
                        'message_id': str(message['_id'])
                    }
                })
            else:
                # Clean up file if message creation failed
                if os.path.exists(file_info['file_path']):
                    os.remove(file_info['file_path'])
                print("❌ Failed to create message in database")
                return jsonify({'error': 'Failed to create message in database'}), 500

        except Exception as e:
            # Clean up file if message creation failed
            if 'file_info' in locals() and os.path.exists(file_info['file_path']):
                os.remove(file_info['file_path'])
            print(f"❌ Error creating message: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Failed to create message: ' + str(e)}), 500

    except Exception as e:
        print(f"❌ Error in file upload: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error: ' + str(e)}), 500

def get_file_type(extension):
    """Get file type for better categorization"""
    image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    video_extensions = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'}
    audio_extensions = {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'}

    if extension in image_extensions:
        return 'image'
    elif extension in video_extensions:
        return 'video'
    elif extension in audio_extensions:
        return 'audio'
    else:
        return 'document'

@app.route('/api/download-file/<user_id>/<filename>')
def download_file(user_id, filename):
    """Download a file"""
    try:
        # Create the file path
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], user_id)
        file_path = os.path.join(user_upload_dir, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        # Get original filename from database if available
        original_filename = filename
        message = db_manager.messages.find_one({
            'message_type': 'file',
            'file_metadata.saved_filename': filename
        })

        if message and message.get('file_metadata', {}).get('original_filename'):
            original_filename = message['file_metadata']['original_filename']

        return send_file(
            file_path,
            as_attachment=True,
            download_name=original_filename,
            mimetype='application/octet-stream'
        )

    except Exception as e:
        print(f"❌ Error downloading file: {e}")
        return jsonify({'error': 'File download failed'}), 500

@app.route('/api/get-file-message/<message_id>')
def get_file_message(message_id):
    """Get file message data for download/forward"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if not message:
            return jsonify({'error': 'Message not found'}), 404

        # Check if user has permission to access this file
        chat = db_manager.chats.find_one({'_id': message['chat_id']})
        if not chat or ObjectId(session['user_profile_id']) not in chat['participants']:
            return jsonify({'error': 'Access denied'}), 403

        # Convert ObjectId to string for JSON serialization
        message_data = {
            '_id': str(message['_id']),
            'sender_id': str(message['sender_id']),
            'chat_id': str(message['chat_id']),
            'content': message['content'],
            'type': message.get('message_type', 'text'),
            'timestamp': message['timestamp'],
            'file_metadata': message.get('file_metadata', {})
        }

        return jsonify({'success': True, 'message': message_data})

    except Exception as e:
        print(f"❌ Error getting file message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview-file/<user_id>/<filename>')
def preview_file(user_id, filename):
    """Serve file for preview (images only)"""
    try:
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], user_id)
        file_path = os.path.join(user_upload_dir, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        # Check if it's an image
        image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext in image_extensions:
            return send_file(file_path, mimetype=f'image/{file_ext}')
        else:
            return jsonify({'error': 'File type not supported for preview'}), 400

    except Exception as e:
        print(f"❌ Error previewing file: {e}")
        return jsonify({'error': 'File preview failed'}), 500

# Add this route for forwarding files
@app.route('/api/forward-file', methods=['POST'])
def forward_file():
    """Forward a file to multiple friends"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        file_id = data.get('file_id')
        friend_ids = data.get('friend_ids', [])
        message_text = data.get('message', '')

        if not file_id or not friend_ids:
            return jsonify({'error': 'Missing file_id or friend_ids'}), 400

        # Get file metadata from the original message
        original_message = db_manager.messages.find_one({'_id': ObjectId(file_id)})
        if not original_message or original_message.get('message_type') != 'file':
            return jsonify({'error': 'File not found'}), 404

        file_metadata = original_message.get('file_metadata', {})

        results = []
        for friend_id in friend_ids:
            try:
                # Create or get chat with friend
                chat = db_manager.create_chat([session['user_profile_id'], friend_id], is_group=False)

                if chat:
                    # Create forwarded message
                    forwarded_content = f"Forwarded: {file_metadata.get('original_filename', 'File')}"
                    if message_text:
                        forwarded_content = f"{message_text}\n\n{forwarded_content}"

                    message = db_manager.create_message(
                        chat_id=chat['_id'],
                        sender_id=session['user_profile_id'],
                        content=forwarded_content,
                        message_type='file',
                        file_metadata=file_metadata
                    )

                    results.append({'friend_id': friend_id, 'success': True})
                else:
                    results.append({'friend_id': friend_id, 'success': False, 'error': 'Failed to create chat'})

            except Exception as e:
                results.append({'friend_id': friend_id, 'success': False, 'error': str(e)})

        return jsonify({
            'success': True,
            'results': results,
            'message': f'File forwarded to {len([r for r in results if r["success"]])} friends'
        })

    except Exception as e:
        print(f"❌ Error forwarding file: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cleanup-orphaned-files', methods=['POST'])
def cleanup_orphaned_files():
    """Clean up files that are no longer referenced in messages"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # Get all file messages
        file_messages = db_manager.messages.find({'message_type': 'file'})
        referenced_files = set()

        for message in file_messages:
            file_metadata = message.get('file_metadata', {})
            file_path = file_metadata.get('file_path')
            if file_path and os.path.exists(file_path):
                referenced_files.add(file_path)

        # Find all files in upload directory
        all_files = []
        for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER']):
            for file in files:
                file_path = os.path.join(root, file)
                all_files.append(file_path)

        # Find orphaned files
        orphaned_files = [f for f in all_files if f not in referenced_files]

        # Delete orphaned files
        deleted_count = 0
        for file_path in orphaned_files:
            try:
                os.remove(file_path)
                deleted_count += 1
                print(f"🗑️ Deleted orphaned file: {file_path}")
            except Exception as e:
                print(f"❌ Error deleting file {file_path}: {e}")

        return jsonify({
            'success': True,
            'message': f'Cleaned up {deleted_count} orphaned files',
            'deleted_count': deleted_count
        })

    except Exception as e:
        print(f"❌ Error cleaning up files: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/delete-message-for-user', methods=['POST'])
def delete_message_for_user():
    """Delete a message only for the current user"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    try:
        result = db_manager.delete_message_for_user(message_id, session['user_profile_id'])

        if result['success']:
            # Notify the user that the message was deleted for them via socket
            socketio.emit('message_deleted_for_user', {
                'message_id': message_id,
                'user_id': session['user_profile_id']
            }, room=session['user_profile_id'])

            print(f"✅ Message {message_id} deleted for user {session['user_profile_id']}")
            return jsonify({'success': True, 'message': 'Message deleted for you'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to delete message')})

    except Exception as e:
        print(f"❌ Error in delete_message_for_user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-reaction', methods=['POST'])
def add_reaction():
    """Add reaction to a message"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        message_id = data.get('message_id')
        emoji = data.get('emoji')

        if not message_id or not emoji:
            return jsonify({'error': 'Missing message_id or emoji'}), 400

        result = db_manager.add_reaction(message_id, session['user_profile_id'], emoji)

        if result['success']:
            # Broadcast reaction to chat
            message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
            if message:
                socketio.emit('reaction_added', {
                    'message_id': message_id,
                    'chat_id': str(message['chat_id']),
                    'emoji': emoji,
                    'user_id': session['user_profile_id'],
                    'reactions': result['reactions']
                }, room=str(message['chat_id']))

        return jsonify(result)

    except Exception as e:
        print(f"❌ Error adding reaction: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/remove-reaction', methods=['POST'])
def remove_reaction():
    """Remove reaction from a message"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        message_id = data.get('message_id')
        emoji = data.get('emoji')

        if not message_id or not emoji:
            return jsonify({'error': 'Missing message_id or emoji'}), 400

        result = db_manager.remove_reaction(message_id, session['user_profile_id'], emoji)

        if result['success']:
            # Broadcast reaction removal to chat
            message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
            if message:
                socketio.emit('reaction_removed', {
                    'message_id': message_id,
                    'chat_id': str(message['chat_id']),
                    'emoji': emoji,
                    'user_id': session['user_profile_id'],
                    'reactions': result['reactions']
                }, room=str(message['chat_id']))

        return jsonify(result)

    except Exception as e:
        print(f"❌ Error removing reaction: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@socketio.on('reaction_added')
def handle_reaction_added(data):
    """Handle reaction added event"""
    message_id = data.get('message_id')
    emoji = data.get('emoji')
    user_id = data.get('user_id')

    if message_id and emoji and user_id:
        # Broadcast to all chat participants except sender
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if message:
            emit('reaction_updated', {
                'message_id': message_id,
                'emoji': emoji,
                'user_id': user_id,
                'action': 'added',
                'reactions': data.get('reactions', [])
            }, room=str(message['chat_id']), include_self=False)

@socketio.on('reaction_removed')
def handle_reaction_removed(data):
    """Handle reaction removed event"""
    message_id = data.get('message_id')
    emoji = data.get('emoji')
    user_id = data.get('user_id')

    if message_id and emoji and user_id:
        # Broadcast to all chat participants except sender
        message = db_manager.messages.find_one({'_id': ObjectId(message_id)})
        if message:
            emit('reaction_updated', {
                'message_id': message_id,
                'emoji': emoji,
                'user_id': user_id,
                'action': 'removed',
                'reactions': data.get('reactions', [])
            }, room=str(message['chat_id']), include_self=False)

@app.route('/admin-debug-setup')
def admin_debug_setup():
    """Debug the admin setup"""
    debug_info = {
        'flask_admin_views': [],
        'custom_admin_routes': [],
        'session_info': {},
        'user_admin_status': False
    }

    # Check Flask-Admin views
    if hasattr(admin, '_views'):
        for view in admin._views:
            debug_info['flask_admin_views'].append({
                'name': getattr(view, 'name', 'Unknown'),
                'endpoint': getattr(view, 'endpoint', 'Unknown'),
                'url': f'/admin-panel/{getattr(view, "endpoint", "unknown")}'
            })

    # Check if user is admin
    if 'user_profile_id' in session:
        user_profile = db_manager.get_user_profile(session['user_profile_id'])
        debug_info['session_info'] = {
            'username': user_profile.get('username') if user_profile else None,
            'is_admin': user_profile.get('is_admin', False) if user_profile else False,
            'profile_id': session['user_profile_id']
        }
        debug_info['user_admin_status'] = user_profile.get('is_admin', False) if user_profile else False

    return jsonify(debug_info)

@app.route('/admin/debug')
def admin_debug():
    """Debug admin access issues"""
    debug_info = {
        'session': dict(session),
        'user_profile_id_in_session': 'user_profile_id' in session,
        'collections_exist': {},
        'admin_views_configured': len(admin._views) if hasattr(admin, '_views') else 0
    }

    if 'user_profile_id' in session:
        user_profile = db_manager.get_user_profile(session['user_profile_id'])
        debug_info['user_profile'] = {
            'username': user_profile.get('username') if user_profile else None,
            'is_admin': user_profile.get('is_admin', False) if user_profile else False
        }

    # Check if collections exist
    collections_to_check = ['user_profiles', 'chats', 'messages', 'friend_requests', 'notifications']
    for coll_name in collections_to_check:
        try:
            collection = getattr(db_manager, coll_name, None)
            if collection:
                count = collection.count_documents({})
                debug_info['collections_exist'][coll_name] = f"Exists ({count} documents)"
            else:
                debug_info['collections_exist'][coll_name] = "Collection not found"
        except Exception as e:
            debug_info['collections_exist'][coll_name] = f"Error: {str(e)}"

    return jsonify(debug_info)

@app.route('/admin/grant-access')
def admin_grant_access():
    """Grant admin access to current user"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    try:
        result = db_manager.user_profiles.update_one(
            {'_id': ObjectId(session['user_profile_id'])},
            {'$set': {'is_admin': True}}
        )

        user_profile = db_manager.get_user_profile(session['user_profile_id'])

        return f"""
        <h1>Admin Access Granted! ✅</h1>
        <p>User: {user_profile['username']} is now an administrator.</p>
        <div class="alert alert-success">
            <strong>Next Steps:</strong>
            <ul>
                <li><a href="/admin/dashboard" class="btn btn-success">Go to Admin Dashboard</a></li>
                <li><a href="/admin-panel/" class="btn btn-primary">Open Flask-Admin Panel</a></li>
            </ul>
        </div>
        """
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

@app.route('/error/404')
def show_404():
    """Direct route to view 404 page (for testing)"""
    return render_template('error/404.html'), 404

@app.route('/error/500')
def show_500():
    """Direct route to view 500 page (for testing)"""
    return render_template('error/500.html'), 500

@app.route('/api/search-users', methods=['GET', 'POST'])
def search_users_api():
    """Search for users by username or email - accepts both GET and POST"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    # Handle both GET and POST requests
    if request.method == 'GET':
        query = request.args.get('query', '').strip()
    else:  # POST
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        query = data.get('query', '').strip()

    print(f"🔍 Search query received: '{query}' from user {session['user_profile_id']}")

    if not query:
        return jsonify({'users': []})

    results = db_manager.search_users(query, session['user_profile_id'])
    print(f"📊 Search results: {len(results)} users found")

    return jsonify({'users': results})

@app.route('/search')
def search_users():
    """Search users page"""
    if 'user_profile_id' not in session:
        return redirect(url_for('login'))

    return render_template('search.html')

@app.route('/api/upload-profile-pic', methods=['POST'])
def upload_profile_pic():
    """Upload and set profile picture"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        if 'profile_pic' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['profile_pic']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate file is an image
        if not file.content_type.startswith('image/'):
            return jsonify({'error': 'Only image files are allowed'}), 400

        # Validate file size (max 5MB)
        file.seek(0, 2)  # Seek to end to get file size
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'error': 'File size must be less than 5MB'}), 400

        # Create profile pictures directory
        profile_pics_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics')
        os.makedirs(profile_pics_dir, exist_ok=True)

        # Generate unique filename
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        unique_filename = f"{session['user_profile_id']}_{uuid.uuid4().hex}.{file_ext}"
        file_path = os.path.join(profile_pics_dir, unique_filename)

        # Save the file
        file.save(file_path)

        # Update user profile with avatar URL
        avatar_url = f"/api/profile-pic/{unique_filename}"
        result = db_manager.update_user_profile(session['user_profile_id'], {'avatar_url': avatar_url})

        if result['success']:
            # Update session
            session['avatar_url'] = avatar_url

            return jsonify({
                'success': True,
                'message': 'Profile picture updated successfully',
                'avatar_url': avatar_url
            })
        else:
            # Clean up file if update failed
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': 'Failed to update profile'}), 500

    except Exception as e:
        print(f"❌ Error uploading profile picture: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/profile-pic/<filename>')
def get_profile_pic(filename):
    """Serve profile pictures"""
    try:
        profile_pics_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics')
        return send_from_directory(profile_pics_dir, filename)
    except Exception as e:
        print(f"❌ Error serving profile picture: {e}")
        return jsonify({'error': 'Profile picture not found'}), 404

@app.route('/api/remove-profile-pic', methods=['POST'])
def remove_profile_pic():
    """Remove profile picture and revert to default"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # Get current user profile
        user_profile = db_manager.get_user_profile(session['user_profile_id'])
        current_avatar_url = user_profile.get('avatar_url') if user_profile else None

        # Remove avatar URL from profile
        result = db_manager.update_user_profile(session['user_profile_id'], {'avatar_url': None})

        if result['success']:
            # Remove from session
            session.pop('avatar_url', None)

            # Delete the physical file if it exists
            if current_avatar_url and current_avatar_url.startswith('/api/profile-pic/'):
                filename = current_avatar_url.split('/')[-1]
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics', filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

            return jsonify({
                'success': True,
                'message': 'Profile picture removed successfully'
            })
        else:
            return jsonify({'error': 'Failed to remove profile picture'}), 500

    except Exception as e:
        print(f"❌ Error removing profile picture: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/upload-debug')
def upload_debug():
    """Debug upload configuration"""
    debug_info = {
        'upload_folder': app.config['UPLOAD_FOLDER'],
        'upload_folder_exists': os.path.exists(app.config['UPLOAD_FOLDER']),
        'max_content_length': app.config['MAX_CONTENT_LENGTH'],
        'allowed_extensions': {k: list(v) for k, v in app.config['ALLOWED_EXTENSIONS'].items()},
        'temp_dir_exists': os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'temp')),
        'profile_pics_dir_exists': os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pics')),
        'upload_folder_permissions': oct(os.stat(app.config['UPLOAD_FOLDER']).st_mode)[-3:] if os.path.exists(app.config['UPLOAD_FOLDER']) else 'N/A'
    }

    # Test directory creation
    try:
        test_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'test_debug')
        os.makedirs(test_dir, exist_ok=True)
        debug_info['can_create_dirs'] = True
        # Clean up
        import shutil
        shutil.rmtree(test_dir)
    except Exception as e:
        debug_info['can_create_dirs'] = False
        debug_info['create_dir_error'] = str(e)

    return jsonify(debug_info)

@app.route('/api/friends')
def get_friends_api():
    """API endpoint to get friends list"""
    if 'user_profile_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    friends = db_manager.get_friends(session['user_profile_id'])
    return jsonify({'friends': friends})

@app.route('/<path:path>')
def catch_all(path):
    """Catch all undefined routes and show 404 page"""
    return render_template('error/404.html'), 404

@app.errorhandler(404)
def not_found(error):
    app.logger.error(f"404 error: {error}")
    return render_template('error/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return render_template('error/500.html'), 500

# Add this to your app.py temporarily to test the connection
@app.route('/debug/db-status')
def debug_db_status():
    try:
        # Test database connection
        db_status = db_manager.db.command('ping')
        collections = db_manager.db.list_collection_names()

        return jsonify({
            'database_connection': '✅ Connected' if db_status.get('ok') else '❌ Failed',
            'collections': collections,
            'users_count': db_manager.users.count_documents({}),
            'user_profiles_count': db_manager.user_profiles.count_documents({})
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with more details"""
    app.logger.error(f"500 error: {error}")
    app.logger.error(f"Traceback: {traceback.format_exc()}")
    return render_template('error/500.html'), 500

# Add this to monitor file operations
def safe_file_operation(operation, *args, **kwargs):
    """Safely perform file operations with error handling"""
    try:
        return operation(*args, **kwargs)
    except OSError as e:
        print(f"❌ File system error: {e}")
        # Check disk space
        if not check_disk_space():
            print("💥 Critical: Out of disk space!")
        raise e
    except Exception as e:
        print(f"❌ File operation error: {e}")
        raise e

def check_disk_space():
    """Check available disk space"""
    try:
        disk = psutil.disk_usage('/')
        free_gb = disk.free / (1024**3)
        print(f"💾 Disk space: {free_gb:.2f} GB free")
        return free_gb > 1.0  # Warn if less than 1GB free
    except:
        return True  # Skip check if psutil not available

def cleanup_temp_files():
    """Clean up temporary files"""
    try:
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            print("✅ Cleaned up temp files")
    except Exception as e:
        print(f"⚠️ Could not clean temp files: {e}")

def startup_checks():
    """Perform startup checks and initialization"""
    print("🔍 Running startup checks...")

    # Check disk space
    if not check_disk_space():
        print("⚠️ Warning: Low disk space!")

    # Ensure upload directories exist
    ensure_upload_directories()

    # Clean up temp files
    cleanup_temp_files()

    # Test database connection
    try:
        db_status = db_manager.db.command('ping')
        print("✅ Database connection: OK")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

    # Check if collections exist
    collections_to_check = ['user_profiles', 'chats', 'messages', 'friend_requests', 'notifications']
    for coll_name in collections_to_check:
        try:
            collection = getattr(db_manager, coll_name, None)
            if collection:
                count = collection.count_documents({})
                print(f"✅ {coll_name}: {count} documents")
            else:
                print(f"❌ {coll_name}: Collection not found")
        except Exception as e:
            print(f"❌ {coll_name}: Error - {str(e)}")

    print("🎉 Startup checks completed!")

if __name__ == '__main__':
    try:
        print("🚀 Starting HangSpace server with enhanced error handling...")

        # Run startup checks
        startup_checks()

        # Start the server
        socketio.run(
            app,
            debug=True,
            host='0.0.0.0',
            port=5000,
            allow_unsafe_werkzeug=True,
            log_output=True
        )
    except Exception as e:
        print(f"💥 Failed to start server: {e}")
        import traceback
        traceback.print_exc()
