from flask import redirect, session, url_for
from google.auth.transport import requests
from google.oauth2 import id_token
import requests as http_requests
from config import Config

class AuthManager:
    def __init__(self):
        self.client_id = Config.GOOGLE_CLIENT_ID
        self.client_secret = Config.GOOGLE_CLIENT_SECRET
    
    def initiate_oauth(self):
        """Create Google OAuth2 URL"""
        from urllib.parse import urlencode
        
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'scope': 'openid email profile',
            'redirect_uri': 'http://localhost:5000/auth/callback',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return redirect(auth_url)
    
    def handle_callback(self, request):
        """Handle OAuth2 callback and verify token"""
        code = request.args.get('code')
        if not code:
            return None
        
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': 'http://localhost:5000/auth/callback'
        }
        
        token_response = http_requests.post(token_url, data=token_data)
        if token_response.status_code != 200:
            return None
        
        tokens = token_response.json()
        id_token_str = tokens.get('id_token')
        
        if not id_token_str:
            return None
        
        # Verify and decode ID token
        try:
            id_info = id_token.verify_oauth2_token(
                id_token_str, 
                requests.Request(), 
                self.client_id
            )
            
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            return {
                'sub': id_info['sub'],
                'email': id_info['email'],
                'name': id_info.get('name', ''),
                'picture': id_info.get('picture', ''),
                'given_name': id_info.get('given_name', ''),
                'family_name': id_info.get('family_name', '')
            }
            
        except ValueError:
            return None