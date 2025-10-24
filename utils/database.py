from typing import Self
from pkg_resources import FileMetadata
from pymongo import MongoClient, ReturnDocument
from bson import ObjectId
from datetime import datetime, timedelta
import uuid
import re
import os
from config import Config

class DatabaseManager:
    def __init__(self):
        try:
            self.client = MongoClient(Config.MONGODB_URI)
            self.db = self.client.hangspace
            
            # Collections - with existence checks
            self.users = self.db.users
            self.user_profiles = self.db.user_profiles
            self.friend_requests = self.db.friend_requests
            self.chats = self.db.chats
            self.messages = self.db.messages
            self.notifications = self.db.notifications
            self.chat_themes = self.db.chat_themes
            self.message_edits = self.db.message_edits
            self.user_deleted_messages = self.db.user_deleted_messages
            
            
            # Initialize missing collections
            self.files = self.db.files
            self.message_reactions = self.db.message_reactions
            self.newsletter_subscriptions = self.db.newsletter_subscriptions  
            
            # Ensure collections exist by inserting a dummy document if empty
            self._ensure_collections_exist()
            
            # Create indexes
            self._create_indexes()
            print("✅ Database connected successfully")
            
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            raise

    def _ensure_collections_exist(self):
        """Ensure all collections exist by inserting empty documents if needed"""
        collections = [
            self.user_profiles, self.chats, self.messages,
            self.friend_requests, self.notifications, self.files,
            self.message_reactions, self.newsletter_subscriptions
        ]
        
        for collection in collections:
            try:
                if collection.count_documents({}) == 0:
                    # Insert and immediately delete a document to create collection
                    temp_id = collection.insert_one({'__init__': True})
                    collection.delete_one({'_id': temp_id.inserted_id})
                    print(f"✅ Created collection: {collection.name}")
            except Exception as e:
                print(f"⚠️ Could not ensure collection {collection.name}: {e}")
        
        # Clean up demo users on initialization
        self.cleanup_demo_users()

    def _create_indexes(self):
        """Create database indexes for performance"""
        try:
            self.user_profiles.create_index([('username', 1)], unique=True)
            self.user_profiles.create_index([('user_id', 1)])
            self.user_profiles.create_index([('username', 'text'), ('display_name', 'text')])
            self.friend_requests.create_index([('from_user_id', 1), ('to_user_id', 1)])
            self.friend_requests.create_index([('to_user_id', 1), ('status', 1)])
            self.messages.create_index([('chat_id', 1), ('timestamp', -1)])
            
            # Skip duplicate index creation to avoid errors
            try:
                self.messages.create_index([
                    ('chat_id', 1), 
                    ('sender_id', 1), 
                    ('content', 1), 
                    ('timestamp', 1)
                ], name='duplicate_prevention')
            except Exception as e:
                print(f"⚠️ Duplicate prevention index already exists: {e}")
                
            self.chats.create_index([('participants', 1)])
            self.chats.create_index([('last_message_at', -1)])
            
            # Index for duplicate chat prevention
            try:
                self.chats.create_index([
                    ('participants', 1),
                    ('is_group', 1)
                ], name='unique_individual_chats')
            except Exception as e:
                print(f"⚠️ Unique individual chats index already exists: {e}")
            
            self.chat_themes.create_index([
            ('chat_id', 1), 
            ('user_id', 1)
            ], unique=True)
            
            # Index for user status queries
            self.user_profiles.create_index([('status', 1)])
            self.user_profiles.create_index([('last_seen', -1)])
            
            # New indexes for message features
            self.messages.create_index([('read_by', 1)])
            self.messages.create_index([('is_deleted', 1)])
            self.messages.create_index([('is_edited', 1)])
            self.messages.create_index([('edit_count', 1)])
            self.notifications.create_index([('user_id', 1), ('is_read', 1)])
            self.notifications.create_index([('created_at', -1)])
            
            # Indexes for message edit history
            self.message_edits.create_index([('message_id', 1), ('edit_number', 1)])
            self.message_edits.create_index([('message_id', 1), ('edited_at', -1)])
            
            # Index for user deleted messages
            self.user_deleted_messages.create_index([('user_id', 1), ('message_id', 1)], unique=True)
            self.user_deleted_messages.create_index([('message_id', 1)])
            self.user_deleted_messages.create_index([('deleted_at', -1)])
            
            # New indexes for files and reactions
            self.files.create_index([('uploaded_by', 1)])
            self.files.create_index([('chat_id', 1)])
            self.files.create_index([('uploaded_at', -1)])
            self.files.create_index([('file_type', 1)])
            
            self.message_reactions.create_index([('message_id', 1), ('user_id', 1)], unique=True)
            self.message_reactions.create_index([('message_id', 1)])
            self.message_reactions.create_index([('user_id', 1)])
            self.message_reactions.create_index([('emoji', 1)])
            
            # Index for consolidated notifications
            self.notifications.create_index([('user_id', 1), ('type', 1), ('data.sender_id', 1), ('is_read', 1)])
            self.notifications.create_index([('user_id', 1), ('type', 1), ('is_read', 1)])
            
            print("✅ Database indexes created")
        except Exception as e:
            print(f"⚠️ Index creation error: {e}")

    def cleanup_demo_users(self):
        """Remove demo users and keep only real created account users"""
        try:
            print("🧹 Cleaning up demo users...")
            
            # Find demo users (users without Google OAuth data)
            demo_users = list(self.users.find({'google_id': {'$exists': False}}))
            
            if not demo_users:
                print("✅ No demo users found")
                return
            
            demo_user_ids = [user['_id'] for user in demo_users]
            
            # Remove demo user profiles
            demo_profiles = list(self.user_profiles.find({'user_id': {'$in': demo_user_ids}}))
            demo_profile_ids = [profile['_id'] for profile in demo_profiles]
            
            # Delete related data
            # 1. Remove friend requests involving demo users
            self.friend_requests.delete_many({
                '$or': [
                    {'from_user_id': {'$in': demo_profile_ids}},
                    {'to_user_id': {'$in': demo_profile_ids}}
                ]
            })
            
            # 2. Find chats with demo users
            demo_chats = list(self.chats.find({
                'participants': {'$in': demo_profile_ids}
            }))
            demo_chat_ids = [chat['_id'] for chat in demo_chats]
            
            # 3. Remove messages from demo chats
            self.messages.delete_many({'chat_id': {'$in': demo_chat_ids}})
            
            # 4. Remove the chats themselves
            self.chats.delete_many({'_id': {'$in': demo_chat_ids}})
            
            # 5. Remove notifications for demo users
            self.notifications.delete_many({'user_id': {'$in': demo_profile_ids}})
            
            # 6. Remove chat themes for demo users
            self.chat_themes.delete_many({'user_profile_id': {'$in': demo_profile_ids}})
            
            # 7. Remove message edits by demo users
            self.message_edits.delete_many({'edited_by': {'$in': demo_profile_ids}})
            
            # 8. Remove user deleted messages for demo users
            self.user_deleted_messages.delete_many({'user_id': {'$in': demo_profile_ids}})
            
            # 9. Remove files uploaded by demo users
            self.files.delete_many({'uploaded_by': {'$in': demo_profile_ids}})
            
            # 10. Remove reactions by demo users
            self.message_reactions.delete_many({'user_id': {'$in': demo_profile_ids}})
            
            # 11. Remove demo user profiles
            self.user_profiles.delete_many({'_id': {'$in': demo_profile_ids}})
            
            # 12. Finally remove demo users
            self.users.delete_many({'_id': {'$in': demo_user_ids}})
            
            print(f"✅ Removed {len(demo_users)} demo users and all their associated data")
            
        except Exception as e:
            print(f"❌ Error cleaning up demo users: {e}")

    # NEW FILE UPLOAD METHODS
    def upload_file(self, file, chat_id, user_id):
        """Handle file upload and return file metadata"""
        try:
            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)
            
            # Save file
            file.save(file_path)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Determine file type
            if file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                file_type = 'image'
            elif file_extension.lower() in ['.mp4', '.avi', '.mov', '.wmv']:
                file_type = 'video'
            elif file_extension.lower() in ['.mp3', '.wav', '.ogg', '.m4a']:
                file_type = 'audio'
            else:
                file_type = 'document'
            
            # Create file metadata
            file_metadata = {
                '_id': ObjectId(),
                'original_filename': file.filename,
                'stored_filename': unique_filename,
                'file_path': file_path,
                'file_size': file_size,
                'file_type': file_type,
                'uploaded_by': ObjectId(user_id),
                'chat_id': ObjectId(chat_id),
                'uploaded_at': datetime.utcnow(),
                'url': f'/api/download-file/{unique_filename}'
            }
            
            # Store metadata in database
            self.files.insert_one(file_metadata)
            
            return file_metadata
            
        except Exception as e:
            print(f"❌ Error uploading file: {e}")
            return None

    def get_file_metadata(self, file_id):
        """Get file metadata by ID"""
        try:
            file_doc = self.files.find_one({'_id': ObjectId(file_id)})
            if file_doc:
                file_doc['_id'] = str(file_doc['_id'])
                file_doc['uploaded_by'] = str(file_doc['uploaded_by'])
                if file_doc.get('chat_id'):
                    file_doc['chat_id'] = str(file_doc['chat_id'])
                if file_doc.get('forwarded_from'):
                    file_doc['forwarded_from'] = str(file_doc['forwarded_from'])
            return file_doc
        except Exception as e:
            print(f"❌ Error getting file metadata: {e}")
            return None

    def serve_file(self, file_id):
        """Serve file for download"""
        try:
            file_metadata = self.get_file_metadata(file_id)
            if not file_metadata:
                return None
            
            from flask import send_file
            return send_file(
                file_metadata['file_path'],
                as_attachment=True,
                download_name=file_metadata['original_filename']
            )
        except Exception as e:
            print(f"❌ Error serving file: {e}")
            return None

    def save_file_metadata(self, file_data):
        """Save file metadata to database"""
        try:
            file_doc = {
                'filename': file_data['filename'],
                'original_filename': file_data['original_filename'],
                'file_size': file_data['file_size'],
                'file_type': file_data['file_type'],
                'mime_type': file_data['mime_type'],
                'uploaded_by': ObjectId(file_data['uploaded_by']),
                'chat_id': ObjectId(file_data['chat_id']) if file_data.get('chat_id') else None,
                'uploaded_at': datetime.utcnow(),
                'url': file_data['url'],
                'thumbnail_url': file_data.get('thumbnail_url'),
                'is_forwarded': file_data.get('is_forwarded', False),
                'forwarded_from': ObjectId(file_data['forwarded_from']) if file_data.get('forwarded_from') else None
            }
            
            result = self.files.insert_one(file_doc)
            file_doc['_id'] = str(result.inserted_id)
            file_doc['uploaded_by'] = file_data['uploaded_by']
            if file_doc.get('chat_id'):
                file_doc['chat_id'] = file_data['chat_id']
            if file_doc.get('forwarded_from'):
                file_doc['forwarded_from'] = file_data['forwarded_from']
            return file_doc
            
        except Exception as e:
            print(f"❌ Error saving file metadata: {e}")
            return None

    def add_message_reaction(self, message_id, user_id, emoji):
        """Add or update reaction to a message"""
        try:
            # Remove existing reaction from same user
            self.message_reactions.delete_one({
                'message_id': ObjectId(message_id),
                'user_id': ObjectId(user_id)
            })
            
            # Add new reaction
            reaction_doc = {
                'message_id': ObjectId(message_id),
                'user_id': ObjectId(user_id),
                'emoji': emoji,
                'reacted_at': datetime.utcnow()
            }
            
            result = self.message_reactions.insert_one(reaction_doc)
            return {'success': True, 'reaction_id': str(result.inserted_id)}
            
        except Exception as e:
            print(f"❌ Error adding reaction: {e}")
            return {'success': False, 'error': str(e)}

    def remove_message_reaction(self, message_id, user_id):
        """Remove reaction from a message"""
        try:
            result = self.message_reactions.delete_one({
                'message_id': ObjectId(message_id),
                'user_id': ObjectId(user_id)
            })
            
            return {'success': True, 'deleted_count': result.deleted_count}
            
        except Exception as e:
            print(f"❌ Error removing reaction: {e}")
            return {'success': False, 'error': str(e)}

    def get_message_reactions(self, message_id):
        """Get all reactions for a message"""
        try:
            reactions = self.message_reactions.aggregate([
                {
                    '$match': {
                        'message_id': ObjectId(message_id)
                    }
                },
                {
                    '$lookup': {
                        'from': 'user_profiles',
                        'localField': 'user_id',
                        'foreignField': '_id',
                        'as': 'user'
                    }
                },
                {
                    '$unwind': '$user'
                },
                {
                    '$sort': {'reacted_at': 1}
                }
            ])
            
            result = []
            for reaction in reactions:
                result.append({
                    'reaction_id': str(reaction['_id']),
                    'emoji': reaction['emoji'],
                    'user_id': str(reaction['user_id']),
                    'username': reaction['user']['username'],
                    'display_name': reaction['user'].get('display_name', reaction['user']['username']),
                    'reacted_at': reaction['reacted_at']
                })
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting message reactions: {e}")
            return []

    def get_user_reaction(self, message_id, user_id):
        """Get user's reaction to a message"""
        try:
            reaction = self.message_reactions.find_one({
                'message_id': ObjectId(message_id),
                'user_id': ObjectId(user_id)
            })
            
            if reaction:
                return {
                    'emoji': reaction['emoji'],
                    'reacted_at': reaction['reacted_at']
                }
            return None
            
        except Exception as e:
            print(f"❌ Error getting user reaction: {e}")
            return None

    def get_files_by_chat(self, chat_id, limit=50):
        """Get files shared in a chat"""
        try:
            files = self.files.find({
                'chat_id': ObjectId(chat_id)
            }).sort('uploaded_at', -1).limit(limit)
            
            result = []
            for file_doc in files:
                file_doc['_id'] = str(file_doc['_id'])
                file_doc['uploaded_by'] = str(file_doc['uploaded_by'])
                file_doc['chat_id'] = str(file_doc['chat_id'])
                if file_doc.get('forwarded_from'):
                    file_doc['forwarded_from'] = str(file_doc['forwarded_from'])
                result.append(file_doc)
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting chat files: {e}")
            return []

    def get_user_files(self, user_id, limit=50):
        """Get files uploaded by a user"""
        try:
            files = self.files.find({
                'uploaded_by': ObjectId(user_id)
            }).sort('uploaded_at', -1).limit(limit)
            
            result = []
            for file_doc in files:
                file_doc['_id'] = str(file_doc['_id'])
                file_doc['uploaded_by'] = str(file_doc['uploaded_by'])
                if file_doc.get('chat_id'):
                    file_doc['chat_id'] = str(file_doc['chat_id'])
                if file_doc.get('forwarded_from'):
                    file_doc['forwarded_from'] = str(file_doc['forwarded_from'])
                result.append(file_doc)
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting user files: {e}")
            return []

    def create_message(self, chat_id, sender_id, content, message_type='text', file_metadata=None):
        """Create a new message with file support"""
        try:
            message_data = {
                'chat_id': ObjectId(chat_id),
                'sender_id': ObjectId(sender_id),
                'content': content,
                'message_type': message_type,
                'timestamp': datetime.utcnow(),
                'is_edited': False,
                'is_deleted': False
            }
            
            if file_metadata and message_type == 'file':
                message_data['file_metadata'] = file_metadata
            
            result = self.messages.insert_one(message_data)
            
            # Update chat's last_activity
            self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {'$set': {'last_activity': datetime.utcnow()}}
            )
            
            message_data['_id'] = result.inserted_id
            return message_data
            
        except Exception as e:
            print(f"❌ Error creating message: {e}")
            return None

    def cleanup_all_mock_users(self):
        """Remove all mock users based on username patterns"""
        try:
            print("🧹 Starting comprehensive mock user cleanup...")
            
            # List of mock username patterns to remove
            mock_username_patterns = [
                'olika_x.bunknx', 'john.cooe', 'jane.jsmith', 'janie.jones',
                'janish_wilton', 'jake_brown', 'tost_user'
            ]
            
            # Find all user profiles with these usernames
            mock_profiles = list(self.user_profiles.find({
                'username': {'$in': mock_username_patterns}
            }))
            
            if not mock_profiles:
                print("✅ No mock users found to clean up")
                return 0
            
            mock_profile_ids = [profile['_id'] for profile in mock_profiles]
            mock_user_ids = [profile['user_id'] for profile in mock_profiles]
            
            print(f"🔍 Found {len(mock_profiles)} mock user profiles to remove")
            
            # Remove all associated data
            friend_requests_deleted = self.friend_requests.delete_many({
                '$or': [
                    {'from_user_id': {'$in': mock_profile_ids}},
                    {'to_user_id': {'$in': mock_profile_ids}}
                ]
            })
            print(f"✅ Removed {friend_requests_deleted.deleted_count} friend requests")
            
            # Find chats with mock users
            mock_chats = list(self.chats.find({
                'participants': {'$in': mock_profile_ids}
            }))
            mock_chat_ids = [chat['_id'] for chat in mock_chats]
            
            # Remove messages from mock chats
            messages_deleted = self.messages.delete_many({'chat_id': {'$in': mock_chat_ids}})
            print(f"✅ Removed {messages_deleted.deleted_count} messages")
            
            # Remove the chats themselves
            chats_deleted = self.chats.delete_many({'_id': {'$in': mock_chat_ids}})
            print(f"✅ Removed {chats_deleted.deleted_count} chats")
            
            # Remove notifications for mock users
            notifications_deleted = self.notifications.delete_many({'user_id': {'$in': mock_profile_ids}})
            print(f"✅ Removed {notifications_deleted.deleted_count} notifications")
            
            # Remove chat themes for mock users
            chat_themes_deleted = self.chat_themes.delete_many({'user_profile_id': {'$in': mock_profile_ids}})
            print(f"✅ Removed {chat_themes_deleted.deleted_count} chat themes")
            
            # Remove message edits by mock users
            message_edits_deleted = self.message_edits.delete_many({'edited_by': {'$in': mock_profile_ids}})
            print(f"✅ Removed {message_edits_deleted.deleted_count} message edits")
            
            # Remove user deleted messages for mock users
            user_deleted_messages_deleted = self.user_deleted_messages.delete_many({'user_id': {'$in': mock_profile_ids}})
            print(f"✅ Removed {user_deleted_messages_deleted.deleted_count} user deleted messages")
            
            # Remove user profiles
            profiles_deleted = self.user_profiles.delete_many({
                '_id': {'$in': mock_profile_ids}
            })
            print(f"✅ Removed {profiles_deleted.deleted_count} user profiles")
            
            # Remove user accounts if no profiles remain
            for user_id in mock_user_ids:
                remaining_profiles = self.user_profiles.count_documents({
                    'user_id': user_id
                })
                if remaining_profiles == 0:
                    self.users.delete_one({'_id': user_id})
                    print(f"✅ Removed user account: {user_id}")
            
            print(f"🎉 Successfully cleaned up all mock users and their data!")
            return profiles_deleted.deleted_count
            
        except Exception as e:
            print(f"❌ Error cleaning up mock users: {e}")
            return 0

    def cleanup_duplicate_chats(self):
        """Clean up duplicate individual chats between users"""
        try:
            print("🧹 Cleaning up duplicate chats...")
            
            individual_chats = list(self.chats.find({'is_group': False}))
            chat_groups = {}
            duplicates_to_remove = []
            
            for chat in individual_chats:
                participants = sorted([str(pid) for pid in chat['participants']])
                key = tuple(participants)
                
                if key not in chat_groups:
                    chat_groups[key] = []
                chat_groups[key].append(chat)
            
            for key, chats in chat_groups.items():
                if len(chats) > 1:
                    print(f"🔍 Found {len(chats)} duplicate chats for participants: {key}")
                    
                    chats.sort(key=lambda x: x.get('created_at', datetime.utcnow()))
                    
                    keep_chat = chats[0]
                    for chat in chats[1:]:
                        duplicates_to_remove.append(chat['_id'])
                        print(f"🗑️ Marking chat for removal: {chat['_id']} (duplicate of {keep_chat['_id']})")
            
            if duplicates_to_remove:
                result = self.chats.delete_many({'_id': {'$in': duplicates_to_remove}})
                print(f"✅ Removed {result.deleted_count} duplicate chats")
                
                self.messages.delete_many({'chat_id': {'$in': duplicates_to_remove}})
                print(f"✅ Cleaned up messages from duplicate chats")
                
                for chat_id in duplicates_to_remove:
                    self.user_profiles.update_many(
                        {'chat_ids': str(chat_id)},
                        {'$pull': {'chat_ids': str(chat_id)}}
                    )
                print(f"✅ Cleaned up chat references from user profiles")
            else:
                print("✅ No duplicate chats found")
                
            return len(duplicates_to_remove)
            
        except Exception as e:
            print(f"❌ Error cleaning up duplicate chats: {e}")
            return 0

    def save_chat_theme(self, user_profile_id, chat_id, theme_name):
        """Save chat theme preference for a user"""
        try:
            # Validate theme name
            valid_themes = ['default', 'romantic', 'dark', 'nature', 'ocean', 'sunset']
            if theme_name not in valid_themes:
                return {'success': False, 'error': 'Invalid theme name'}
            
            # Create or update theme preference
            theme_data = {
                'user_profile_id': ObjectId(user_profile_id),
                'chat_id': ObjectId(chat_id),
                'theme_name': theme_name,
                'updated_at': datetime.utcnow()
            }
            
            # Upsert the theme preference
            result = self.chat_themes.update_one(
                {
                    'user_profile_id': ObjectId(user_profile_id),
                    'chat_id': ObjectId(chat_id)
                },
                {'$set': theme_data},
                upsert=True
            )
            
            print(f"✅ Saved theme '{theme_name}' for user {user_profile_id} in chat {chat_id}")
            return {
                'success': True, 
                'upserted_id': str(result.upserted_id) if result.upserted_id else None,
                'modified_count': result.modified_count
            }
            
        except Exception as e:
            print(f"❌ Error saving chat theme: {e}")
            return {'success': False, 'error': str(e)}

    def get_chat_theme(self, user_profile_id, chat_id):
        """Get chat theme preference for a user"""
        try:
            theme_pref = self.chat_themes.find_one({
                'user_profile_id': ObjectId(user_profile_id),
                'chat_id': ObjectId(chat_id)
            })
            
            if theme_pref:
                return {
                    'theme_name': theme_pref['theme_name'],
                    'updated_at': theme_pref['updated_at']
                }
            return None
            
        except Exception as e:
            print(f"❌ Error getting chat theme: {e}")
            return None

    def get_user_chat_themes(self, user_profile_id):
        """Get all theme preferences for a user"""
        try:
            themes = list(self.chat_themes.find({
                'user_profile_id': ObjectId(user_profile_id)
            }))
            
            result = {}
            for theme in themes:
                result[str(theme['chat_id'])] = {
                    'theme_name': theme['theme_name'],
                    'updated_at': theme['updated_at']
                }
                
            print(f"✅ Found {len(result)} theme preferences for user {user_profile_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting user chat themes: {e}")
            return {}

    def delete_chat_theme(self, user_profile_id, chat_id):
        """Delete chat theme preference (reset to default)"""
        try:
            result = self.chat_themes.delete_one({
                'user_profile_id': ObjectId(user_profile_id),
                'chat_id': ObjectId(chat_id)
            })
            
            print(f"✅ Deleted theme preference for user {user_profile_id} in chat {chat_id}")
            return {
                'success': True,
                'deleted_count': result.deleted_count
            }
            
        except Exception as e:
            print(f"❌ Error deleting chat theme: {e}")
            return {'success': False, 'error': str(e)}

    def get_or_create_user(self, user_info):
        """Get existing user or create new one from Google OAuth data"""
        try:
            user = self.users.find_one({'google_id': user_info['sub']})
            
            if not user:
                user = {
                    'google_id': user_info['sub'],
                    'email': user_info['email'],
                    'name': user_info.get('name', ''),
                    'picture': user_info.get('picture', ''),
                    'created_at': datetime.utcnow(),
                    'last_login': datetime.utcnow()
                }
                result = self.users.insert_one(user)
                user['_id'] = result.inserted_id
                print(f"✅ New user created: {user_info['email']}")
            else:
                # Update last login
                self.users.update_one(
                    {'_id': user['_id']},
                    {'$set': {
                        'last_login': datetime.utcnow(),
                        'name': user_info.get('name', user.get('name', '')),
                        'picture': user_info.get('picture', user.get('picture', ''))
                    }}
                )
                print(f"✅ User logged in: {user_info['email']}")
            
            # Convert ObjectId to string for session
            user['_id'] = str(user['_id'])
            return user
            
        except Exception as e:
            print(f"❌ Error in get_or_create_user: {e}")
            return None

    def create_user_profile(self, user_id, username, display_name):
        """Create a new user profile under a Google account"""
        try:
            profile = {
                'user_id': ObjectId(user_id),
                'username': username.lower(),
                'display_name': display_name,
                'status': 'Hey there! I\'m using HangSpace',
                'status_message': 'Hey there! I\'m using HangSpace',
                'avatar_url': None,
                'is_online': False,
                'last_seen': datetime.utcnow(),
                'created_at': datetime.utcnow(),
                'friends': [],
                'chat_ids': [],
                'is_admin': False
            }
            
            result = self.user_profiles.insert_one(profile)
            profile['_id'] = str(result.inserted_id)
            profile['user_id'] = user_id
            print(f"✅ New profile created: {username} (Display: {display_name})")
            return profile
            
        except Exception as e:
            print(f"❌ Error creating user profile: {e}")
            return None

    def get_user_profiles(self, user_id):
        """Get all profiles for a user"""
        try:
            profiles = list(self.user_profiles.find({'user_id': ObjectId(user_id)}))
            for profile in profiles:
                profile['_id'] = str(profile['_id'])
                profile['user_id'] = str(profile['user_id'])
            print(f"✅ Found {len(profiles)} profiles for user {user_id}")
            return profiles
        except Exception as e:
            print(f"❌ Error getting user profiles: {e}")
            return []

    def get_user_profile(self, profile_id):
        """Get a specific user profile"""
        try:
            if not profile_id:
                print("❌ No profile_id provided to get_user_profile")
                return None
                
            profile = self.user_profiles.find_one({'_id': ObjectId(profile_id)})
            if profile:
                profile['_id'] = str(profile['_id'])
                profile['user_id'] = str(profile['user_id'])
                
                if 'status' not in profile:
                    profile['status'] = 'offline'
                elif profile.get('is_online', False) and profile['status'] == 'offline':
                    profile['status'] = 'online'
                
                print(f"✅ Retrieved profile: {profile.get('username', 'Unknown')} (Status: {profile.get('status', 'unknown')})")
                return profile
            else:
                print(f"❌ Profile not found: {profile_id}")
                return None
        except Exception as e:
            print(f"❌ Error getting user profile: {e}")
            return None

    def is_username_available(self, username):
        """Check if username is available"""
        try:
            existing = self.user_profiles.find_one({'username': username.lower()})
            available = existing is None
            print(f"🔍 Username '{username}' available: {available}")
            return available
        except Exception as e:
            print(f"❌ Error checking username availability: {e}")
            return False

    def update_user_status(self, profile_id, status):
        """Update user online/offline status with proper status field"""
        try:
            is_online = status == 'online'
            update_data = {
                'is_online': is_online,
                'last_seen': datetime.utcnow(),
                'status': status
            }
            
            result = self.user_profiles.update_one(
                {'_id': ObjectId(profile_id)},
                {'$set': update_data}
            )
            print(f"✅ Updated status for {profile_id}: {status} (modified: {result.modified_count})")
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating user status: {e}")
            return False

    def get_user_status(self, profile_id):
        """Get user online/offline status"""
        try:
            profile = self.user_profiles.find_one({'_id': ObjectId(profile_id)})
            if profile:
                if 'status' in profile:
                    return profile['status']
                else:
                    return 'online' if profile.get('is_online', False) else 'offline'
            return 'offline'
        except Exception as e:
            print(f"❌ Error getting user status: {e}")
            return 'offline'

    def get_chat_participant_statuses(self, chat_id, current_user_id):
        """Get online/offline statuses for all participants in a chat"""
        try:
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat:
                print(f"❌ Chat not found: {chat_id}")
                return []
            
            statuses = []
            for participant_id in chat['participants']:
                participant_id_str = str(participant_id)
                
                if participant_id_str == current_user_id:
                    continue
                
                user_profile = self.get_user_profile(participant_id_str)
                if user_profile:
                    status = user_profile.get('status', 'offline')
                    statuses.append({
                        'user_id': participant_id_str,
                        'status': status,
                        'username': user_profile.get('display_name', user_profile['username']),
                        'last_seen': user_profile.get('last_seen')
                    })
            
            print(f"✅ Found {len(statuses)} participant statuses for chat {chat_id}")
            return statuses
            
        except Exception as e:
            print(f"❌ Error getting chat participant statuses: {e}")
            return []

    def search_users(self, query, current_user_id):
        """Search for users by username or display name - INCLUDES current user"""
        try:
            if not query or len(query) < 1:
                print("🔍 Empty search query")
                return []

            print(f"🔍 Database search for: '{query}' (current user: {current_user_id})")
            
            regex_query = {'$regex': f'.*{re.escape(query)}.*', '$options': 'i'}
            
            current_user = self.user_profiles.find_one({'_id': ObjectId(current_user_id)})
            current_user_friends = current_user.get('friends', []) if current_user else []
            
            print(f"🔍 Searching with regex: {regex_query}")
            
            users_cursor = self.user_profiles.find({
                '$or': [
                    {'username': regex_query},
                    {'display_name': regex_query}
                ]
            })
            
            users = list(users_cursor)
            print(f"📊 Database query returned {len(users)} results (including current user)")
            
            result = []
            for user in users:
                user_id_str = str(user['_id'])
                is_current_user = user_id_str == current_user_id
                is_friend = ObjectId(user_id_str) in current_user_friends if not is_current_user else False
                
                has_pending_request = False
                if not is_current_user and not is_friend:
                    pending_request = self.friend_requests.find_one({
                        '$or': [
                            {'from_user_id': ObjectId(current_user_id), 'to_user_id': ObjectId(user_id_str), 'status': 'pending'},
                            {'from_user_id': ObjectId(user_id_str), 'to_user_id': ObjectId(current_user_id), 'status': 'pending'}
                        ]
                    })
                    has_pending_request = pending_request is not None
                
                status = user.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if user.get('is_online', False) else 'offline'
                
                user_data = {
                    '_id': user_id_str,
                    'username': user['username'],
                    'display_name': user.get('display_name', user['username']),
                    'avatar_url': user.get('avatar_url'),
                    'is_online': user.get('is_online', False),
                    'status': status,
                    'status_message': user.get('status_message', ''),
                    'is_friend': is_friend,
                    'has_pending_request': has_pending_request,
                    'is_current_user': is_current_user,
                    'last_seen': user.get('last_seen'),
                    'user_id': user_id_str
                }
                result.append(user_data)
                print(f"👤 Search result: {user['username']} (id: {user_id_str}) - Status: {status}, Current User: {is_current_user}, Friend: {is_friend}, Pending: {has_pending_request}")

            print(f"✅ Final search results: {len(result)} users")
            return result
            
        except Exception as e:
            print(f"❌ Error searching users: {e}")
            import traceback
            traceback.print_exc()
            return []

    def send_friend_request(self, from_user_id, to_user_id):
        """Send a friend request"""
        try:
            existing = self.friend_requests.find_one({
                'from_user_id': ObjectId(from_user_id),
                'to_user_id': ObjectId(to_user_id),
                'status': 'pending'
            })
            
            if existing:
                print(f"⚠️ Friend request already exists from {from_user_id} to {to_user_id}")
                return {'success': False, 'error': 'Friend request already sent'}

            from_user = self.user_profiles.find_one({'_id': ObjectId(from_user_id)})
            if from_user and ObjectId(to_user_id) in from_user.get('friends', []):
                print(f"⚠️ Users {from_user_id} and {to_user_id} are already friends")
                return {'success': False, 'error': 'Already friends'}

            friend_request = {
                'from_user_id': ObjectId(from_user_id),
                'to_user_id': ObjectId(to_user_id),
                'status': 'pending',
                'created_at': datetime.utcnow()
            }
            
            result = self.friend_requests.insert_one(friend_request)
            
            sender_profile = self.user_profiles.find_one({'_id': ObjectId(from_user_id)})
            sender_name = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'
            
            self._create_notification(
                to_user_id,
                'friend_request',
                f'{sender_name} sent you a friend request',
                {'from_user_id': from_user_id}
            )
            
            print(f"✅ Friend request sent from {from_user_id} to {to_user_id}")
            return {'success': True}
            
        except Exception as e:
            print(f"❌ Error sending friend request: {e}")
            return {'success': False, 'error': str(e)}

    def get_pending_requests(self, user_id):
        """Get pending friend requests for a user"""
        try:
            requests = self.friend_requests.aggregate([
                {
                    '$match': {
                        'to_user_id': ObjectId(user_id),
                        'status': 'pending'
                    }
                },
                {
                    '$lookup': {
                        'from': 'user_profiles',
                        'localField': 'from_user_id',
                        'foreignField': '_id',
                        'as': 'from_user'
                    }
                },
                {
                    '$unwind': '$from_user'
                },
                {
                    '$sort': {'created_at': -1}
                }
            ])
            
            result = []
            for req in requests:
                status = req['from_user'].get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if req['from_user'].get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(req['_id']),
                    'from_user': {
                        '_id': str(req['from_user']['_id']),
                        'username': req['from_user']['username'],
                        'display_name': req['from_user']['display_name'],
                        'avatar_url': req['from_user'].get('avatar_url'),
                        'status': status,
                        'last_seen': req['from_user'].get('last_seen')
                    },
                    'created_at': req['created_at']
                })
            
            print(f"✅ Found {len(result)} pending requests for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting pending requests: {e}")
            return []

    def respond_friend_request(self, request_id, action, user_id):
        """Accept or decline a friend request"""
        try:
            print(f"🔍 Processing friend request response: request_id={request_id}, action={action}, user_id={user_id}")
            
            friend_request = self.friend_requests.find_one({
                '_id': ObjectId(request_id),
                'to_user_id': ObjectId(user_id),
                'status': 'pending'
            })
            
            if not friend_request:
                print(f"❌ Friend request not found: {request_id} for user {user_id}")
                return {'success': False, 'error': 'Friend request not found'}
            
            print(f"✅ Found friend request: from {friend_request['from_user_id']} to {friend_request['to_user_id']}")
            
            if action == 'accept':
                print(f"🤝 Accepting friend request between {friend_request['from_user_id']} and {user_id}")
                
                result1 = self.user_profiles.update_one(
                    {'_id': friend_request['from_user_id']},
                    {'$addToSet': {'friends': ObjectId(user_id)}}
                )
                result2 = self.user_profiles.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$addToSet': {'friends': friend_request['from_user_id']}}
                )
                
                print(f"✅ Friends update - From user: {result1.modified_count}, To user: {result2.modified_count}")
                
                chat = self.create_chat([str(friend_request['from_user_id']), user_id], is_group=False)
                if chat:
                    print(f"✅ Chat handled: {chat['_id']}")
                else:
                    print("⚠️ Chat creation returned None")
                
                accepter_profile = self.user_profiles.find_one({'_id': ObjectId(user_id)})
                accepter_name = accepter_profile.get('display_name', accepter_profile['username']) if accepter_profile else 'Unknown'
                
                self._create_notification(
                    str(friend_request['from_user_id']),
                    'friend_request_accepted',
                    f'{accepter_name} accepted your friend request!',
                    {'user_id': user_id}
                )
            
            delete_result = self.friend_requests.delete_one({'_id': ObjectId(request_id)})
            print(f"✅ Deleted friend request: {delete_result.deleted_count} document(s) deleted")
            
            print(f"✅ Friend request {request_id} {action}ed by {user_id}")
            return {'success': True}
            
        except Exception as e:
            print(f"❌ Error responding to friend request: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def get_friends(self, user_id):
        """Get user's friends list with accurate status"""
        try:
            user = self.user_profiles.find_one({'_id': ObjectId(user_id)})
            if not user:
                print(f"❌ User not found: {user_id}")
                return []
                
            if 'friends' not in user or not user['friends']:
                print(f"✅ No friends found for user {user_id}")
                return []

            friends = self.user_profiles.find({
                '_id': {'$in': user['friends']}
            })
            
            result = []
            for friend in friends:
                status = friend.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if friend.get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(friend['_id']),
                    'username': friend['username'],
                    'display_name': friend.get('display_name', friend['username']),
                    'avatar_url': friend.get('avatar_url'),
                    'is_online': friend.get('is_online', False),
                    'status': status,
                    'status_message': friend.get('status_message', ''),
                    'last_seen': friend.get('last_seen')
                })
            
            print(f"✅ Found {len(result)} friends for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting friends: {e}")
            return []

    def create_chat(self, participant_ids, chat_name=None, is_group=False):
        """Create a new chat with duplicate prevention"""
        try:
            participants = [ObjectId(pid) for pid in participant_ids]
            
            if not is_group and len(participants) == 2:
                existing_chat = self.chats.find_one({
                    'participants': {'$all': participants},
                    'is_group': False,
                    'participants': {'$size': 2}
                })
                
                if existing_chat:
                    print(f"✅ Chat already exists between users: {existing_chat['_id']}")
                    existing_chat['_id'] = str(existing_chat['_id'])
                    existing_chat['participants'] = [str(pid) for pid in existing_chat['participants']]
                    return existing_chat
            
            chat = {
                'participants': participants,
                'is_group': is_group,
                'created_at': datetime.utcnow(),
                'last_message_at': datetime.utcnow()
            }
            
            if is_group and chat_name:
                chat['name'] = chat_name
            elif not is_group and len(participants) == 2:
                other_user_id = None
                for pid in participants:
                    if not other_user_id:
                        other_user_id = pid
                    else:
                        other_user = self.user_profiles.find_one({'_id': pid})
                        if other_user:
                            chat['name'] = other_user.get('display_name', other_user['username'])
                            break
                
                if 'name' not in chat:
                    chat['name'] = 'Direct Chat'
            else:
                chat['name'] = 'Group Chat'
            
            result = self.chats.insert_one(chat)
            chat['_id'] = str(result.inserted_id)
            
            chat['participants'] = [str(pid) for pid in participants]
            
            for participant_id in participant_ids:
                self.user_profiles.update_one(
                    {'_id': ObjectId(participant_id)},
                    {'$addToSet': {'chat_ids': chat['_id']}}
                )
            
            print(f"✅ Created new chat: {chat['name']} ({chat['_id']})")
            return chat
            
        except Exception as e:
            print(f"❌ Error creating chat: {e}")
            return None

    def get_user_chats(self, user_id):
        """Get all chats for a user with duplicate handling"""
        try:
            chats = self.chats.aggregate([
                {
                    '$match': {
                        'participants': ObjectId(user_id)
                    }
                },
                {
                    '$lookup': {
                        'from': 'messages',
                        'let': {'chat_id': '$_id'},
                        'pipeline': [
                            {'$match': {'$expr': {'$eq': ['$chat_id', '$$chat_id']}}},
                            {'$sort': {'timestamp': -1}},
                            {'$limit': 1}
                        ],
                        'as': 'last_message'
                    }
                },
                {
                    '$sort': {'last_message_at': -1}
                }
            ])
            
            seen_chats = set()
            result = []
            
            for chat in chats:
                if not chat.get('is_group', False) and len(chat['participants']) == 2:
                    participants = sorted([str(pid) for pid in chat['participants']])
                    chat_key = tuple(participants)
                    
                    if chat_key in seen_chats:
                        print(f"⚠️ Skipping duplicate chat in results: {chat['_id']}")
                        continue
                    seen_chats.add(chat_key)
                
                chat_name = chat.get('name', 'Chat')
                if not chat.get('is_group', False) and len(chat['participants']) == 2:
                    other_participant_id = None
                    for participant_id in chat['participants']:
                        if str(participant_id) != user_id:
                            other_participant_id = participant_id
                            break
                    
                    if other_participant_id:
                        other_user = self.user_profiles.find_one({'_id': other_participant_id})
                        if other_user:
                            chat_name = other_user.get('display_name', other_user['username'])
                
                chat_data = {
                    '_id': str(chat['_id']),
                    'name': chat_name,
                    'is_group': chat.get('is_group', False),
                    'last_message_at': chat.get('last_message_at'),
                    'participants': [str(pid) for pid in chat['participants']]
                }
                
                if chat.get('last_message'):
                    last_msg = chat['last_message'][0]
                    chat_data['last_message'] = {
                        'content': last_msg['content'],
                        'sender_id': str(last_msg['sender_id']),
                        'timestamp': last_msg['timestamp'],
                        'type': last_msg.get('type', 'text')
                    }
                
                result.append(chat_data)
            
            print(f"✅ Found {len(result)} unique chats for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting user chats: {e}")
            return []

    def get_chat(self, chat_id, user_id):
        """Get chat details if user is participant"""
        try:
            chat = self.chats.find_one({
                '_id': ObjectId(chat_id),
                'participants': ObjectId(user_id)
            })
            
            if chat:
                chat['_id'] = str(chat['_id'])
                chat['participants'] = [str(pid) for pid in chat['participants']]
                
                if not chat.get('is_group', False) and len(chat['participants']) == 2:
                    other_participant_id = None
                    for participant_id in chat['participants']:
                        if str(participant_id) != user_id:
                            other_participant_id = participant_id
                            break
                    
                    if other_participant_id:
                        other_user = self.user_profiles.find_one({'_id': ObjectId(other_participant_id)})
                        if other_user:
                            chat['name'] = other_user.get('display_name', other_user['username'])
                
                return chat
            return None
            
        except Exception as e:
            print(f"❌ Error getting chat: {e}")
            return None

    def get_chat_messages(self, chat_id, limit=50):
        """Get messages for a chat"""
        try:
            messages = self.messages.find(
                {'chat_id': ObjectId(chat_id)}
            ).sort('timestamp', 1).limit(limit)
            
            result = []
            for message in messages:
                message_data = {
                    '_id': str(message['_id']),
                    'chat_id': str(message['chat_id']),
                    'sender_id': str(message['sender_id']),
                    'content': message['content'],
                    'type': message.get('type', 'text'),
                    'timestamp': message['timestamp'],
                    'is_edited': message.get('is_edited', False),
                    'is_deleted': message.get('is_deleted', False),
                    'edited_at': message.get('edited_at'),
                    'read_by': [str(user_id) for user_id in message.get('read_by', [])] if message.get('read_by') else [],
                    'edit_count': message.get('edit_count', 0)
                }
                result.append(message_data)
            
            print(f"✅ Found {len(result)} messages for chat {chat_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting chat messages: {e}")
            return []

    def update_message(self, message_id, sender_id, new_content):
        """Update a message content with edit history"""
        try:
            original_message = self.messages.find_one({'_id': ObjectId(message_id)})
            if not original_message:
                return {'success': False, 'error': 'Message not found'}
            
            if original_message['sender_id'] != ObjectId(sender_id):
                return {'success': False, 'error': 'Not authorized to edit this message'}
            
            if original_message.get('is_deleted', False):
                return {'success': False, 'error': 'Cannot edit deleted message'}
            
            # Store edit history before updating
            if not original_message.get('is_edited', False):
                # First edit - store original content in edit history
                edit_record = {
                    'message_id': ObjectId(message_id),
                    'edit_number': 1,
                    'previous_content': original_message['content'],
                    'new_content': new_content,
                    'edited_by': ObjectId(sender_id),
                    'edited_at': datetime.utcnow()
                }
                self.message_edits.insert_one(edit_record)
            else:
                # Subsequent edit - store in edit history
                current_edit_count = original_message.get('edit_count', 0)
                edit_record = {
                    'message_id': ObjectId(message_id),
                    'edit_number': current_edit_count + 1,
                    'previous_content': original_message['content'],
                    'new_content': new_content,
                    'edited_by': ObjectId(sender_id),
                    'edited_at': datetime.utcnow()
                }
                self.message_edits.insert_one(edit_record)
            
            update_data = {
                'content': new_content,
                'edited_at': datetime.utcnow(),
                'is_edited': True,
                'edit_count': original_message.get('edit_count', 0) + 1
            }
            
            # Store original content on first edit
            if not original_message.get('is_edited', False):
                update_data['original_content'] = original_message['content']
            
            result = self.messages.update_one(
                {
                    '_id': ObjectId(message_id),
                    'sender_id': ObjectId(sender_id)
                },
                {
                    '$set': update_data
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Message {message_id} updated by user {sender_id} (edit #{update_data['edit_count']})")
                return {
                    'success': True, 
                    'message': 'Message updated successfully',
                    'edit_count': update_data['edit_count']
                }
            else:
                return {'success': False, 'error': 'Message not found or not authorized'}
                
        except Exception as e:
            print(f"❌ Error updating message: {e}")
            return {'success': False, 'error': str(e)}

    def get_message_edit_history(self, message_id, user_id):
        """Get complete edit history for a message"""
        try:
            message = self.messages.find_one({'_id': ObjectId(message_id)})
            if not message:
                return {'success': False, 'error': 'Message not found'}
            
            # Check if user has permission to view this message's history
            chat = self.chats.find_one({'_id': message['chat_id']})
            if not chat or ObjectId(user_id) not in chat['participants']:
                return {'success': False, 'error': 'Access denied'}
            
            # Get all edit records for this message
            edit_history = list(self.message_edits.find(
                {'message_id': ObjectId(message_id)}
            ).sort('edit_number', 1))
            
            history_data = {
                'current_content': message['content'],
                'original_content': message.get('original_content', message['content']),
                'edit_count': message.get('edit_count', 0),
                'last_edited': message.get('edited_at'),
                'first_sent': message['timestamp'],
                'edits': []
            }
            
            # Build edit history
            for edit in edit_history:
                editor_profile = self.user_profiles.find_one({'_id': edit['edited_by']})
                editor_name = editor_profile.get('display_name', editor_profile['username']) if editor_profile else 'Unknown'
                
                history_data['edits'].append({
                    'edit_number': edit['edit_number'],
                    'previous_content': edit['previous_content'],
                    'new_content': edit['new_content'],
                    'edited_by': str(edit['edited_by']),
                    'edited_by_name': editor_name,
                    'edited_at': edit['edited_at']
                })
            
            return {'success': True, 'history': history_data}
            
        except Exception as e:
            print(f"❌ Error getting message history: {e}")
            return {'success': False, 'error': str(e)}

    def delete_message(self, message_id, sender_id):
        """Soft delete a message"""
        try:
            # First get the message to verify ownership
            message = self.messages.find_one({'_id': ObjectId(message_id)})
            if not message:
                return {'success': False, 'error': 'Message not found'}
            
            if message['sender_id'] != ObjectId(sender_id):
                return {'success': False, 'error': 'Not authorized to delete this message'}
            
            result = self.messages.update_one(
                {
                    '_id': ObjectId(message_id),
                    'sender_id': ObjectId(sender_id)
                },
                {
                    '$set': {
                        'is_deleted': True,
                        'deleted_at': datetime.utcnow(),
                        'content': 'This message was deleted',
                        'original_content': message.get('original_content', message['content'])
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Message {message_id} deleted by user {sender_id}")
                return {'success': True, 'message': 'Message deleted successfully'}
            else:
                return {'success': False, 'error': 'Message not found or not authorized'}
                
        except Exception as e:
            print(f"❌ Error deleting message: {e}")
            return {'success': False, 'error': str(e)}

    def delete_message_for_user(self, message_id, user_id):
        """Delete a message only for the specific user"""
        try:
            # First get the message to verify it exists
            message = self.messages.find_one({'_id': ObjectId(message_id)})
            if not message:
                return {'success': False, 'error': 'Message not found'}
            
            # Store user's deleted messages in user_deleted_messages collection
            user_deleted_message = {
                'user_id': ObjectId(user_id),
                'message_id': ObjectId(message_id),
                'deleted_at': datetime.utcnow(),
                'original_content': message.get('original_content', message['content']),
                'original_sender_id': message['sender_id'],
                'chat_id': message['chat_id']
            }
            
            # Insert into user_deleted_messages collection
            self.user_deleted_messages.update_one(
                {
                    'user_id': ObjectId(user_id),
                    'message_id': ObjectId(message_id)
                },
                {'$set': user_deleted_message},
                upsert=True
            )
            
            print(f"✅ Message {message_id} deleted for user {user_id}")
            return {'success': True, 'message': 'Message deleted for you'}
            
        except Exception as e:
            print(f"❌ Error deleting message for user: {e}")
            return {'success': False, 'error': str(e)}

    def delete_message_for_everyone(self, message_id, user_id):
        """Delete a message for all participants (soft delete)"""
        try:
            # First get the message to verify ownership
            message = self.messages.find_one({'_id': ObjectId(message_id)})
            if not message:
                return {'success': False, 'error': 'Message not found'}
            
            # Check if user is the sender
            if message['sender_id'] != ObjectId(user_id):
                return {'success': False, 'error': 'Only the message sender can delete for everyone'}
            
            # Soft delete the message
            result = self.messages.update_one(
                {
                    '_id': ObjectId(message_id),
                    'sender_id': ObjectId(user_id)
                },
                {
                    '$set': {
                        'is_deleted': True,
                        'deleted_at': datetime.utcnow(),
                        'deleted_by': ObjectId(user_id),
                        'original_content': message.get('original_content', message['content']),
                        'content': 'This message was deleted'
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Message {message_id} deleted for everyone by user {user_id}")
                return {'success': True, 'message': 'Message deleted for everyone'}
            else:
                return {'success': False, 'error': 'Message not found or not authorized'}
            
        except Exception as e:
            print(f"❌ Error deleting message for everyone: {e}")
            return {'success': False, 'error': str(e)}

    def is_message_deleted_for_user(self, message_id, user_id):
        """Check if a message is deleted for a specific user"""
        try:
            deleted = self.user_deleted_messages.find_one({
                'user_id': ObjectId(user_id),
                'message_id': ObjectId(message_id)
            })
            return deleted is not None
        except Exception as e:
            print(f"❌ Error checking if message deleted for user: {e}")
            return False

    def get_user_visible_messages(self, chat_id, user_id):
        """Get messages that are visible to a specific user"""
        try:
            # Get all messages for the chat
            messages = self.messages.find(
                {'chat_id': ObjectId(chat_id)}
            ).sort('timestamp', 1)
            
            # Get messages deleted by this user
            user_deleted_messages = self.user_deleted_messages.find({
                'user_id': ObjectId(user_id)
            })
            deleted_message_ids = [msg['message_id'] for msg in user_deleted_messages]
            
            result = []
            for message in messages:
                message_id = message['_id']
                
                # Skip messages deleted by this user
                if message_id in deleted_message_ids:
                    continue
                
                message_data = {
                    '_id': str(message['_id']),
                    'chat_id': str(message['chat_id']),
                    'sender_id': str(message['sender_id']),
                    'content': message['content'],
                    'type': message.get('type', 'text'),
                    'timestamp': message['timestamp'],
                    'is_edited': message.get('is_edited', False),
                    'is_deleted': message.get('is_deleted', False),
                    'edited_at': message.get('edited_at'),
                    'read_by': [str(user_id) for user_id in message.get('read_by', [])] if message.get('read_by') else [],
                    'edit_count': message.get('edit_count', 0)
                }
                result.append(message_data)
            
            print(f"✅ Found {len(result)} visible messages for user {user_id} in chat {chat_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting user visible messages: {e}")
            return []

    def mark_message_as_read(self, message_id, user_id):
        """Mark a message as read by a user"""
        try:
            result = self.messages.update_one(
                {
                    '_id': ObjectId(message_id)
                },
                {
                    '$addToSet': {'read_by': ObjectId(user_id)}
                }
            )
            
            if result.modified_count > 0:
                message = self.messages.find_one({'_id': ObjectId(message_id)})
                if message:
                    sender_id = str(message['sender_id'])
                    if sender_id != user_id:
                        self._create_notification(
                            sender_id,
                            'message_read',
                            f'Your message was read',
                            {
                                'message_id': message_id,
                                'reader_id': user_id,
                                'chat_id': str(message['chat_id'])
                            }
                        )
                
                return {'success': True}
            return {'success': False}
            
        except Exception as e:
            print(f"❌ Error marking message as read: {e}")
            return {'success': False}

    def get_unread_messages_count(self, user_id, chat_id=None):
        """Get count of unread messages for a user"""
        try:
            query = {
                'read_by': {'$ne': ObjectId(user_id)},
                'sender_id': {'$ne': ObjectId(user_id)},
                'is_deleted': {'$ne': True}
            }
            
            if chat_id:
                query['chat_id'] = ObjectId(chat_id)
                
            count = self.messages.count_documents(query)
            return count
            
        except Exception as e:
            print(f"❌ Error getting unread messages count: {e}")
            return 0

    # CONSOLIDATED NOTIFICATION METHODS

    def create_consolidated_message_notification(self, message_data, receiver_id):
        """Create or update consolidated notification for multiple messages from same sender"""
        try:
            sender_id = message_data['sender_id']
            chat_id = message_data['chat_id']
            
            # Check for existing unread notification from same sender
            existing_notification = self.notifications.find_one({
                'user_id': ObjectId(receiver_id),
                'type': 'new_message',
                'is_read': False,
                'data.sender_id': sender_id
            })
            
            sender_profile = self.get_user_profile(sender_id)
            sender_name = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'
            
            # Truncate message content for preview
            message_preview = message_data['content']
            if len(message_preview) > 50:
                message_preview = message_preview[:47] + '...'
            
            if existing_notification:
                # Update existing notification with message count
                message_count = existing_notification.get('data', {}).get('message_count', 1) + 1
                
                notification_message = f"{sender_name}: {message_preview}"
                
                # Update existing notification
                self.notifications.update_one(
                    {'_id': existing_notification['_id']},
                    {'$set': {
                        'message': notification_message,
                        'data.message_count': message_count,
                        'data.latest_content': message_data['content'],
                        'data.latest_timestamp': message_data.get('timestamp', datetime.utcnow()),
                        'updated_at': datetime.utcnow()
                    }}
                )
                
                # Return the updated notification
                existing_notification['_id'] = str(existing_notification['_id'])
                existing_notification['message'] = notification_message
                existing_notification['data']['message_count'] = message_count
                existing_notification['data']['latest_content'] = message_data['content']
                
                print(f"✅ Updated consolidated notification for user {receiver_id} from {sender_name} (count: {message_count})")
                return existing_notification
                
            else:
                # Create new consolidated notification
                notification_message = f"{sender_name}: {message_preview}"
                
                notification = {
                    'user_id': ObjectId(receiver_id),
                    'type': 'new_message',
                    'message': notification_message,
                    'data': {
                        'message_id': message_data.get('message_id', str(ObjectId())),
                        'chat_id': chat_id,
                        'sender_id': sender_id,
                        'sender_name': sender_name,
                        'content': message_data['content'],
                        'chat_name': message_data.get('chat_name', 'Chat'),
                        'message_count': 1,
                        'latest_content': message_data['content'],
                        'latest_timestamp': message_data.get('timestamp', datetime.utcnow())
                    },
                    'is_read': False,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                result = self.notifications.insert_one(notification)
                notification['_id'] = str(result.inserted_id)
                
                print(f"✅ Created consolidated notification for user {receiver_id} from {sender_name}")
                return notification
                
        except Exception as e:
            print(f"❌ Error creating consolidated notification: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_message_notification(self, message_data, receiver_id):
        """Create notification for new message - now uses consolidated approach"""
        return self.create_consolidated_message_notification(message_data, receiver_id)

    def _create_notification(self, user_id, notification_type, message, data=None):
        """Create a notification for a user"""
        try:
            notification = {
                'user_id': ObjectId(user_id),
                'type': notification_type,
                'message': message,
                'data': data or {},
                'is_read': False,
                'created_at': datetime.utcnow()
            }
            
            result = self.notifications.insert_one(notification)
            notification['_id'] = str(result.inserted_id)
            print(f"✅ Created notification for user {user_id}: {message}")
            return notification
            
        except Exception as e:
            print(f"❌ Error creating notification: {e}")
            return None

    def get_user_notifications(self, user_id, limit=20, unread_only=False):
        """Get notifications for a user"""
        try:
            query = {'user_id': ObjectId(user_id)}
            if unread_only:
                query['is_read'] = False
                
            notifications = self.notifications.find(query).sort('created_at', -1).limit(limit)
            
            result = []
            for notification in notifications:
                result.append({
                    '_id': str(notification['_id']),
                    'type': notification['type'],
                    'message': notification['message'],
                    'data': notification.get('data', {}),
                    'is_read': notification['is_read'],
                    'created_at': notification['created_at']
                })
            
            print(f"✅ Found {len(result)} notifications for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting notifications: {e}")
            return []

    def mark_notification_as_read(self, notification_id, user_id):
        """Mark a notification as read"""
        try:
            result = self.notifications.update_one(
                {
                    '_id': ObjectId(notification_id),
                    'user_id': ObjectId(user_id)
                },
                {
                    '$set': {'is_read': True}
                }
            )
            
            if result.modified_count > 0:
                print(f"✅ Marked notification {notification_id} as read")
                return {'success': True}
            return {'success': False, 'error': 'Notification not found'}
            
        except Exception as e:
            print(f"❌ Error marking notification as read: {e}")
            return {'success': False, 'error': str(e)}

    def mark_all_notifications_as_read(self, user_id):
        """Mark all notifications as read for a user"""
        try:
            result = self.notifications.update_many(
                {
                    'user_id': ObjectId(user_id),
                    'is_read': False
                },
                {
                    '$set': {'is_read': True}
                }
            )
            
            print(f"✅ Marked {result.modified_count} notifications as read for user {user_id}")
            return {'success': True, 'marked_count': result.modified_count}
            
        except Exception as e:
            print(f"❌ Error marking all notifications as read: {e}")
            return {'success': False, 'error': str(e)}

    def get_unread_notifications_count(self, user_id):
        """Get count of unread notifications for a user"""
        try:
            count = self.notifications.count_documents({
                'user_id': ObjectId(user_id),
                'is_read': False
            })
            return count
        except Exception as e:
            print(f"❌ Error getting unread notifications count: {e}")
            return 0

    # NEW METHODS FOR BELL ICON MANAGEMENT

    def mark_all_message_notifications_as_read(self, user_id, sender_id=None):
        """Mark all message notifications from a specific sender as read"""
        try:
            query = {
                'user_id': ObjectId(user_id),
                'type': 'new_message',
                'is_read': False
            }
            
            if sender_id:
                query['data.sender_id'] = sender_id
            
            result = self.notifications.update_many(
                query,
                {'$set': {'is_read': True, 'read_at': datetime.utcnow()}}
            )
            
            print(f"✅ Marked {result.modified_count} message notifications as read for user {user_id}")
            return result.modified_count
            
        except Exception as e:
            print(f"❌ Error marking message notifications as read: {e}")
            return 0

    def get_unread_message_notifications_count(self, user_id, sender_id=None):
        """Get count of unread message notifications from a specific sender"""
        try:
            query = {
                'user_id': ObjectId(user_id),
                'type': 'new_message',
                'is_read': False
            }
            
            if sender_id:
                query['data.sender_id'] = sender_id
            
            count = self.notifications.count_documents(query)
            return count
            
        except Exception as e:
            print(f"❌ Error getting unread message notifications count: {e}")
            return 0

    def get_message_notifications_by_sender(self, user_id, sender_id=None):
        """Get all message notifications from a specific sender"""
        try:
            query = {
                'user_id': ObjectId(user_id),
                'type': 'new_message'
            }
            
            if sender_id:
                query['data.sender_id'] = sender_id
            
            notifications = self.notifications.find(query).sort('created_at', -1)
            
            result = []
            for notification in notifications:
                result.append({
                    '_id': str(notification['_id']),
                    'type': notification['type'],
                    'message': notification['message'],
                    'data': notification.get('data', {}),
                    'is_read': notification['is_read'],
                    'created_at': notification['created_at']
                })
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting message notifications by sender: {e}")
            return []

    def get_active_message_senders(self, user_id):
        """Get list of senders who have unread message notifications for the user"""
        try:
            pipeline = [
                {
                    '$match': {
                        'user_id': ObjectId(user_id),
                        'type': 'new_message',
                        'is_read': False
                    }
                },
                {
                    '$group': {
                        '_id': '$data.sender_id',
                        'sender_name': {'$first': '$data.sender_name'},
                        'message_count': {'$sum': 1},
                        'latest_timestamp': {'$max': '$created_at'},
                        'latest_content': {'$last': '$data.latest_content'}
                    }
                },
                {
                    '$sort': {'latest_timestamp': -1}
                }
            ]
            
            senders = self.notifications.aggregate(pipeline)
            
            result = []
            for sender in senders:
                if sender['_id']:  # Ensure sender_id is not None
                    result.append({
                        'sender_id': sender['_id'],
                        'sender_name': sender.get('sender_name', 'Unknown'),
                        'message_count': sender['message_count'],
                        'latest_timestamp': sender['latest_timestamp'],
                        'latest_content': sender.get('latest_content', '')
                    })
            
            print(f"✅ Found {len(result)} active message senders for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting active message senders: {e}")
            return []

    def cleanup_old_notifications(self, days_old=30):
        """Clean up notifications older than specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            result = self.notifications.delete_many({
                'created_at': {'$lt': cutoff_date},
                'is_read': True
            })
            
            print(f"✅ Cleaned up {result.deleted_count} old notifications")
            return result.deleted_count
            
        except Exception as e:
            print(f"❌ Error cleaning up old notifications: {e}")
            return 0

    def get_notification_stats(self, user_id):
        """Get notification statistics for a user"""
        try:
            total_notifications = self.notifications.count_documents({
                'user_id': ObjectId(user_id)
            })
            
            unread_notifications = self.notifications.count_documents({
                'user_id': ObjectId(user_id),
                'is_read': False
            })
            
            message_notifications = self.notifications.count_documents({
                'user_id': ObjectId(user_id),
                'type': 'new_message'
            })
            
            friend_notifications = self.notifications.count_documents({
                'user_id': ObjectId(user_id),
                'type': {'$in': ['friend_request', 'friend_request_accepted']}
            })
            
            return {
                'total': total_notifications,
                'unread': unread_notifications,
                'message_notifications': message_notifications,
                'friend_notifications': friend_notifications
            }
            
        except Exception as e:
            print(f"❌ Error getting notification stats: {e}")
            return {}

    def get_user_by_username(self, username):
        """Get user profile by username"""
        try:
            user = self.user_profiles.find_one({'username': username.lower()})
            if user:
                user['_id'] = str(user['_id'])
                user['user_id'] = str(user['user_id'])
                print(f"✅ Found user by username: {username}")
            return user
        except Exception as e:
            print(f"❌ Error getting user by username: {e}")
            return None

    def remove_friend(self, user_id, friend_id):
        """Remove a friend from user's friend list"""
        try:
            self.user_profiles.update_one(
                {'_id': ObjectId(user_id)},
                {'$pull': {'friends': ObjectId(friend_id)}}
            )
            self.user_profiles.update_one(
                {'_id': ObjectId(friend_id)},
                {'$pull': {'friends': ObjectId(user_id)}}
            )
            
            print(f"✅ Removed friend {friend_id} from user {user_id}")
            return {'success': True}
            
        except Exception as e:
            print(f"❌ Error removing friend: {e}")
            return {'success': False, 'error': str(e)}

    def update_user_profile(self, profile_id, updates):
        """Update user profile information"""
        try:
            allowed_fields = ['display_name', 'status', 'status_message', 'avatar_url', 'username']
            update_data = {k: v for k, v in updates.items() if k in allowed_fields}
            
            if not update_data:
                return {'success': False, 'error': 'No valid fields to update'}
            
            if 'username' in update_data:
                new_username = update_data['username'].lower()
                existing = self.user_profiles.find_one({
                    'username': new_username,
                    '_id': {'$ne': ObjectId(profile_id)}
                })
                if existing:
                    return {'success': False, 'error': 'Username already taken'}
            
            result = self.user_profiles.update_one(
                {'_id': ObjectId(profile_id)},
                {'$set': update_data}
            )
            
            if result.modified_count > 0:
                print(f"✅ Updated profile {profile_id}: {update_data}")
                return {'success': True, 'updated_fields': list(update_data.keys())}
            else:
                return {'success': False, 'error': 'No changes made'}
                
        except Exception as e:
            print(f"❌ Error updating user profile: {e}")
            return {'success': False, 'error': str(e)}

    def update_user_status_message(self, profile_id, status_message):
        """Update user status message"""
        try:
            result = self.user_profiles.update_one(
                {'_id': ObjectId(profile_id)},
                {'$set': {
                    'status_message': status_message,
                    'last_seen': datetime.utcnow()
                }}
            )
            
            if result.modified_count > 0:
                print(f"✅ Updated status message for {profile_id}: {status_message}")
                return {'success': True}
            else:
                return {'success': False, 'error': 'No changes made'}
                
        except Exception as e:
            print(f"❌ Error updating user status message: {e}")
            return {'success': False, 'error': str(e)}

    def get_chat_participants(self, chat_id):
        """Get all participants in a chat"""
        try:
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat:
                return []
            
            participants = self.user_profiles.find({
                '_id': {'$in': chat['participants']}
            })
            
            result = []
            for participant in participants:
                status = participant.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if participant.get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(participant['_id']),
                    'username': participant['username'],
                    'display_name': participant['display_name'],
                    'avatar_url': participant.get('avatar_url'),
                    'is_online': participant.get('is_online', False),
                    'status': status,
                    'last_seen': participant.get('last_seen')
                })
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting chat participants: {e}")
            return []

    def cleanup_old_sessions(self):
        """Clean up old sessions and update user statuses"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            result = self.user_profiles.update_many(
                {'last_seen': {'$lt': cutoff_time}},
                {'$set': {
                    'is_online': False,
                    'status': 'offline'
                }}
            )
            print(f"✅ Cleaned up {result.modified_count} old sessions")
        except Exception as e:
            print(f"❌ Error cleaning up sessions: {e}")

    def get_all_users(self, exclude_user_id=None):
        """Get all users for debugging"""
        try:
            query = {}
            if exclude_user_id:
                query['_id'] = {'$ne': ObjectId(exclude_user_id)}
            
            users = list(self.user_profiles.find(query))
            
            result = []
            for user in users:
                status = user.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if user.get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(user['_id']),
                    'username': user['username'],
                    'display_name': user.get('display_name', ''),
                    'status': status,
                    'is_online': user.get('is_online', False),
                    'created_at': user.get('created_at'),
                    'last_seen': user.get('last_seen')
                })
            
            return result
        except Exception as e:
            print(f"❌ Error getting all users: {e}")
            return []

    def get_friend_requests_sent(self, user_id):
        """Get friend requests sent by user"""
        try:
            requests = self.friend_requests.aggregate([
                {
                    '$match': {
                        'from_user_id': ObjectId(user_id),
                        'status': 'pending'
                    }
                },
                {
                    '$lookup': {
                        'from': 'user_profiles',
                        'localField': 'to_user_id',
                        'foreignField': '_id',
                        'as': 'receiver'
                    }
                },
                {
                    '$unwind': '$receiver'
                },
                {
                    '$sort': {'created_at': -1}
                }
            ])
            
            result = []
            for req in requests:
                status = req['receiver'].get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if req['receiver'].get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(req['_id']),
                    'to_user': {
                        '_id': str(req['receiver']['_id']),
                        'username': req['receiver']['username'],
                        'display_name': req['receiver']['display_name'],
                        'avatar_url': req['receiver'].get('avatar_url'),
                        'status': status,
                        'last_seen': req['receiver'].get('last_seen')
                    },
                    'created_at': req['created_at']
                })
            
            print(f"✅ Found {len(result)} sent requests for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting sent requests: {e}")
            return []

    def get_mutual_friends(self, user_id, other_user_id):
        """Get mutual friends between two users"""
        try:
            user = self.user_profiles.find_one({'_id': ObjectId(user_id)})
            other_user = self.user_profiles.find_one({'_id': ObjectId(other_user_id)})
            
            if not user or not other_user:
                return []
            
            user_friends = set(user.get('friends', []))
            other_friends = set(other_user.get('friends', []))
            mutual_friends_ids = user_friends.intersection(other_friends)
            
            if not mutual_friends_ids:
                return []
            
            mutual_friends = self.user_profiles.find({
                '_id': {'$in': list(mutual_friends_ids)}}
            )
            
            result = []
            for friend in mutual_friends:
                status = friend.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if friend.get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(friend['_id']),
                    'username': friend['username'],
                    'display_name': friend.get('display_name', friend['username']),
                    'avatar_url': friend.get('avatar_url'),
                    'is_online': friend.get('is_online', False),
                    'status': status,
                    'last_seen': friend.get('last_seen')
                })
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting mutual friends: {e}")
            return []

    def is_friends(self, user_id, other_user_id):
        """Check if two users are friends"""
        try:
            user = self.user_profiles.find_one({'_id': ObjectId(user_id)})
            if user and 'friends' in user:
                return ObjectId(other_user_id) in user['friends']
            return False
        except Exception as e:
            print(f"❌ Error checking friendship: {e}")
            return False

    def get_user_stats(self, user_id):
        """Get user statistics"""
        try:
            user = self.user_profiles.find_one({'_id': ObjectId(user_id)})
            if not user:
                return {}
            
            friends_count = len(user.get('friends', []))
            chats_count = len(user.get('chat_ids', []))
            
            messages_count = self.messages.count_documents({
                'sender_id': ObjectId(user_id)
            })
            
            return {
                'friends_count': friends_count,
                'chats_count': chats_count,
                'messages_count': messages_count,
                'account_age_days': (datetime.utcnow() - user.get('created_at', datetime.utcnow())).days
            }
            
        except Exception as e:
            print(f"❌ Error getting user stats: {e}")
            return {}

    def get_online_users_count(self):
        """Get count of online users"""
        try:
            count = self.user_profiles.count_documents({
                'status': 'online'
            })
            return count
        except Exception as e:
            print(f"❌ Error getting online users count: {e}")
            return 0

    def bulk_update_user_statuses(self, user_ids, status):
        """Update status for multiple users at once"""
        try:
            result = self.user_profiles.update_many(
                {'_id': {'$in': [ObjectId(uid) for uid in user_ids]}},
                {'$set': {
                    'status': status,
                    'is_online': status == 'online',
                    'last_seen': datetime.utcnow()
                }}
            )
            print(f"✅ Updated status to '{status}' for {result.modified_count} users")
            return result.modified_count
        except Exception as e:
            print(f"❌ Error bulk updating user statuses: {e}")
            return 0

    def cleanup_read_notifications(self, user_id):
        """Remove all read notifications for a user"""
        try:
            result = self.notifications.delete_many({
                'user_id': ObjectId(user_id),
                'is_read': True
            })
            print(f"✅ Cleaned up {result.deleted_count} read notifications for user {user_id}")
            return result.deleted_count
        except Exception as e:
            print(f"❌ Error cleaning up read notifications: {e}")
            return 0

    def delete_user_profile(self, user_profile_id, user_id):
        """Comprehensive user profile deletion - handles all associated data"""
        try:
            print(f"🗑️ Starting comprehensive profile deletion for user_profile_id: {user_profile_id}, user_id: {user_id}")
            
            # 1. Remove user from friends lists of all other users
            user_profile = self.user_profiles.find_one({'_id': ObjectId(user_profile_id)})
            if user_profile and 'friends' in user_profile:
                for friend_id in user_profile['friends']:
                    self.user_profiles.update_one(
                        {'_id': friend_id},
                        {'$pull': {'friends': ObjectId(user_profile_id)}}
                    )
                print(f"✅ Removed user from {len(user_profile['friends'])} friends' lists")
            
            # 2. Delete all friend requests involving this user
            friend_requests_deleted = self.friend_requests.delete_many({
                '$or': [
                    {'from_user_id': ObjectId(user_profile_id)},
                    {'to_user_id': ObjectId(user_profile_id)}
                ]
            })
            print(f"✅ Deleted {friend_requests_deleted.deleted_count} friend requests")
            
            # 3. Get all chats the user is in
            user_chats = list(self.chats.find({
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
                self.chats.update_many(
                    {'_id': {'$in': chats_to_update}},
                    {'$pull': {'participants': ObjectId(user_profile_id)}}
                )
                print(f"✅ Removed user from {len(chats_to_update)} group chats")
            
            # Delete individual chats
            if chats_to_delete:
                # Delete messages from these chats
                messages_deleted = self.messages.delete_many({
                    'chat_id': {'$in': chats_to_delete}
                })
                # Delete the chats themselves
                chats_deleted = self.chats.delete_many({
                    '_id': {'$in': chats_to_delete}
                })
                print(f"✅ Deleted {chats_deleted.deleted_count} individual chats and {messages_deleted.deleted_count} messages")
            
            # 5. Delete all messages sent by the user
            user_messages_deleted = self.messages.delete_many({
                'sender_id': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted {user_messages_deleted.deleted_count} messages sent by user")
            
            # 6. Delete notifications for the user
            notifications_deleted = self.notifications.delete_many({
                'user_id': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted {notifications_deleted.deleted_count} notifications")
            
            # 7. Delete chat themes for the user
            chat_themes_deleted = self.chat_themes.delete_many({
                'user_profile_id': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted {chat_themes_deleted.deleted_count} chat themes")
            
            # 8. Delete message edits by the user
            message_edits_deleted = self.message_edits.delete_many({
                'edited_by': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted {message_edits_deleted.deleted_count} message edits")
            
            # 9. Delete user deleted messages records
            user_deleted_messages_deleted = self.user_deleted_messages.delete_many({
                'user_id': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted {user_deleted_messages_deleted.deleted_count} user deleted messages records")
            
            # 10. Finally delete the user profile
            profile_deleted = self.user_profiles.delete_one({
                '_id': ObjectId(user_profile_id)
            })
            print(f"✅ Deleted user profile: {profile_deleted.deleted_count} profile")
            
            # 11. Check if this was the last profile for the user account
            remaining_profiles = self.user_profiles.count_documents({
                'user_id': ObjectId(user_id)
            })
            
            if remaining_profiles == 0:
                # Delete the user account too
                self.users.delete_one({'_id': ObjectId(user_id)})
                print(f"✅ Deleted user account (no remaining profiles)")
            
            print("🎉 Profile deletion completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error in delete_user_profile: {e}")
            import traceback
            traceback.print_exc()
            return False

    # NEW METHODS FOR GROUP MANAGEMENT

    def get_group_participants(self, chat_id):
        """Get all participants in a group chat with detailed info"""
        try:
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat or not chat.get('is_group', False):
                return []
            
            participants = self.user_profiles.find({
                '_id': {'$in': chat['participants']}
            })
            
            result = []
            for participant in participants:
                status = participant.get('status', 'offline')
                if status not in ['online', 'offline', 'away']:
                    status = 'online' if participant.get('is_online', False) else 'offline'
                
                result.append({
                    '_id': str(participant['_id']),
                    'username': participant['username'],
                    'display_name': participant.get('display_name', participant['username']),
                    'avatar_url': participant.get('avatar_url'),
                    'is_online': participant.get('is_online', False),
                    'status': status,
                    'status_message': participant.get('status_message', ''),
                    'last_seen': participant.get('last_seen')
                })
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting group participants: {e}")
            return []

    def delete_group(self, chat_id, user_id):
        """Delete a group chat and all associated data"""
        try:
            # Verify the chat exists and user is a participant
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat:
                return {'success': False, 'error': 'Group not found'}
            
            if not chat.get('is_group', False):
                return {'success': False, 'error': 'Can only delete group chats'}
            
            # Check if user is a participant
            if ObjectId(user_id) not in chat['participants']:
                return {'success': False, 'error': 'Not authorized to delete this group'}
            
            # Delete all messages in the group
            messages_deleted = self.messages.delete_many({'chat_id': ObjectId(chat_id)})
            print(f"✅ Deleted {messages_deleted.deleted_count} messages from group {chat_id}")
            
            # Delete the chat
            chat_deleted = self.chats.delete_one({'_id': ObjectId(chat_id)})
            
            # Remove chat reference from all participants
            self.user_profiles.update_many(
                {'chat_ids': chat_id},
                {'$pull': {'chat_ids': chat_id}}
            )
            
            # Delete chat themes for this group
            self.chat_themes.delete_many({'chat_id': ObjectId(chat_id)})
            
            # Delete file metadata for this group
            self.files.delete_many({'chat_id': ObjectId(chat_id)})
            
            # Delete message reactions for messages in this group
            self.message_reactions.delete_many({'message_id': {'$in': [msg['_id'] for msg in self.messages.find({'chat_id': ObjectId(chat_id)})]}})
            
            if chat_deleted.deleted_count > 0:
                print(f"✅ Group {chat_id} deleted by user {user_id}")
                return {
                    'success': True, 
                    'message': 'Group deleted successfully',
                    'messages_deleted': messages_deleted.deleted_count
                }
            else:
                return {'success': False, 'error': 'Failed to delete group'}
            
        except Exception as e:
            print(f"❌ Error deleting group: {e}")
            return {'success': False, 'error': str(e)}

    def get_user_groups(self, user_id):
        """Get all group chats for a user"""
        try:
            groups = self.chats.aggregate([
                {
                    '$match': {
                        'participants': ObjectId(user_id),
                        'is_group': True
                    }
                },
                {
                    '$lookup': {
                        'from': 'messages',
                        'let': {'chat_id': '$_id'},
                        'pipeline': [
                            {'$match': {'$expr': {'$eq': ['$chat_id', '$$chat_id']}}},
                            {'$sort': {'timestamp': -1}},
                            {'$limit': 1}
                        ],
                        'as': 'last_message'
                    }
                },
                {
                    '$sort': {'last_message_at': -1}
                }
            ])
            
            result = []
            for group in groups:
                group_data = {
                    '_id': str(group['_id']),
                    'name': group.get('name', 'Group Chat'),
                    'is_group': True,
                    'last_message_at': group.get('last_message_at'),
                    'participants': [str(pid) for pid in group['participants']],
                    'participant_count': len(group['participants'])
                }
                
                if group.get('last_message'):
                    last_msg = group['last_message'][0]
                    group_data['last_message'] = {
                        'content': last_msg['content'],
                        'sender_id': str(last_msg['sender_id']),
                        'timestamp': last_msg['timestamp'],
                        'type': last_msg.get('type', 'text')
                    }
                
                result.append(group_data)
            
            print(f"✅ Found {len(result)} groups for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting user groups: {e}")
            return []

    def get_user_individual_chats(self, user_id):
        """Get all individual chats for a user"""
        try:
            chats = self.chats.aggregate([
                {
                    '$match': {
                        'participants': ObjectId(user_id),
                        'is_group': False
                    }
                },
                {
                    '$lookup': {
                        'from': 'messages',
                        'let': {'chat_id': '$_id'},
                        'pipeline': [
                            {'$match': {'$expr': {'$eq': ['$chat_id', '$$chat_id']}}},
                            {'$sort': {'timestamp': -1}},
                            {'$limit': 1}
                        ],
                        'as': 'last_message'
                    }
                },
                {
                    '$sort': {'last_message_at': -1}
                }
            ])
            
            seen_chats = set()
            result = []
            
            for chat in chats:
                if len(chat['participants']) == 2:
                    participants = sorted([str(pid) for pid in chat['participants']])
                    chat_key = tuple(participants)
                    
                    if chat_key in seen_chats:
                        continue
                    seen_chats.add(chat_key)
                
                chat_name = chat.get('name', 'Chat')
                if len(chat['participants']) == 2:
                    other_participant_id = None
                    for participant_id in chat['participants']:
                        if str(participant_id) != user_id:
                            other_participant_id = participant_id
                            break
                    
                    if other_participant_id:
                        other_user = self.user_profiles.find_one({'_id': other_participant_id})
                        if other_user:
                            chat_name = other_user.get('display_name', other_user['username'])
                
                chat_data = {
                    '_id': str(chat['_id']),
                    'name': chat_name,
                    'is_group': False,
                    'last_message_at': chat.get('last_message_at'),
                    'participants': [str(pid) for pid in chat['participants']]
                }
                
                if chat.get('last_message'):
                    last_msg = chat['last_message'][0]
                    chat_data['last_message'] = {
                        'content': last_msg['content'],
                        'sender_id': str(last_msg['sender_id']),
                        'timestamp': last_msg['timestamp'],
                        'type': last_msg.get('type', 'text')
                    }
                
                result.append(chat_data)
            
            print(f"✅ Found {len(result)} individual chats for user {user_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting user individual chats: {e}")
            return []

    def add_participant_to_group(self, chat_id, user_id, adder_id):
        """Add a participant to a group chat"""
        try:
            # Verify the chat exists and is a group
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat or not chat.get('is_group', False):
                return {'success': False, 'error': 'Group not found'}
            
            # Check if adder is a participant
            if ObjectId(adder_id) not in chat['participants']:
                return {'success': False, 'error': 'Not authorized to add participants'}
            
            # Check if user is already a participant
            if ObjectId(user_id) in chat['participants']:
                return {'success': False, 'error': 'User is already in the group'}
            
            # Add user to participants
            result = self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {'$addToSet': {'participants': ObjectId(user_id)}}
            )
            
            # Add chat to user's chat_ids
            self.user_profiles.update_one(
                {'_id': ObjectId(user_id)},
                {'$addToSet': {'chat_ids': chat_id}}
            )
            
            # Create notification for the added user
            adder_profile = self.get_user_profile(adder_id)
            adder_name = adder_profile.get('display_name', adder_profile['username']) if adder_profile else 'Unknown'
            
            self._create_notification(
                user_id,
                'added_to_group',
                f'{adder_name} added you to the group "{chat.get("name", "Group Chat")}"',
                {
                    'chat_id': chat_id,
                    'group_name': chat.get('name', 'Group Chat'),
                    'added_by': adder_id,
                    'added_by_name': adder_name
                }
            )
            
            print(f"✅ User {user_id} added to group {chat_id} by {adder_id}")
            return {'success': True, 'message': 'User added to group successfully'}
            
        except Exception as e:
            print(f"❌ Error adding participant to group: {e}")
            return {'success': False, 'error': str(e)}

    def remove_participant_from_group(self, chat_id, user_id, remover_id):
        """Remove a participant from a group chat"""
        try:
            # Verify the chat exists and is a group
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat or not chat.get('is_group', False):
                return {'success': False, 'error': 'Group not found'}
            
            # Check if remover is a participant
            if ObjectId(remover_id) not in chat['participants']:
                return {'success': False, 'error': 'Not authorized to remove participants'}
            
            # Check if user is a participant
            if ObjectId(user_id) not in chat['participants']:
                return {'success': False, 'error': 'User is not in the group'}
            
            # Cannot remove yourself (use leave_group instead)
            if user_id == remover_id:
                return {'success': False, 'error': 'Cannot remove yourself from group'}
            
            # Remove user from participants
            result = self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {'$pull': {'participants': ObjectId(user_id)}}
            )
            
            # Remove chat from user's chat_ids
            self.user_profiles.update_one(
                {'_id': ObjectId(user_id)},
                {'$pull': {'chat_ids': chat_id}}
            )
            
            # Create notification for the removed user
            remover_profile = self.get_user_profile(remover_id)
            remover_name = remover_profile.get('display_name', remover_profile['username']) if remover_profile else 'Unknown'
            
            self._create_notification(
                user_id,
                'removed_from_group',
                f'{remover_name} removed you from the group "{chat.get("name", "Group Chat")}"',
                {
                    'chat_id': chat_id,
                    'group_name': chat.get('name', 'Group Chat'),
                    'removed_by': remover_id,
                    'removed_by_name': remover_name
                }
            )
            
            print(f"✅ User {user_id} removed from group {chat_id} by {remover_id}")
            return {'success': True, 'message': 'User removed from group successfully'}
            
        except Exception as e:
            print(f"❌ Error removing participant from group: {e}")
            return {'success': False, 'error': str(e)}

    def leave_group(self, chat_id, user_id):
        """Leave a group chat"""
        try:
            # Verify the chat exists and is a group
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat or not chat.get('is_group', False):
                return {'success': False, 'error': 'Group not found'}
            
            # Check if user is a participant
            if ObjectId(user_id) not in chat['participants']:
                return {'success': False, 'error': 'You are not in this group'}
            
            # Remove user from participants
            result = self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {'$pull': {'participants': ObjectId(user_id)}}
            )
            
            # Remove chat from user's chat_ids
            self.user_profiles.update_one(
                {'_id': ObjectId(user_id)},
                {'$pull': {'chat_ids': chat_id}}
            )
            
            # Notify other participants
            user_profile = self.get_user_profile(user_id)
            user_name = user_profile.get('display_name', user_profile['username']) if user_profile else 'Unknown'
            
            for participant_id in chat['participants']:
                if str(participant_id) != user_id:
                    self._create_notification(
                        str(participant_id),
                        'user_left_group',
                        f'{user_name} left the group "{chat.get("name", "Group Chat")}"',
                        {
                            'chat_id': chat_id,
                            'group_name': chat.get('name', 'Group Chat'),
                            'user_id': user_id,
                            'user_name': user_name
                        }
                    )
            
            print(f"✅ User {user_id} left group {chat_id}")
            return {'success': True, 'message': 'Left group successfully'}
            
        except Exception as e:
            print(f"❌ Error leaving group: {e}")
            return {'success': False, 'error': str(e)}

    def update_group_name(self, chat_id, new_name, user_id):
        """Update group name"""
        try:
            # Verify the chat exists and is a group
            chat = self.chats.find_one({'_id': ObjectId(chat_id)})
            if not chat or not chat.get('is_group', False):
                return {'success': False, 'error': 'Group not found'}
            
            # Check if user is a participant
            if ObjectId(user_id) not in chat['participants']:
                return {'success': False, 'error': 'Not authorized to update group name'}
            
            # Update group name
            result = self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {'$set': {'name': new_name}}
            )
            
            # Notify all participants
            user_profile = self.get_user_profile(user_id)
            user_name = user_profile.get('display_name', user_profile['username']) if user_profile else 'Unknown'
            
            for participant_id in chat['participants']:
                if str(participant_id) != user_id:
                    self._create_notification(
                        str(participant_id),
                        'group_name_updated',
                        f'{user_name} changed the group name to "{new_name}"',
                        {
                            'chat_id': chat_id,
                            'old_name': chat.get('name', 'Group Chat'),
                            'new_name': new_name,
                            'updated_by': user_id,
                            'updated_by_name': user_name
                        }
                    )
            
            print(f"✅ Group {chat_id} name updated to '{new_name}' by {user_id}")
            return {'success': True, 'message': 'Group name updated successfully'}
            
        except Exception as e:
            print(f"❌ Error updating group name: {e}")
            return {'success': False, 'error': str(e)}

    # NEW PERSISTENCE METHODS

    def get_chat_messages_with_persistence(self, chat_id, user_id, limit=50):
        """Get messages for a chat with user-specific persistence"""
        try:
            # First get all messages for the chat
            messages = self.messages.find(
                {'chat_id': ObjectId(chat_id)}
            ).sort('timestamp', 1).limit(limit)
            
            # Get messages deleted by this user
            user_deleted_messages = self.user_deleted_messages.find({
                'user_id': ObjectId(user_id)
            })
            deleted_message_ids = [msg['message_id'] for msg in user_deleted_messages]
            
            result = []
            for message in messages:
                message_id = message['_id']
                
                # Skip messages deleted by this user
                if message_id in deleted_message_ids:
                    continue
                
                # Check if message is soft-deleted for everyone
                if message.get('is_deleted', False):
                    # Only show deletion notice if user should see it
                    if (message.get('deleted_by') and 
                        str(message['deleted_by']) != user_id and
                        message['sender_id'] != ObjectId(user_id)):
                        # Show deletion notice to other participants
                        message_data = {
                            '_id': str(message['_id']),
                            'chat_id': str(message['chat_id']),
                            'sender_id': str(message['sender_id']),
                            'content': 'This message was deleted',
                            'type': message.get('type', 'text'),
                            'timestamp': message['timestamp'],
                            'is_edited': False,
                            'is_deleted': True,
                            'edited_at': None,
                            'read_by': [],
                            'edit_count': 0
                        }
                        result.append(message_data)
                    continue
                
                # Regular message processing
                message_data = {
                    '_id': str(message['_id']),
                    'chat_id': str(message['chat_id']),
                    'sender_id': str(message['sender_id']),
                    'content': message['content'],
                    'type': message.get('type', 'text'),
                    'timestamp': message['timestamp'],
                    'is_edited': message.get('is_edited', False),
                    'is_deleted': message.get('is_deleted', False),
                    'edited_at': message.get('edited_at'),
                    'read_by': [str(user_id) for user_id in message.get('read_by', [])] if message.get('read_by') else [],
                    'edit_count': message.get('edit_count', 0)
                }
                
                # Add file metadata if present
                if message.get('file_metadata'):
                    message_data['file_metadata'] = message['file_metadata']
                    # Ensure file_metadata has proper string IDs
                    if 'uploaded_by' in message_data['file_metadata']:
                        message_data['file_metadata']['uploaded_by'] = str(message_data['file_metadata']['uploaded_by'])
                
                result.append(message_data)
            
            print(f"✅ Found {len(result)} persistent messages for user {user_id} in chat {chat_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error getting persistent chat messages: {e}")
            return []

    def _format_message_for_response(self, message_data):
        """Format message data for API response"""
        try:
            # Get sender info
            sender_profile = self.get_user_profile(str(message_data['sender_id']))
            sender_username = sender_profile.get('display_name', sender_profile['username']) if sender_profile else 'Unknown'
            
            formatted_message = {
                'message_id': str(message_data['_id']),
                'chat_id': str(message_data['chat_id']),
                'sender_id': str(message_data['sender_id']),
                'sender_username': sender_username,
                'content': message_data['content'],
                'type': message_data.get('message_type', 'text'),
                'timestamp': message_data['timestamp'],
                'is_edited': message_data.get('is_edited', False),
                'is_deleted': message_data.get('is_deleted', False)
            }
            
            # Add file metadata if present
            if message_data.get('file_metadata'):
                file_meta = message_data['file_metadata'].copy()
                # Convert ObjectId to string for JSON serialization
                if 'uploaded_by' in file_meta:
                    file_meta['uploaded_by'] = str(file_meta['uploaded_by'])
                formatted_message['file_metadata'] = file_meta
            
            return formatted_message
            
        except Exception as e:
            print(f"❌ Error formatting message for response: {e}")
            return None

    def get_chat_with_theme(self, chat_id, user_id):
        """Get chat details with theme preference"""
        try:
            chat = self.chats.find_one({
                '_id': ObjectId(chat_id),
                'participants': ObjectId(user_id)
            })
            
            if not chat:
                return None
                
            chat['_id'] = str(chat['_id'])
            chat['participants'] = [str(pid) for pid in chat['participants']]
            
            # Get theme preference for this user
            theme_pref = self.get_chat_theme(user_id, chat_id)
            if theme_pref:
                chat['current_theme'] = theme_pref['theme_name']
            else:
                chat['current_theme'] = 'default'
            
            # Set chat name for individual chats
            if not chat.get('is_group', False) and len(chat['participants']) == 2:
                other_participant_id = None
                for participant_id in chat['participants']:
                    if participant_id != user_id:
                        other_participant_id = participant_id
                        break
                
                if other_participant_id:
                    other_user = self.user_profiles.find_one({'_id': ObjectId(other_participant_id)})
                    if other_user:
                        chat['name'] = other_user.get('display_name', other_user['username'])
            
            return chat
            
        except Exception as e:
            print(f"❌ Error getting chat with theme: {e}")
            return None
        
    def create_message_with_persistence(self, chat_id, sender_id, content, message_type='text', file_metadata=None):
        """Create a new message with proper persistence handling"""
        try:
            message_data = {
                'chat_id': ObjectId(chat_id),
                'sender_id': ObjectId(sender_id),
                'content': content,
                'message_type': message_type,
                'timestamp': datetime.utcnow(),
                'is_edited': False,
                'is_deleted': False,
                'read_by': [ObjectId(sender_id)]  # Mark as read by sender
            }
            
            if file_metadata and message_type == 'file':
                # Ensure file_metadata has proper ObjectId for uploaded_by
                if 'uploaded_by' in file_metadata:
                    file_metadata['uploaded_by'] = ObjectId(file_metadata['uploaded_by'])
                
                # Convert any datetime strings back to datetime objects for storage
                if 'uploaded_at' in file_metadata and isinstance(file_metadata['uploaded_at'], str):
                    try:
                        file_metadata['uploaded_at'] = datetime.fromisoformat(file_metadata['uploaded_at'].replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        file_metadata['uploaded_at'] = datetime.utcnow()
                
                message_data['file_metadata'] = file_metadata
            
            result = self.messages.insert_one(message_data)
            
            # Update chat's last_activity and last_message_at
            self.chats.update_one(
                {'_id': ObjectId(chat_id)},
                {
                    '$set': {
                        'last_activity': datetime.utcnow(),
                        'last_message_at': datetime.utcnow()
                    }
                }
            )
            
            # Get the complete message with all fields
            message_data['_id'] = result.inserted_id
            return self._format_message_for_response(message_data)
            
        except Exception as e:
            print(f"❌ Error creating persistent message: {e}")
            return None

# Create a global instance
db_manager = DatabaseManager()