import os

class Config:
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # MongoDB Configuration
    MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/hangspace')
    
    # Google OAuth2 Configuration
    GOOGLE_CLIENT_ID = '154544422249-lv6k6ejvn8usjf90h10ce9jgd4i0b2il.apps.googleusercontent.com'
    GOOGLE_CLIENT_SECRET = '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'
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
    
    # Application Settings
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
    MESSAGE_LIMIT = 50