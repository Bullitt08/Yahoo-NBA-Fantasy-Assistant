"""
Player matching service - combines Yahoo Fantasy data with real NBA stats
"""

from typing import Dict, List, Optional
import difflib
from .models import YahooPlayer


class PlayerMatcher:
    """
    Matches Yahoo Fantasy players with real NBA stats from our database
    
    Features:
    - Fuzzy name matching for players with different spellings
    - Team abbreviation mapping
    - Position normalization
    """
    
    # Yahoo to NBA team abbreviation mapping
    TEAM_MAPPING = {
        'Atl': 'ATL', 'Bos': 'BOS', 'Bkn': 'BRK', 'Cha': 'CHO', 'Chi': 'CHI',
        'Cle': 'CLE', 'Dal': 'DAL', 'Den': 'DEN', 'Det': 'DET', 'GS': 'GSW',
        'Hou': 'HOU', 'Ind': 'IND', 'LAC': 'LAC', 'LAL': 'LAL', 'Mem': 'MEM',
        'Mia': 'MIA', 'Mil': 'MIL', 'Min': 'MIN', 'NO': 'NOP', 'NY': 'NYK',
        'OKC': 'OKC', 'Orl': 'ORL', 'Phi': 'PHI', 'Phx': 'PHO', 'Por': 'POR',
        'Sac': 'SAC', 'SA': 'SAS', 'Tor': 'TOR', 'Uta': 'UTA', 'Was': 'WAS',
    }
    
    def __init__(self, nba_players: List[Dict]):
        """
        Initialize matcher with NBA player data
        
        Args:
            nba_players: List of NBA player dictionaries from DataManager
        """
        self.nba_players = nba_players
        self.player_name_map = {p['name'].lower(): p for p in nba_players}
    
    def normalize_team(self, yahoo_team: str) -> str:
        """Convert Yahoo team abbreviation to NBA standard"""
        return self.TEAM_MAPPING.get(yahoo_team, yahoo_team.upper())
    
    def find_best_match(self, yahoo_player: YahooPlayer, threshold: float = 0.8) -> Optional[Dict]:
        """
        Find best matching NBA player for a Yahoo player
        
        Args:
            yahoo_player: YahooPlayer object
            threshold: Minimum similarity score (0-1)
            
        Returns:
            NBA player dictionary or None
        """
        # Try exact match first
        if yahoo_player.name.lower() in self.player_name_map:
            return self.player_name_map[yahoo_player.name.lower()]
        
        # Try fuzzy matching
        player_names = list(self.player_name_map.keys())
        matches = difflib.get_close_matches(
            yahoo_player.name.lower(),
            player_names,
            n=1,
            cutoff=threshold
        )
        
        if matches:
            return self.player_name_map[matches[0]]
        
        # Try matching by team and position
        normalized_team = self.normalize_team(yahoo_player.team_abbr)
        candidates = [
            p for p in self.nba_players
            if p.get('team', '').upper() == normalized_team
        ]
        
        if candidates:
            # Check for partial name matches
            for candidate in candidates:
                if (yahoo_player.last_name.lower() in candidate['name'].lower() or
                    yahoo_player.first_name.lower() in candidate['name'].lower()):
                    return candidate
        
        return None
    
    def merge_player_data(self, yahoo_player: YahooPlayer) -> YahooPlayer:
        """
        Merge Yahoo player data with NBA stats
        
        Args:
            yahoo_player: YahooPlayer object
            
        Returns:
            YahooPlayer with merged nba_stats
        """
        nba_match = self.find_best_match(yahoo_player)
        
        if nba_match:
            yahoo_player.nba_stats = {
                'player_id': nba_match.get('player_id'),
                'games_played': nba_match.get('games_played', 0),
                'minutes': nba_match.get('minutes', 0),
                'stats': nba_match.get('stats', {}),
                'age': nba_match.get('age'),
                'experience': nba_match.get('experience'),
            }
        
        return yahoo_player
    
    def batch_merge(self, yahoo_players: List[YahooPlayer]) -> List[YahooPlayer]:
        """
        Merge multiple Yahoo players with NBA stats
        
        Args:
            yahoo_players: List of YahooPlayer objects
            
        Returns:
            List of YahooPlayer objects with merged data
        """
        return [self.merge_player_data(p) for p in yahoo_players]
    
    def get_match_report(self, yahoo_players: List[YahooPlayer]) -> Dict:
        """
        Generate matching report showing success rate
        
        Args:
            yahoo_players: List of YahooPlayer objects
            
        Returns:
            Dictionary with matching statistics
        """
        total = len(yahoo_players)
        matched = 0
        unmatched = []
        
        for player in yahoo_players:
            if self.find_best_match(player):
                matched += 1
            else:
                unmatched.append(player.name)
        
        return {
            'total_players': total,
            'matched': matched,
            'unmatched': total - matched,
            'match_rate': (matched / total * 100) if total > 0 else 0,
            'unmatched_players': unmatched
        }
