"""
Yahoo OAuth2 Authentication Module
Handles OAuth2 flow for Yahoo Fantasy Sports API access
"""

import requests
from requests_oauthlib import OAuth2Session
import base64
import json


class YahooAuth:
    """Handles Yahoo OAuth2 authentication flow"""
    
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = 'https://api.login.yahoo.com/oauth2'
        self.redirect_uri = 'http://localhost:5000/callback'  # Update for production
        
        # Yahoo OAuth2 endpoints
        self.authorization_base_url = f'{self.base_url}/request_auth'
        self.token_url = f'{self.base_url}/get_token'
        
    def get_authorization_url(self):
        """Generate authorization URL for OAuth2 flow"""
        yahoo = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=['fspt-r']  # Fantasy Sports read permission
        )
        
        authorization_url, state = yahoo.authorization_url(
            self.authorization_base_url
        )
        
        return authorization_url
    
    def get_access_token(self, authorization_code):
        """Exchange authorization code for access token"""
        
        # Prepare authentication header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'code': authorization_code,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(self.token_url, headers=headers, data=data)
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        tokens = response.json()
        return tokens
    
    def refresh_access_token(self, refresh_token):
        """Refresh an expired access token"""
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(self.token_url, headers=headers, data=data)
        
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        
        return response.json()
    
    def make_authenticated_request(self, url, access_token, method='GET', **kwargs):
        """Make an authenticated request to Yahoo API"""
        
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {access_token}'
        headers['Accept'] = 'application/json'
        
        kwargs['headers'] = headers
        
        if method.upper() == 'GET':
            response = requests.get(url, **kwargs)
        elif method.upper() == 'POST':
            response = requests.post(url, **kwargs)
        elif method.upper() == 'PUT':
            response = requests.put(url, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code == 401:
            raise Exception("Access token expired or invalid")
        elif response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
        
        return response.json()