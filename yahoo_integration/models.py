"""
Data models for Yahoo Fantasy Basketball
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime


@dataclass
class YahooPlayer:
    """Yahoo Fantasy Player Model"""
    player_key: str
    player_id: str
    name: str
    first_name: str
    last_name: str
    position: str
    team: str
    team_abbr: str
    is_undroppable: bool = False
    position_type: str = 'P'  # P = Player, G = Goalie (for hockey)
    uniform_number: Optional[str] = None
    display_position: str = ''
    image_url: Optional[str] = None
    editorial_team_abbr: str = ''
    
    # Yahoo-specific stats
    ownership: Optional[Dict[str, Any]] = None
    percent_owned: Optional[float] = None
    
    # Real NBA stats (merged from our database)
    nba_stats: Optional[Dict[str, Any]] = None
    season: str = '2024-25'
    
    def __post_init__(self):
        if not self.display_position:
            self.display_position = self.position


@dataclass
class Team:
    """Yahoo Fantasy Team Model"""
    team_key: str
    team_id: str
    league_key: str = ""
    name: str = ""
    team_logo_url: Optional[str] = None
    waiver_priority: int = 0
    number_of_moves: int = 0
    number_of_trades: int = 0
    roster_adds: Dict[str, int] = field(default_factory=dict)
    clinched_playoffs: bool = False
    league_scoring_type: str = 'head'
    
    # Team managers
    managers: List[Dict[str, Any]] = field(default_factory=list)
    
    # Team standings
    team_standings: Optional[Dict[str, Any]] = None
    wins: int = 0
    losses: int = 0
    ties: int = 0
    standing: int = 0
    
    # Roster
    roster: List['YahooPlayer'] = field(default_factory=list)
    
    # Projected/Actual points
    team_points: Optional[Dict[str, float]] = None
    team_projected_points: Optional[Dict[str, float]] = None


@dataclass
class League:
    """Yahoo Fantasy League Model"""
    league_key: str
    league_id: str
    name: str
    season: str
    game_code: str
    
    # League settings
    num_teams: int = 0
    scoring_type: str = 'head'  # head, point, headpoint
    draft_status: str = 'predraft'
    current_week: int = 1
    start_week: int = 1
    end_week: int = 24
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_finished: bool = False
    
    # League URL
    url: Optional[str] = None
    
    # Stat categories
    stat_categories: List[Dict[str, Any]] = field(default_factory=list)
    roster_positions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Teams in league
    teams: List[Team] = field(default_factory=list)
    
    # Settings
    settings: Optional[Dict[str, Any]] = None


@dataclass
class Player:
    """Generic NBA Player Model (for matching with Yahoo players)"""
    player_id: str
    name: str
    first_name: str
    last_name: str
    team: str
    position: str
    
    # Stats from our database
    stats: Dict[str, Any] = field(default_factory=dict)
    season: str = '2024-25'
    games_played: int = 0
    minutes: float = 0.0
    
    # Additional info
    age: Optional[int] = None
    experience: Optional[int] = None
    is_active: bool = True


@dataclass
class MatchupWeek:
    """Yahoo Fantasy Matchup for a specific week"""
    week: int
    week_start: str
    week_end: str
    matchups: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PlayerTransaction:
    """Yahoo Fantasy Player Transaction"""
    transaction_key: str
    transaction_id: str
    type: str  # add, drop, trade, etc.
    status: str
    timestamp: datetime
    
    # Players involved
    players: List[Dict[str, Any]] = field(default_factory=list)
    
    # Teams involved (for trades)
    teams: List[str] = field(default_factory=list)
