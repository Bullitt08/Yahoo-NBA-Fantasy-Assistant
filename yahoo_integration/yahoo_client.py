"""
Yahoo Fantasy Basketball API Client

Handles all interactions with Yahoo Fantasy Sports API v2
including OAuth 2.0 authentication and data retrieval.
"""

import json
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import requests
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient

from .config import (
    YAHOO_CLIENT_ID,
    YAHOO_CLIENT_SECRET,
    YAHOO_REDIRECT_URI,
    YAHOO_AUTH_URL,
    YAHOO_TOKEN_URL,
    YAHOO_API_BASE_URL,
    CACHE_DIR,
    CACHE_TIMEOUT,
    NBA_GAME_KEYS
)
from .models import League, Team, YahooPlayer, MatchupWeek


class YahooFantasyClient:
    """
    Yahoo Fantasy Sports API v2 Client for Basketball
    
    Features:
    - OAuth 2.0 authentication with automatic token refresh
    - League, team, and player data retrieval
    - Caching for improved performance
    - Rate limiting to respect API limits
    - XML to JSON parsing
    """
    
    def __init__(self, client_id: str = None, client_secret: str = None):
        """Initialize Yahoo Fantasy API client"""
        self.client_id = client_id or YAHOO_CLIENT_ID
        self.client_secret = client_secret or YAHOO_CLIENT_SECRET
        self.redirect_uri = YAHOO_REDIRECT_URI
        
        # OAuth session
        self.oauth = None
        self.token = None
        
        # Rate limiting
        self.last_request_time = None
        self.min_request_interval = 0.1  # 100ms between requests
        
        # Cache
        self.cache = {}
        self.cache_timestamps = {}
    
    def get_authorization_url(self) -> tuple:
        """
        Get Yahoo OAuth authorization URL for user to visit
        
        Returns:
            (authorization_url, state)
        """
        self.oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=['fspt-r']  # Fantasy sports read permission
        )
        
        authorization_url, state = self.oauth.authorization_url(YAHOO_AUTH_URL)
        return authorization_url, state
    
    def fetch_token(self, authorization_response: str) -> Dict:
        """
        Exchange authorization code for access token
        
        Args:
            authorization_response: The full callback URL with code
            
        Returns:
            Token dictionary
        """
        if not self.oauth:
            self.oauth = OAuth2Session(
                self.client_id,
                redirect_uri=self.redirect_uri
            )
        
        self.token = self.oauth.fetch_token(
            YAHOO_TOKEN_URL,
            authorization_response=authorization_response,
            client_secret=self.client_secret
        )
        
        return self.token
    
    def get_user_info(self) -> Dict:
        """
        Get current user's Yahoo profile information
        
        Returns:
            User info including GUID and email
        """
        try:
            response = self._make_request('/users;use_login=1')
            
            if response and 'fantasy_content' in response:
                users = response['fantasy_content'].get('users', {})
                if users and '0' in users and 'user' in users['0']:
                    user = users['0']['user'][0]
                    return {
                        'guid': user.get('guid', ''),
                        'email': user.get('email', ''),
                        'nickname': user.get('nickname', '')
                    }
            
            return {}
        except Exception as e:
            print(f"Error getting user info: {e}")
            return {}
    
    def refresh_token(self, refresh_token: str) -> Dict:
        """
        Refresh expired access token
        
        Args:
            refresh_token: The refresh token from previous authentication
            
        Returns:
            New token dictionary
        """
        extra = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        
        self.oauth = OAuth2Session(self.client_id, token=self.token)
        self.token = self.oauth.refresh_token(
            YAHOO_TOKEN_URL,
            refresh_token=refresh_token,
            **extra
        )
        
        return self.token
    
    def set_token(self, token: Dict):
        """Set existing token for authenticated requests"""
        self.token = token
        self.oauth = OAuth2Session(
            self.client_id,
            token=token
        )
    
    def _rate_limit(self):
        """Implement rate limiting"""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
        
        self.last_request_time = time.time()
    
    def _get_cached(self, key: str, timeout: int = CACHE_TIMEOUT) -> Optional[Any]:
        """Get cached data if available and not expired"""
        if key in self.cache:
            timestamp = self.cache_timestamps.get(key)
            if timestamp and (time.time() - timestamp) < timeout:
                return self.cache[key]
        return None
    
    def _set_cache(self, key: str, data: Any):
        """Set cache data with timestamp"""
        self.cache[key] = data
        self.cache_timestamps[key] = time.time()
    
    def _make_request(self, endpoint: str, use_cache: bool = True, cache_timeout: int = CACHE_TIMEOUT) -> str:
        """
        Make authenticated API request
        
        Args:
            endpoint: API endpoint (e.g., '/users;use_login=1/games')
            use_cache: Whether to use cached response
            cache_timeout: Cache timeout in seconds
            
        Returns:
            Response text (XML)
        """
        if not self.oauth or not self.token:
            raise ValueError("Not authenticated. Call set_token() or fetch_token() first.")
        
        # Check if token is expired or expiring soon
        if 'expires_at' in self.token:
            import time
            # Refresh if token expires in less than 5 minutes
            if time.time() > (self.token['expires_at'] - 300):
                if 'refresh_token' in self.token:
                    print("[DEBUG] Token expired or expiring soon, refreshing...")
                    try:
                        self.refresh_token(self.token['refresh_token'])
                    except Exception as e:
                        print(f"[ERROR] Failed to refresh token: {e}")
                        raise Exception(f"token_expired: {str(e)}")
        
        # Check cache
        cache_key = f"request_{endpoint}"
        if use_cache:
            cached = self._get_cached(cache_key, cache_timeout)
            if cached:
                return cached
        
        # Rate limiting
        self._rate_limit()
        
        # Make request
        url = f"{YAHOO_API_BASE_URL}{endpoint}"
        
        try:
            response = self.oauth.get(url)
            
            if response.status_code == 401 or response.status_code == 403:
                # Token expired or forbidden, try to refresh
                if 'refresh_token' in self.token:
                    print(f"[DEBUG] Got {response.status_code}, attempting token refresh...")
                    try:
                        self.refresh_token(self.token['refresh_token'])
                        # Recreate session with new token
                        self.oauth = OAuth2Session(self.client_id, token=self.token)
                        response = self.oauth.get(url)
                        print("[DEBUG] ✅ Token refreshed successfully, retry succeeded")
                    except Exception as refresh_error:
                        print(f"[ERROR] Token refresh failed: {refresh_error}")
                        raise Exception(f"token_refresh_failed: {str(refresh_error)}")
                else:
                    raise Exception("token_expired_no_refresh")
            
            response.raise_for_status()
            
            # Cache response
            self._set_cache(cache_key, response.text)
            
            return response.text
            
        except Exception as e:
            # Clear cache on error
            if cache_key in self.cache:
                del self.cache[cache_key]
            if 'token_expired' in str(e).lower() or 'unauthorized' in str(e).lower() or '401' in str(e):
                raise Exception("token_expired")
            raise
    
    def _parse_xml_to_dict(self, xml_string: str) -> Dict:
        """Parse Yahoo XML response to dictionary"""
        root = ET.fromstring(xml_string)
        
        # Remove namespace prefixes for easier parsing
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
        
        return self._element_to_dict(root)
    
    def _element_to_dict(self, element: ET.Element) -> Any:
        """Convert XML element to dictionary recursively"""
        # If element has no children, return its text
        if len(element) == 0:
            return element.text
        
        # If element has children, process them
        result = {}
        for child in element:
            child_data = self._element_to_dict(child)
            
            # Handle multiple children with same tag
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data
        
        return result
    
    def get_user_leagues(self, game_key: str = 'nba', season: str = '2024-25') -> List[League]:
        """
        Get all fantasy leagues for the authenticated user
        
        Args:
            game_key: Game type (e.g., 'nba')
            season: Season year (e.g., '2024-25')
            
        Returns:
            List of League objects
        """
        game_code = NBA_GAME_KEYS.get(season, NBA_GAME_KEYS['2024-25'])
        endpoint = f'/users;use_login=1/games;game_keys={game_code}/leagues'
        
        xml_response = self._make_request(endpoint)
        print(f"[DEBUG] Raw XML Response:\n{xml_response[:500]}...")  # Print first 500 chars
        
        data = self._parse_xml_to_dict(xml_response)
        print(f"[DEBUG] Parsed data structure: {list(data.keys())}")
        print(f"[DEBUG] Full parsed data: {json.dumps(data, indent=2)[:1000]}...")
        
        leagues = []
        
        # Navigate XML structure
        try:
            users = data.get('users', {})
            print(f"[DEBUG] users type: {type(users)}, keys: {list(users.keys()) if isinstance(users, dict) else 'N/A'}")
            
            if isinstance(users, dict):
                user = users.get('user', {})
                print(f"[DEBUG] user type: {type(user)}, keys: {list(user.keys()) if isinstance(user, dict) else 'N/A'}")
                
                games = user.get('games', {}) if user else {}
                print(f"[DEBUG] games type: {type(games)}, keys: {list(games.keys()) if isinstance(games, dict) else 'N/A'}")
                
                game = games.get('game', {}) if games else {}
                print(f"[DEBUG] game type: {type(game)}, keys: {list(game.keys()) if isinstance(game, dict) else 'N/A'}")
                
                leagues_data = game.get('leagues', {}) if game else {}
                print(f"[DEBUG] leagues_data type: {type(leagues_data)}, keys: {list(leagues_data.keys()) if isinstance(leagues_data, dict) else 'N/A'}")
                
                league_list = leagues_data.get('league', []) if leagues_data else []
                print(f"[DEBUG] league_list type: {type(league_list)}, count: {len(league_list) if isinstance(league_list, list) else 1}")
                
                # Ensure it's a list
                if not isinstance(league_list, list):
                    league_list = [league_list] if league_list else []
                
                for league_data in league_list:
                    league = self._parse_league(league_data)
                    leagues.append(league)
        except Exception as e:
            print(f"Error parsing leagues: {e}")
            import traceback
            traceback.print_exc()
        
        return leagues
    
    def _parse_league(self, league_data: Dict) -> League:
        """Parse league data from API response"""
        return League(
            league_key=league_data.get('league_key', ''),
            league_id=league_data.get('league_id', ''),
            name=league_data.get('name', ''),
            season=league_data.get('season', ''),
            game_code=league_data.get('game_code', 'nba'),
            num_teams=int(league_data.get('num_teams', 0)),
            scoring_type=league_data.get('scoring_type', 'head'),
            draft_status=league_data.get('draft_status', 'predraft'),
            current_week=int(league_data.get('current_week', 1)),
            start_week=int(league_data.get('start_week', 1)),
            end_week=int(league_data.get('end_week', 24)),
            start_date=league_data.get('start_date'),
            end_date=league_data.get('end_date'),
            is_finished=league_data.get('is_finished', '0') == '1',
            url=league_data.get('url')
        )
    
    def get_league_details(self, league_key: str) -> League:
        """
        Get detailed information about a specific league
        
        Args:
            league_key: Yahoo league key (e.g., '418.l.12345')
            
        Returns:
            League object with full details
        """
        endpoint = f'/league/{league_key}'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        league_data = data.get('league', {})
        league = self._parse_league(league_data)
        
        # Get stat categories and roster positions
        league.stat_categories = self._parse_stat_categories(league_data.get('settings', {}).get('stat_categories', {}))
        league.roster_positions = self._parse_roster_positions(league_data.get('settings', {}).get('roster_positions', {}))
        
        return league
    
    def _parse_stat_categories(self, stat_data: Dict) -> List[Dict]:
        """Parse stat categories from league settings"""
        stats = []
        stat_list = stat_data.get('stats', {}).get('stat', [])
        
        if not isinstance(stat_list, list):
            stat_list = [stat_list]
        
        for stat in stat_list:
            if isinstance(stat, dict):
                stats.append({
                    'stat_id': stat.get('stat_id'),
                    'name': stat.get('name'),
                    'display_name': stat.get('display_name'),
                    'sort_order': stat.get('sort_order', '1'),
                    'position_type': stat.get('position_type', 'P')
                })
        
        return stats
    
    def _parse_roster_positions(self, roster_data: Dict) -> List[Dict]:
        """Parse roster positions from league settings"""
        positions = []
        position_list = roster_data.get('roster_position', [])
        
        if not isinstance(position_list, list):
            position_list = [position_list]
        
        for pos in position_list:
            if isinstance(pos, dict):
                positions.append({
                    'position': pos.get('position'),
                    'position_type': pos.get('position_type', 'P'),
                    'count': int(pos.get('count', 1))
                })
        
        return positions
    
    def get_league_teams(self, league_key: str, include_rosters: bool = False) -> List[Team]:
        """
        Get all teams in a league
        
        Args:
            league_key: Yahoo league key
            include_rosters: If True, fetch rosters with teams in one request
            
        Returns:
            List of Team objects
        """
        # If rosters requested, add to endpoint
        if include_rosters:
            endpoint = f'/league/{league_key}/teams;out=roster'
        else:
            endpoint = f'/league/{league_key}/teams'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        teams = []
        
        try:
            league_data = data.get('league', {})
            teams_data = league_data.get('teams', {})
            team_list = teams_data.get('team', [])
            
            # Handle both single team and multiple teams
            if not isinstance(team_list, list):
                team_list = [team_list] if team_list else []
            
            print(f"[DEBUG] Found {len(team_list)} teams in league {league_key} (rosters={include_rosters})")
            
            for team_data in team_list:
                if team_data:  # Skip None/empty entries
                    team = self._parse_team(team_data, include_roster=include_rosters)
                    teams.append(team)
        except Exception as e:
            print(f"Error parsing teams: {e}")
            import traceback
            traceback.print_exc()
        
        return teams
    
    def _parse_team(self, team_data: Dict, include_roster: bool = False) -> Team:
        """Parse team data from API response"""
        # Parse managers
        managers = []
        managers_data = team_data.get('managers', {})
        manager_list = managers_data.get('manager', [])
        
        if not isinstance(manager_list, list):
            manager_list = [manager_list] if manager_list else []
        
        for manager in manager_list:
            if isinstance(manager, dict):
                managers.append({
                    'manager_id': manager.get('manager_id'),
                    'nickname': manager.get('nickname'),
                    'guid': manager.get('guid'),
                    'email': manager.get('email'),
                    'is_commissioner': manager.get('is_commissioner', '0') == '1',
                    'is_current_login': manager.get('is_current_login', '0') == '1'
                })
        
        # Parse roster if included
        roster_players = []
        if include_roster:
            roster_data = team_data.get('roster', {})
            if roster_data:
                players_data = roster_data.get('players', {})
                if players_data:
                    player_list = players_data.get('player', [])
                    if not isinstance(player_list, list):
                        player_list = [player_list] if player_list else []
                    
                    for player_data in player_list:
                        if player_data:
                            player = self._parse_yahoo_player(player_data)
                            if player and player.name:
                                roster_players.append(player)
                    
                    print(f"[DEBUG] Team {team_data.get('name')} has {len(roster_players)} players")
        
        team = Team(
            team_key=team_data.get('team_key', ''),
            team_id=team_data.get('team_id', ''),
            league_key=team_data.get('league_key', ''),
            name=team_data.get('name', ''),
            team_logo_url=team_data.get('team_logos', {}).get('team_logo', {}).get('url', '') if 'team_logos' in team_data else '',
            waiver_priority=team_data.get('waiver_priority'),
            number_of_moves=team_data.get('number_of_moves', '0'),
            number_of_trades=team_data.get('number_of_trades', '0'),
            managers=managers
        )
        
        # Attach roster to team if included
        if include_roster:
            team.roster = roster_players
        
        return team
        
        # Parse team logo
        team_logo_url = None
        team_logos = team_data.get('team_logos', {})
        if team_logos:
            logo_data = team_logos.get('team_logo', {})
            if isinstance(logo_data, dict):
                team_logo_url = logo_data.get('url')
            elif isinstance(logo_data, list) and len(logo_data) > 0:
                team_logo_url = logo_data[0].get('url')
        
        return Team(
            team_key=team_data.get('team_key', ''),
            team_id=team_data.get('team_id', ''),
            name=team_data.get('name', ''),
            team_logo_url=team_logo_url,
            waiver_priority=int(team_data.get('waiver_priority', 0)) if team_data.get('waiver_priority') else None,
            number_of_moves=int(team_data.get('number_of_moves', 0)),
            number_of_trades=int(team_data.get('number_of_trades', 0)),
            managers=managers
        )
    
    def get_team_roster(self, team_key: str) -> List[YahooPlayer]:
        """
        Get roster for a specific team
        
        Args:
            team_key: Yahoo team key (e.g., '418.l.12345.t.1')
            
        Returns:
            List of YahooPlayer objects
        """
        endpoint = f'/team/{team_key}/roster/players'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        print(f"[DEBUG] Roster endpoint: {endpoint}")
        print(f"[DEBUG] Response top-level keys: {list(data.keys()) if data else 'None'}")
        
        players = []
        
        try:
            # Try different data structures
            team_data = data.get('team', {})
            
            if team_data:
                print(f"[DEBUG] team_data keys: {list(team_data.keys())}")
                roster_data = team_data.get('roster', {})
                
                if roster_data:
                    print(f"[DEBUG] roster_data keys: {list(roster_data.keys()) if isinstance(roster_data, dict) else type(roster_data)}")
                    
                    # Get players - try multiple paths
                    players_data = roster_data.get('players', {}) if isinstance(roster_data, dict) else None
                    
                    if players_data:
                        print(f"[DEBUG] players_data type: {type(players_data)}")
                        print(f"[DEBUG] players_data keys: {list(players_data.keys()) if isinstance(players_data, dict) else 'not a dict'}")
                        
                        # Try different structures for player list
                        player_list = []
                        if isinstance(players_data, dict):
                            # First try: players_data has 'player' key
                            if 'player' in players_data:
                                player_list = players_data.get('player', [])
                            # Second try: check for count and numbered keys (0, 1, 2, etc.)
                            elif 'count' in players_data:
                                count = int(players_data.get('count', 0))
                                player_list = [players_data.get(str(i), {}).get('player', {}) for i in range(count) if str(i) in players_data]
                        elif isinstance(players_data, list):
                            player_list = players_data
                        
                        if not isinstance(player_list, list):
                            player_list = [player_list] if player_list else []
                        
                        print(f"[DEBUG] Found {len(player_list)} players")
                        
                        for player_data in player_list:
                            if player_data:
                                player = self._parse_yahoo_player(player_data)
                                if player and player.name:
                                    players.append(player)
                                    print(f"[DEBUG] ✅ Added: {player.name}")
                    else:
                        print("[DEBUG] ❌ No players_data found in roster")
                else:
                    print("[DEBUG] ❌ No roster_data found")
            else:
                print("[DEBUG] ❌ No team_data found")
                
        except Exception as e:
            print(f"❌ Error parsing roster: {e}")
            import traceback
            traceback.print_exc()
        
        return players
    
    def _parse_yahoo_player(self, player_data: Dict) -> YahooPlayer:
        """Parse player data from API response"""
        if not player_data:
            return None
        
        # Get player name
        name_data = player_data.get('name', {})
        if not name_data:
            print(f"[DEBUG] No name data for player: {player_data.get('player_key', 'unknown')}")
            return None
        
        full_name = name_data.get('full', '')
        first_name = name_data.get('first', '')
        last_name = name_data.get('last', '')
        
        if not full_name:
            full_name = f"{first_name} {last_name}".strip()
        
        # Get position(s)
        eligible_positions = player_data.get('eligible_positions', {})
        position_list = eligible_positions.get('position', []) if eligible_positions else []
        if not isinstance(position_list, list):
            position_list = [position_list]
        position = ','.join(str(p) for p in position_list if p)
        
        # Get team
        editorial_team_abbr = player_data.get('editorial_team_abbr', '')
        
        return YahooPlayer(
            player_key=player_data.get('player_key', ''),
            player_id=player_data.get('player_id', ''),
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            position=position,
            team=editorial_team_abbr,
            team_abbr=editorial_team_abbr,
            is_undroppable=player_data.get('is_undroppable', '0') == '1',
            uniform_number=player_data.get('uniform_number'),
            display_position=player_data.get('display_position', position),
            image_url=player_data.get('image_url'),
            editorial_team_abbr=editorial_team_abbr
        )
    
    def get_league_standings(self, league_key: str) -> List[Team]:
        """
        Get league standings
        
        Args:
            league_key: Yahoo league key
            
        Returns:
            List of Team objects with standings data
        """
        endpoint = f'/league/{league_key}/standings'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        teams = []
        
        try:
            league_data = data.get('league', {})
            standings_data = league_data.get('standings', {})
            teams_data = standings_data.get('teams', {})
            team_list = teams_data.get('team', [])
            
            if not isinstance(team_list, list):
                team_list = [team_list]
            
            for team_data in team_list:
                team = self._parse_team(team_data)
                
                # Add standings info
                team_standings = team_data.get('team_standings', {})
                team.team_standings = {
                    'rank': int(team_standings.get('rank', 0)),
                    'outcome_totals': team_standings.get('outcome_totals', {}),
                    'points_for': float(team_standings.get('points_for', 0)),
                    'points_against': float(team_standings.get('points_against', 0))
                }
                
                teams.append(team)
        except Exception as e:
            print(f"Error parsing standings: {e}")
        
        return teams
    
    def get_free_agents(self, league_key: str, position: str = None, count: int = 25) -> List[YahooPlayer]:
        """
        Get available free agents in a league
        
        Args:
            league_key: Yahoo league key
            position: Filter by position (optional)
            count: Number of players to return
            
        Returns:
            List of YahooPlayer objects (only truly free agents, not owned by any team)
        """
        # Build endpoint with filters
        # status=FA means Free Agent (not owned by any team)
        # status=A means Available (includes waivers)
        endpoint = f'/league/{league_key}/players;status=FA;count={count}'
        if position:
            endpoint += f';position={position}'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        players = []
        
        try:
            league_data = data.get('league', {})
            players_data = league_data.get('players', {})
            player_list = players_data.get('player', [])
            
            if not isinstance(player_list, list):
                player_list = [player_list]
            
            for player_data in player_list:
                player = self._parse_yahoo_player(player_data)
                
                # Add ownership percentage if available
                ownership = player_data.get('ownership', {})
                if ownership:
                    player.percent_owned = float(ownership.get('percent_owned', 0))
                
                players.append(player)
        except Exception as e:
            print(f"Error parsing free agents: {e}")
        
        return players
    
    def get_league_scoreboard(self, league_key: str, week: int = None) -> Dict:
        """
        Get league scoreboard with all matchups for a specific week
        
        Args:
            league_key: Yahoo league key
            week: Week number (current week if None)
            
        Returns:
            Dictionary with matchups data including team stats
        """
        endpoint = f'/league/{league_key}/scoreboard'
        if week:
            endpoint += f';week={week}'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        matchups = []
        current_week = None
        
        try:
            league_data = data.get('league', {})
            current_week = int(league_data.get('current_week', 0))
            
            scoreboard_data = league_data.get('scoreboard', {})
            matchups_data = scoreboard_data.get('matchups', {})
            matchup_list = matchups_data.get('matchup', [])
            
            if not isinstance(matchup_list, list):
                matchup_list = [matchup_list]
            
            for matchup_data in matchup_list:
                matchup = self._parse_matchup(matchup_data)
                matchups.append(matchup)
                
        except Exception as e:
            print(f"Error parsing scoreboard: {e}")
        
        return {
            'league_key': league_key,
            'current_week': current_week,
            'week': week or current_week,
            'matchups': matchups
        }
    
    def get_team_matchup(self, team_key: str, week: int = None) -> Optional[Dict]:
        """
        Get specific team's matchup for a week including detailed stats
        
        Args:
            team_key: Yahoo team key
            week: Week number (current week if None)
            
        Returns:
            Dictionary with matchup details and 9-cat stats
        """
        endpoint = f'/team/{team_key}/matchups'
        if week:
            endpoint += f';weeks={week}'
        
        xml_response = self._make_request(endpoint)
        data = self._parse_xml_to_dict(xml_response)
        
        try:
            team_data = data.get('team', {})
            matchups_data = team_data.get('matchups', {})
            matchup_list = matchups_data.get('matchup', [])
            
            if not isinstance(matchup_list, list):
                matchup_list = [matchup_list]
            
            if matchup_list:
                return self._parse_matchup(matchup_list[0])
                
        except Exception as e:
            print(f"Error parsing team matchup: {e}")
        
        return None
    
    def _parse_matchup(self, matchup_data: Dict) -> Dict:
        """Parse matchup data from XML response"""
        matchup = {
            'week': int(matchup_data.get('week', 0)),
            'week_start': matchup_data.get('week_start', ''),
            'week_end': matchup_data.get('week_end', ''),
            'status': matchup_data.get('status', ''),
            'is_playoffs': int(matchup_data.get('is_playoffs', 0)),
            'is_consolation': int(matchup_data.get('is_consolation', 0)),
            'is_tied': int(matchup_data.get('is_tied', 0)),
            'winner_team_key': matchup_data.get('winner_team_key', ''),
            'teams': []
        }
        
        # Parse teams in matchup
        teams_data = matchup_data.get('teams', {})
        team_list = teams_data.get('team', [])
        
        if not isinstance(team_list, list):
            team_list = [team_list]
        
        for team_data in team_list:
            team_info = {
                'team_key': team_data.get('team_key', ''),
                'team_id': team_data.get('team_id', ''),
                'name': team_data.get('name', ''),
                'team_logo_url': team_data.get('team_logos', {}).get('team_logo', {}).get('url', ''),
                'managers': team_data.get('managers', {}).get('manager', []),
                'stats': {},
                'projected_stats': {}
            }
            
            # Parse team stats (actual stats for the week)
            team_stats_data = team_data.get('team_stats', {})
            if team_stats_data:
                stats_list = team_stats_data.get('stats', {}).get('stat', [])
                if not isinstance(stats_list, list):
                    stats_list = [stats_list]
                
                for stat in stats_list:
                    stat_id = stat.get('stat_id')
                    value = stat.get('value', '0')
                    team_info['stats'][stat_id] = value
            
            # Parse projected stats
            team_projected_data = team_data.get('team_projected_stats', {})
            if team_projected_data:
                stats_list = team_projected_data.get('stats', {}).get('stat', [])
                if not isinstance(stats_list, list):
                    stats_list = [stats_list]
                
                for stat in stats_list:
                    stat_id = stat.get('stat_id')
                    value = stat.get('value', '0')
                    team_info['projected_stats'][stat_id] = value
            
            # Parse team points (categories won/lost/tied)
            team_points = team_data.get('team_points', {})
            if team_points:
                team_info['total_points'] = float(team_points.get('total', 0))
            
            matchup['teams'].append(team_info)
        
        return matchup


# Global instance for easy import
yahoo_client = YahooFantasyClient()
