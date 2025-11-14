"""
Yahoo Fantasy API Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Yahoo OAuth 2.0 Settings
YAHOO_CLIENT_ID = os.getenv('YAHOO_CLIENT_ID', '')
YAHOO_CLIENT_SECRET = os.getenv('YAHOO_CLIENT_SECRET', '')
YAHOO_REDIRECT_URI = os.getenv('YAHOO_REDIRECT_URI', 'http://localhost:5000/auth/yahoo/callback')

# Yahoo Fantasy API Endpoints
YAHOO_AUTH_URL = 'https://api.login.yahoo.com/oauth2/request_auth'
YAHOO_TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token'
YAHOO_API_BASE_URL = 'https://fantasysports.yahooapis.com/fantasy/v2'

# Database Settings
DATABASE_URL = os.getenv('YAHOO_DATABASE_URL', 'sqlite:///yahoo_fantasy.db')

# Cache Settings
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache', 'yahoo')
CACHE_TIMEOUT = 300  # 5 minutes for league data
PLAYER_CACHE_TIMEOUT = 3600  # 1 hour for player stats

# API Rate Limiting
RATE_LIMIT_CALLS = 10000  # Yahoo allows 10k calls per day
RATE_LIMIT_PERIOD = 86400  # 24 hours in seconds

# Season Settings
CURRENT_GAME_KEY = 'nba'  # For NBA games
NBA_GAME_CODE = '418'  # 2024-25 season (updates each year)

# Valid NBA game keys by season
# 
# Note: Game keys increment each year but not always sequentially
# Use /yahoo/games endpoint to discover current season's game_key
NBA_GAME_KEYS = {
    '2024-25': '466',  # 2024-25 season (confirmed: season=2025)
    '2023-24': '428',  # 2023-24 season (season=2023)
    '2022-23': '418',
    '2021-22': '406',
    '2020-21': '395',
}

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)
