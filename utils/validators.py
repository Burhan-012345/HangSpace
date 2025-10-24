import re
from datetime import datetime

class Validators:
    @staticmethod
    def validate_username(username):
        """Validate username format"""
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters long"
        
        if len(username) > 20:
            return False, "Username must be less than 20 characters"
        
        if not re.match(r'^[a-z0-9_]+$', username):
            return False, "Username can only contain lowercase letters, numbers, and underscores"
        
        return True, "Valid username"
    
    @staticmethod
    def validate_display_name(display_name):
        """Validate display name format"""
        if not display_name or len(display_name.strip()) < 2:
            return False, "Display name must be at least 2 characters long"
        
        if len(display_name) > 30:
            return False, "Display name must be less than 30 characters"
        
        return True, "Valid display name"
    
    @staticmethod
    def validate_message_content(content):
        """Validate message content"""
        if not content or len(content.strip()) == 0:
            return False, "Message cannot be empty"
        
        if len(content) > 1000:
            return False, "Message must be less than 1000 characters"
        
        return True, "Valid message"
    
    @staticmethod
    def sanitize_input(text):
        """Basic input sanitization"""
        if not text:
            return text
        
        # Remove potentially dangerous characters
        text = re.sub(r'[<>&"\'\\]', '', text)
        return text.strip()