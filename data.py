"""
NBA Fantasy Basketball Data Management Module
Updated for 2025-26 NBA Season with Basketball Reference Scraper
"""

import json
import os
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np
from services.nba_scraper import NBAStatsScraper


class DataManager:
    """Central data management class for NBA Fantasy Basketball Assistant"""
    
    def __init__(self):
        # Initialize NBA Stats Scraper
        self.scraper = NBAStatsScraper()
        
        # Season configuration - Updated with real data
        self.current_season = "2025-26"  # Current active season
        self.available_seasons = ["2025-26", "2024-25", "2023-24", "2022-23"]
        self.season_id = "22025"
        self.season_type = "Regular Season"
        
        # Cache for performance
        self.cache_timeout = 300  # 5 minutes
        self.player_cache = {}
        self.season_players_cache = {}
        self.last_cache_update = None
        
        # Initialize data
        print(f"Initializing NBA data for {self.current_season} season using scraper...")
        self._initialize_data()
    
    def _initialize_data(self):
        """Initialize NBA player data using scraper"""
        try:
            # Load from database (real Basketball Reference data)
            # 2024-25 season = year 2025 in database
            season_year = int(self.current_season.split('-')[0]) + 1
            df = self.scraper.get_season_stats(season_year)
            
            if df is not None and not df.empty:
                # Convert DataFrame to player list
                self.nba_players = self._convert_df_to_players(df, season_year)
                self.teams = self._load_nba_teams()
                print(f"✓ Loaded {len(self.nba_players)} NBA players for {self.current_season} season from database")
            else:
                # Use fallback data if database is empty
                print(f"No data in database for {season_year}, using fallback data")
                self.nba_players = self._get_fallback_players(self.current_season)
                self.teams = self._load_nba_teams()
        except Exception as e:
            print(f"Warning: Loading fallback data due to: {e}")
            self.nba_players = self._get_fallback_players(self.current_season)
            self.teams = self._load_nba_teams()
    
    def _convert_df_to_players(self, df: pd.DataFrame, season_year: int) -> List[Dict]:
        """Convert DataFrame to player dictionaries"""
        
        def safe_float(value, default=0.0):
            """Safely convert value to float, handling NaN, None, and pd.NA"""
            if value is None or pd.isna(value):
                return default
            try:
                result = float(value)
                # Check if result is NaN
                if np.isnan(result):
                    return default
                return result
            except (ValueError, TypeError):
                return default
        
        def safe_int(value, default=0):
            """Safely convert value to int, handling NaN, None, and pd.NA"""
            if value is None or pd.isna(value):
                return default
            try:
                result = int(value)
                return result
            except (ValueError, TypeError):
                return default
        
        players = []
        for _, row in df.iterrows():
            # Fix player name encoding
            player_name = str(row['player_name'])
            try:
                # Try to fix common encoding issues
                player_name = player_name.encode('latin1').decode('utf-8')
            except:
                pass  # Keep original if conversion fails
            
            player = {
                'id': str(hash(player_name) % 10000000),
                'player_id': str(hash(player_name) % 10000000),
                'name': player_name,
                'team': row['team'],
                'position': row.get('position', 'G'),
                'age': safe_int(row.get('age'), 25),
                'experience': max(0, safe_int(row.get('age'), 25) - 19),
                'games_played': safe_int(row.get('games_played'), 0),
                'games_started': safe_int(row.get('games_started'), 0),
                'minutes': safe_float(row.get('minutes_per_game'), 0),
                'is_active': True,
                'season': f"{season_year}-{str(season_year+1)[-2:]}",
                'stats': {
                    'points': safe_float(row.get('points'), 0),
                    'rebounds': safe_float(row.get('total_rebounds'), 0),
                    'assists': safe_float(row.get('assists'), 0),
                    'steals': safe_float(row.get('steals'), 0),
                    'blocks': safe_float(row.get('blocks'), 0),
                    'turnovers': safe_float(row.get('turnovers'), 0),
                    # Shooting percentages
                    'fg_percentage': safe_float(row.get('field_goal_pct'), 0),
                    'three_point_percentage': safe_float(row.get('three_point_pct'), None) if pd.notna(row.get('three_point_pct')) else None,
                    'ft_percentage': safe_float(row.get('free_throw_pct'), None) if pd.notna(row.get('free_throw_pct')) else None,
                    'two_point_pct': safe_float(row.get('two_point_pct'), None) if pd.notna(row.get('two_point_pct')) else None,
                    'effective_fg_pct': safe_float(row.get('effective_fg_pct'), None) if pd.notna(row.get('effective_fg_pct')) else None,
                    # Field goals
                    'field_goals': safe_float(row.get('field_goals'), 0),
                    'field_goal_attempts': safe_float(row.get('field_goal_attempts'), 0),
                    # Three pointers
                    'three_pointers_made': safe_float(row.get('three_pointers'), 0),
                    'three_point_attempts': safe_float(row.get('three_point_attempts'), 0),
                    # Two pointers
                    'two_pointers': safe_float(row.get('two_pointers'), 0),
                    'two_point_attempts': safe_float(row.get('two_point_attempts'), 0),
                    # Free throws
                    'free_throws': safe_float(row.get('free_throws'), 0),
                    'free_throw_attempts': safe_float(row.get('free_throw_attempts'), 0),
                    # Rebounds
                    'offensive_rebounds': safe_float(row.get('offensive_rebounds'), 0),
                    'defensive_rebounds': safe_float(row.get('defensive_rebounds'), 0),
                    # Other
                    'personal_fouls': safe_float(row.get('personal_fouls'), 0),
                }
            }
            players.append(player)
        return players
    
    def _load_players_from_scraper(self, season_year: int) -> List[Dict]:
        """Load players from the NBA scraper database.
        
        Args:
            season_year: Year of the season (e.g., 2024 for 2024-25 season)
            
        Returns:
            List of player dictionaries
        """
        try:
            print(f"Loading players from scraper for {season_year}...")
            
            # Try to get from database first
            df = self.scraper.get_season_stats(season_year)
            
            # If database is empty, scrape the data
            if df is None or df.empty:
                print(f"Scraping season {season_year} data from Basketball Reference...")
                results = self.scraper.scrape_seasons([season_year], save_csv=True, save_db=True)
                if season_year in results:
                    df = results[season_year]
                else:
                    raise ValueError(f"Failed to scrape data for season {season_year}")
            
            # Convert DataFrame to list of dictionaries
            return self._convert_df_to_players(df, season_year)
            
        except Exception as e:
            print(f"NBA scraper error for season {season_year}: {e}")
            raise
    
    def _load_players_for_season(self, season: str) -> List[Dict]:
        """Load players who actually played in the given season using scraper.
        Falls back to sample data on failure.
        """
        try:
            # Convert season string to year in database (e.g., "2024-25" -> 2025, "2025-26" -> 2026)
            season_year = int(season.split('-')[0]) + 1
            print(f"Fetching season players via scraper for {season} (DB year: {season_year})...")
            
            players = self._load_players_from_scraper(season_year)
            
            if players:
                return players
            else:
                raise ValueError(f"No players found for season {season}")
                
        except Exception as e:
            print(f"NBA scraper error for season {season}: {e}")
            # Fallback to sample data
            return self._get_fallback_players(season=season)
    
    def get_all_nba_players(self, season: Optional[str] = None, min_games: int = 0, use_cache: bool = True) -> List[Dict]:
        """Get all NBA players with cache management for a specific season."""
        if season is None:
            season = self.current_season

        now = datetime.now()
        cache_key = f"players_{season}"

        if use_cache and cache_key in self.season_players_cache:
            cached_data = self.season_players_cache[cache_key]
            if 'timestamp' in cached_data and (now - cached_data['timestamp']).total_seconds() < 3600:
                players = cached_data['players']
            else:  # Cache expired
                players = self._load_players_for_season(season)
                self.season_players_cache[cache_key] = {'players': players, 'timestamp': now}
        else:  # Not in cache or don't use cache
            players = self._load_players_for_season(season)
            self.season_players_cache[cache_key] = {'players': players, 'timestamp': now}
        
        self.nba_players = players # Keep self.nba_players updated with the latest fetched season

        # Filter by minimum games if specified
        if min_games > 0:
            return [p for p in players if p.get('games_played', 0) >= min_games]

        return players
    
    def get_player_by_name(self, name: str, season: Optional[str] = None) -> Optional[Dict]:
        """Get player information by name"""
        players = self.get_all_nba_players(season=season)
        name_lower = name.lower()
        for player in players:
            if player['name'].lower() == name_lower:
                return player
        return None
    
    def get_players_by_position(self, position: str, season: Optional[str] = None) -> List[Dict]:
        """Get all players at a specific position"""
        players = self.get_all_nba_players(season=season)
        return [p for p in players if p.get('position', '').upper() == position.upper()]
    
    def get_top_scorers(self, limit: int = 10, season: Optional[str] = None) -> List[Dict]:
        """Get top scorers for a season"""
        players = self.get_all_nba_players(season=season, min_games=20)
        sorted_players = sorted(players, key=lambda x: x.get('stats', {}).get('points', 0), reverse=True)
        return sorted_players[:limit]
    
    def get_player_stats_multi_season(self, player_name: str, seasons: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Get player stats across multiple seasons"""
        if seasons is None:
            seasons = self.available_seasons
        
        stats_by_season = {}
        for season in seasons:
            player = self.get_player_by_name(player_name, season=season)
            if player:
                stats_by_season[season] = player['stats']
        
        return stats_by_season
    
    def _load_nba_teams(self):
        """Load NBA teams data"""
        return {
            'ATL': {'name': 'Atlanta Hawks', 'conference': 'Eastern', 'division': 'Southeast'},
            'BOS': {'name': 'Boston Celtics', 'conference': 'Eastern', 'division': 'Atlantic'},
            'BRK': {'name': 'Brooklyn Nets', 'conference': 'Eastern', 'division': 'Atlantic'},
            'CHI': {'name': 'Chicago Bulls', 'conference': 'Eastern', 'division': 'Central'},
            'CHO': {'name': 'Charlotte Hornets', 'conference': 'Eastern', 'division': 'Southeast'},
            'CLE': {'name': 'Cleveland Cavaliers', 'conference': 'Eastern', 'division': 'Central'},
            'DAL': {'name': 'Dallas Mavericks', 'conference': 'Western', 'division': 'Southwest'},
            'DEN': {'name': 'Denver Nuggets', 'conference': 'Western', 'division': 'Northwest'},
            'DET': {'name': 'Detroit Pistons', 'conference': 'Eastern', 'division': 'Central'},
            'GSW': {'name': 'Golden State Warriors', 'conference': 'Western', 'division': 'Pacific'},
            'HOU': {'name': 'Houston Rockets', 'conference': 'Western', 'division': 'Southwest'},
            'IND': {'name': 'Indiana Pacers', 'conference': 'Eastern', 'division': 'Central'},
            'LAC': {'name': 'Los Angeles Clippers', 'conference': 'Western', 'division': 'Pacific'},
            'LAL': {'name': 'Los Angeles Lakers', 'conference': 'Western', 'division': 'Pacific'},
            'MEM': {'name': 'Memphis Grizzlies', 'conference': 'Western', 'division': 'Southwest'},
            'MIA': {'name': 'Miami Heat', 'conference': 'Eastern', 'division': 'Southeast'},
            'MIL': {'name': 'Milwaukee Bucks', 'conference': 'Eastern', 'division': 'Central'},
            'MIN': {'name': 'Minnesota Timberwolves', 'conference': 'Western', 'division': 'Northwest'},
            'NOP': {'name': 'New Orleans Pelicans', 'conference': 'Western', 'division': 'Southwest'},
            'NYK': {'name': 'New York Knicks', 'conference': 'Eastern', 'division': 'Atlantic'},
            'OKC': {'name': 'Oklahoma City Thunder', 'conference': 'Western', 'division': 'Northwest'},
            'ORL': {'name': 'Orlando Magic', 'conference': 'Eastern', 'division': 'Southeast'},
            'PHI': {'name': 'Philadelphia 76ers', 'conference': 'Eastern', 'division': 'Atlantic'},
            'PHO': {'name': 'Phoenix Suns', 'conference': 'Western', 'division': 'Pacific'},
            'POR': {'name': 'Portland Trail Blazers', 'conference': 'Western', 'division': 'Northwest'},
            'SAC': {'name': 'Sacramento Kings', 'conference': 'Western', 'division': 'Pacific'},
            'SAS': {'name': 'San Antonio Spurs', 'conference': 'Western', 'division': 'Southwest'},
            'TOR': {'name': 'Toronto Raptors', 'conference': 'Eastern', 'division': 'Atlantic'},
            'UTA': {'name': 'Utah Jazz', 'conference': 'Western', 'division': 'Northwest'},
            'WAS': {'name': 'Washington Wizards', 'conference': 'Eastern', 'division': 'Southeast'},
        }
    
    def _get_fallback_players(self, season: str = "2025-26") -> List[Dict]:
        """Return fallback/sample player data when scraper fails"""
        print(f"Using fallback player data for season {season}")
        
        # Sample top players with realistic stats (early 2025-26 season)
        sample_players = [
            {
                'id': '1629029', 'player_id': '1629029', 'name': 'Luka Dončić', 'team': 'DAL', 'position': 'PG',
                'age': 25, 'experience': 6, 'games_played': 70, 'minutes': 36.2, 'is_active': True, 'season': season,
                'stats': {'points': 33.9, 'rebounds': 9.2, 'assists': 9.8, 'steals': 1.4, 'blocks': 0.5, 'turnovers': 4.0,
                         'fg_percentage': 0.487, 'three_point_percentage': 0.382, 'ft_percentage': 0.786,
                         'three_pointers_made': 4.1, 'field_goals_made': 11.5, 'free_throws_made': 8.8}
            },
            {
                'id': '203999', 'player_id': '203999', 'name': 'Nikola Jokić', 'team': 'DEN', 'position': 'C',
                'age': 29, 'experience': 9, 'games_played': 79, 'minutes': 34.6, 'is_active': True, 'season': season,
                'stats': {'points': 26.4, 'rebounds': 12.4, 'assists': 9.0, 'steals': 1.4, 'blocks': 0.9, 'turnovers': 3.0,
                         'fg_percentage': 0.583, 'three_point_percentage': 0.356, 'ft_percentage': 0.814,
                         'three_pointers_made': 1.4, 'field_goals_made': 10.0, 'free_throws_made': 5.2}
            },
            {
                'id': '1628369', 'player_id': '1628369', 'name': 'Shai Gilgeous-Alexander', 'team': 'OKC', 'position': 'PG',
                'age': 26, 'experience': 6, 'games_played': 75, 'minutes': 34.0, 'is_active': True, 'season': season,
                'stats': {'points': 30.1, 'rebounds': 5.5, 'assists': 6.2, 'steals': 2.0, 'blocks': 0.9, 'turnovers': 1.9,
                         'fg_percentage': 0.535, 'three_point_percentage': 0.353, 'ft_percentage': 0.874,
                         'three_pointers_made': 2.4, 'field_goals_made': 10.9, 'free_throws_made': 7.2}
            },
            {
                'id': '203507', 'player_id': '203507', 'name': 'Giannis Antetokounmpo', 'team': 'MIL', 'position': 'PF',
                'age': 29, 'experience': 11, 'games_played': 73, 'minutes': 35.2, 'is_active': True, 'season': season,
                'stats': {'points': 30.4, 'rebounds': 11.5, 'assists': 6.5, 'steals': 1.2, 'blocks': 1.1, 'turnovers': 3.4,
                         'fg_percentage': 0.612, 'three_point_percentage': 0.274, 'ft_percentage': 0.657,
                         'three_pointers_made': 0.6, 'field_goals_made': 11.6, 'free_throws_made': 7.5}
            },
            {
                'id': '203954', 'player_id': '203954', 'name': 'Joel Embiid', 'team': 'PHI', 'position': 'C',
                'age': 30, 'experience': 10, 'games_played': 39, 'minutes': 34.6, 'is_active': True, 'season': season,
                'stats': {'points': 34.7, 'rebounds': 11.0, 'assists': 5.6, 'steals': 1.2, 'blocks': 1.7, 'turnovers': 3.4,
                         'fg_percentage': 0.529, 'three_point_percentage': 0.389, 'ft_percentage': 0.885,
                         'three_pointers_made': 2.2, 'field_goals_made': 11.8, 'free_throws_made': 9.8}
            },
        ]
        
        return sample_players
    
    def clear_cache(self):
        """Clear all cached data"""
        self.player_cache.clear()
        self.season_players_cache.clear()
        self.last_cache_update = None
        print("Data cache cleared")


# Initialize global data manager instance
data_manager = DataManager()
