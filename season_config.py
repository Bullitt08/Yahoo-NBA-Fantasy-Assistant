"""
Centralized NBA Season Configuration & Dynamic Season Resolver
Eliminates hardcoded seasons and automatically shifts historical weights.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# Configurable relative historical weights:
# Offset 0: Target / Current active season (60%)
# Offset 1: 1 season ago (30%)
# Offset 2: 2 seasons ago (10%)
DEFAULT_RELATIVE_WEIGHTS: Dict[int, float] = {
    0: 0.60,
    1: 0.30,
    2: 0.10
}


def season_to_year(season_str: str) -> int:
    """
    Convert NBA season string (e.g., '2025-26') to ending calendar year (e.g., 2026)
    used by Basketball Reference and the database.
    """
    if not season_str or not isinstance(season_str, str):
        return 2026
    
    clean = season_str.strip()
    if '-' in clean:
        parts = clean.split('-')
        start_year = int(parts[0])
        return start_year + 1
    
    # If already a 4-digit year string
    try:
        return int(clean)
    except ValueError:
        return 2026


def year_to_season(year: int) -> str:
    """
    Convert ending calendar year (e.g., 2026) to NBA season string (e.g., '2025-26').
    """
    start_year = int(year) - 1
    end_suffix = str(year)[-2:]
    return f"{start_year}-{end_suffix}"


def sort_seasons_descending(seasons: List[str]) -> List[str]:
    """
    Sort a collection of NBA season strings dynamically descending by start/end year.
    Newest season is guaranteed to be first (e.g., 2026-27, 2025-26, 2024-25...).
    """
    if not seasons:
        return []
    return sorted(list(dict.fromkeys(seasons)), key=lambda s: season_to_year(s), reverse=True)


def detect_current_season() -> str:
    """
    Automatically detect the active NBA season based on the calendar date
    or an explicit environment variable override (NBA_CURRENT_SEASON).
    
    NBA season schedule:
    - October (month 10) through June (month 6) is the regular season and playoffs.
    - July-September is off-season / pre-draft preparation for the upcoming season.
    - If month >= 10: season ending in year + 1 (e.g. Oct 2025 -> 2025-26).
    - If month < 10: season ending in current year (e.g. Feb 2026 -> 2025-26).
    """
    override = os.getenv('NBA_CURRENT_SEASON')
    if override:
        return override.strip()

    now = datetime.now()
    if now.month >= 10:
        start_year = now.year
        end_year = now.year + 1
    else:
        start_year = now.year - 1
        end_year = now.year

    return f"{start_year}-{str(end_year)[-2:]}"


def get_relative_season_weights(base_season: Optional[str] = None) -> Dict[str, float]:
    """Module-level helper to get relative season weights."""
    return season_manager.get_relative_season_weights(base_season)


class SeasonManager:
    """
    Central manager for NBA seasons, dynamic historical weights, and season shifting.
    """
    _instance: Optional['SeasonManager'] = None

    def __init__(self, current_season: Optional[str] = None, weights: Optional[Tuple[float, ...]] = None):
        self._configured_season = current_season
        if weights:
            self.relative_weights = {i: w for i, w in enumerate(weights)}
        else:
            self.relative_weights = dict(DEFAULT_RELATIVE_WEIGHTS)

    @classmethod
    def get_instance(cls) -> 'SeasonManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def current_season(self) -> str:
        """Get the current active NBA season."""
        if self._configured_season:
            return self._configured_season
        return detect_current_season()

    @current_season.setter
    def current_season(self, season: str):
        self._configured_season = season

    def set_relative_weights(self, weights: Dict[int, float]):
        """Update relative historical weights (e.g., {0: 0.6, 1: 0.3, 2: 0.1})."""
        total = sum(weights.values())
        if total > 0:
            self.relative_weights = {k: v / total for k, v in weights.items()}
        else:
            self.relative_weights = dict(weights)

    def get_relative_season_weights(self, base_season: Optional[str] = None) -> Dict[str, float]:
        """
        Generate dynamic season-to-weight mapping shifted to base_season.
        
        Example with base_season='2025-26':
            {'2025-26': 0.60, '2024-25': 0.30, '2023-24': 0.10}
        
        Example with base_season='2026-27':
            {'2026-27': 0.60, '2025-26': 0.30, '2024-25': 0.10}
        """
        target = base_season or self.current_season
        base_year = season_to_year(target)

        weights_by_season: Dict[str, float] = {}
        for offset, weight in sorted(self.relative_weights.items()):
            season_str = year_to_season(base_year - offset)
            weights_by_season[season_str] = round(weight, 4)

        return weights_by_season

    def get_season_weights(self, base_season: Optional[str] = None) -> Dict[str, float]:
        """Alias for get_relative_season_weights."""
        return self.get_relative_season_weights(base_season)

    def get_available_seasons(self, base_season: Optional[str] = None, count: int = 5) -> List[str]:
        """
        Return ordered list of available seasons starting from base_season downwards.
        """
        target = base_season or self.current_season
        base_year = season_to_year(target)
        return [year_to_season(base_year - i) for i in range(count)]

    def get_previous_season(self, season_str: str, offset: int = 1) -> str:
        """Get the season string offset by N years prior."""
        year = season_to_year(season_str)
        return year_to_season(year - offset)


# Global default instance
season_manager = SeasonManager.get_instance()
