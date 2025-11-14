"""
Recommendation Engine Module
Analyzes potential roster moves and provides optimization suggestions
Using real Basketball Reference data
"""

import numpy as np
from itertools import combinations


class RecommendationEngine:
    """Provides intelligent roster move recommendations"""
    
    def __init__(self, data_manager, matchup_simulator, draft_assistant=None):
        self.data_manager = data_manager
        self.simulator = matchup_simulator
        self.draft_assistant = draft_assistant
        self.other_teams_rosters = []  # Will store rosters of other teams for trade suggestions
        
    def get_recommendations_for_roster(self, current_roster, free_agents, all_players, max_recommendations=100, other_teams_rosters=None):
        """Get comprehensive roster move recommendations using real data
        
        Args:
            current_roster: User's current team roster
            free_agents: Players not owned by any team (true free agents)
            all_players: All NBA players
            max_recommendations: Maximum number of recommendations to return
            other_teams_rosters: List of other teams' rosters for trade suggestions
        """
        
        try:
            recommendations = []
            seen_recommendations = set()  # Track unique recommendations to avoid duplicates
            
            # Store other teams data for trade suggestions
            if other_teams_rosters:
                self.other_teams_rosters = other_teams_rosters
            
            print(f"DEBUG: Starting recommendation generation - Roster: {len(current_roster)}, FAs: {len(free_agents)}, Other Teams: {len(self.other_teams_rosters) if self.other_teams_rosters else 0}")
            
            # 1. Simple 1-for-1 swaps
            single_swap_recs = self._analyze_single_swaps(
                current_roster, free_agents
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
                current_roster, free_agents
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
                current_roster, free_agents
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
    
    def _analyze_add_drop_moves_real_data(self, current_roster, free_agents):
        """DEPRECATED - Use _analyze_single_swaps instead"""
        return self._analyze_single_swaps(current_roster, free_agents)
    
    def _analyze_single_swaps(self, current_roster, free_agents):
        """Analyze 1-for-1 player swaps for ALL roster players with position consideration"""
        recommendations = []
        
        print(f"🔍 _analyze_single_swaps: Roster={len(current_roster)}, Free Agents={len(free_agents)}")
        
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
            roster_position = roster_player.get('position', '')
            
            # Find better free agents
            for fa in sorted_free_agents:
                fa_value = self._calculate_player_value(fa)
                fa_position = fa.get('position', '')
                
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
                                'fantasy_team': roster_player.get('fantasy_team', 'My Team')
                            }],
                            'add_players': [{
                                'name': fa['name'],
                                'team': fa.get('team', '-'),
                                'position': fa.get('position', '-'),
                                'stats': fa.get('stats', {}),
                                'value': round(fa_value, 1),
                                'fantasy_team': fa.get('fantasy_team', 'Free Agent')
                            }],
                            'impact_score': round(improvement, 1),
                            'all_categories': category_changes.get('all_categories', []),
                            'category_improvements': category_changes['improvements'],
                            'category_declines': category_changes['declines'],
                            'reasoning': self._generate_swap_reasoning(
                                [roster_player], [fa], improvement, 0, category_changes
                            ),
                            'priority': 'high' if improvement > 10.0 else 'medium'
                        })
                        
                        # Early stopping: if we have enough single swaps, stop
                        if len(recommendations) >= 60:
                            print(f"DEBUG: Early stopping at {len(recommendations)} single swaps")
                            return recommendations
        
        return recommendations
    
    def _analyze_multi_player_swaps(self, current_roster, free_agents):
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
                drop_positions = [p.get('position', '') for p in drop_combo]
                
                for add_combo in fa_combos:
                    add_value_total = sum(self._calculate_player_value(p) for p in add_combo)
                    add_positions = [p.get('position', '') for p in add_combo]
                    
                    value_change = add_value_total - drop_value_total
                    
                    # Check if positions are reasonably balanced
                    position_balanced = self._check_multi_position_balance(drop_positions, add_positions)
                    
                    # Only if significant improvement
                    if value_change > threshold:
                        print(f"  ✅ Found {swap_size}-for-{swap_size}: value_change={value_change:.1f}")
                        
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
                                'fantasy_team': p.get('fantasy_team', 'My Team')
                            } for p in drop_combo],
                            'add_players': [{
                                'name': p['name'],
                                'team': p.get('team', '-'),
                                'position': p.get('position', '-'),
                                'stats': p.get('stats', {}),
                                'fantasy_team': p.get('fantasy_team', 'Free Agent')
                            } for p in add_combo],
                            'impact_score': round(value_change, 1),
                            'all_categories': combined_changes.get('all_categories', []),
                            'category_improvements': combined_changes['improvements'],
                            'category_declines': combined_changes['declines'],
                            'reasoning': self._generate_swap_reasoning(
                                list(drop_combo), list(add_combo), value_change, 0, combined_changes
                            ),
                            'priority': 'high' if value_change > (threshold * 2) else 'medium'
                        })
                        
                        # Limit total multi-swaps to avoid too many options
                        if len(recommendations) >= 30:
                            print(f"DEBUG: Reached limit of {len(recommendations)} multi-swap recommendations")
                            return recommendations
        
        print(f"DEBUG: Total multi-swap recommendations found: {len(recommendations)}")
        return recommendations
    
    def _find_budget_upgrades(self, current_roster, free_agents):
        """Find value upgrades (better performance)"""
        recommendations = []
        
        # Check ALL roster players for value opportunities
        for roster_player in current_roster:
            roster_value = self._calculate_player_value(roster_player)
            roster_position = roster_player.get('position', '')
            
            # Find better performing FAs
            for fa in free_agents:
                fa_value = self._calculate_player_value(fa)
                fa_position = fa.get('position', '')
                
                # Check position compatibility
                position_compatible = self._check_position_compatibility(roster_position, fa_position)
                
                # Value upgrade: better performance and position fits
                if fa_value > roster_value * 1.05 and position_compatible:  # Only 5% better
                    improvement = fa_value - roster_value
                    
                    # Calculate category improvements
                    category_changes = self._analyze_category_improvements(roster_player, fa)
                    
                    # Build reasoning with category details
                    improvement_str = ', '.join(category_changes['improvements'][:3]) if category_changes['improvements'] else 'overall value'
                    
                    recommendations.append({
                        'type': 'budget_upgrade',
                        'swap_type': 'value-play',
                        'drop_players': [{
                            'name': roster_player['name'],
                            'team': roster_player.get('team', '-'),
                            'position': roster_player.get('position', '-'),
                            'stats': roster_player.get('stats', {}),
                            'fantasy_team': roster_player.get('fantasy_team', 'My Team')
                        }],
                        'add_players': [{
                            'name': fa['name'],
                            'team': fa.get('team', '-'),
                            'position': fa.get('position', '-'),
                            'stats': fa.get('stats', {}),
                            'fantasy_team': fa.get('fantasy_team', 'Free Agent')
                        }],
                        'impact_score': round(improvement, 1),
                        'category_improvements': category_changes['improvements'],
                        'category_declines': category_changes['declines'],
                        'reasoning': f"💎 Value pick: {fa['name']} is {round((fa_value/roster_value - 1) * 100)}% better! ({improvement_str})",
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
        
        # 9-Category Fantasy Basketball (equal weight approach)
        # PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO
        
        # Counting stats (normalized)
        pts = stats.get('points', 0) * 1.0         # Points
        reb = stats.get('rebounds', 0) * 1.3       # Rebounds (slightly more valuable)
        ast = stats.get('assists', 0) * 1.5        # Assists (playmaking valued)
        stl = stats.get('steals', 0) * 3.5         # Steals (rare defensive stat)
        blk = stats.get('blocks', 0) * 3.5         # Blocks (rare defensive stat)
        threes = stats.get('three_pointers_made', 0) * 1.5  # 3-pointers made
        to = stats.get('turnovers', 0) * -2.0      # Turnovers (penalty)
        
        # Shooting percentages (scaled to match counting stats impact)
        fg_pct = stats.get('fg_percentage', 0)
        fg_value = (fg_pct - 0.45) * 100 if fg_pct else 0  # League avg ~45%
        
        ft_pct = stats.get('ft_percentage', 0)
        ft_value = (ft_pct - 0.75) * 80 if ft_pct else 0   # League avg ~75%
        
        # Total value
        value = pts + reb + ast + stl + blk + threes + to + fg_value + ft_value
        
        return value
    
    def _calculate_player_credit(self, player):
        """Calculate player credit using DraftAssistant if available"""
        if not self.draft_assistant:
            # Fallback simple calculation
            return int(self._calculate_player_value(player) / 10)
        
        stats = player.get('stats', {})
        minutes = player.get('minutes', 0)
        return self.draft_assistant.calculate_player_credit(stats, minutes)
    
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
            drop_val = drop_stats.get(stat_key, 0)
            add_val = add_stats.get(stat_key, 0)
            
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
        
        return reason
    
    def _analyze_trade_opportunities(self, current_roster, other_teams_rosters):
        """Analyze realistic trade opportunities with other teams
        
        Only suggests balanced trades where values are similar (within 20%)
        to prevent unrealistic suggestions like trading Alex Sarr for Jokic
        """
        recommendations = []
        
        print(f"🔍 _analyze_trade_opportunities: Current roster={len(current_roster)}, Other teams={len(other_teams_rosters)}")
        
        # Debug: Show other teams info
        for team_data in other_teams_rosters:
            team_name = team_data.get('team_name', 'Unknown')
            team_roster = team_data.get('roster', [])
            print(f"   Team: {team_name}, Players: {len(team_roster)}")
            if team_roster:
                sample_player = team_roster[0]
                print(f"      Sample player: {sample_player.get('name')} - fantasy_team: {sample_player.get('fantasy_team', 'MISSING')}")
        
        # For each player in user's roster
        for my_player in current_roster:
            my_value = self._calculate_player_value(my_player)
            my_position = my_player.get('position', '')
            
            # Check all other teams
            for team_data in other_teams_rosters:
                team_name = team_data.get('team_name', 'Unknown Team')
                team_roster = team_data.get('roster', [])
                
                # Check each player in other team
                for other_player in team_roster:
                    other_value = self._calculate_player_value(other_player)
                    other_position = other_player.get('position', '')
                    other_fantasy_team = other_player.get('fantasy_team', team_name)
                    
                    # Debug: Check if fantasy_team is set correctly
                    if not other_player.get('fantasy_team'):
                        print(f"⚠️ WARNING: {other_player['name']} from {team_name} has no fantasy_team field!")
                    
                    # Check if trade is realistic (values within 20%)
                    value_ratio = other_value / my_value if my_value > 0 else 0
                    
                    # Only suggest if:
                    # 1. Other player is better (10%+ improvement)
                    # 2. Trade is realistic (values within 20% = ratio between 1.1 and 1.2)
                    # 3. Positions are compatible
                    if 1.1 <= value_ratio <= 1.25 and self._check_position_compatibility(my_position, other_position):
                        improvement = other_value - my_value
                        category_changes = self._analyze_category_improvements(my_player, other_player)
                        
                        # Get fantasy team names with fallback
                        my_fantasy_team = my_player.get('fantasy_team', 'My Team')
                        other_fantasy_team = other_player.get('fantasy_team', team_name)
                        
                        # Debug logging
                        print(f"🔄 Trade: {my_player['name']} ({my_fantasy_team}) <-> {other_player['name']} ({other_fantasy_team})")
                        
                        recommendations.append({
                            'type': 'trade',
                            'swap_type': 'trade-1-for-1',
                            'trade_partner': team_name,
                            'drop_players': [{
                                'name': my_player['name'],
                                'team': my_player.get('team', '-'),
                                'position': my_player.get('position', '-'),
                                'stats': my_player.get('stats', {}),
                                'value': round(my_value, 1),
                                'fantasy_team': my_fantasy_team
                            }],
                            'add_players': [{
                                'name': other_player['name'],
                                'team': other_player.get('team', '-'),
                                'position': other_player.get('position', '-'),
                                'stats': other_player.get('stats', {}),
                                'value': round(other_value, 1),
                                'fantasy_team': other_fantasy_team
                            }],
                            'impact_score': round(improvement, 1),
                            'all_categories': category_changes.get('all_categories', []),
                            'category_improvements': category_changes['improvements'],
                            'category_declines': category_changes['declines'],
                            'reasoning': f"🤝 Trade with {team_name}: {my_player['name']} for {other_player['name']} ({', '.join(category_changes['improvements'][:2]) if category_changes['improvements'] else 'balanced upgrade'})",
                            'priority': 'high' if improvement > 5.0 else 'medium'
                        })
                        
                        # Limit trades per player to avoid too many suggestions
                        if len([r for r in recommendations if r['drop_players'][0]['name'] == my_player['name']]) >= 3:
                            break
        
        # Limit total 1-for-1 trade suggestions
        one_for_one_trades = recommendations[:20]
        
        # 2. Multi-player trades (2-for-2, 3-for-3, 4-for-4)
        print(f"🔍 Starting multi-player trade analysis...")
        multi_trades = self._analyze_multi_player_trades(current_roster, other_teams_rosters)
        print(f"✅ Found {len(multi_trades)} multi-player trade recommendations")
        
        # Combine all trades
        all_trades = one_for_one_trades + multi_trades
        
        return all_trades[:40]  # Return top 40 total trades
    
    def _analyze_multi_player_trades(self, current_roster, other_teams_rosters):
        """Analyze 2-for-2, 3-for-3, and 4-for-4 trade opportunities"""
        recommendations = []
        
        # For each other team
        for team_data in other_teams_rosters:
            team_name = team_data.get('team_name', 'Unknown Team')
            team_roster = team_data.get('roster', [])
            
            if len(team_roster) < 2:
                continue
            
            # 2-for-2 trades (most common)
            for my_combo in combinations(current_roster, 2):
                my_total_value = sum(self._calculate_player_value(p) for p in my_combo)
                
                for other_combo in combinations(team_roster, 2):
                    other_total_value = sum(self._calculate_player_value(p) for p in other_combo)
                    
                    # Check if trade is realistic (within 25% value difference)
                    if my_total_value == 0:
                        continue
                    
                    value_ratio = other_total_value / my_total_value
                    
                    # 10-30% improvement, balanced trade
                    if 1.1 <= value_ratio <= 1.3:
                        improvement = other_total_value - my_total_value
                        
                        # Calculate category changes
                        my_stats_total = self._sum_player_stats(my_combo)
                        other_stats_total = self._sum_player_stats(other_combo)
                        category_changes = self._compare_stat_totals(my_stats_total, other_stats_total)
                        
                        # Build recommendation
                        my_fantasy_team = my_combo[0].get('fantasy_team', 'My Team')
                        
                        recommendations.append({
                            'type': 'trade',
                            'swap_type': 'trade-2-for-2',
                            'trade_partner': team_name,
                            'drop_players': [{
                                'name': p['name'],
                                'team': p.get('team', '-'),
                                'position': p.get('position', '-'),
                                'stats': p.get('stats', {}),
                                'fantasy_team': p.get('fantasy_team', my_fantasy_team)
                            } for p in my_combo],
                            'add_players': [{
                                'name': p['name'],
                                'team': p.get('team', '-'),
                                'position': p.get('position', '-'),
                                'stats': p.get('stats', {}),
                                'fantasy_team': p.get('fantasy_team', team_name)
                            } for p in other_combo],
                            'impact_score': round(improvement, 1),
                            'all_categories': category_changes.get('all_categories', []),
                            'category_improvements': category_changes['improvements'],
                            'category_declines': category_changes['declines'],
                            'reasoning': f"🤝 2-for-2 Trade with {team_name}: {', '.join(p['name'] for p in my_combo)} for {', '.join(p['name'] for p in other_combo)}",
                            'priority': 'high' if improvement > 10.0 else 'medium'
                        })
                        
                        # Limit 2-for-2 per team
                        if len([r for r in recommendations if r.get('trade_partner') == team_name and r.get('swap_type') == 'trade-2-for-2']) >= 3:
                            break
            
            # 3-for-3 trades (less common, bigger impact)
            if len(current_roster) >= 3 and len(team_roster) >= 3:
                my_combos_3 = list(combinations(current_roster, 3))[:15]  # Limit combos
                other_combos_3 = list(combinations(team_roster, 3))[:15]
                
                for my_combo in my_combos_3:
                    my_total_value = sum(self._calculate_player_value(p) for p in my_combo)
                    
                    for other_combo in other_combos_3:
                        other_total_value = sum(self._calculate_player_value(p) for p in other_combo)
                        
                        if my_total_value == 0:
                            continue
                        
                        value_ratio = other_total_value / my_total_value
                        
                        # 15-35% improvement for 3-for-3
                        if 1.15 <= value_ratio <= 1.35:
                            improvement = other_total_value - my_total_value
                            
                            my_stats_total = self._sum_player_stats(my_combo)
                            other_stats_total = self._sum_player_stats(other_combo)
                            category_changes = self._compare_stat_totals(my_stats_total, other_stats_total)
                            
                            my_fantasy_team = my_combo[0].get('fantasy_team', 'My Team')
                            
                            recommendations.append({
                                'type': 'trade',
                                'swap_type': 'trade-3-for-3',
                                'trade_partner': team_name,
                                'drop_players': [{
                                    'name': p['name'],
                                    'team': p.get('team', '-'),
                                    'position': p.get('position', '-'),
                                    'stats': p.get('stats', {}),
                                    'fantasy_team': p.get('fantasy_team', my_fantasy_team)
                                } for p in my_combo],
                                'add_players': [{
                                    'name': p['name'],
                                    'team': p.get('team', '-'),
                                    'position': p.get('position', '-'),
                                    'stats': p.get('stats', {}),
                                    'fantasy_team': p.get('fantasy_team', team_name)
                                } for p in other_combo],
                                'impact_score': round(improvement, 1),
                                'all_categories': category_changes.get('all_categories', []),
                                'category_improvements': category_changes['improvements'],
                                'category_declines': category_changes['declines'],
                                'reasoning': f"🤝 3-for-3 Trade with {team_name}: Major roster shake-up",
                                'priority': 'high' if improvement > 15.0 else 'medium'
                            })
                            
                            # Limit 3-for-3 per team
                            if len([r for r in recommendations if r.get('trade_partner') == team_name and r.get('swap_type') == 'trade-3-for-3']) >= 2:
                                break
        
        # Sort by impact
        recommendations.sort(key=lambda x: x.get('impact_score', 0), reverse=True)
        return recommendations[:20]  # Top 20 multi-player trades
    
    def _sum_player_stats(self, players):
        """Sum stats across multiple players"""
        totals = {
            'points': 0, 'rebounds': 0, 'assists': 0, 'steals': 0, 'blocks': 0,
            'three_pointers_made': 0, 'field_goals': 0, 'field_goal_attempts': 0,
            'free_throws': 0, 'free_throw_attempts': 0, 'turnovers': 0
        }
        
        for p in players:
            stats = p.get('stats', {})
            for key in totals.keys():
                totals[key] += stats.get(key, 0)
        
        return totals
    
    def _compare_stat_totals(self, my_stats, other_stats):
        """Compare stat totals and return ALL 9 categories with +/- values"""
        all_categories = []
        improvements = []
        declines = []
        
        # Calculate FG% and FT% from made/attempts
        my_fg_pct = (my_stats.get('field_goals', 0) / my_stats.get('field_goal_attempts', 1)) if my_stats.get('field_goal_attempts', 0) > 0 else 0
        other_fg_pct = (other_stats.get('field_goals', 0) / other_stats.get('field_goal_attempts', 1)) if other_stats.get('field_goal_attempts', 0) > 0 else 0
        
        my_ft_pct = (my_stats.get('free_throws', 0) / my_stats.get('free_throw_attempts', 1)) if my_stats.get('free_throw_attempts', 0) > 0 else 0
        other_ft_pct = (other_stats.get('free_throws', 0) / other_stats.get('free_throw_attempts', 1)) if other_stats.get('free_throw_attempts', 0) > 0 else 0
        
        # All 9 fantasy categories
        categories = [
            ('points', 'PTS', False, my_stats.get('points', 0), other_stats.get('points', 0)),
            ('rebounds', 'REB', False, my_stats.get('rebounds', 0), other_stats.get('rebounds', 0)),
            ('assists', 'AST', False, my_stats.get('assists', 0), other_stats.get('assists', 0)),
            ('steals', 'STL', False, my_stats.get('steals', 0), other_stats.get('steals', 0)),
            ('blocks', 'BLK', False, my_stats.get('blocks', 0), other_stats.get('blocks', 0)),
            ('three_pointers_made', '3PM', False, my_stats.get('three_pointers_made', 0), other_stats.get('three_pointers_made', 0)),
            ('fg_percentage', 'FG%', True, my_fg_pct, other_fg_pct),
            ('ft_percentage', 'FT%', True, my_ft_pct, other_ft_pct),
            ('turnovers', 'TO', False, my_stats.get('turnovers', 0), other_stats.get('turnovers', 0))
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
                'type': 'add_drop',
                'action': 'drop_add',
                'drop_player': {
                    'name': 'Sample Player A',
                    'team': 'LAL',
                    'position': 'SG'
                },
                'add_player': {
                    'name': 'Sample Player B',
                    'team': 'BOS',
                    'position': 'SF'
                },
                'impact_score': 12.5,
                'reasoning': 'Better all-around production',
                'priority': 'high'
            }
        ]
