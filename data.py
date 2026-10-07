"""
NBA Fantasy Basketball Data Management Module
Integrated with Dynamic Season Configuration and Basketball Reference Scraper
Supports Per Game and Total statistics separation for all seasons.
"""

import json
import os
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional, Union
from pathlib import Path
import pandas as pd
import numpy as np

from services.nba_scraper import NBAStatsScraper
from season_config import season_manager, season_to_year, year_to_season


class DataManager:
    """Central data management class for NBA Fantasy Basketball Assistant"""
    
    def __init__(self):
        # Initialize NBA Stats Scraper
        self.scraper = NBAStatsScraper()
        
        # Central season configuration - fully dynamic
        self.season_manager = season_manager
        # Check available seasons from DB if exists
        self._discovered_seasons = []
        self.available_seasons = self._discover_available_seasons()
        # Default active season is the latest season that actually has records in DB/CSV
        if self._discovered_seasons:
            self.current_season = self._discovered_seasons[0]
        elif self.available_seasons:
            self.current_season = self.available_seasons[0]
        else:
            self.current_season = self.season_manager.current_season
        self.season_id = f"2{season_to_year(self.current_season)}"
        self.season_type = "Regular Season"
        
        # Cache for performance
        self.cache_timeout = 300  # 5 minutes
        self.player_cache = {}
        self.season_players_cache = {}
        self.last_cache_update = None
        self.teams = self._load_nba_teams()
        
        # Initialize data for current season
        print(f"[DATA] Initializing NBA data for {self.current_season} season...")
        self._initialize_data()
    
    def _discover_available_seasons(self) -> List[str]:
        """Discover available seasons from the database and season manager."""
        discovered = []
        try:
            # Query distinct seasons from database
            session = self.scraper.Session()
            from services.nba_scraper import PlayerStats
            db_years = session.query(PlayerStats.season).distinct().all()
            session.close()
            if db_years:
                years = sorted([y[0] for y in db_years if y[0]], reverse=True)
                discovered = [year_to_season(y) for y in years]
                self._discovered_seasons = list(discovered)
        except Exception as e:
            print(f"[DATA] Note: Database season discovery: {e}")
        
        # Merge with dynamically generated available seasons
        standard = self.season_manager.get_available_seasons(count=6)
        all_seasons = set(discovered + standard)
        # Sort seasons strictly by start/ending year descending (newest season first)
        sorted_seasons = sorted(all_seasons, key=lambda s: season_to_year(s), reverse=True)
        return sorted_seasons if sorted_seasons else ["2026-27", "2025-26", "2024-25", "2023-24", "2022-23", "2021-22"]

    def _initialize_data(self):
        """Initialize NBA player data using scraper or database"""
        try:
            season_year = season_to_year(self.current_season)
            df = self.scraper.get_season_stats(season_year)
            
            if df is not None and not df.empty:
                self.nba_players = self._convert_df_to_players(df, season_year)
                print(f"[DATA] Loaded {len(self.nba_players)} NBA players for {self.current_season} season from database")
            else:
                # Try fallback CSV
                csv_path = Path("data") / f"players_{season_year}.csv"
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    self.nba_players = self._convert_df_to_players(df, season_year)
                    print(f"[DATA] Loaded {len(self.nba_players)} players from CSV {csv_path}")
                else:
                    print(f"[DATA] No data in database/CSV for {season_year}, using fallback sample data")
                    self.nba_players = self._get_fallback_players(self.current_season)
        except Exception as e:
            print(f"[DATA] Warning: Loading fallback data due to: {e}")
            self.nba_players = self._get_fallback_players(self.current_season)
    
    def _convert_df_to_players(self, df: pd.DataFrame, season_year: int) -> List[Dict]:
        """Convert DataFrame to player dictionaries with both Per Game and Total statistics."""
        
        def safe_float(value, default=0.0):
            if value is None or pd.isna(value):
                return default
            try:
                res = float(value)
                return default if np.isnan(res) else res
            except (ValueError, TypeError):
                return default
        
        def safe_int(value, default=0):
            if value is None or pd.isna(value):
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        # Clean column mapping for CSV differences if needed
        cols = {c.lower(): c for c in df.columns}
        
        def get_col(candidates, default=None):
            for cand in candidates:
                if cand.lower() in cols:
                    return df[cols[cand.lower()]]
            return default

        season_str = year_to_season(season_year)
        players = []
        
        for _, row in df.iterrows():
            raw_name = row.get('player_name', row.get('Player', 'Unknown Player'))
            player_name = str(raw_name)
            try:
                player_name = player_name.encode('latin1').decode('utf-8')
            except Exception:
                pass
            
            games_played = safe_int(row.get('games_played', row.get('G', 0)), 0)
            games_started = safe_int(row.get('games_started', row.get('GS', 0)), 0)
            age = safe_int(row.get('age', row.get('Age', 25)), 25)
            team = str(row.get('team', row.get('Team', 'FA')))
            position = str(row.get('position', row.get('Pos', 'G')))
            
            raw_pts = safe_float(row.get('points', row.get('PTS', 0.0)))
            raw_min = safe_float(row.get('minutes_per_game', row.get('MP', 0.0)))
            raw_reb = safe_float(row.get('total_rebounds', row.get('TRB', 0.0)))
            raw_ast = safe_float(row.get('assists', row.get('AST', 0.0)))
            raw_stl = safe_float(row.get('steals', row.get('STL', 0.0)))
            raw_blk = safe_float(row.get('blocks', row.get('BLK', 0.0)))
            raw_fg3m = safe_float(row.get('three_pointers', row.get('3P', 0.0)))
            raw_tov = safe_float(row.get('turnovers', row.get('TOV', 0.0)))
            raw_pf = safe_float(row.get('personal_fouls', row.get('PF', 0.0)))
            raw_oreb = safe_float(row.get('offensive_rebounds', row.get('ORB', 0.0)))
            raw_dreb = safe_float(row.get('defensive_rebounds', row.get('DRB', 0.0)))
            raw_fg = safe_float(row.get('field_goals', row.get('FG', 0.0)))
            raw_fga = safe_float(row.get('field_goal_attempts', row.get('FGA', 0.0)))
            raw_ft = safe_float(row.get('free_throws', row.get('FT', 0.0)))
            raw_fta = safe_float(row.get('free_throw_attempts', row.get('FTA', 0.0)))
            raw_fg3a = safe_float(row.get('three_point_attempts', row.get('3PA', 0.0)))
            raw_two = safe_float(row.get('two_pointers', row.get('2P', 0.0)))
            raw_twoa = safe_float(row.get('two_point_attempts', row.get('2PA', 0.0)))

            # Check if this row represents raw season totals or per-game averages
            is_totals = (raw_pts > 60.0 or raw_min > 55.0) and games_played > 0
            
            if is_totals:
                # Row is season totals -> derive per-game
                pts_pg = round(raw_pts / games_played, 2)
                pts_tot = round(raw_pts, 1)
                min_pg = round(raw_min / games_played, 2)
                min_tot = round(raw_min, 1)
                reb_pg = round(raw_reb / games_played, 2)
                reb_tot = round(raw_reb, 1)
                ast_pg = round(raw_ast / games_played, 2)
                ast_tot = round(raw_ast, 1)
                stl_pg = round(raw_stl / games_played, 2)
                stl_tot = round(raw_stl, 1)
                blk_pg = round(raw_blk / games_played, 2)
                blk_tot = round(raw_blk, 1)
                fg3m_pg = round(raw_fg3m / games_played, 2)
                fg3m_tot = round(raw_fg3m, 1)
                tov_pg = round(raw_tov / games_played, 2)
                tov_tot = round(raw_tov, 1)
                pf_pg = round(raw_pf / games_played, 2)
                pf_tot = round(raw_pf, 1)
                oreb_pg = round(raw_oreb / games_played, 2)
                oreb_tot = round(raw_oreb, 1)
                dreb_pg = round(raw_dreb / games_played, 2)
                dreb_tot = round(raw_dreb, 1)
                fg_pg = round(raw_fg / games_played, 2)
                fg_tot = round(raw_fg, 1)
                fga_pg = round(raw_fga / games_played, 2)
                fga_tot = round(raw_fga, 1)
                ft_pg = round(raw_ft / games_played, 2)
                ft_tot = round(raw_ft, 1)
                fta_pg = round(raw_fta / games_played, 2)
                fta_tot = round(raw_fta, 1)
                fg3a_pg = round(raw_fg3a / games_played, 2)
                fg3a_tot = round(raw_fg3a, 1)
                two_pg = round(raw_two / games_played, 2)
                two_tot = round(raw_two, 1)
                twoa_pg = round(raw_twoa / games_played, 2)
                twoa_tot = round(raw_twoa, 1)
            else:
                # Row is per-game averages -> derive totals
                pts_pg = round(raw_pts, 2)
                pts_tot = round(raw_pts * games_played, 1) if games_played > 0 else 0.0
                min_pg = round(raw_min, 2)
                min_tot = round(raw_min * games_played, 1) if games_played > 0 else 0.0
                reb_pg = round(raw_reb, 2)
                reb_tot = round(raw_reb * games_played, 1) if games_played > 0 else 0.0
                ast_pg = round(raw_ast, 2)
                ast_tot = round(raw_ast * games_played, 1) if games_played > 0 else 0.0
                stl_pg = round(raw_stl, 2)
                stl_tot = round(raw_stl * games_played, 1) if games_played > 0 else 0.0
                blk_pg = round(raw_blk, 2)
                blk_tot = round(raw_blk * games_played, 1) if games_played > 0 else 0.0
                fg3m_pg = round(raw_fg3m, 2)
                fg3m_tot = round(raw_fg3m * games_played, 1) if games_played > 0 else 0.0
                tov_pg = round(raw_tov, 2)
                tov_tot = round(raw_tov * games_played, 1) if games_played > 0 else 0.0
                pf_pg = round(raw_pf, 2)
                pf_tot = round(raw_pf * games_played, 1) if games_played > 0 else 0.0
                oreb_pg = round(raw_oreb, 2)
                oreb_tot = round(raw_oreb * games_played, 1) if games_played > 0 else 0.0
                dreb_pg = round(raw_dreb, 2)
                dreb_tot = round(raw_dreb * games_played, 1) if games_played > 0 else 0.0
                fg_pg = round(raw_fg, 2)
                fg_tot = round(raw_fg * games_played, 1) if games_played > 0 else 0.0
                fga_pg = round(raw_fga, 2)
                fga_tot = round(raw_fga * games_played, 1) if games_played > 0 else 0.0
                ft_pg = round(raw_ft, 2)
                ft_tot = round(raw_ft * games_played, 1) if games_played > 0 else 0.0
                fta_pg = round(raw_fta, 2)
                fta_tot = round(raw_fta * games_played, 1) if games_played > 0 else 0.0
                fg3a_pg = round(raw_fg3a, 2)
                fg3a_tot = round(raw_fg3a * games_played, 1) if games_played > 0 else 0.0
                two_pg = round(raw_two, 2)
                two_tot = round(raw_two * games_played, 1) if games_played > 0 else 0.0
                twoa_pg = round(raw_twoa, 2)
                twoa_tot = round(raw_twoa * games_played, 1) if games_played > 0 else 0.0

            # Percentages
            fg_pct = safe_float(row.get('field_goal_pct', row.get('FG%', 0.0)))
            if fg_pct == 0.0 and fga_tot > 0:
                fg_pct = round(fg_tot / fga_tot, 4)
                
            ft_pct = safe_float(row.get('free_throw_pct', row.get('FT%', 0.0)))
            if ft_pct == 0.0 and fta_tot > 0:
                ft_pct = round(ft_tot / fta_tot, 4)
                
            three_pct = safe_float(row.get('three_point_pct', row.get('3P%', 0.0)))
            if three_pct == 0.0 and fg3a_tot > 0:
                three_pct = round(fg3m_tot / fg3a_tot, 4)
                
            efg_pct = safe_float(row.get('effective_fg_pct', row.get('eFG%', 0.0)))
            two_pct = safe_float(row.get('two_point_pct', row.get('2P%', 0.0)))

            player_id = str(abs(hash(player_name)) % 10000000)

            # Per-game stats dictionary
            stats_per_game = {
                'points': pts_pg,
                'rebounds': reb_pg,
                'assists': ast_pg,
                'steals': stl_pg,
                'blocks': blk_pg,
                'turnovers': tov_pg,
                'fg_percentage': fg_pct,
                'ft_percentage': ft_pct,
                'three_point_percentage': three_pct,
                'effective_fg_pct': efg_pct,
                'two_point_pct': two_pct,
                'three_pointers_made': fg3m_pg,
                'three_point_attempts': fg3a_pg,
                'field_goals': fg_pg,
                'field_goal_attempts': fga_pg,
                'two_pointers': two_pg,
                'two_point_attempts': twoa_pg,
                'free_throws': ft_pg,
                'free_throw_attempts': fta_pg,
                'offensive_rebounds': oreb_pg,
                'defensive_rebounds': dreb_pg,
                'personal_fouls': pf_pg,
                'minutes': min_pg
            }

            # Total stats dictionary
            total_stats = {
                'points': pts_tot,
                'rebounds': reb_tot,
                'assists': ast_tot,
                'steals': stl_tot,
                'blocks': blk_tot,
                'turnovers': tov_tot,
                'fg_percentage': fg_pct,
                'ft_percentage': ft_pct,
                'three_point_percentage': three_pct,
                'effective_fg_pct': efg_pct,
                'two_point_pct': two_pct,
                'three_pointers_made': fg3m_tot,
                'three_point_attempts': fg3a_tot,
                'field_goals': fg_tot,
                'field_goal_attempts': fga_tot,
                'two_pointers': two_tot,
                'two_point_attempts': twoa_tot,
                'free_throws': ft_tot,
                'free_throw_attempts': fta_tot,
                'offensive_rebounds': oreb_tot,
                'defensive_rebounds': dreb_tot,
                'personal_fouls': pf_tot,
                'minutes': min_tot
            }

            player = {
                'id': player_id,
                'player_id': player_id,
                'name': player_name,
                'team': team,
                'position': position,
                'age': age,
                'experience': max(0, age - 19),
                'games_played': games_played,
                'games_started': games_started,
                'minutes': min_pg,
                'total_minutes': min_tot,
                'is_active': True,
                'season': season_str,
                'stats': stats_per_game,
                'total_stats': total_stats
            }
            players.append(player)
            
        return players
    
    def _load_players_from_scraper(self, season_year: int) -> List[Dict]:
        """Load players from the NBA scraper database or CSV files."""
        try:
            print(f"[DATA] Loading players for DB season year {season_year}...")
            df = self.scraper.get_season_stats(season_year)
            
            if df is not None and not df.empty:
                return self._convert_df_to_players(df, season_year)
            
            # Check local CSV file if DB has no records
            csv_path = Path("data") / f"players_{season_year}.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                return self._convert_df_to_players(df, season_year)
            
            raise ValueError(f"No records found in DB or CSV for season year {season_year}")
        except Exception as e:
            print(f"[DATA] Error loading players for season year {season_year}: {e}")
            raise
    
    def _load_players_for_season(self, season: str) -> List[Dict]:
        """Load players who played in the given season."""
        try:
            season_year = season_to_year(season)
            players = self._load_players_from_scraper(season_year)
            if players:
                return players
            raise ValueError(f"No players for {season}")
        except Exception as e:
            print(f"[DATA] Falling back to sample players for {season}: {e}")
            return self._get_fallback_players(season=season)
    
    def get_all_nba_players(self, season: Optional[str] = None, min_games: int = 0, use_cache: bool = True) -> List[Dict]:
        """Get all NBA players with strict season isolation and cache management."""
        if season is None:
            season = self.current_season

        now = datetime.now()
        cache_key = f"players_{season}"

        if use_cache and cache_key in self.season_players_cache:
            cached_data = self.season_players_cache[cache_key]
            if 'timestamp' in cached_data and (now - cached_data['timestamp']).total_seconds() < 3600:
                players = cached_data['players']
            else:
                players = self._load_players_for_season(season)
                self.season_players_cache[cache_key] = {'players': players, 'timestamp': now}
        else:
            players = self._load_players_for_season(season)
            self.season_players_cache[cache_key] = {'players': players, 'timestamp': now}
        
        # If querying the active current season, keep self.nba_players updated
        if season == self.current_season:
            self.nba_players = players

        if min_games > 0:
            return [p for p in players if p.get('games_played', 0) >= min_games]

        return players
    
    def get_player_by_name(self, name: str, season: Optional[str] = None) -> Optional[Dict]:
        """Get player information by name for a specific season."""
        players = self.get_all_nba_players(season=season)
        name_lower = name.lower()
        for player in players:
            if player['name'].lower() == name_lower:
                return player
        return None

    def get_player_stats(self, player_id: str, season: Optional[str] = None) -> Optional[Dict]:
        """Get detailed player stats by player_id for a specific season."""
        players = self.get_all_nba_players(season=season)
        for player in players:
            if str(player.get('player_id')) == str(player_id) or str(player.get('id')) == str(player_id):
                return player
        return None
    
    def get_players_by_position(self, position: str, season: Optional[str] = None) -> List[Dict]:
        """Get all players at a specific position for a season."""
        players = self.get_all_nba_players(season=season)
        return [p for p in players if position.upper() in p.get('position', '').upper()]
    
    def get_top_scorers(self, limit: int = 10, season: Optional[str] = None) -> List[Dict]:
        """Get top scorers for a season."""
        players = self.get_all_nba_players(season=season, min_games=20)
        sorted_players = sorted(players, key=lambda x: x.get('stats', {}).get('points', 0), reverse=True)
        return sorted_players[:limit]
    
    def get_player_stats_multi_season(self, player_name: str, seasons: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Get player stats across multiple seasons."""
        if seasons is None:
            seasons = self.available_seasons
        
        stats_by_season = {}
        for s in seasons:
            player = self.get_player_by_name(player_name, season=s)
            if player:
                stats_by_season[s] = player['stats']
        
        return stats_by_season
    
    def _load_nba_teams(self):
        """Load NBA teams mapping"""
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
    
    def _get_fallback_players(self, season: Optional[str] = None) -> List[Dict]:
        """Return fallback player data when database has no records for a season."""
        s = season or self.current_season
        raw = [
            {'name': 'Nikola Jokić', 'team': 'DEN', 'position': 'C', 'age': 30, 'gp': 75, 'min': 34.6, 'pts': 26.4, 'reb': 12.4, 'ast': 9.0, 'stl': 1.4, 'blk': 0.9, 'tov': 3.0, 'fg_pct': 0.583, 'ft_pct': 0.814, 'fg3m': 1.4},
            {'name': 'Shai Gilgeous-Alexander', 'team': 'OKC', 'position': 'PG', 'age': 26, 'gp': 75, 'min': 34.0, 'pts': 30.1, 'reb': 5.5, 'ast': 6.2, 'stl': 2.0, 'blk': 0.9, 'tov': 2.2, 'fg_pct': 0.535, 'ft_pct': 0.874, 'fg3m': 1.3},
            {'name': 'Luka Dončić', 'team': 'DAL', 'position': 'PG', 'age': 26, 'gp': 70, 'min': 36.2, 'pts': 33.9, 'reb': 9.2, 'ast': 9.8, 'stl': 1.4, 'blk': 0.5, 'tov': 4.0, 'fg_pct': 0.487, 'ft_pct': 0.786, 'fg3m': 4.1},
            {'name': 'Giannis Antetokounmpo', 'team': 'MIL', 'position': 'PF', 'age': 30, 'gp': 73, 'min': 35.2, 'pts': 30.4, 'reb': 11.5, 'ast': 6.5, 'stl': 1.2, 'blk': 1.1, 'tov': 3.4, 'fg_pct': 0.612, 'ft_pct': 0.657, 'fg3m': 0.6},
            {'name': 'Joel Embiid', 'team': 'PHI', 'position': 'C', 'age': 31, 'gp': 45, 'min': 34.6, 'pts': 34.7, 'reb': 11.0, 'ast': 5.6, 'stl': 1.2, 'blk': 1.7, 'tov': 3.4, 'fg_pct': 0.529, 'ft_pct': 0.885, 'fg3m': 1.4},
        ]
        players = []
        for p in raw:
            pid = str(abs(hash(p['name'])) % 10000000)
            gp = p['gp']
            stats_pg = {
                'points': p['pts'], 'rebounds': p['reb'], 'assists': p['ast'],
                'steals': p['stl'], 'blocks': p['blk'], 'turnovers': p['tov'],
                'fg_percentage': p['fg_pct'], 'ft_percentage': p['ft_pct'],
                'three_point_percentage': 0.36, 'three_pointers_made': p['fg3m'],
                'minutes': p['min'], 'personal_fouls': 2.5
            }
            stats_tot = {
                'points': round(p['pts'] * gp, 1), 'rebounds': round(p['reb'] * gp, 1),
                'assists': round(p['ast'] * gp, 1), 'steals': round(p['stl'] * gp, 1),
                'blocks': round(p['blk'] * gp, 1), 'turnovers': round(p['tov'] * gp, 1),
                'fg_percentage': p['fg_pct'], 'ft_percentage': p['ft_pct'],
                'three_point_percentage': 0.36, 'three_pointers_made': round(p['fg3m'] * gp, 1),
                'minutes': round(p['min'] * gp, 1), 'personal_fouls': round(2.5 * gp, 1)
            }
            players.append({
                'id': pid, 'player_id': pid, 'name': p['name'], 'team': p['team'],
                'position': p['position'], 'age': p['age'], 'games_played': gp,
                'games_started': gp, 'minutes': p['min'], 'total_minutes': round(p['min'] * gp, 1),
                'is_active': True, 'season': s, 'stats': stats_pg, 'total_stats': stats_tot
            })
        return players
    
    def clear_cache(self):
        """Clear all cached data"""
        self.player_cache.clear()
        self.season_players_cache.clear()
        self.last_cache_update = None
        print("[DATA] Cache cleared")


# Global data manager instance
data_manager = DataManager()
