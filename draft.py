"""
Draft Assistant Module
Analyzes historical player data to provide draft recommendations
"""

import pandas as pd
import numpy as np
from datetime import datetime


class DraftAssistant:
    """Provides draft analysis and recommendations based on historical data"""
    
    def __init__(self, data_manager):
        self.data_manager = data_manager
        # Updated season weights for real Basketball Reference data
        self.season_weights = {
            '2024-25': 0.6,  # Most recent season (2025 in DB) - highest weight
            '2023-24': 0.3,  # Previous season (2024 in DB)
            '2022-23': 0.1   # Older season (2023 in DB) - lowest weight
        }
        
        # Standard fantasy basketball categories (aligned with DataManager stats keys)
        self.categories = [
            'points', 'rebounds', 'assists', 'steals', 'blocks', 'fg3m',
            'fg_percentage', 'ft_percentage', 'turnovers'
        ]
    
    def get_draft_rankings(self, top_n=None):
        """Generate draft rankings using weighted multi-season analysis (2024-25, 2023-24, 2022-23)."""
        try:
            seasons = list(self.season_weights.keys())
            season_data = {}
            for s in seasons:
                # Get all players without games filter to include all active players
                season_data[s] = {
                    p['player_id']: p for p in self.data_manager.get_all_nba_players(s, min_games=0)
                }

            # Unified set of player ids present in any season
            all_ids = set()
            for s in seasons:
                all_ids |= set(season_data[s].keys())

            # Use actual number of active players from current season if top_n not specified
            if top_n is None:
                current_season_players = len(season_data.get('2024-25', {}))
                top_n = current_season_players if current_season_players > 0 else len(all_ids)

            rankings = []
            for pid in all_ids:
                # Build historical stats per player across seasons
                historical = {}
                for s in seasons:
                    p = season_data[s].get(pid)
                    if not p:
                        continue
                    st = p.get('stats', {})
                    # normalize keys to expected categories
                    hist_entry = {
                        'points': st.get('points', 0),
                        'rebounds': st.get('rebounds', 0),
                        'assists': st.get('assists', 0),
                        'steals': st.get('steals', 0),
                        'blocks': st.get('blocks', 0),
                        'fg3m': st.get('three_pointers_made', 0),
                        'turnovers': st.get('turnovers', 0),
                        'fg_percentage': st.get('fg_percentage', 0) if st.get('fg_percentage') is not None else 0,
                        'ft_percentage': st.get('ft_percentage', 0) if st.get('ft_percentage') is not None else 0,
                        'minutes': p.get('minutes', 0),
                        'games': p.get('games_played', 0)
                    }
                    historical[s] = hist_entry

                if not historical:
                    continue

                # Weighted averages
                weighted = self._calculate_weighted_averages(historical)

                # Compute fantasy value
                fantasy_value = self._calculate_fantasy_value(weighted)

                # Per-minute stats
                minutes = 0.0
                for s, w in self.season_weights.items():
                    minutes += w * (historical.get(s, {}).get('minutes', 0) or 0)
                per_minute_stats = {}
                if minutes > 0:
                    for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
                        if cat in weighted:
                            per_minute_stats[f'{cat}_per_min'] = round(weighted[cat] / minutes, 4)

                # Choose most recent season presence for meta
                recent = None
                for s in seasons:
                    if pid in season_data[s]:
                        recent = season_data[s][pid]
                        break

                # Calculate credit value using CURRENT SEASON stats (2024-25) not weighted
                # This ensures consistency with dashboard and recommendation displays
                current_season_stats = historical.get('2024-25', {})
                if current_season_stats:
                    # Use current season stats and minutes
                    player_credit = self.calculate_player_credit(current_season_stats, current_season_stats.get('minutes', 0))
                else:
                    # Fallback to weighted if current season not available
                    player_credit = self.calculate_player_credit(weighted, weighted.get('minutes', 0))
                
                ranking_entry = {
                    'player_id': pid,
                    'name': recent['name'] if recent else pid,
                    'position': recent.get('position', '-') if recent else '-',
                    'team': recent.get('team', '-') if recent else '-',
                    'fantasy_value': fantasy_value,
                    'credit': player_credit,  # NEW: Player credit value
                    'weighted_stats': weighted,
                    'per_minute_stats': per_minute_stats,
                    'trends': self._calculate_trends(historical),
                    'age': recent.get('age', 25) if recent else 25,
                    'games_played': int(sum((historical[s]['games'] for s in historical), 0) / max(1, len(historical))),
                    'minutes_per_game': round(minutes, 1),
                    'injury_risk': self._assess_injury_risk_from_games(int(sum((historical[s]['games'] for s in historical), 0) / max(1, len(historical))))
                }
                rankings.append(ranking_entry)

            rankings.sort(key=lambda x: x['fantasy_value'], reverse=True)
            for i, player in enumerate(rankings[:top_n]):
                player['draft_rank'] = i + 1
            return rankings[:top_n]
        except Exception as e:
            print(f"Error generating draft rankings: {e}")
            # Use fallback with actual player count or default
            fallback_count = top_n if top_n is not None else 100
            return self._get_sample_rankings(fallback_count)
    
    def _calculate_weighted_averages(self, historical_stats):
        """Calculate weighted averages based on season recency"""
        weighted_stats = {}
        total_weight = 0
        for season, weight in self.season_weights.items():
            if season in historical_stats:
                stats = historical_stats[season]
                total_weight += weight
                for category in self.categories + ['minutes']:
                    if category in stats:
                        weighted_stats[category] = weighted_stats.get(category, 0) + (stats[category] * weight)
        if total_weight > 0:
            for category in list(weighted_stats.keys()):
                weighted_stats[category] /= total_weight
        return weighted_stats
    
    def _assess_injury_risk_from_games(self, games_played):
        """Assess injury risk based on games played (out of ~82)"""
        if games_played >= 70:
            return 'Low'
        elif games_played >= 50:
            return 'Medium'
        else:
            return 'High'
    
    def _get_sample_rankings(self, top_n):
        """Fallback sample rankings if NBA API fails (Yahoo Auction values)"""
        sample_rankings = [
            {
                'player_id': '203999',
                'name': 'Nikola Jokić',
                'position': 'C',
                'team': 'DEN',
                'fantasy_value': 65.2,
                'credit': 68,  # Elite tier - Yahoo $68
                'draft_rank': 1,
                'age': 31,
                'games_played': 79,
                'minutes_per_game': 34.6,
                'injury_risk': 'Low'
            },
            {
                'player_id': '1630162',
                'name': 'Shai Gilgeous-Alexander',
                'position': 'PG',
                'team': 'OKC',
                'fantasy_value': 62.8,
                'credit': 64,  # Elite tier - Yahoo $64
                'draft_rank': 2,
                'age': 27,
                'games_played': 80,
                'minutes_per_game': 34.1,
                'injury_risk': 'Low'
            },
            {
                'player_id': '203507',
                'name': 'Giannis Antetokounmpo',
                'position': 'PF',
                'team': 'MIL',
                'fantasy_value': 61.5,
                'credit': 62,  # Elite tier - Yahoo $62
                'draft_rank': 3,
                'age': 31,
                'games_played': 73,
                'minutes_per_game': 35.2,
                'injury_risk': 'Low'
            },
            {
                'player_id': '1629029',
                'name': 'Luka Dončić',
                'position': 'PG',
                'team': 'DAL',
                'fantasy_value': 59.3,
                'credit': 58,  # Elite tier - Yahoo $58
                'draft_rank': 4,
                'age': 26,
                'games_played': 70,
                'minutes_per_game': 37.5,
                'injury_risk': 'Medium'
            },
            {
                'player_id': '203076',
                'name': 'Anthony Davis',
                'position': 'PF-C',
                'team': 'LAL',
                'fantasy_value': 57.1,
                'credit': 55,  # Elite tier - Yahoo $55
                'draft_rank': 5,
                'age': 32,
                'games_played': 76,
                'minutes_per_game': 35.1,
                'injury_risk': 'Medium'
            }
        ]
        return sample_rankings[:top_n]
    
    def _calculate_fantasy_value(self, stats):
        """Calculate overall fantasy value score"""
        if not stats:
            return 0
        
        # Standard fantasy basketball scoring weights (aligned with our stat keys)
        scoring_weights = {
            'points': 1.0,
            'rebounds': 1.2,
            'assists': 1.5,
            'steals': 3.0,
            'blocks': 3.0,
            'fg3m': 3.0,  # 3-pointers made
            'fg_percentage': 10.0,  # 0-1 scale
            'ft_percentage': 8.0,   # 0-1 scale
            'turnovers': -1.0
        }
        
        fantasy_value = 0
        
        for category, value in stats.items():
            if category in scoring_weights:
                if category in ['fg_percentage', 'ft_percentage']:
                    # Handle percentage categories (0-1 range)
                    fantasy_value += value * scoring_weights[category]
                else:
                    fantasy_value += value * scoring_weights[category]
        
        return round(fantasy_value, 2)
    
    def calculate_player_credit(self, stats, minutes=0):
        """Calculate player credit value based on Yahoo Fantasy Auction Draft system
        
        Yahoo Fantasy Basketball Auction Draft Budget: $200 total
        Credit distribution based on 2024-25 season stats (most recent season):
        - Elite players (top 2-3%): $50-70 (Jokic, Giannis, SGA level)
        - Star players (top 10%): $35-49 (All-Stars, franchise players)
        - Strong starters (top 20%): $25-34 (Quality starters)
        - Solid starters (top 35%): $15-24 (Average starters)
        - Role players (top 50%): $8-14 (Bench contributors)
        - Deep bench (bottom 50%): $1-7 (Waiver wire players)
        
        Stat weights (Yahoo 9-Category H2H):
        - PTS: 1.0x (baseline)
        - REB: 1.2x (more valuable)
        - AST: 1.5x (scarce for non-guards)
        - STL: 3.0x (very rare)
        - BLK: 3.0x (very rare)
        - 3PM: 0.5x (bonus for spacing)
        - FG%: League avg 46.0% baseline
        - FT%: League avg 78.0% baseline
        - TO: -1.0x (negative impact)
        """
        if not stats:
            return 1
        
        # Minutes filter - players with <10 MPG get minimum credit
        if minutes < 10:
            return 1
        
        # Extract per-game stats (current season only - 2024-25)
        pts = stats.get('points', 0)
        reb = stats.get('rebounds', 0)
        ast = stats.get('assists', 0)
        stl = stats.get('steals', 0)
        blk = stats.get('blocks', 0)
        fg3m = stats.get('three_pointers_made', 0)
        to = stats.get('turnovers', 0)
        fg_pct = stats.get('fg_percentage', 0)
        ft_pct = stats.get('ft_percentage', 0)
        
        # Yahoo Fantasy 9-Category scoring formula
        # Each stat contributes to overall fantasy value
        score = 0
        
        # Counting stats with Yahoo weights
        score += pts * 1.0        # Points (baseline)
        score += reb * 1.2        # Rebounds (valued 20% higher)
        score += ast * 1.5        # Assists (valued 50% higher - scarce)
        score += stl * 3.0        # Steals (3x value - very rare)
        score += blk * 3.0        # Blocks (3x value - very rare)
        score += fg3m * 0.5       # Three-pointers (spacing bonus)
        
        # Shooting efficiency impact (league averages as baseline)
        # FG% contribution (46.0% league average)
        if fg_pct > 0:
            fg_impact = (fg_pct - 0.46) * 50  # Each 1% above/below avg = 0.5 pts
            score += fg_impact
        
        # FT% contribution (78.0% league average)
        if ft_pct > 0:
            ft_impact = (ft_pct - 0.78) * 30  # Each 1% above/below avg = 0.3 pts
            score += ft_impact
        
        # Turnovers penalty
        score -= to * 1.0  # Each TO reduces value
        
        # Convert composite score to Yahoo Auction $ value (1-70 range)
        # Distribution matches Yahoo Fantasy auction values
        if score >= 55:  # Elite tier (Jokic $65-70, Giannis $60-65, SGA $55-60)
            credit = 50 + min(20, (score - 55) * 1.5)
        elif score >= 45:  # Star tier ($35-49)
            credit = 35 + ((score - 45) * 1.4)
        elif score >= 35:  # Strong starter tier ($25-34)
            credit = 25 + ((score - 35) * 1.0)
        elif score >= 25:  # Solid starter tier ($15-24)
            credit = 15 + ((score - 25) * 1.0)
        elif score >= 15:  # Role player tier ($8-14)
            credit = 8 + ((score - 15) * 0.7)
        elif score >= 5:  # Deep bench tier ($3-7)
            credit = 3 + ((score - 5) * 0.4)
        else:  # Waiver wire tier ($1-2)
            credit = max(1, score * 0.4)
        
        # Minutes adjustment - players with limited minutes get proportional reduction
        # This prevents low-minute high-efficiency players from being overvalued
        if minutes < 28:  # Less than starter minutes (~28 MPG)
            minutes_factor = 0.6 + (minutes / 28) * 0.4  # 60-100% based on minutes
            credit *= minutes_factor
        
        # Final credit value: $1-70 range (Yahoo auction budget scale)
        return max(1, min(70, round(credit)))
    
    def _calculate_per_minute_production(self, stats):
        """Calculate per-minute production metrics"""
        if not stats or stats.get('minutes', 0) == 0:
            return {}
        
        minutes = stats['minutes']
        per_minute = {}
        
        for category in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
            if category in stats:
                per_minute[f'{category}_per_min'] = round(stats[category] / minutes, 4)
        
        return per_minute
    
    def _calculate_trends(self, historical_stats):
        """Analyze performance trends across seasons"""
        trends = {}
        
        seasons = sorted(historical_stats.keys())
        if len(seasons) < 2:
            return {'trend': 'insufficient_data'}
        
        # Calculate trends for key categories
        for category in ['points', 'rebounds', 'assists']:
            if category in historical_stats[seasons[0]] and category in historical_stats[seasons[-1]]:
                old_value = historical_stats[seasons[0]][category]
                new_value = historical_stats[seasons[-1]][category]
                
                if old_value > 0:
                    trend_pct = ((new_value - old_value) / old_value) * 100
                    trends[f'{category}_trend'] = round(trend_pct, 1)
        
        # Overall trend assessment
        avg_trend = np.mean([v for v in trends.values() if isinstance(v, (int, float))])
        
        if avg_trend > 5:
            trends['overall_trend'] = 'improving'
        elif avg_trend < -5:
            trends['overall_trend'] = 'declining'
        else:
            trends['overall_trend'] = 'stable'
        
        return trends
    
    def _assess_injury_risk(self, historical_stats):
        """Assess injury risk based on games played"""
        total_games = []
        
        for season_stats in historical_stats.values():
            if 'games' in season_stats:
                total_games.append(season_stats['games'])
        
        if not total_games:
            return 'unknown'
        
        avg_games = np.mean(total_games)
        
        if avg_games >= 70:
            return 'low'
        elif avg_games >= 60:
            return 'medium'
        else:
            return 'high'

    def build_player_analysis(self, player_id: str):
        """Assemble weighted stats, trends, and meta for a player for Draft modal/API."""
        seasons = list(self.season_weights.keys())
        historical = {}
        recent_meta = None
        for s in seasons:
            season_players = {p['player_id']: p for p in self.data_manager.get_all_nba_players(s, min_games=0)}
            p = season_players.get(player_id)
            if p:
                st = p.get('stats', {})
                historical[s] = {
                    'points': st.get('points', 0),
                    'rebounds': st.get('rebounds', 0),
                    'assists': st.get('assists', 0),
                    'steals': st.get('steals', 0),
                    'blocks': st.get('blocks', 0),
                    'turnovers': st.get('turnovers', 0),
                    'fg_percentage': st.get('fg_percentage', 0) if st.get('fg_percentage') is not None else 0,
                    'ft_percentage': st.get('ft_percentage', 0) if st.get('ft_percentage') is not None else 0,
                    'minutes': p.get('minutes', 0),
                    'games': p.get('games_played', 0)
                }
                if not recent_meta:
                    recent_meta = p
        if not historical:
            return None
        weighted = self._calculate_weighted_averages(historical)
        trends = self._calculate_trends(historical)
        injury_risk = self._assess_injury_risk(historical)
        minutes = weighted.get('minutes', 0)
        per_min = {}
        if minutes:
            for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
                if cat in weighted:
                    per_min[f'{cat}_per_min'] = round(weighted[cat] / minutes, 4)
        return {
            'player_id': player_id,
            'name': recent_meta.get('name') if recent_meta else player_id,
            'position': recent_meta.get('position', '-') if recent_meta else '-',
            'team': recent_meta.get('team', '-') if recent_meta else '-',
            'weighted_stats': weighted,
            'trends': trends,
            'injury_risk': injury_risk,
            'per_minute_stats': per_min
        }
    
    def get_player_comparison(self, player_ids):
        """Compare multiple players side by side"""
        comparisons = []
        
        for player_id in player_ids:
            # This would get actual player data in production
            player_data = self._get_sample_player_data(player_id)
            comparisons.append(player_data)
        
        return comparisons
    
    def get_position_rankings(self, position):
        """Get rankings filtered by position"""
        all_rankings = self.get_draft_rankings()
        return [p for p in all_rankings if position.upper() in p['position'].upper()]
    
    def _get_sample_player_pool(self):
        """Sample player pool for MVP testing (2025-26 season)"""
        return [
            {
                'player_id': '2544',
                'name': 'LeBron James',
                'position': 'SF/PF',
                'team': 'LAL',
                'age': 41
            },
            {
                'player_id': '203076',
                'name': 'Anthony Davis',
                'position': 'PF/C',
                'team': 'LAL',
                'age': 32
            },
            {
                'player_id': '203507',
                'name': 'Giannis Antetokounmpo',
                'position': 'PF/SF',
                'team': 'MIL',
                'age': 31
            },
            {
                'player_id': '201566',
                'name': 'Russell Westbrook',
                'position': 'PG',
                'team': 'DEN',
                'age': 37
            },
            {
                'player_id': '202695',
                'name': 'Jayson Tatum',
                'position': 'SF/PF',
                'team': 'BOS',
                'age': 27
            },
            {
                'player_id': '203081',
                'name': 'Damian Lillard',
                'position': 'PG',
                'team': 'MIL',
                'age': 35
            },
            {
                'player_id': '203999',
                'name': 'Nikola Jokić',
                'position': 'C',
                'team': 'DEN',
                'age': 31
            },
            {
                'player_id': '201939',
                'name': 'Stephen Curry',
                'position': 'PG',
                'team': 'GSW',
                'age': 37
            },
            {
                'player_id': '203954',
                'name': 'Joel Embiid',
                'position': 'C',
                'team': 'PHI',
                'age': 31
            },
            {
                'player_id': '1629029',
                'name': 'Luka Dončić',
                'position': 'PG/SG',
                'team': 'DAL',
                'age': 26
            }
        ]
    
    def _get_sample_historical_stats(self, player_id):
        """Generate sample historical stats for MVP testing"""
        
        # Sample historical data for key players (updated for 2025-26 season)
        sample_data = {
            '2544': {  # LeBron James
                '2024-25': {'points': 24.8, 'rebounds': 7.0, 'assists': 8.8, 'steals': 1.1, 'blocks': 0.4, 'fg3m': 2.4, 'fg_pct': 0.535, 'ft_pct': 0.741, 'turnovers': 3.8, 'games': 76, 'minutes': 34.5},
                '2023-24': {'points': 25.7, 'rebounds': 7.3, 'assists': 8.3, 'steals': 1.3, 'blocks': 0.5, 'fg3m': 2.1, 'fg_pct': 0.540, 'ft_pct': 0.750, 'turnovers': 3.5, 'games': 71, 'minutes': 35.3},
                '2022-23': {'points': 28.9, 'rebounds': 8.3, 'assists': 6.8, 'steals': 0.9, 'blocks': 0.6, 'fg3m': 2.9, 'fg_pct': 0.500, 'ft_pct': 0.764, 'turnovers': 3.9, 'games': 55, 'minutes': 35.5}
            },
            '203507': {  # Giannis Antetokounmpo
                '2024-25': {'points': 32.1, 'rebounds': 11.2, 'assists': 6.8, 'steals': 1.3, 'blocks': 1.0, 'fg3m': 0.8, 'fg_pct': 0.618, 'ft_pct': 0.672, 'turnovers': 3.2, 'games': 78, 'minutes': 35.8},
                '2023-24': {'points': 30.4, 'rebounds': 11.5, 'assists': 6.5, 'steals': 1.2, 'blocks': 1.1, 'fg3m': 0.6, 'fg_pct': 0.613, 'ft_pct': 0.658, 'turnovers': 3.4, 'games': 73, 'minutes': 35.2},
                '2022-23': {'points': 31.1, 'rebounds': 11.8, 'assists': 5.7, 'steals': 0.8, 'blocks': 0.8, 'fg3m': 0.8, 'fg_pct': 0.553, 'ft_pct': 0.645, 'turnovers': 4.0, 'games': 63, 'minutes': 32.1}
            },
            '203999': {  # Nikola Jokić
                '2024-25': {'points': 28.2, 'rebounds': 13.1, 'assists': 9.5, 'steals': 1.5, 'blocks': 0.8, 'fg3m': 1.2, 'fg_pct': 0.591, 'ft_pct': 0.835, 'turnovers': 2.8, 'games': 81, 'minutes': 35.2},
                '2023-24': {'points': 26.4, 'rebounds': 12.4, 'assists': 9.0, 'steals': 1.4, 'blocks': 0.9, 'fg3m': 1.0, 'fg_pct': 0.583, 'ft_pct': 0.817, 'turnovers': 3.0, 'games': 79, 'minutes': 34.6},
                '2022-23': {'points': 24.5, 'rebounds': 11.8, 'assists': 9.8, 'steals': 1.3, 'blocks': 0.7, 'fg3m': 0.9, 'fg_pct': 0.633, 'ft_pct': 0.822, 'turnovers': 3.6, 'games': 69, 'minutes': 33.7}
            }
        }
        
        if player_id in sample_data:
            return sample_data[player_id]
        else:
            # Generate random realistic stats for other players (updated for 2025-26)
            return {
                '2024-25': {
                    'points': np.random.uniform(12, 28), 'rebounds': np.random.uniform(3, 12), 'assists': np.random.uniform(2, 8),
                    'steals': np.random.uniform(0.5, 2.0), 'blocks': np.random.uniform(0.2, 2.5), 'fg3m': np.random.uniform(0.5, 3.5),
                    'fg_pct': np.random.uniform(0.42, 0.62), 'ft_pct': np.random.uniform(0.65, 0.90), 'turnovers': np.random.uniform(1.5, 4.5),
                    'games': np.random.randint(50, 82), 'minutes': np.random.uniform(25, 38)
                },
                '2023-24': {
                    'points': np.random.uniform(10, 26), 'rebounds': np.random.uniform(2, 11), 'assists': np.random.uniform(1, 7),
                    'steals': np.random.uniform(0.4, 1.8), 'blocks': np.random.uniform(0.1, 2.2), 'fg3m': np.random.uniform(0.3, 3.2),
                    'fg_pct': np.random.uniform(0.40, 0.60), 'ft_pct': np.random.uniform(0.60, 0.88), 'turnovers': np.random.uniform(1.2, 4.2),
                    'games': np.random.randint(45, 80), 'minutes': np.random.uniform(22, 36)
                },
                '2022-23': {
                    'points': np.random.uniform(8, 24), 'rebounds': np.random.uniform(2, 10), 'assists': np.random.uniform(1, 6),
                    'steals': np.random.uniform(0.3, 1.6), 'blocks': np.random.uniform(0.1, 2.0), 'fg3m': np.random.uniform(0.2, 3.0),
                    'fg_pct': np.random.uniform(0.38, 0.58), 'ft_pct': np.random.uniform(0.58, 0.86), 'turnovers': np.random.uniform(1.0, 4.0),
                    'games': np.random.randint(40, 75), 'minutes': np.random.uniform(20, 34)
                }
            }
    
    def _get_sample_player_data(self, player_id):
        """Generate sample player data for comparison"""
        # This would return actual calculated data in production
        return {
            'player_id': player_id,
            'fantasy_value': np.random.uniform(30, 60),
            'projected_stats': {
                'points': np.random.uniform(15, 30),
                'rebounds': np.random.uniform(4, 12),
                'assists': np.random.uniform(3, 10)
            }
        }