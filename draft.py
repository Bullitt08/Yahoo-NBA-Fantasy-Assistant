"""
Draft Assistant Module
Analyzes historical player data with dynamic season weights, supports league-specific
auction values, configurable draft strategies (Balanced vs 5-4 Punt), and Monte Carlo
draft team optimization.
"""

import copy
import random
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from season_config import season_manager, season_to_year, year_to_season


class DraftAssistant:
    """Provides draft analysis, multi-season rankings, auction valuation, and roster optimization."""
    
    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.season_manager = season_manager
        
        # Standard 9-category fantasy basketball categories
        self.categories = [
            'points', 'rebounds', 'assists', 'steals', 'blocks', 'fg3m',
            'fg_percentage', 'ft_percentage', 'turnovers'
        ]
        
        # Category aliases for user input (e.g. from UI)
        self.category_aliases = {
            'pts': 'points',
            'points': 'points',
            'reb': 'rebounds',
            'rebounds': 'rebounds',
            'trb': 'rebounds',
            'ast': 'assists',
            'assists': 'assists',
            'stl': 'steals',
            'steals': 'steals',
            'blk': 'blocks',
            'blocks': 'blocks',
            '3pm': 'fg3m',
            'fg3m': 'fg3m',
            'threes': 'fg3m',
            'fg%': 'fg_percentage',
            'fg_pct': 'fg_percentage',
            'fg_percentage': 'fg_percentage',
            'ft%': 'ft_percentage',
            'ft_pct': 'ft_percentage',
            'ft_percentage': 'ft_percentage',
            'to': 'turnovers',
            'tov': 'turnovers',
            'turnovers': 'turnovers'
        }
        self.league_auction_values: Dict[str, float] = {}

    def set_league_auction_values(self, values: Dict[str, float]):
        """Set league-specific auction values for players."""
        self.league_auction_values = dict(values or {})

    def get_league_auction_values(self) -> Dict[str, float]:
        """Get stored league auction values."""
        return dict(self.league_auction_values)

    def reset_league_auction_value(self, player_id_or_name: str) -> bool:
        """Reset custom auction override for an individual player."""
        if not player_id_or_name:
            return False
        clean = str(player_id_or_name).strip().lower()
        keys_to_remove = [k for k in self.league_auction_values if str(k).strip().lower() == clean]
        for k in keys_to_remove:
            del self.league_auction_values[k]
        return len(keys_to_remove) > 0

    def clear_all_league_auction_values(self):
        """Reset all custom auction overrides back to default model values."""
        self.league_auction_values.clear()

    def _normalize_category_name(self, cat: str) -> str:
        """Normalize category name to canonical key."""
        clean = str(cat).lower().strip()
        return self.category_aliases.get(clean, clean)

    def get_season_weights(self, season: Optional[str] = None) -> Dict[str, float]:
        """Get dynamic relative season weights for the target season."""
        target_season = season or self.data_manager.current_season
        return self.season_manager.get_relative_season_weights(target_season)

    def calculate_fair_market_value(
        self,
        stats: Dict,
        minutes: float = 0,
        games_played: int = 0,
        mode: str = 'per_game',
        total_stats: Optional[Dict] = None
    ) -> int:
        """
        Calculate baseline projected fair market auction value based on standard $200 budget.
        Accounts for:
        - Per-game production and total season volume production
        - Games played and availability discounting (avoids overvaluing low-game spikes)
        - Category scarcity (defensive premium, shooting efficiency)
        """
        if not stats:
            return 1
        
        # When evaluating in 'total' mode, use volume production normalized to standard 82-game scale
        if mode == 'total' and total_stats:
            target_st = {
                'points': (total_stats.get('points', 0) or 0) / 82.0,
                'rebounds': (total_stats.get('rebounds', 0) or 0) / 82.0,
                'assists': (total_stats.get('assists', 0) or 0) / 82.0,
                'steals': (total_stats.get('steals', 0) or 0) / 82.0,
                'blocks': (total_stats.get('blocks', 0) or 0) / 82.0,
                'fg3m': (total_stats.get('three_pointers_made', total_stats.get('fg3m', 0)) or 0) / 82.0,
                'turnovers': (total_stats.get('turnovers', 0) or 0) / 82.0,
                'fg_percentage': total_stats.get('fg_percentage', stats.get('fg_percentage', 0)) or 0,
                'ft_percentage': total_stats.get('ft_percentage', stats.get('ft_percentage', 0)) or 0
            }
        else:
            target_st = stats

        pts = target_st.get('points', 0) or 0
        reb = target_st.get('rebounds', 0) or 0
        ast = target_st.get('assists', 0) or 0
        stl = target_st.get('steals', 0) or 0
        blk = target_st.get('blocks', 0) or 0
        fg3m = target_st.get('fg3m', target_st.get('three_pointers_made', 0)) or 0
        tov = target_st.get('turnovers', 0) or 0
        fg_pct = target_st.get('fg_percentage', 0) or 0
        ft_pct = target_st.get('ft_percentage', 0) or 0
        
        # Standard composite production score with category scarcity weights
        score = (
            pts * 1.0 +
            reb * 1.2 +
            ast * 1.5 +
            stl * 3.0 +
            blk * 3.0 +
            fg3m * 1.0 -
            tov * 1.0
        )
        if fg_pct > 0:
            score += (fg_pct - 0.46) * 45
        if ft_pct > 0:
            score += (ft_pct - 0.78) * 25
            
        if minutes < 24 and minutes > 0:
            score *= (0.5 + (minutes / 24) * 0.5)
            
        # Account for games played & availability:
        # Avoid overvaluing players who have excellent per-game numbers but very few games played.
        gp = games_played if games_played > 0 else (stats.get('games_played') or stats.get('games', 0) or 0)
        if gp > 0 and gp < 58:
            if gp < 15:
                availability = 0.30 + 0.70 * (gp / 15.0)
            elif gp < 35:
                availability = 0.60 + 0.25 * ((gp - 15.0) / 20.0)
            else:
                availability = 0.85 + 0.15 * ((gp - 35.0) / 23.0)
            score *= availability
            
        # Scale to standard auction budget ($1 to $75)
        if score >= 55:
            val = 50 + min(22, (score - 55) * 1.5)
        elif score >= 42:
            val = 35 + ((score - 42) * 1.15)
        elif score >= 30:
            val = 22 + ((score - 30) * 1.0)
        elif score >= 20:
            val = 12 + ((score - 20) * 1.0)
        elif score >= 10:
            val = 5 + ((score - 10) * 0.7)
        else:
            val = max(1, score * 0.4)
            
        return max(1, min(75, round(val)))

    def calculate_player_credit(
        self,
        stats: Dict,
        minutes: float = 0,
        games_played: int = 0,
        mode: str = 'per_game',
        total_stats: Optional[Dict] = None
    ) -> int:
        """
        Calculate model's estimated auction credit value ($1 - $75).
        Accounts for minutes stability, defensive stat premium, efficiency, and games played availability.
        """
        if not stats:
            return 1
        
        if minutes > 0 and minutes < 10:
            return 1
        
        if mode == 'total' and total_stats:
            target_st = {
                'points': (total_stats.get('points', 0) or 0) / 82.0,
                'rebounds': (total_stats.get('rebounds', 0) or 0) / 82.0,
                'assists': (total_stats.get('assists', 0) or 0) / 82.0,
                'steals': (total_stats.get('steals', 0) or 0) / 82.0,
                'blocks': (total_stats.get('blocks', 0) or 0) / 82.0,
                'fg3m': (total_stats.get('three_pointers_made', total_stats.get('fg3m', 0)) or 0) / 82.0,
                'turnovers': (total_stats.get('turnovers', 0) or 0) / 82.0,
                'fg_percentage': total_stats.get('fg_percentage', stats.get('fg_percentage', 0)) or 0,
                'ft_percentage': total_stats.get('ft_percentage', stats.get('ft_percentage', 0)) or 0
            }
        else:
            target_st = stats

        pts = target_st.get('points', 0) or 0
        reb = target_st.get('rebounds', 0) or 0
        ast = target_st.get('assists', 0) or 0
        stl = target_st.get('steals', 0) or 0
        blk = target_st.get('blocks', 0) or 0
        fg3m = target_st.get('fg3m', target_st.get('three_pointers_made', 0)) or 0
        tov = target_st.get('turnovers', 0) or 0
        fg_pct = target_st.get('fg_percentage', 0) or 0
        ft_pct = target_st.get('ft_percentage', 0) or 0
        
        score = (
            pts * 1.0 +
            reb * 1.25 +
            ast * 1.55 +
            stl * 3.1 +
            blk * 3.1 +
            fg3m * 0.6 -
            tov * 1.0
        )
        
        if fg_pct > 0:
            score += (fg_pct - 0.46) * 50
        if ft_pct > 0:
            score += (ft_pct - 0.78) * 30
            
        gp = games_played if games_played > 0 else (stats.get('games_played') or stats.get('games', 0) or 0)
        if gp > 0 and gp < 58:
            if gp < 15:
                availability = 0.30 + 0.70 * (gp / 15.0)
            elif gp < 35:
                availability = 0.60 + 0.25 * ((gp - 15.0) / 20.0)
            else:
                availability = 0.85 + 0.15 * ((gp - 35.0) / 23.0)
            score *= availability

        if score >= 55:
            credit = 50 + min(20, (score - 55) * 1.5)
        elif score >= 45:
            credit = 35 + ((score - 45) * 1.4)
        elif score >= 35:
            credit = 25 + ((score - 35) * 1.0)
        elif score >= 25:
            credit = 15 + ((score - 25) * 1.0)
        elif score >= 15:
            credit = 8 + ((score - 15) * 0.7)
        elif score >= 5:
            credit = 3 + ((score - 5) * 0.4)
        else:
            credit = max(1, score * 0.4)
            
        if minutes > 0 and minutes < 28:
            minutes_factor = 0.6 + (minutes / 28) * 0.4
            credit *= minutes_factor
            
        return max(1, min(75, round(credit)))

    def calculate_player_valuation(
        self,
        stats: Dict,
        total_stats: Optional[Dict] = None,
        games_played: int = 0,
        minutes: float = 0,
        mode: str = 'per_game',
        strategy: str = 'balanced',
        target_categories: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Shared unified valuation model for Draft Assistant, Draft Optimizer, and Team Optimizer.
        Factors in:
        - Per-game production
        - Total season volume production
        - Games played & availability discounting (avoids small-sample inflation)
        - Category scarcity & strategy weighting
        """
        fair_val = self.calculate_fair_market_value(
            stats=stats,
            minutes=minutes,
            games_played=games_played,
            mode=mode,
            total_stats=total_stats
        )
        credit_val = self.calculate_player_credit(
            stats=stats,
            minutes=minutes,
            games_played=games_played,
            mode=mode,
            total_stats=total_stats
        )
        fantasy_val = self._calculate_fantasy_value(
            stats=stats,
            games_played=games_played,
            mode=mode,
            total_stats=total_stats
        )
        strat_score = self.calculate_strategy_score(
            stats=stats,
            strategy=strategy,
            target_categories=target_categories,
            mode=mode,
            games_played=games_played,
            total_stats=total_stats
        )
        return {
            'model_fair_value': fair_val,
            'model_estimated_value': credit_val,
            'fantasy_value': fantasy_val,
            'strategy_score': strat_score
        }

    def calculate_strategy_score(
        self,
        stats: Dict,
        strategy: str = 'balanced',
        target_categories: Optional[List[str]] = None,
        mode: str = 'per_game',
        games_played: int = 0,
        total_stats: Optional[Dict] = None
    ) -> float:
        """
        Calculate player value according to the chosen draft strategy:
        - Strategy A (balanced): Above-average across all 9 categories.
        - Strategy B (punt_5_4): Heavily prioritizes the 5 target categories, keeps other 4 reasonable.
        Supports both per-game and total production modes with availability discounting.
        """
        if not stats:
            return 0.0
        
        target_st = stats
        if mode == 'total' and total_stats:
            target_st = {
                'points': (total_stats.get('points', 0) or 0) / 82.0,
                'rebounds': (total_stats.get('rebounds', 0) or 0) / 82.0,
                'assists': (total_stats.get('assists', 0) or 0) / 82.0,
                'steals': (total_stats.get('steals', 0) or 0) / 82.0,
                'blocks': (total_stats.get('blocks', 0) or 0) / 82.0,
                'fg3m': (total_stats.get('three_pointers_made', total_stats.get('fg3m', 0)) or 0) / 82.0,
                'turnovers': (total_stats.get('turnovers', 0) or 0) / 82.0,
                'fg_percentage': total_stats.get('fg_percentage', stats.get('fg_percentage', 0)) or 0,
                'ft_percentage': total_stats.get('ft_percentage', stats.get('ft_percentage', 0)) or 0
            }
        
        canonical_weights = {
            'points': 1.0,
            'rebounds': 1.2,
            'assists': 1.5,
            'steals': 3.0,
            'blocks': 3.0,
            'fg3m': 2.5,
            'fg_percentage': 15.0,
            'ft_percentage': 12.0,
            'turnovers': -1.0
        }
        
        if strategy == 'punt_5_4' and target_categories:
            norm_targets = set(self._normalize_category_name(c) for c in target_categories)
            score = 0.0
            for cat, w in canonical_weights.items():
                val = target_st.get(cat, 0) or 0
                if cat in norm_targets:
                    multiplier = 2.5
                else:
                    multiplier = 0.7
                score += val * w * multiplier
        else:
            # Strategy A: Balanced
            score = 0.0
            for cat, w in canonical_weights.items():
                val = target_st.get(cat, 0) or 0
                score += val * w

        gp = games_played if games_played > 0 else (stats.get('games_played') or stats.get('games', 0) or 0)
        if gp > 0 and gp < 50:
            score *= (0.5 + 0.5 * (gp / 50.0))

        return round(score, 2)

    def get_draft_rankings(
        self,
        top_n: Optional[int] = None,
        season: Optional[str] = None,
        league_auction_values: Optional[Dict[str, float]] = None,
        strategy: str = 'balanced',
        target_categories: Optional[List[str]] = None,
        mode: str = 'per_game',
        sort_category: Optional[str] = None,
        sort_direction: str = 'desc'
    ) -> List[Dict]:
        """
        Generate draft rankings using dynamic weighted multi-season analysis
        specifically for the selected season.
        Supports:
        - mode='per_game' vs mode='total'
        - dynamic league auction price calibration scaling model
        - distinct actual_auction_price, model_fair_value, adjusted_auction_value
        - availability and games played discounting
        - sorting by fantasy category (PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TOV)
        """
        try:
            target_season = season or self.data_manager.current_season
            season_weights = self.get_season_weights(target_season)
            seasons = list(season_weights.keys())
            
            # Fetch players per season with strict season isolation
            season_data = {}
            for s in seasons:
                season_data[s] = {
                    p['player_id']: p for p in self.data_manager.get_all_nba_players(s, min_games=0)
                }

            all_ids = set()
            for s in seasons:
                all_ids |= set(season_data[s].keys())

            if top_n is None:
                current_count = len(season_data.get(target_season, {}))
                top_n = current_count if current_count > 0 else len(all_ids)

            # Build league auction price lookup (by id and normalized lowercase name)
            price_lookup = {}
            active_prices = league_auction_values if league_auction_values is not None else self.league_auction_values
            if active_prices:
                for k, v in active_prices.items():
                    if v is not None:
                        try:
                            clean_val = float(v)
                            price_lookup[str(k).strip().lower()] = clean_val
                        except (ValueError, TypeError):
                            pass

            # Step 1: Precompute player historical profiles and baseline model fair values
            player_profiles = {}
            overridden_actual_sum = 0.0
            overridden_model_sum = 0.0

            for pid in all_ids:
                historical = {}
                historical_totals = {}
                for s in seasons:
                    p = season_data[s].get(pid)
                    if not p:
                        continue
                    st = p.get('stats', {})
                    tot_st = p.get('total_stats', {})
                    historical[s] = {
                        'points': st.get('points', 0) or 0,
                        'rebounds': st.get('rebounds', 0) or 0,
                        'assists': st.get('assists', 0) or 0,
                        'steals': st.get('steals', 0) or 0,
                        'blocks': st.get('blocks', 0) or 0,
                        'fg3m': st.get('three_pointers_made', st.get('fg3m', 0)) or 0,
                        'turnovers': st.get('turnovers', 0) or 0,
                        'fg_percentage': st.get('fg_percentage', 0) if st.get('fg_percentage') is not None else 0,
                        'ft_percentage': st.get('ft_percentage', 0) if st.get('ft_percentage') is not None else 0,
                        'minutes': p.get('minutes', 0) or 0,
                        'games': p.get('games_played', 0) or 0
                    }
                    if tot_st:
                        historical_totals[s] = {
                            'points': tot_st.get('points', 0) or 0,
                            'rebounds': tot_st.get('rebounds', 0) or 0,
                            'assists': tot_st.get('assists', 0) or 0,
                            'steals': tot_st.get('steals', 0) or 0,
                            'blocks': tot_st.get('blocks', 0) or 0,
                            'fg3m': tot_st.get('three_pointers_made', tot_st.get('fg3m', 0)) or 0,
                            'turnovers': tot_st.get('turnovers', 0) or 0,
                            'fg_percentage': tot_st.get('fg_percentage', 0) if tot_st.get('fg_percentage') is not None else 0,
                            'ft_percentage': tot_st.get('ft_percentage', 0) if tot_st.get('ft_percentage') is not None else 0,
                            'minutes': tot_st.get('minutes', 0) or 0,
                            'games': p.get('games_played', 0) or 0
                        }

                if not historical:
                    continue

                weighted = self._calculate_weighted_averages(historical, season_weights)
                target_season_stats = historical.get(target_season)
                base_stats = target_season_stats if target_season_stats else weighted

                target_totals = historical_totals.get(target_season)
                base_totals = target_totals if target_totals else {}

                meta = season_data.get(target_season, {}).get(pid)
                if not meta:
                    for s in seasons:
                        if pid in season_data[s]:
                            meta = season_data[s][pid]
                            break

                player_name = meta['name'] if meta else str(pid)
                norm_name = player_name.lower().strip()

                avg_games = int(sum((historical[s]['games'] for s in historical), 0) / max(1, len(historical)))
                actual_games = meta.get('games_played', avg_games) if meta else avg_games

                minutes = 0.0
                for s, w in season_weights.items():
                    minutes += w * (historical.get(s, {}).get('minutes', 0) or 0)

                # Baseline model fair value ($1 - $75)
                base_fair = self.calculate_fair_market_value(
                    stats=base_stats,
                    minutes=minutes,
                    games_played=actual_games,
                    mode=mode,
                    total_stats=base_totals
                )
                base_model_est = self.calculate_player_credit(
                    stats=base_stats,
                    minutes=minutes,
                    games_played=actual_games,
                    mode=mode,
                    total_stats=base_totals
                )

                # Check manual override
                actual_price = None
                if pid in price_lookup:
                    actual_price = price_lookup[pid]
                elif norm_name in price_lookup:
                    actual_price = price_lookup[norm_name]

                if actual_price is not None and actual_price > 0:
                    overridden_actual_sum += actual_price
                    overridden_model_sum += base_fair

                player_profiles[pid] = {
                    'name': player_name,
                    'meta': meta,
                    'historical': historical,
                    'historical_totals': historical_totals,
                    'weighted': weighted,
                    'base_stats': base_stats,
                    'base_totals': base_totals,
                    'actual_games': actual_games,
                    'minutes': minutes,
                    'base_fair': base_fair,
                    'base_model_est': base_model_est,
                    'actual_price': actual_price
                }

            # Step 2: Calculate Auction Calibration Scaling Factor
            # When user sets Jokic $72 -> $100, scale factor k = 100 / 72 ~= 1.3889
            # Then Doncic ($60 base) becomes max(1, round(60 * 1.3889)) = $83 - $84
            if overridden_model_sum > 0 and overridden_actual_sum > 0:
                scale_factor = overridden_actual_sum / overridden_model_sum
            else:
                scale_factor = 1.0

            # Step 3: Build Final Rankings with distinct actual, model, and adjusted values
            rankings = []
            for pid, prof in player_profiles.items():
                meta = prof['meta']
                base_fair = prof['base_fair']
                actual_price = prof['actual_price']
                base_model_est = prof['base_model_est']
                base_stats = prof['base_stats']
                base_totals = prof['base_totals']
                weighted = prof['weighted']
                actual_games = prof['actual_games']
                minutes = prof['minutes']

                if actual_price is not None:
                    adjusted_auction_val = actual_price
                else:
                    adjusted_auction_val = max(1.0, round(base_fair * scale_factor, 1))

                effective_credit = int(round(adjusted_auction_val))

                # Fantasy value & strategy score respect Per Game / Total mode
                fantasy_value = self._calculate_fantasy_value(
                    stats=weighted,
                    games_played=actual_games,
                    mode=mode,
                    total_stats=base_totals
                )
                strategy_score = self.calculate_strategy_score(
                    stats=base_stats,
                    strategy=strategy,
                    target_categories=target_categories,
                    mode=mode,
                    games_played=actual_games,
                    total_stats=base_totals
                )

                # Per-minute production
                per_minute_stats = {}
                if minutes > 0:
                    for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
                        if cat in weighted:
                            per_minute_stats[f'{cat}_per_min'] = round(weighted[cat] / minutes, 4)

                # Formulate displayed_stats based on mode
                if mode == 'total':
                    displayed_stats = {
                        'points': base_totals.get('points', round(weighted.get('points', 0) * actual_games, 1)),
                        'rebounds': base_totals.get('rebounds', round(weighted.get('rebounds', 0) * actual_games, 1)),
                        'assists': base_totals.get('assists', round(weighted.get('assists', 0) * actual_games, 1)),
                        'steals': base_totals.get('steals', round(weighted.get('steals', 0) * actual_games, 1)),
                        'blocks': base_totals.get('blocks', round(weighted.get('blocks', 0) * actual_games, 1)),
                        'fg3m': base_totals.get('fg3m', base_totals.get('three_pointers_made', round(weighted.get('fg3m', 0) * actual_games, 1))),
                        'turnovers': base_totals.get('turnovers', round(weighted.get('turnovers', 0) * actual_games, 1)),
                        'fg_percentage': base_totals.get('fg_percentage', weighted.get('fg_percentage', 0.0)),
                        'ft_percentage': base_totals.get('ft_percentage', weighted.get('ft_percentage', 0.0)),
                    }
                else:
                    displayed_stats = {
                        'points': round(weighted.get('points', 0), 1),
                        'rebounds': round(weighted.get('rebounds', 0), 1),
                        'assists': round(weighted.get('assists', 0), 1),
                        'steals': round(weighted.get('steals', 0), 1),
                        'blocks': round(weighted.get('blocks', 0), 1),
                        'fg3m': round(weighted.get('fg3m', 0), 1),
                        'turnovers': round(weighted.get('turnovers', 0), 1),
                        'fg_percentage': weighted.get('fg_percentage', 0.0),
                        'ft_percentage': weighted.get('ft_percentage', 0.0),
                    }

                entry = {
                    'player_id': pid,
                    'name': prof['name'],
                    'position': meta.get('position', '-') if meta else '-',
                    'team': meta.get('team', '-') if meta else '-',
                    'fantasy_value': fantasy_value,
                    'strategy_score': strategy_score,
                    'actual_auction_price': actual_price,
                    'model_fair_value': base_fair,
                    'projected_fair_value': base_fair,
                    'adjusted_auction_value': adjusted_auction_val,
                    'model_estimated_value': base_model_est,
                    'credit': effective_credit,
                    'weighted_stats': weighted,
                    'displayed_stats': displayed_stats,
                    'current_season_stats': base_stats,
                    'total_stats': base_totals or (meta.get('total_stats') if meta else {}) or {},
                    'per_minute_stats': per_minute_stats,
                    'trends': self._calculate_trends(prof['historical']),
                    'age': meta.get('age', 25) if meta else 25,
                    'games_played': actual_games,
                    'minutes_per_game': round(minutes, 1),
                    'injury_risk': self._assess_injury_risk_from_games(actual_games),
                    'season': target_season,
                    'mode': mode
                }
                rankings.append(entry)

            # Sort by category if requested, otherwise by strategy/fantasy value
            cat_map = {
                'PTS': 'points',
                'REB': 'rebounds',
                'AST': 'assists',
                'STL': 'steals',
                'BLK': 'blocks',
                '3PM': 'fg3m',
                '3PTM': 'fg3m',
                'FG%': 'fg_percentage',
                'FT%': 'ft_percentage',
                'TOV': 'turnovers',
                'TO': 'turnovers'
            }
            if sort_category and sort_category.upper() in ['CREDIT', 'PRICE', 'VALUE']:
                is_reverse = (sort_direction.lower() != 'asc')
                rankings.sort(
                    key=lambda x: (
                        x.get('credit') is not None,
                        x.get('credit', 0) or 0
                    ),
                    reverse=is_reverse
                )
            elif sort_category and sort_category.upper() in cat_map:
                stat_key = cat_map[sort_category.upper()]
                is_reverse = (sort_direction.lower() != 'asc')
                rankings.sort(
                    key=lambda x: (
                        x.get('displayed_stats', {}).get(stat_key) is not None,
                        x.get('displayed_stats', {}).get(stat_key, 0.0) or 0.0
                    ),
                    reverse=is_reverse
                )
            else:
                sort_key = 'strategy_score' if strategy == 'punt_5_4' else 'fantasy_value'
                rankings.sort(key=lambda x: x[sort_key], reverse=True)
            
            for i, p in enumerate(rankings[:top_n]):
                p['draft_rank'] = i + 1

            return rankings[:top_n]
        except Exception as e:
            print(f"[DRAFT] Error generating rankings for {season}: {e}")
            fallback_count = top_n if top_n is not None else 100
            return self._get_sample_rankings(fallback_count)

    def _calculate_weighted_averages(self, historical_stats: Dict, season_weights: Dict[str, float]) -> Dict:
        """Calculate weighted averages using dynamic season weights."""
        weighted_stats = {}
        total_weight = 0.0
        for s, w in season_weights.items():
            if s in historical_stats:
                st = historical_stats[s]
                total_weight += w
                for cat in self.categories + ['minutes']:
                    if cat in st:
                        weighted_stats[cat] = weighted_stats.get(cat, 0.0) + (st[cat] * w)
        if total_weight > 0:
            for cat in list(weighted_stats.keys()):
                weighted_stats[cat] = round(weighted_stats[cat] / total_weight, 3)
        return weighted_stats

    def _assess_injury_risk_from_games(self, games_played: int) -> str:
        """Assess injury risk based on games played."""
        if games_played >= 68:
            return 'Low'
        elif games_played >= 50:
            return 'Medium'
        return 'High'

    def _calculate_fantasy_value(
        self,
        stats: Dict,
        games_played: int = 0,
        mode: str = 'per_game',
        total_stats: Optional[Dict] = None
    ) -> float:
        """Calculate baseline fantasy value score considering games played and mode."""
        if not stats:
            return 0.0
        
        target_st = stats
        if mode == 'total' and total_stats:
            target_st = {
                'points': (total_stats.get('points', 0) or 0) / 82.0,
                'rebounds': (total_stats.get('rebounds', 0) or 0) / 82.0,
                'assists': (total_stats.get('assists', 0) or 0) / 82.0,
                'steals': (total_stats.get('steals', 0) or 0) / 82.0,
                'blocks': (total_stats.get('blocks', 0) or 0) / 82.0,
                'fg3m': (total_stats.get('three_pointers_made', total_stats.get('fg3m', 0)) or 0) / 82.0,
                'turnovers': (total_stats.get('turnovers', 0) or 0) / 82.0,
                'fg_percentage': total_stats.get('fg_percentage', stats.get('fg_percentage', 0)) or 0,
                'ft_percentage': total_stats.get('ft_percentage', stats.get('ft_percentage', 0)) or 0
            }

        scoring_weights = {
            'points': 1.0,
            'rebounds': 1.2,
            'assists': 1.5,
            'steals': 3.0,
            'blocks': 3.0,
            'fg3m': 2.5,
            'fg_percentage': 12.0,
            'ft_percentage': 10.0,
            'turnovers': -1.0
        }
        fantasy_value = 0.0
        for category, weight in scoring_weights.items():
            val = target_st.get(category, 0) or 0
            fantasy_value += val * weight

        gp = games_played if games_played > 0 else (stats.get('games_played') or stats.get('games', 0) or 0)
        if gp > 0 and gp < 55:
            if gp < 15:
                availability = 0.35 + 0.65 * (gp / 15.0)
            elif gp < 35:
                availability = 0.65 + 0.25 * ((gp - 15.0) / 20.0)
            else:
                availability = 0.90 + 0.10 * ((gp - 35.0) / 20.0)
            fantasy_value *= availability

        return round(fantasy_value, 2)

    def _calculate_trends(self, historical_stats: Dict) -> Dict:
        """Analyze performance trends across seasons with safe fallback defaults."""
        trends = {
            'points_trend': 0.0,
            'rebounds_trend': 0.0,
            'assists_trend': 0.0,
            'overall_trend': 'stable',
            'trend': 'stable'
        }
        seasons = sorted(historical_stats.keys())
        if len(seasons) < 2:
            return trends
        
        for category in ['points', 'rebounds', 'assists']:
            first_val = historical_stats[seasons[0]].get(category, 0) or 0
            last_val = historical_stats[seasons[-1]].get(category, 0) or 0
            if first_val > 0:
                trend_pct = ((last_val - first_val) / first_val) * 100
                trends[f'{category}_trend'] = round(trend_pct, 1)
            else:
                trends[f'{category}_trend'] = 0.0
        
        vals = [v for k, v in trends.items() if k.endswith('_trend') and isinstance(v, (int, float))]
        avg_trend = np.mean(vals) if vals else 0
        if avg_trend > 5:
            trends['overall_trend'] = 'improving'
        elif avg_trend < -5:
            trends['overall_trend'] = 'declining'
        else:
            trends['overall_trend'] = 'stable'
        return trends

    def _assess_injury_risk(self, historical_stats: Dict) -> str:
        """Assess injury risk across multiple seasons."""
        games = [s['games'] for s in historical_stats.values() if 'games' in s]
        if not games:
            return 'Low'
        avg_g = np.mean(games)
        if avg_g >= 68:
            return 'Low'
        elif avg_g >= 50:
            return 'Medium'
        return 'High'

    def build_player_analysis(
        self,
        player_id: str,
        season: Optional[str] = None,
        league_auction_values: Optional[Dict[str, float]] = None,
        mode: str = 'per_game'
    ) -> Optional[Dict]:
        """Assemble multi-season stats, trends, auction tiers, and meta for player modal/API."""
        target_season = season or self.data_manager.current_season
        season_weights = self.get_season_weights(target_season)
        seasons = list(season_weights.keys())
        
        historical = {}
        historical_totals = {}
        recent_meta = None
        for s in seasons:
            season_players = {
                p['player_id']: p for p in self.data_manager.get_all_nba_players(s, min_games=0)
            }
            p = season_players.get(player_id)
            if p:
                st = p.get('stats', {})
                tot_st = p.get('total_stats', {})
                historical[s] = {
                    'points': st.get('points', 0) or 0,
                    'rebounds': st.get('rebounds', 0) or 0,
                    'assists': st.get('assists', 0) or 0,
                    'steals': st.get('steals', 0) or 0,
                    'blocks': st.get('blocks', 0) or 0,
                    'fg3m': st.get('three_pointers_made', st.get('fg3m', 0)) or 0,
                    'turnovers': st.get('turnovers', 0) or 0,
                    'fg_percentage': st.get('fg_percentage', 0) if st.get('fg_percentage') is not None else 0,
                    'ft_percentage': st.get('ft_percentage', 0) if st.get('ft_percentage') is not None else 0,
                    'minutes': p.get('minutes', 0) or 0,
                    'games': p.get('games_played', 0) or 0
                }
                if tot_st:
                    historical_totals[s] = {
                        'points': tot_st.get('points', 0) or 0,
                        'rebounds': tot_st.get('rebounds', 0) or 0,
                        'assists': tot_st.get('assists', 0) or 0,
                        'steals': tot_st.get('steals', 0) or 0,
                        'blocks': tot_st.get('blocks', 0) or 0,
                        'fg3m': tot_st.get('three_pointers_made', tot_st.get('fg3m', 0)) or 0,
                        'turnovers': tot_st.get('turnovers', 0) or 0,
                        'fg_percentage': tot_st.get('fg_percentage', 0) if tot_st.get('fg_percentage') is not None else 0,
                        'ft_percentage': tot_st.get('ft_percentage', 0) if tot_st.get('ft_percentage') is not None else 0,
                        'minutes': tot_st.get('minutes', 0) or 0,
                        'games': p.get('games_played', 0) or 0
                    }
                if not recent_meta or s == target_season:
                    recent_meta = p
                    
        if not historical:
            return None
            
        weighted = self._calculate_weighted_averages(historical, season_weights)
        target_stats = historical.get(target_season, weighted)
        target_totals = historical_totals.get(target_season, {})
        trends = self._calculate_trends(historical)
        injury_risk = self._assess_injury_risk(historical)
        
        player_name = recent_meta.get('name', player_id) if recent_meta else player_id
        norm = player_name.lower().strip()
        
        active_prices = league_auction_values if league_auction_values is not None else self.league_auction_values
        actual_price = None
        if active_prices:
            if player_id in active_prices:
                actual_price = float(active_prices[player_id])
            elif norm in active_prices:
                actual_price = float(active_prices[norm])

        minutes = target_stats.get('minutes', 0) or 0
        actual_games = recent_meta.get('games_played', 0) if recent_meta else 0
        
        projected_fair_value = self.calculate_fair_market_value(
            stats=target_stats,
            minutes=minutes,
            games_played=actual_games,
            mode=mode,
            total_stats=target_totals
        )
        model_estimated_value = self.calculate_player_credit(
            stats=target_stats,
            minutes=minutes,
            games_played=actual_games,
            mode=mode,
            total_stats=target_totals
        )
        
        # Calibration scaling factor if active overrides exist
        scale_factor = 1.0
        if active_prices:
            # Check calibration
            rankings_sample = self.get_draft_rankings(top_n=20, season=target_season, league_auction_values=active_prices, mode=mode)
            matched = next((p for p in rankings_sample if p['player_id'] == player_id or p['name'].lower() == norm), None)
            if matched:
                adjusted_auction_val = matched['adjusted_auction_value']
                effective_credit = matched['credit']
            else:
                adjusted_auction_val = actual_price if actual_price is not None else projected_fair_value
                effective_credit = int(round(adjusted_auction_val))
        else:
            adjusted_auction_val = projected_fair_value
            effective_credit = int(actual_price) if actual_price is not None and actual_price > 0 else model_estimated_value

        per_min = {}
        if minutes > 0:
            for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
                if cat in weighted:
                    per_min[f'{cat}_per_min'] = round(weighted[cat] / minutes, 4)
                    
        return {
            'player_id': player_id,
            'name': player_name,
            'position': recent_meta.get('position', '-') if recent_meta else '-',
            'team': recent_meta.get('team', '-') if recent_meta else '-',
            'weighted_stats': weighted,
            'current_season_stats': target_stats,
            'total_stats': target_totals or (recent_meta.get('total_stats') if recent_meta else {}) or {},
            'trends': trends,
            'injury_risk': injury_risk,
            'per_minute_stats': per_min,
            'actual_auction_price': actual_price,
            'model_fair_value': projected_fair_value,
            'projected_fair_value': projected_fair_value,
            'adjusted_auction_value': adjusted_auction_val,
            'model_estimated_value': model_estimated_value,
            'credit': effective_credit,
            'season': target_season,
            'historical_seasons': list(historical.keys())
        }

    def get_player_comparison(
        self,
        player_ids: List[str],
        season: Optional[str] = None,
        league_auction_values: Optional[Dict[str, float]] = None
    ) -> List[Dict]:
        """Compare multiple players side by side using selected season data."""
        comparisons = []
        for pid in player_ids:
            analysis = self.build_player_analysis(pid, season=season, league_auction_values=league_auction_values)
            if analysis:
                comparisons.append(analysis)
        return comparisons

    def optimize_draft_roster(
        self,
        current_roster: Optional[List[Dict]] = None,
        budget: int = 200,
        roster_size: int = 15,
        strategy: str = 'balanced',
        target_categories: Optional[List[str]] = None,
        season: Optional[str] = None,
        league_auction_values: Optional[Dict[str, float]] = None,
        num_simulations: int = 250,
        mode: str = 'per_game',
        **kwargs
    ) -> Dict:
        """
        Monte Carlo Draft Team Optimizer:
        Optimizes candidate rosters using a multi-factor objective:
        Score = 60% Win Probability (Monte Carlo)
              + 20% Category / Strategy Fit (Balanced vs 5-4 Punt)
              + 10% Roster / Positional Fit (PG, SG, G, SF, PF, F, C, C, Util, Util, 3 BN, 2 IL)
              + 10% Player Value / Surplus
        Considers both per-game and total/volume production, games played, availability,
        budget limits, and 15-player league position constraints.
        """
        if kwargs.get('existing_roster') is not None:
            er = kwargs['existing_roster']
            if current_roster is None or len(current_roster) == 0:
                current_roster = er

        target_season = season or self.data_manager.current_season
        current_roster = current_roster or []
        
        # Get draft rankings for player pool with mode consideration
        all_pool = self.get_draft_rankings(
            top_n=None,
            season=target_season,
            league_auction_values=league_auction_values,
            strategy=strategy,
            target_categories=target_categories,
            mode=mode
        )

        # Hydrate current_roster with complete statistical profiles from player pool
        pool_by_id = {str(p.get('player_id')): p for p in all_pool if p.get('player_id')}
        pool_by_name = {str(p.get('name', '')).lower().strip(): p for p in all_pool if p.get('name')}

        hydrated_roster = []
        for item in current_roster:
            if isinstance(item, str):
                p_id = None
                p_name = item.strip()
                custom_credit = None
                custom_pos = None
            elif isinstance(item, dict):
                p_id = str(item.get('player_id') or '')
                p_name = str(item.get('name') or item.get('player_name') or '').strip()
                custom_credit = item.get('credit')
                custom_pos = item.get('position')
            else:
                continue

            matched = pool_by_id.get(p_id) or pool_by_name.get(p_name.lower())
            if matched:
                full_p = dict(matched)
                if custom_credit is not None:
                    full_p['credit'] = custom_credit
                if custom_pos and custom_pos != 'UTIL':
                    full_p['position'] = custom_pos
                hydrated_roster.append(full_p)
            elif isinstance(item, dict):
                analysis = self.build_player_analysis(p_id or p_name, season=target_season, league_auction_values=league_auction_values, mode=mode)
                if analysis:
                    full_p = dict(analysis)
                    if custom_credit is not None:
                        full_p['credit'] = custom_credit
                    if custom_pos:
                        full_p['position'] = custom_pos
                    hydrated_roster.append(full_p)
                else:
                    hydrated_roster.append(item)
            elif isinstance(item, str):
                hydrated_roster.append({'name': item, 'credit': 1, 'position': 'UTIL'})

        current_roster = hydrated_roster

        # Configurable objective weights (Requirement 7)
        obj_weights = kwargs.get('objective_weights') or {
            'win_prob': 0.60,
            'strategy_fit': 0.20,
            'roster_fit': 0.10,
            'player_value': 0.10
        }
        w_win = float(obj_weights.get('win_prob', 0.60))
        w_strat = float(obj_weights.get('strategy_fit', 0.20))
        w_roster = float(obj_weights.get('roster_fit', 0.10))
        w_val = float(obj_weights.get('player_value', 0.10))
        
        # Calculate spent budget and occupied positions
        spent = sum(p.get('credit', 1) for p in current_roster if isinstance(p, dict))
        remaining_budget = max(roster_size - len(current_roster), budget - spent)
        slots_to_fill = max(0, roster_size - len(current_roster))
        
        if slots_to_fill == 0:
            assigned_current = self._assign_roster_slots(current_roster, roster_size)
            cat_totals = self._calculate_roster_category_totals(assigned_current)
            return {
                'success': True,
                'optimal_roster': assigned_current,
                'recommended_roster': assigned_current,
                'total_cost': spent,
                'remaining_budget': budget - spent,
                'win_probability': 75.0,
                'simulated_win_rate': 0.75,
                'strategy': strategy,
                'target_categories': target_categories or [],
                'simulated_stats': cat_totals,
                'projected_category_totals': cat_totals,
                'objective_score': 75.0,
                'objective_breakdown': {
                    'win_probability': 75.0,
                    'strategy_fit': 75.0,
                    'roster_fit': 100.0,
                    'player_value': 75.0,
                    'composite_score': 75.0,
                    'weights': {
                        'win_probability': w_win,
                        'strategy_fit': w_strat,
                        'roster_fit': w_roster,
                        'player_value': w_val
                    }
                },
                'message': 'Roster is already full.'
            }

        # Filter out players already drafted
        drafted_names = {p['name'].lower().strip() for p in current_roster if p.get('name')}
        available_pool = [p for p in all_pool if p['name'].lower().strip() not in drafted_names]

        # Normalize target categories if 5-4 punt
        norm_targets = set()
        if strategy == 'punt_5_4' and target_categories:
            norm_targets = {self._normalize_category_name(c) for c in target_categories}

        # Positional buckets helper
        def has_pos(player, pos):
            return pos.upper() in player.get('position', '').upper()

        best_roster = None
        best_score = -float('inf')
        best_win_prob = 50.0
        best_breakdown = {}

        # Baseline opponent category averages for Monte Carlo comparison
        # (Typical 12-team 9-cat league benchmarks for 13 players)
        league_avg_benchmarks = {
            'points': 14.5 * 10,
            'rebounds': 6.0 * 10,
            'assists': 3.5 * 10,
            'steals': 1.1 * 10,
            'blocks': 0.8 * 10,
            'fg3m': 1.8 * 10,
            'fg_percentage': 0.472,
            'ft_percentage': 0.785,
            'turnovers': 1.8 * 10
        }

        num_candidates = min(500, max(120, num_simulations * 2))
        sorted_candidates = list(available_pool)
        if strategy == 'punt_5_4' and norm_targets:
            sorted_candidates.sort(key=lambda x: x.get('strategy_score', 0), reverse=True)
        else:
            sorted_candidates.sort(key=lambda x: x.get('fantasy_value', 0), reverse=True)

        for attempt in range(num_candidates):
            candidate_picks = []
            current_cost = 0
            
            existing_positions = [(p.get('position') or '').upper() for p in current_roster]
            missing_pos = []
            if not any('PG' in ep for ep in existing_positions): missing_pos.append('PG')
            if not any('SG' in ep for ep in existing_positions): missing_pos.append('SG')
            if not any('SF' in ep for ep in existing_positions): missing_pos.append('SF')
            if not any('PF' in ep for ep in existing_positions): missing_pos.append('PF')
            c_cnt = sum(1 for ep in existing_positions if 'C' in ep)
            if c_cnt < 2:
                for _ in range(2 - c_cnt):
                    missing_pos.append('C')
            
            stars = [p for p in sorted_candidates if p['credit'] >= 25][:30]
            mids = [p for p in sorted_candidates if 8 <= p['credit'] < 25][:40]
            cheap = [p for p in sorted_candidates if p['credit'] < 8]
            
            def get_valid_pick(pool, pos_req=None):
                remaining_slots = slots_to_fill - len(candidate_picks)
                max_affordable = (remaining_budget - current_cost) - (remaining_slots - 1)
                if max_affordable < 1:
                    return None
                
                candidates = [
                    p for p in pool
                    if p not in candidate_picks
                    and p['credit'] <= max_affordable
                    and (pos_req is None or has_pos(p, pos_req))
                ]
                if not candidates:
                    return None
                candidates.sort(key=lambda x: x.get('strategy_score', x.get('fantasy_value', 0)), reverse=True)
                return random.choice(candidates[:min(5, len(candidates))])

            # Fill missing core positions
            for pos in missing_pos:
                pick = get_valid_pick(stars + mids + cheap, pos_req=pos)
                if pick:
                    candidate_picks.append(pick)
                    current_cost += pick['credit']

            # Fill remaining slots with best affordable players
            while len(candidate_picks) < slots_to_fill:
                remaining_slots = slots_to_fill - len(candidate_picks)
                max_affordable = (remaining_budget - current_cost) - (remaining_slots - 1)
                if max_affordable < 1:
                    break
                
                avg_remaining = (remaining_budget - current_cost) / remaining_slots
                if avg_remaining > 20 and len(candidate_picks) < 3:
                    pick = get_valid_pick(stars) or get_valid_pick(mids) or get_valid_pick(cheap)
                elif avg_remaining > 10:
                    pick = get_valid_pick(mids) or get_valid_pick(cheap)
                else:
                    pick = get_valid_pick(cheap) or get_valid_pick(mids)
                    
                if not pick:
                    pick = get_valid_pick(available_pool)
                    if not pick:
                        break
                        
                candidate_picks.append(pick)
                current_cost += pick['credit']

            if len(candidate_picks) < slots_to_fill:
                continue

            full_roster = current_roster + candidate_picks
            roster_totals = self._calculate_roster_category_totals(full_roster)
            
            # --- 1. Roster Fit Score (0-100) ---
            # Coverage of 10 starters: PG, SG, G (>=3 guards), SF, PF, F (>=3 forwards), C (>=2 centers)
            cov_pg = 1.0 if sum(1 for p in full_roster if 'PG' in (p.get('position') or '').upper()) >= 1 else 0.0
            cov_sg = 1.0 if sum(1 for p in full_roster if 'SG' in (p.get('position') or '').upper()) >= 1 else 0.0
            cov_g  = 1.0 if sum(1 for p in full_roster if any(x in (p.get('position') or '').upper() for x in ['PG', 'SG', 'G'])) >= 3 else 0.0
            cov_sf = 1.0 if sum(1 for p in full_roster if 'SF' in (p.get('position') or '').upper()) >= 1 else 0.0
            cov_pf = 1.0 if sum(1 for p in full_roster if 'PF' in (p.get('position') or '').upper()) >= 1 else 0.0
            cov_f  = 1.0 if sum(1 for p in full_roster if any(x in (p.get('position') or '').upper() for x in ['SF', 'PF', 'F'])) >= 3 else 0.0
            cov_c  = min(1.0, sum(1 for p in full_roster if 'C' in (p.get('position') or '').upper()) / 2.0)
            roster_fit_score = ((cov_pg + cov_sg + cov_g + cov_sf + cov_pf + cov_f + (cov_c * 2)) / 8.0) * 100.0

            # --- 2. Strategy Fit Score (0-100) ---
            if strategy == 'punt_5_4' and norm_targets:
                # 5 Target Categories must strongly dominate (> benchmark)
                target_ratios = []
                for cat in norm_targets:
                    val = roster_totals.get(cat, 0)
                    bench = league_avg_benchmarks.get(cat, 1.0)
                    r = (bench / max(0.1, val)) if cat == 'turnovers' else (val / max(0.1, bench))
                    target_ratios.append(r)
                
                # 4 Non-Target Categories must avoid catastrophic collapse (ratio >= 0.70)
                other_ratios = []
                catastrophe_penalty = 0.0
                for cat in self.categories:
                    if cat not in norm_targets:
                        val = roster_totals.get(cat, 0)
                        bench = league_avg_benchmarks.get(cat, 1.0)
                        r = (bench / max(0.1, val)) if cat == 'turnovers' else (val / max(0.1, bench))
                        other_ratios.append(r)
                        if r < 0.65:
                            catastrophe_penalty += 20.0  # Avoid catastrophic weaknesses
                
                target_score_comp = min(100.0, np.mean(target_ratios) * 75.0)
                other_score_comp = min(100.0, np.mean(other_ratios) * 60.0)
                strategy_fit_score = max(0.0, min(100.0, (target_score_comp * 0.7 + other_score_comp * 0.3) - catastrophe_penalty))
            else:
                # Balanced: Competitive across all 9 categories
                category_ratios = []
                for cat in self.categories:
                    val = roster_totals.get(cat, 0)
                    bench = league_avg_benchmarks.get(cat, 1.0)
                    r = (bench / max(0.1, val)) if cat == 'turnovers' else (val / max(0.1, bench))
                    category_ratios.append(r)
                
                avg_r = float(np.mean(category_ratios))
                min_r = float(np.min(category_ratios))
                var_r = float(np.var(category_ratios))
                balanced_raw = (avg_r * 60.0) + (min_r * 40.0) - (var_r * 30.0)
                strategy_fit_score = max(0.0, min(100.0, balanced_raw))

            # --- 3. Player / Auction Value Score (0-100) ---
            total_val = sum(p.get('fantasy_value', 0) for p in full_roster)
            total_spend = sum(p.get('credit', 1) for p in full_roster)
            player_value_score = min(100.0, max(0.0, (total_val / max(1, total_spend)) * 14.0))

            # --- 4. Monte Carlo Win Probability (0-100) ---
            sim_count = min(100, max(40, num_simulations // 2))
            wins = 0
            for _ in range(sim_count):
                cats_won = 0
                for cat in self.categories:
                    team_val = roster_totals.get(cat, 0) * random.gauss(1.0, 0.10)
                    opp_val = league_avg_benchmarks.get(cat, 1.0) * random.gauss(1.0, 0.10)
                    if cat == 'turnovers':
                        if team_val < opp_val:
                            cats_won += 1
                    else:
                        if team_val > opp_val:
                            cats_won += 1
                if cats_won >= 5:
                    wins += 1
            cand_win_prob = round((wins / sim_count) * 100, 1)

            # Combined multi-factor objective score:
            # Score = 60% Win Probability + 20% Category/Strategy Fit + 10% Roster Fit + 10% Player Value
            # Rosters with win probability > 50% generally preferred
            composite_score = (
                (w_win * cand_win_prob) +
                (w_strat * strategy_fit_score) +
                (w_roster * roster_fit_score) +
                (w_val * player_value_score)
            )

            if composite_score > best_score:
                best_score = composite_score
                best_roster = full_roster
                best_win_prob = cand_win_prob
                best_breakdown = {
                    'win_probability': cand_win_prob,
                    'strategy_fit': round(strategy_fit_score, 2),
                    'roster_fit': round(roster_fit_score, 2),
                    'player_value': round(player_value_score, 2),
                    'composite_score': round(composite_score, 2),
                    'weights': {
                        'win_probability': w_win,
                        'strategy_fit': w_strat,
                        'roster_fit': w_roster,
                        'player_value': w_val
                    }
                }

        # Fallback if no full candidate succeeded
        if not best_roster:
            best_roster = current_roster + sorted_candidates[:slots_to_fill]
            best_win_prob = 55.0
            best_breakdown = {
                'win_probability': best_win_prob,
                'strategy_fit': 50.0,
                'roster_fit': 50.0,
                'player_value': 50.0,
                'composite_score': 50.0,
                'weights': {
                    'win_probability': w_win,
                    'strategy_fit': w_strat,
                    'roster_fit': w_roster,
                    'player_value': w_val
                }
            }

        # Assign standard fantasy roster slots to final roster (10 Starters + 3 BN + 2 IL)
        best_roster = self._assign_roster_slots(best_roster, roster_size)

        total_cost = sum(p.get('credit', 1) for p in best_roster)
        cat_totals = self._calculate_roster_category_totals(best_roster)
        return {
            'success': True,
            'optimal_roster': best_roster,
            'recommended_roster': best_roster,
            'newly_added': [p for p in best_roster if p not in current_roster],
            'total_cost': total_cost,
            'remaining_budget': max(0, budget - total_cost),
            'win_probability': best_win_prob,
            'simulated_win_rate': (best_win_prob / 100.0) if best_win_prob > 1 else best_win_prob,
            'strategy': strategy,
            'target_categories': list(norm_targets) if norm_targets else self.categories,
            'simulated_stats': cat_totals,
            'projected_category_totals': cat_totals,
            'season': target_season,
            'mode': mode,
            'objective_score': round(best_score if best_score > -float('inf') else 50.0, 2),
            'objective_breakdown': best_breakdown
        }

    def _assign_roster_slots(self, roster: List[Dict], roster_size: int = 15) -> List[Dict]:
        """
        Assign standard fantasy roster slots according to 15-player league configuration:
        10 Starters: PG, SG, G, SF, PF, F, C, C, Util, Util
        3 Bench: BN, BN, BN
        2 Injured Reserve: IL, IL
        """
        if roster_size >= 15:
            slot_names = ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'C', 'Util', 'Util', 'BN', 'BN', 'BN', 'IL', 'IL']
        else:
            slot_names = ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'C', 'Util', 'Util', 'BN', 'BN', 'BN'][:roster_size]

        remaining = [dict(p) for p in roster]
        slot_map = {}  # slot_index -> player

        def pos_match(player, target):
            pos = (player.get('position') or '').upper()
            if target in ['PG', 'SG', 'SF', 'PF', 'C']:
                return target in pos
            if target == 'G':
                return any(x in pos for x in ['PG', 'SG', 'G'])
            if target == 'F':
                return any(x in pos for x in ['SF', 'PF', 'F'])
            return True

        def pop_best_for(target, prefer_healthy=True):
            cand_idx = -1
            best_val = -float('inf')
            for i, p in enumerate(remaining):
                if pos_match(p, target):
                    is_inj = (p.get('injury_risk') == 'High' or p.get('is_injured'))
                    score = p.get('fantasy_value', 0)
                    if prefer_healthy and is_inj:
                        score -= 50
                    if score > best_val:
                        best_val = score
                        cand_idx = i
            if cand_idx >= 0:
                return remaining.pop(cand_idx)
            return None

        # 1. Fill specific starter slots (PG, SG, SF, PF, C, C)
        for s in ['PG', 'SG', 'SF', 'PF', 'C', 'C']:
            idx = next((i for i, name in enumerate(slot_names) if name == s and i not in slot_map), None)
            if idx is not None:
                p = pop_best_for(s, prefer_healthy=True)
                if p:
                    p['roster_slot'] = s
                    slot_map[idx] = p

        # 2. Fill compound starter slots (G, F)
        for s in ['G', 'F']:
            idx = next((i for i, name in enumerate(slot_names) if name == s and i not in slot_map), None)
            if idx is not None:
                p = pop_best_for(s, prefer_healthy=True)
                if p:
                    p['roster_slot'] = s
                    slot_map[idx] = p

        # 3. If IL slots exist, assign high-risk / injured players first
        il_indices = [i for i, name in enumerate(slot_names) if name == 'IL' and i not in slot_map]
        for idx in il_indices:
            inj_idx = next((i for i, p in enumerate(remaining) if p.get('injury_risk') == 'High' or p.get('is_injured')), None)
            if inj_idx is not None:
                p = remaining.pop(inj_idx)
                p['roster_slot'] = 'IL'
                slot_map[idx] = p

        # 4. Fill Util slots
        util_indices = [i for i, name in enumerate(slot_names) if name == 'Util' and i not in slot_map]
        for idx in util_indices:
            if remaining:
                p = remaining.pop(0)
                p['roster_slot'] = 'Util'
                slot_map[idx] = p

        # 5. Fill BN slots
        bn_indices = [i for i, name in enumerate(slot_names) if name == 'BN' and i not in slot_map]
        for idx in bn_indices:
            if remaining:
                p = remaining.pop(0)
                p['roster_slot'] = 'BN'
                slot_map[idx] = p

        # 6. Fill any remaining unassigned slots
        for idx, s in enumerate(slot_names):
            if idx not in slot_map and remaining:
                p = remaining.pop(0)
                p['roster_slot'] = s
                slot_map[idx] = p

        # 7. Assemble final list in exact slot order
        result = [slot_map[i] for i in range(len(slot_names)) if i in slot_map]
        for p in remaining:
            p['roster_slot'] = 'BN'
            result.append(p)

        return result

    def _calculate_roster_category_totals(self, roster: List[Dict]) -> Dict[str, float]:
        """Aggregate per-game category contributions of a roster."""
        totals = {cat: 0.0 for cat in self.categories}
        fg_makes = 0.0
        fg_attempts = 0.0
        ft_makes = 0.0
        ft_attempts = 0.0
        
        for p in roster:
            st = p.get('displayed_stats') or p.get('weighted_stats') or p.get('stats') or {}
            for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks', 'turnovers']:
                totals[cat] += float(st.get(cat, 0.0) or 0.0)
            totals['fg3m'] += float(st.get('three_pointers_made', st.get('fg3m', 0.0)) or 0.0)
            
            fg_pct = float(st.get('fg_percentage', 0.46) or 0.46)
            fga = float(st.get('field_goal_attempts', 12.0) or 12.0)
            fg_makes += fg_pct * fga
            fg_attempts += fga
            
            ft_pct = float(st.get('ft_percentage', 0.78) or 0.78)
            fta = float(st.get('free_throw_attempts', 4.0) or 4.0)
            ft_makes += ft_pct * fta
            ft_attempts += fta
            
        totals['fg_percentage'] = round(fg_makes / max(1.0, fg_attempts), 4)
        totals['ft_percentage'] = round(ft_makes / max(1.0, ft_attempts), 4)
        for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks', 'fg3m', 'turnovers']:
            totals[cat] = round(totals[cat], 1)
        return totals

    def _get_sample_rankings(self, top_n: int) -> List[Dict]:
        """Fallback sample rankings"""
        sample = [
            {'player_id': '1', 'name': 'Nikola Jokić', 'position': 'C', 'team': 'DEN', 'fantasy_value': 65.2, 'credit': 68, 'draft_rank': 1, 'age': 31, 'games_played': 79, 'minutes_per_game': 34.6, 'injury_risk': 'Low'},
            {'player_id': '2', 'name': 'Shai Gilgeous-Alexander', 'position': 'PG', 'team': 'OKC', 'fantasy_value': 62.8, 'credit': 64, 'draft_rank': 2, 'age': 27, 'games_played': 80, 'minutes_per_game': 34.1, 'injury_risk': 'Low'},
            {'player_id': '3', 'name': 'Giannis Antetokounmpo', 'position': 'PF', 'team': 'MIL', 'fantasy_value': 61.5, 'credit': 62, 'draft_rank': 3, 'age': 31, 'games_played': 73, 'minutes_per_game': 35.2, 'injury_risk': 'Low'},
            {'player_id': '4', 'name': 'Luka Dončić', 'position': 'PG', 'team': 'DAL', 'fantasy_value': 59.3, 'credit': 58, 'draft_rank': 4, 'age': 26, 'games_played': 70, 'minutes_per_game': 37.5, 'injury_risk': 'Medium'},
        ]
        return sample[:top_n]