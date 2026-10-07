"""
Recommendation Engine Module
Analyzes potential roster moves and provides optimization suggestions
Using real Basketball Reference data
"""

import numpy as np
from itertools import combinations
from typing import List, Dict, Optional, Any


class RecommendationEngine:
    """Provides intelligent roster move recommendations"""
    
    def __init__(self, data_manager, matchup_simulator, draft_assistant=None):
        self.data_manager = data_manager
        self.simulator = matchup_simulator
        self.draft_assistant = draft_assistant
        self.other_teams_rosters = []  # Will store rosters of other teams for trade suggestions
        
    def get_recommendations_for_roster(self, current_roster, free_agents, all_players, max_recommendations=100, other_teams_rosters=None, remaining_credit=None, **kwargs):
        """Get comprehensive roster move recommendations using real data
        
        Args:
            current_roster: User's current team roster
            free_agents: Players not owned by any team (true free agents)
            all_players: All NBA players
            max_recommendations: Maximum number of recommendations to return
            other_teams_rosters: List of other teams' rosters for trade suggestions
            remaining_credit: Maximum credit difference user can afford (optional)
        """
        
        try:
            recommendations = []
            seen_recommendations = set()  # Track unique recommendations to avoid duplicates
            
            # Store other teams data for trade suggestions
            if other_teams_rosters:
                self.other_teams_rosters = other_teams_rosters
            
            print(f"DEBUG: Starting recommendation generation - Roster: {len(current_roster)}, FAs: {len(free_agents)}, Other Teams: {len(self.other_teams_rosters) if self.other_teams_rosters else 0}, Remaining Credit: {remaining_credit}")
            
            # 1. Simple 1-for-1 swaps
            single_swap_recs = self._analyze_single_swaps(
                current_roster, free_agents, remaining_credit=remaining_credit
            )
            print(f"DEBUG: Found {len(single_swap_recs)} single swap recommendations")
            for rec in single_swap_recs:
                rec_key = self._get_recommendation_key(rec)
                if rec_key not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec_key)
            
            # 2. Multi-player trades (2-for-2, 3-for-3, 4-for-4, 5-for-5)
            print(f"DEBUG: Starting multi-player swap analysis...")
            multi_swap_recs = self._analyze_multi_player_swaps(
                current_roster, free_agents, remaining_credit=remaining_credit
            )
            print(f"DEBUG: Found {len(multi_swap_recs)} multi-swap recommendations")
            for rec in multi_swap_recs:
                rec_key = self._get_recommendation_key(rec)
                if rec_key not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec_key)
                else:
                    print(f"  SKIPPED DUPLICATE: {rec.get('swap_type', 'unknown')}")
            
            # 3. Value upgrades (better performance) - FREE AGENTS ONLY
            budget_upgrades = self._find_budget_upgrades(
                current_roster, free_agents, remaining_credit=remaining_credit
            )
            print(f"DEBUG: Found {len(budget_upgrades)} value upgrade recommendations")
            for rec in budget_upgrades:
                rec_key = self._get_recommendation_key(rec)
                if rec_key not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec_key)
            
            # 4. Trade suggestions with other teams (if data available)
            if self.other_teams_rosters:
                print(f"DEBUG: Starting trade analysis with {len(self.other_teams_rosters)} other teams...")
                trade_suggestions = self._analyze_trade_opportunities(
                    current_roster, self.other_teams_rosters
                )
                print(f"DEBUG: Found {len(trade_suggestions)} trade recommendations")
                for rec in trade_suggestions:
                    rec_key = self._get_recommendation_key(rec)
                    if rec_key not in seen_recommendations:
                        recommendations.append(rec)
                        seen_recommendations.add(rec_key)
            
            # Sort by impact score
            recommendations.sort(key=lambda x: x.get('impact_score', 0), reverse=True)
            
            print(f"DEBUG: Total unique recommendations: {len(recommendations)}")
            print(f"DEBUG: Breakdown by type:")
            for swap_type in ['1-for-1', '2-for-2', '3-for-3', '4-for-4', '5-for-5', 'value-play']:
                count = sum(1 for r in recommendations if r.get('swap_type') == swap_type)
                if count > 0:
                    print(f"  - {swap_type}: {count}")
            
            return recommendations[:max_recommendations]
            
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            import traceback
            traceback.print_exc()
            return self._get_sample_recommendations()
    
    def _get_recommendation_key(self, rec):
        """Generate unique key for recommendation to avoid duplicates"""
        drop_names = tuple(sorted([p['name'] for p in rec.get('drop_players', [])]))
        add_names = tuple(sorted([p['name'] for p in rec.get('add_players', [])]))
        return (drop_names, add_names)
    
    def _analyze_add_drop_moves_real_data(self, current_roster, free_agents, remaining_credit=None):
        """DEPRECATED - Use _analyze_single_swaps instead"""
        return self._analyze_single_swaps(current_roster, free_agents, remaining_credit=remaining_credit)
    
    def _analyze_single_swaps(self, current_roster, free_agents, remaining_credit=None):
        """Analyze 1-for-1 player swaps for ALL roster players with position consideration"""
        recommendations = []
        
        print(f"[DEBUG] _analyze_single_swaps: Roster={len(current_roster)}, Free Agents={len(free_agents)}")
        
        # Sort roster by value to identify upgrade candidates
        sorted_roster = sorted(current_roster, key=lambda x: self._calculate_player_value(x))
        
        # Sort free agents by value - Limit for performance
        sorted_free_agents = sorted(free_agents, 
                                    key=lambda x: self._calculate_player_value(x), 
                                    reverse=True)[:80]  # Top 80 FAs (was 150, reduced for performance)
        
        print(f"   Top 5 roster players by value: {[p['name'] for p in sorted_roster[-5:]]}")
        print(f"   Top 5 free agents by value: {[p['name'] for p in sorted_free_agents[:5]]}")
        
        # Check ALL roster players for potential upgrades
        for roster_player in sorted_roster:
            roster_value = self._calculate_player_value(roster_player)
            roster_credit = self._calculate_player_credit(roster_player)
            roster_position = roster_player.get('position', '')
            
            # Find better free agents
            for fa in sorted_free_agents:
                fa_value = self._calculate_player_value(fa)
                fa_credit = self._calculate_player_credit(fa)
                fa_position = fa.get('position', '')
                
                # Check credit constraint if applicable
                credit_change = fa_credit - roster_credit
                if remaining_credit is not None and credit_change > remaining_credit:
                    continue
                
                # Check position compatibility
                position_compatible = self._check_position_compatibility(roster_position, fa_position)
                
                # Only recommend if there's improvement AND position fits
                if fa_value > roster_value and position_compatible:
                    improvement = fa_value - roster_value
                    
                    # Calculate category improvements
                    category_changes = self._analyze_category_improvements(roster_player, fa)
                    
                    if improvement > 0.5:  # Show ALMOST ALL upgrades (very low threshold)
                        recommendations.append({
                            'type': 'single_swap',
                            'swap_type': '1-for-1',
                            'drop_players': [{
                                'name': roster_player['name'],
                                'team': roster_player.get('team', '-'),
                                'position': roster_player.get('position', '-'),
                                'stats': roster_player.get('stats', {}),
                                'value': round(roster_value, 1),
                                'credit': roster_credit,
                                'fantasy_team': roster_player.get('fantasy_team', 'My Team')
                            }],
                            'add_players': [{
                                'name': fa['name'],
                                'team': fa.get('team', '-'),
                                'position': fa.get('position', '-'),
                                'stats': fa.get('stats', {}),
                                'value': round(fa_value, 1),
                                'credit': fa_credit,
                                'fantasy_team': fa.get('fantasy_team', 'Free Agent')
                            }],
                            'credit_change': credit_change,
                            'impact_score': round(improvement, 1),
                            'all_categories': category_changes.get('all_categories', []),
                            'category_improvements': category_changes['improvements'],
                            'category_declines': category_changes['declines'],
                            'reasoning': self._generate_swap_reasoning(
                                [roster_player], [fa], improvement, credit_change, category_changes
                            ),
                            'priority': 'high' if improvement > 10.0 else 'medium'
                        })
                        
                        # Early stopping: if we have enough single swaps, stop
                        if len(recommendations) >= 60:
                            print(f"DEBUG: Early stopping at {len(recommendations)} single swaps")
                            return recommendations
        
        return recommendations
    
    def _analyze_multi_player_swaps(self, current_roster, free_agents, remaining_credit=None):
        """Analyze 2-3 player swaps with position balance"""
        recommendations = []
        
        # Analyze different swap sizes: 2-for-2, 3-for-3 (4-5 are too slow)
        swap_sizes = [2, 3]
        
        for swap_size in swap_sizes:
            # Limit combinations STRICTLY to avoid timeout/crash
            max_combos = {2: 50, 3: 30}  # VERY LIMITED for performance
            max_combo = max_combos.get(swap_size, 10)
            
            # Use LIMITED free agents to prevent performance issues
            roster_combos = list(combinations(current_roster, swap_size))[:max_combo]
            fa_combos = list(combinations(free_agents[:50], swap_size))[:max_combo]  # Only top 50 FAs
            
            # Minimum value improvement threshold
            min_improvement = {2: 0.5, 3: 1.0}
            threshold = min_improvement.get(swap_size, 0.5)
            
            print(f"DEBUG: Analyzing {swap_size}-for-{swap_size} swaps - {len(roster_combos)} roster combos, {len(fa_combos)} FA combos, threshold={threshold}")
            
            for drop_combo in roster_combos:
                drop_value_total = sum(self._calculate_player_value(p) for p in drop_combo)
                drop_credit_total = sum(self._calculate_player_credit(p) for p in drop_combo)
                drop_positions = [p.get('position', '') for p in drop_combo]
                
                for add_combo in fa_combos:
                    add_value_total = sum(self._calculate_player_value(p) for p in add_combo)
                    add_credit_total = sum(self._calculate_player_credit(p) for p in add_combo)
                    add_positions = [p.get('position', '') for p in add_combo]
                    
                    credit_change = add_credit_total - drop_credit_total
                    if remaining_credit is not None and credit_change > remaining_credit:
                        continue
                    
                    value_change = add_value_total - drop_value_total
                    
                    # Check if positions are reasonably balanced
                    position_balanced = self._check_multi_position_balance(drop_positions, add_positions)
                    
                    # Only if significant improvement
                    if value_change > threshold and position_balanced:
                        print(f"  [+] Found {swap_size}-for-{swap_size}: value_change={value_change:.1f}")
                        
                        # Calculate overall category improvements
                        all_improvements = []
                        all_declines = []
                        for i in range(len(drop_combo)):
                            cat_changes = self._analyze_category_improvements(drop_combo[i], add_combo[i])
                            all_improvements.extend(cat_changes['improvements'])
                            all_declines.extend(cat_changes['declines'])
                        
                        # Create combined changes dict
                        combined_changes = {
                            'improvements': list(set(all_improvements))[:5],
                            'declines': list(set(all_declines))[:3],
                            'combined': list(set(all_improvements + all_declines))[:6]
                        }
                        
                        recommendations.append({
                            'type': 'multi_swap',
                            'swap_type': f'{swap_size}-for-{swap_size}',
                            'drop_players': [{
                                'name': p['name'],
                                'team': p.get('team', '-'),
                                'position': p.get('position', '-'),
                                'stats': p.get('stats', {}),
                                'credit': self._calculate_player_credit(p),
                                'fantasy_team': p.get('fantasy_team', 'My Team')
                            } for p in drop_combo],
                            'add_players': [{
                                'name': p['name'],
                                'team': p.get('team', '-'),
                                'position': p.get('position', '-'),
                                'stats': p.get('stats', {}),
                                'credit': self._calculate_player_credit(p),
                                'fantasy_team': p.get('fantasy_team', 'Free Agent')
                            } for p in add_combo],
                            'credit_change': credit_change,
                            'impact_score': round(value_change, 1),
                            'all_categories': combined_changes.get('all_categories', []),
                            'category_improvements': combined_changes['improvements'],
                            'category_declines': combined_changes['declines'],
                            'reasoning': self._generate_swap_reasoning(
                                list(drop_combo), list(add_combo), value_change, credit_change, combined_changes
                            ),
                            'priority': 'high' if value_change > (threshold * 2) else 'medium'
                        })
                        
                        # Limit total multi-swaps to avoid too many options
                        if len(recommendations) >= 30:
                            print(f"DEBUG: Reached limit of {len(recommendations)} multi-swap recommendations")
                            return recommendations
        
        print(f"DEBUG: Total multi-swap recommendations found: {len(recommendations)}")
        return recommendations
    
    def _find_budget_upgrades(self, current_roster, free_agents, remaining_credit=None):
        """Find value upgrades (better performance)"""
        recommendations = []
        
        # Check ALL roster players for value opportunities
        for roster_player in current_roster:
            roster_value = self._calculate_player_value(roster_player)
            roster_credit = self._calculate_player_credit(roster_player)
            roster_position = roster_player.get('position', '')
            
            # Find better performing FAs
            for fa in free_agents:
                fa_value = self._calculate_player_value(fa)
                fa_credit = self._calculate_player_credit(fa)
                fa_position = fa.get('position', '')
                
                credit_change = fa_credit - roster_credit
                if remaining_credit is not None and credit_change > remaining_credit:
                    continue
                
                # Check position compatibility
                position_compatible = self._check_position_compatibility(roster_position, fa_position)
                
                # Value upgrade: better performance and position fits
                if fa_value > roster_value * 1.05 and position_compatible:  # Only 5% better
                    improvement = fa_value - roster_value
                    
                    # Calculate category improvements
                    category_changes = self._analyze_category_improvements(roster_player, fa)
                    
                    # Build reasoning with category details
                    improvement_str = ', '.join(category_changes['improvements'][:3]) if category_changes['improvements'] else 'overall value'
                    
                    cost_str = f" (Costs {credit_change} credits)" if credit_change > 0 else f" (Saves {abs(credit_change)} credits)" if credit_change < 0 else ""
                    
                    recommendations.append({
                        'type': 'budget_upgrade',
                        'swap_type': 'value-play',
                        'drop_players': [{
                            'name': roster_player['name'],
                            'team': roster_player.get('team', '-'),
                            'position': roster_player.get('position', '-'),
                            'stats': roster_player.get('stats', {}),
                            'credit': roster_credit,
                            'fantasy_team': roster_player.get('fantasy_team', 'My Team')
                        }],
                        'add_players': [{
                            'name': fa['name'],
                            'team': fa.get('team', '-'),
                            'position': fa.get('position', '-'),
                            'stats': fa.get('stats', {}),
                            'credit': fa_credit,
                            'fantasy_team': fa.get('fantasy_team', 'Free Agent')
                        }],
                        'credit_change': credit_change,
                        'impact_score': round(improvement, 1),
                        'category_improvements': category_changes['improvements'],
                        'category_declines': category_changes['declines'],
                        'reasoning': f"💎 Value pick: {fa['name']} is {round((fa_value/roster_value - 1) * 100)}% better! ({improvement_str}){cost_str}",
                        'priority': 'high'
                    })
        
        return recommendations[:20]  # Top 20 value plays (was 10)
    
    def _analyze_category_needs(self, current_roster, all_players):
        """Analyze which categories need improvement"""
        recommendations = []
        
        roster_stats = self._calculate_roster_stats(current_roster)
        
        # Identify weak categories
        categories = ['points', 'rebounds', 'assists', 'steals', 'blocks']
        weak_categories = []
        
        for cat in categories:
            roster_avg = roster_stats.get(cat, 0)
            league_avg = np.mean([p['stats'].get(cat, 0) for p in all_players])
            
            if roster_avg < league_avg * 0.8:  # 20% below league average
                weak_categories.append(cat)
        
        if weak_categories:
            # Find players who excel in weak categories
            for cat in weak_categories:
                top_players = sorted(all_players,
                                   key=lambda x: x['stats'].get(cat, 0),
                                   reverse=True)[:5]
                
                recommendations.append({
                    'type': 'category_need',
                    'action': 'target_category',
                    'category': cat,
                    'reasoning': f"Your roster is weak in {cat}. Consider targeting these players.",
                    'suggested_players': [
                        {
                            'name': p['name'],
                            'team': p.get('team', '-'),
                            'stat_value': p['stats'].get(cat, 0)
                        } for p in top_players
                    ],
                    'impact_score': 10.0,
                    'priority': 'medium'
                })
        
        return recommendations
    
    def _calculate_roster_stats(self, roster):
        """Calculate aggregate roster statistics"""
        stats = {
            'points': 0,
            'rebounds': 0,
            'assists': 0,
            'steals': 0,
            'blocks': 0,
            'turnovers': 0
        }
        
        for player in roster:
            player_stats = player.get('stats', {})
            for key in stats.keys():
                stats[key] += player_stats.get(key, 0)
        
        # Calculate averages
        roster_size = len(roster) if roster else 1
        for key in stats.keys():
            stats[key] /= roster_size
        
        return stats
    
    def _calculate_player_value(self, player):
        """Calculate overall fantasy value using all 9 categories (balanced approach)"""
        stats = player.get('stats', {})
        
        # Helper function to safely get numeric values
        def get_stat(key, default=0):
            val = stats.get(key, default)
            return float(val) if val is not None else default
        
        # 9-Category Fantasy Basketball (equal weight approach)
        # PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO
        
        # Counting stats (normalized)
        pts = get_stat('points', 0) * 1.0         # Points
        reb = get_stat('rebounds', 0) * 1.3       # Rebounds (slightly more valuable)
        ast = get_stat('assists', 0) * 1.5        # Assists (playmaking valued)
        stl = get_stat('steals', 0) * 3.5         # Steals (rare defensive stat)
        blk = get_stat('blocks', 0) * 3.5         # Blocks (rare defensive stat)
        threes = get_stat('three_pointers_made', 0) * 1.5  # 3-pointers made
        to = get_stat('turnovers', 0) * -2.0      # Turnovers (penalty)
        
        # Shooting percentages (scaled to match counting stats impact)
        fg_pct = get_stat('fg_percentage', 0)
        fg_value = (fg_pct - 0.45) * 100 if fg_pct else 0  # League avg ~45%
        
        ft_pct = get_stat('ft_percentage', 0)
        ft_value = (ft_pct - 0.75) * 80 if ft_pct else 0   # League avg ~75%
        
        # Total value
        value = pts + reb + ast + stl + blk + threes + to + fg_value + ft_value
        
        return value
    
    def _calculate_player_credit(self, player):
        """Calculate player credit using DraftAssistant if available"""
        if player.get('credit') is not None:
            return player['credit']
        
        if not self.draft_assistant:
            # Fallback simple calculation
            credit = max(1, int(self._calculate_player_value(player) / 10))
            player['credit'] = credit
            return credit
        
        stats = player.get('stats', {})
        minutes = player.get('minutes', 0)
        credit = self.draft_assistant.calculate_player_credit(stats, minutes)
        player['credit'] = credit
        return credit
    
    def _check_position_compatibility(self, pos1, pos2):
        """Check if two positions are compatible for swapping"""
        if not pos1 or not pos2:
            return True  # If position unknown, allow swap
        
        # Position groups (players can play multiple positions)
        guards = ['PG', 'SG', 'G']
        forwards = ['SF', 'PF', 'F']
        centers = ['C']
        
        # Combo positions
        wing = ['SG', 'SF', 'G', 'F']
        big = ['PF', 'C', 'F']
        
        # Same position = compatible
        if pos1 == pos2:
            return True
        
        # Guard swaps
        if pos1 in guards and pos2 in guards:
            return True
        
        # Forward swaps
        if pos1 in forwards and pos2 in forwards:
            return True
        
        # Wing swaps (SG/SF)
        if pos1 in wing and pos2 in wing:
            return True
        
        # Big swaps (PF/C)
        if pos1 in big and pos2 in big:
            return True
        
        return False  # Different position groups
    
    def _check_multi_position_balance(self, drop_positions, add_positions):
        """Check if multi-player swap maintains position balance"""
        # Count position types
        def count_position_types(positions):
            guards = sum(1 for p in positions if p in ['PG', 'SG', 'G'])
            forwards = sum(1 for p in positions if p in ['SF', 'PF', 'F'])
            centers = sum(1 for p in positions if p in ['C'])
            return guards, forwards, centers
        
        drop_g, drop_f, drop_c = count_position_types(drop_positions)
        add_g, add_f, add_c = count_position_types(add_positions)
        
        # Allow some flexibility (±1 in each category)
        return (abs(drop_g - add_g) <= 1 and 
                abs(drop_f - add_f) <= 1 and 
                abs(drop_c - add_c) <= 1)
    
    def _analyze_category_improvements(self, drop_player, add_player):
        """Analyze ALL changes across all 9 fantasy categories - returns EVERY category with +/- values"""
        drop_stats = drop_player.get('stats', {})
        add_stats = add_player.get('stats', {})
        
        all_categories = []  # Will show ALL 9 categories
        improvements = []
        declines = []
        
        categories = [
            ('points', 'PTS', 1.0, False),
            ('rebounds', 'REB', 1.0, False),
            ('assists', 'AST', 1.0, False),
            ('steals', 'STL', 1.0, False),
            ('blocks', 'BLK', 1.0, False),
            ('three_pointers_made', '3PM', 1.0, False),
            ('fg_percentage', 'FG%', 100, True),  # Is percentage
            ('ft_percentage', 'FT%', 100, True),  # Is percentage
            ('turnovers', 'TO', 1.0, False)  # Special case - lower is better
        ]
        
        for stat_key, stat_name, multiplier, is_percentage in categories:
            # Handle None values - convert to 0
            drop_val = drop_stats.get(stat_key, 0)
            add_val = add_stats.get(stat_key, 0)
            
            # Ensure values are numeric (not None)
            drop_val = float(drop_val) if drop_val is not None else 0.0
            add_val = float(add_val) if add_val is not None else 0.0
            
            if stat_key == 'turnovers':
                # For turnovers, LOWER is BETTER
                diff = drop_val - add_val  # Positive diff = improvement (less TO)
                
                if abs(diff) > 0.01:  # Show even tiny changes
                    if diff > 0:
                        category_str = f"{stat_name} ↓{round(abs(diff), 1)}"
                        all_categories.append(category_str)
                        improvements.append(category_str)
                    else:
                        category_str = f"{stat_name} ↑{round(abs(diff), 1)}"
                        all_categories.append(category_str)
                        declines.append(category_str)
                else:
                    all_categories.append(f"{stat_name} —")  # No change
            else:
                # For all other stats, HIGHER is BETTER
                diff = add_val - drop_val  # Positive diff = improvement
                
                if is_percentage:
                    # For percentages (FG%, FT%)
                    pct_diff = diff * 100  # Convert to percentage points
                    
                    if abs(pct_diff) > 0.01:  # Show even tiny changes
                        if pct_diff > 0:
                            category_str = f"{stat_name} +{round(pct_diff, 1)}%"
                            all_categories.append(category_str)
                            improvements.append(category_str)
                        else:
                            category_str = f"{stat_name} {round(pct_diff, 1)}%"
                            all_categories.append(category_str)
                            declines.append(category_str)
                    else:
                        all_categories.append(f"{stat_name} —")  # No change
                else:
                    # For counting stats - show ALL changes
                    if abs(diff) > 0.01:  # Show even tiny changes
                        if diff > 0:
                            category_str = f"{stat_name} +{round(diff, 1)}"
                            all_categories.append(category_str)
                            improvements.append(category_str)
                        else:
                            category_str = f"{stat_name} {round(diff, 1)}"
                            all_categories.append(category_str)
                            declines.append(category_str)
                    else:
                        all_categories.append(f"{stat_name} —")  # No change
        
        # Return ALL categories plus categorized improvements/declines
        all_changes = {
            'all_categories': all_categories,  # NEW: All 9 categories with +/- values
            'improvements': improvements,
            'declines': declines,
            'combined': improvements + declines
        }
        
        return all_changes
    
    def _generate_add_drop_reasoning(self, drop_player, add_player, improvement, credit_change=0, can_afford=True):
        """DEPRECATED - Use _generate_swap_reasoning instead"""
        drop_stats = drop_player.get('stats', {})
        add_stats = add_player.get('stats', {})
        
        # Find biggest improvement categories
        improvements = []
        for cat in ['points', 'rebounds', 'assists', 'steals', 'blocks']:
            add_val = add_stats.get(cat, 0)
            drop_val = drop_stats.get(cat, 0)
            if add_val > drop_val * 1.2:
                improvements.append(f"{cat} (+{round(add_val - drop_val, 1)})")
        
        if improvements:
            reason = f"{add_player['name']} provides better {', '.join(improvements[:2])}"
        else:
            reason = f"{add_player['name']} is a better overall player"
        
        if credit_change > 0:
            reason += f" (Costs {credit_change} credits)"
        elif credit_change < 0:
            reason += f" (Saves {abs(credit_change)} credits)"
        
        return reason
    
    def _generate_swap_reasoning(self, drop_players, add_players, improvement, credit_change, category_changes=None):
        """Generate reasoning for single or multi-player swaps with category details"""
        if len(drop_players) == 1 and len(add_players) == 1:
            # Single swap
            drop_p = drop_players[0]
            add_p = add_players[0]
            
            drop_name = drop_p['name'] if isinstance(drop_p, dict) else drop_p.get('name', 'Unknown')
            add_name = add_p['name'] if isinstance(add_p, dict) else add_p.get('name', 'Unknown')
            
            if category_changes:
                improvements = category_changes.get('improvements', [])
                declines = category_changes.get('declines', [])
                
                if improvements:
                    # Show improvements
                    cat_str = ', '.join(improvements[:3])
                    reason = f"Upgrade {drop_name} → {add_name}: {cat_str}"
                    
                    # Add declines if any
                    if declines:
                        decline_str = ', '.join(declines[:2])
                        reason += f" | Loses: {decline_str}"
                else:
                    reason = f"Upgrade {drop_name} → {add_name}: +{round(improvement, 1)} overall value"
            else:
                reason = f"Upgrade {drop_name} → {add_name}: +{round(improvement, 1)} overall value"
        else:
            # Multi-player swap
            drop_names = ', '.join([p['name'] if isinstance(p, dict) else p.get('name', '?') for p in drop_players])
            add_names = ', '.join([p['name'] if isinstance(p, dict) else p.get('name', '?') for p in add_players])
            
            if category_changes:
                improvements = category_changes.get('improvements', [])
                declines = category_changes.get('declines', [])
                
                if improvements:
                    cat_str = ', '.join(list(set(improvements))[:3])
                    reason = f"Swap {drop_names} for {add_names}: {cat_str}"
                    
                    if declines:
                        decline_str = ', '.join(list(set(declines))[:2])
                        reason += f" | Loses: {decline_str}"
                else:
                    reason = f"Swap {drop_names} for {add_names}: +{round(improvement, 1)} total value"
            else:
                reason = f"Swap {drop_names} for {add_names}: +{round(improvement, 1)} total value"
        
        if credit_change > 0:
            reason += f" (Costs {credit_change} credits)"
        elif credit_change < 0:
            reason += f" (Saves {abs(credit_change)} credits)"
        
        return reason

    def _evaluate_candidate_trade(
        self,
        current_roster: Optional[List[Dict]] = None,
        partner_roster: Optional[List[Dict]] = None,
        my_players: Optional[List[Dict]] = None,
        their_players: Optional[List[Dict]] = None,
        partner_team_name: str = "Opponent",
        swap_type: str = 'trade-1-for-1',
        **kwargs
    ) -> Optional[Dict]:
        """
        Evaluate a candidate trade:
        - Rejects unrealistic trades (huge value disparities, star-for-scrub, etc.)
        - Considers category surpluses and deficits for both teams
        - Calculates Win Probability before trade -> after trade using MatchupSimulator
        - Evaluates if the trade is mutually beneficial for BOTH teams
        - Ranks by usefulness and plausibility
        """
        if kwargs.get('my_roster') is not None:
            current_roster = kwargs['my_roster']
        if kwargs.get('opp_roster') is not None:
            partner_roster = kwargs['opp_roster']
        if kwargs.get('give_player') is not None:
            gp = kwargs['give_player']
            my_players = [gp] if isinstance(gp, dict) else list(gp)
        if kwargs.get('receive_player') is not None:
            rp = kwargs['receive_player']
            their_players = [rp] if isinstance(rp, dict) else list(rp)
        if kwargs.get('opp_name') is not None:
            partner_team_name = kwargs['opp_name']

        current_roster = current_roster or []
        partner_roster = partner_roster or []
        if not my_players or not their_players:
            return None

        my_total_value = sum(self._calculate_player_value(p) for p in my_players)
        their_total_value = sum(self._calculate_player_value(p) for p in their_players)

        if my_total_value <= 0 or their_total_value <= 0:
            return None

        # Value ratio check (must be within realistic boundary)
        value_ratio = their_total_value / max(0.1, my_total_value)
        # Avoid massively one-sided trades (giving away 40%+ more value or asking for 50%+ more)
        if value_ratio < 0.60 or value_ratio > 1.65:
            return None

        # Star disparity check: A superstar (> 50 value) must not be traded 1-for-1 for a role player (< 25)
        max_my = max(self._calculate_player_value(p) for p in my_players)
        max_their = max(self._calculate_player_value(p) for p in their_players)
        if len(my_players) == 1 and len(their_players) == 1:
            if (max_my >= 50 and max_their < 25) or (max_their >= 50 and max_my < 25):
                return None

        # Positional compatibility check:
        # Cross-position trades (e.g., trading excess PG for needed C) are common in fantasy basketball.
        # We only reject if positions are completely incompatible in a multi-player swap.
        my_positions = [p.get('position', '') for p in my_players]
        their_positions = [p.get('position', '') for p in their_players]
        if len(my_players) > 1 and len(their_players) > 1:
            if not self._check_multi_position_balance(my_positions, their_positions):
                return None

        # Build simulated rosters before and after
        my_names = {p['name'] for p in my_players}
        their_names = {p['name'] for p in their_players}
        
        user_roster_pre = list(current_roster)
        partner_roster_pre = list(partner_roster)
        
        user_roster_post = [p for p in user_roster_pre if p['name'] not in my_names] + their_players
        partner_roster_post = [p for p in partner_roster_pre if p['name'] not in their_names] + my_players

        # Calculate Win Probabilities before and after using MatchupSimulator
        win_prob_before = 50.0
        win_prob_after = 50.0
        try:
            if self.simulator and user_roster_pre and partner_roster_pre:
                sim_pre = self.simulator.simulate_matchup(user_roster_pre, partner_roster_pre)
                win_prob_before = round(sim_pre.get('win_probability', 50.0), 1)

                sim_post = self.simulator.simulate_matchup(user_roster_post, partner_roster_post)
                win_prob_after = round(sim_post.get('win_probability', 50.0), 1)
        except Exception as e:
            # Fallback estimation based on value improvement
            val_diff = their_total_value - my_total_value
            win_prob_before = 50.0
            win_prob_after = min(95.0, max(5.0, round(50.0 + (val_diff * 1.5), 1)))

        win_prob_change = round(win_prob_after - win_prob_before, 1)

        # Partner's perspective
        partner_impact = round(-win_prob_change, 1)

        # Analyze category impact for user and partner
        my_stats_total = self._sum_player_stats(my_players)
        their_stats_total = self._sum_player_stats(their_players)
        category_changes = self._compare_stat_totals(my_stats_total, their_stats_total)

        # Category surplus/deficit matching:
        partner_val_gain = my_total_value - their_total_value
        beneficial_for_both = (
            abs(win_prob_change) <= 5.0 or (partner_val_gain >= -2.0) or len(category_changes.get('declines', [])) >= 2
        )

        # Plausibility score (0 to 100)
        value_fairness = 1.0 - abs(my_total_value - their_total_value) / max(my_total_value, their_total_value)
        plausibility_num = (value_fairness * 70.0) + (30.0 if beneficial_for_both else 10.0)
        plausibility = "High" if plausibility_num >= 70 else ("Medium" if plausibility_num >= 45 else "Low")

        # Overall ranking score: usefulness (win probability gain) + plausibility
        overall_rank_score = (max(0.0, win_prob_change) * 0.6) + ((plausibility_num / 10.0) * 0.4)

        my_fantasy_team = my_players[0].get('fantasy_team', 'My Team')
        other_fantasy_team = their_players[0].get('fantasy_team', partner_team_name)

        my_names_str = ', '.join(p['name'] for p in my_players)
        their_names_str = ', '.join(p['name'] for p in their_players)

        reasoning = (
            f"🤝 Trade with {partner_team_name}: {my_names_str} for {their_names_str}. "
            f"Win prob: {win_prob_before}% → {win_prob_after}% ({'+' if win_prob_change >= 0 else ''}{win_prob_change}%). "
            f"{'Beneficial for both teams.' if beneficial_for_both else 'Fair market value.'}"
        )

        return {
            'type': 'trade',
            'swap_type': swap_type,
            'trade_partner': partner_team_name,
            'drop_players': [{
                'name': p['name'],
                'team': p.get('team', '-'),
                'position': p.get('position', '-'),
                'stats': p.get('stats', {}),
                'value': round(self._calculate_player_value(p), 1),
                'fantasy_team': p.get('fantasy_team', my_fantasy_team)
            } for p in my_players],
            'add_players': [{
                'name': p['name'],
                'team': p.get('team', '-'),
                'position': p.get('position', '-'),
                'stats': p.get('stats', {}),
                'value': round(self._calculate_player_value(p), 1),
                'fantasy_team': p.get('fantasy_team', other_fantasy_team)
            } for p in their_players],
            'impact_score': round(their_total_value - my_total_value, 1),
            'win_probability_before': win_prob_before,
            'win_probability_after': win_prob_after,
            'win_prob_before': win_prob_before,
            'win_prob_after': win_prob_after,
            'win_prob_change': win_prob_change,
            'partner_impact': partner_impact,
            'beneficial_for_both': beneficial_for_both,
            'plausibility': plausibility,
            'plausibility_score': round(plausibility_num, 1),
            'rank_score': round(overall_rank_score, 2),
            'all_categories': category_changes.get('all_categories', []),
            'category_improvements': category_changes.get('improvements', []),
            'category_declines': category_changes.get('declines', []),
            'reasoning': reasoning,
            'priority': 'high' if win_prob_change >= 4.0 and beneficial_for_both else 'medium'
        }

    def _analyze_trade_opportunities(self, current_roster, other_teams_rosters):
        """Analyze realistic, context-aware trade opportunities with other teams."""
        recommendations = []
        
        if not current_roster or not other_teams_rosters:
            return recommendations

        print(f"[DEBUG] _analyze_trade_opportunities: Current roster={len(current_roster)}, Other teams={len(other_teams_rosters)}")

        # 1. Realistic 1-for-1 trades
        for my_player in current_roster:
            for team_data in other_teams_rosters:
                team_name = team_data.get('team_name', 'Unknown Team')
                team_roster = team_data.get('roster', [])
                
                for other_player in team_roster:
                    rec = self._evaluate_candidate_trade(
                        current_roster, team_roster, [my_player], [other_player],
                        team_name, swap_type='trade-1-for-1'
                    )
                    if rec:
                        recommendations.append(rec)

        # 2. Realistic 2-for-2 trades
        if len(current_roster) >= 2:
            my_2_combos = list(combinations(current_roster, 2))[:20]
            for team_data in other_teams_rosters:
                team_name = team_data.get('team_name', 'Unknown Team')
                team_roster = team_data.get('roster', [])
                if len(team_roster) < 2:
                    continue
                other_2_combos = list(combinations(team_roster, 2))[:20]
                
                for my_combo in my_2_combos:
                    for other_combo in other_2_combos:
                        rec = self._evaluate_candidate_trade(
                            current_roster, team_roster, list(my_combo), list(other_combo),
                            team_name, swap_type='trade-2-for-2'
                        )
                        if rec:
                            recommendations.append(rec)

        # Rank trades by overall usefulness and plausibility
        recommendations.sort(key=lambda x: (x.get('rank_score', 0), x.get('win_prob_change', 0)), reverse=True)
        return recommendations[:40]
    
    def _sum_player_stats(self, players):
        """Sum stats across multiple players (handles None values)"""
        totals = {
            'points': 0, 'rebounds': 0, 'assists': 0, 'steals': 0, 'blocks': 0,
            'three_pointers_made': 0, 'field_goals': 0, 'field_goal_attempts': 0,
            'free_throws': 0, 'free_throw_attempts': 0, 'turnovers': 0
        }
        
        for p in players:
            stats = p.get('stats', {})
            for key in totals.keys():
                val = stats.get(key, 0)
                # Handle None values
                totals[key] += float(val) if val is not None else 0
        
        return totals
    
    def _compare_stat_totals(self, my_stats, other_stats):
        """Compare stat totals and return ALL 9 categories with +/- values (handles None)"""
        all_categories = []
        improvements = []
        declines = []
        
        # Helper to safely get numeric values
        def get_val(stats, key, default=0):
            val = stats.get(key, default)
            return float(val) if val is not None else default
        
        # Calculate FG% and FT% from made/attempts
        my_fg = get_val(my_stats, 'field_goals', 0)
        my_fga = get_val(my_stats, 'field_goal_attempts', 1)
        my_fg_pct = (my_fg / my_fga) if my_fga > 0 else 0
        
        other_fg = get_val(other_stats, 'field_goals', 0)
        other_fga = get_val(other_stats, 'field_goal_attempts', 1)
        other_fg_pct = (other_fg / other_fga) if other_fga > 0 else 0
        
        my_ft = get_val(my_stats, 'free_throws', 0)
        my_fta = get_val(my_stats, 'free_throw_attempts', 1)
        my_ft_pct = (my_ft / my_fta) if my_fta > 0 else 0
        
        other_ft = get_val(other_stats, 'free_throws', 0)
        other_fta = get_val(other_stats, 'free_throw_attempts', 1)
        other_ft_pct = (other_ft / other_fta) if other_fta > 0 else 0
        
        # All 9 fantasy categories
        categories = [
            ('points', 'PTS', False, get_val(my_stats, 'points'), get_val(other_stats, 'points')),
            ('rebounds', 'REB', False, get_val(my_stats, 'rebounds'), get_val(other_stats, 'rebounds')),
            ('assists', 'AST', False, get_val(my_stats, 'assists'), get_val(other_stats, 'assists')),
            ('steals', 'STL', False, get_val(my_stats, 'steals'), get_val(other_stats, 'steals')),
            ('blocks', 'BLK', False, get_val(my_stats, 'blocks'), get_val(other_stats, 'blocks')),
            ('three_pointers_made', '3PM', False, get_val(my_stats, 'three_pointers_made'), get_val(other_stats, 'three_pointers_made')),
            ('fg_percentage', 'FG%', True, my_fg_pct, other_fg_pct),
            ('ft_percentage', 'FT%', True, my_ft_pct, other_ft_pct),
            ('turnovers', 'TO', False, get_val(my_stats, 'turnovers'), get_val(other_stats, 'turnovers'))
        ]
        
        for stat_key, display_name, is_percentage, my_val, other_val in categories:
            if stat_key == 'turnovers':
                # For turnovers, lower is better
                diff = my_val - other_val  # Positive = improvement (less TO)
                if abs(diff) > 0.01:
                    if diff > 0:
                        cat_str = f"{display_name} ↓{round(abs(diff), 1)}"
                        all_categories.append(cat_str)
                        improvements.append(cat_str)
                    else:
                        cat_str = f"{display_name} ↑{round(abs(diff), 1)}"
                        all_categories.append(cat_str)
                        declines.append(cat_str)
                else:
                    all_categories.append(f"{display_name} —")
            else:
                diff = other_val - my_val
                
                if is_percentage:
                    pct_diff = diff * 100
                    if abs(pct_diff) > 0.01:
                        if pct_diff > 0:
                            cat_str = f"{display_name} +{round(pct_diff, 1)}%"
                            all_categories.append(cat_str)
                            improvements.append(cat_str)
                        else:
                            cat_str = f"{display_name} {round(pct_diff, 1)}%"
                            all_categories.append(cat_str)
                            declines.append(cat_str)
                    else:
                        all_categories.append(f"{display_name} —")
                else:
                    if abs(diff) > 0.01:
                        if diff > 0:
                            cat_str = f"{display_name} +{round(diff, 1)}"
                            all_categories.append(cat_str)
                            improvements.append(cat_str)
                        else:
                            cat_str = f"{display_name} {round(diff, 1)}"
                            all_categories.append(cat_str)
                            declines.append(cat_str)
                    else:
                        all_categories.append(f"{display_name} —")
        
        return {
            'all_categories': all_categories,
            'improvements': improvements,
            'declines': declines
        }
    
    def _get_sample_recommendations(self):
        """Fallback sample recommendations"""
        return [
            {
                'type': 'single_swap',
                'swap_type': '1-for-1',
                'drop_players': [{
                    'name': 'Sample Player A',
                    'team': 'LAL',
                    'position': 'SG',
                    'credit': 15
                }],
                'add_players': [{
                    'name': 'Sample Player B',
                    'team': 'BOS',
                    'position': 'SF',
                    'credit': 15
                }],
                'credit_change': 0,
                'impact_score': 12.5,
                'reasoning': 'Better all-around production',
                'priority': 'high'
            }
        ]
