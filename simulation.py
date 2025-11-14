"""
Matchup Simulation Module
Monte Carlo simulation engine for fantasy basketball matchups
"""

import numpy as np
import pandas as pd
from scipy import stats
import random


class MatchupSimulator:
    """Runs Monte Carlo simulations for fantasy matchups"""
    
    def __init__(self, num_simulations=10000):
        self.num_simulations = num_simulations
        
        # Standard deviation multipliers for stat variability
        self.stat_volatility = {
            'points': 0.25,
            'rebounds': 0.30,
            'assists': 0.35,
            'steals': 0.50,
            'blocks': 0.60,
            'three_pointers_made': 0.40,
            'fg_percentage': 0.15,
            'ft_percentage': 0.10,
            'turnovers': 0.30
        }
        
        # 9 category names for display
        self.stat_categories = [
            'points', 'rebounds', 'assists', 'steals', 'blocks',
            'three_pointers_made', 'fg_percentage', 'ft_percentage', 'turnovers'
        ]
    
    def simulate_matchup(self, my_roster, opponent_roster, league_settings=None):
        """Run Monte Carlo simulation for a head-to-head matchup"""
        
        if league_settings is None:
            league_settings = self._get_default_league_settings()
        
        # Get projected stats for both teams
        my_projections = self._get_team_projections(my_roster)
        opponent_projections = self._get_team_projections(opponent_roster)
        
        # Run simulations
        simulation_results = self._run_simulations(
            my_projections, opponent_projections, league_settings
        )
        
        return {
            'win_probability': simulation_results['win_probability'],
            'category_breakdown': simulation_results['category_breakdown'],
            'expected_categories_won': simulation_results['expected_categories_won'],
            'expected_categories_lost': simulation_results['expected_categories_lost'],
            'expected_categories_tied': simulation_results['expected_categories_tied'],
            'my_team_projections': my_projections,
            'opponent_projections': opponent_projections,
            'simulation_details': simulation_results['details'],
            'recommendations': self._generate_matchup_recommendations(simulation_results)
        }
    
    def _get_team_projections(self, roster):
        """Calculate team projections from roster"""
        team_projections = {
            'points': 0, 'rebounds': 0, 'assists': 0, 'steals': 0, 'blocks': 0,
            'three_pointers_made': 0, 'fg_percentage': 0, 'ft_percentage': 0, 'turnovers': 0
        }
        
        active_players = 0
        fg_makes = 0
        fg_attempts = 0
        ft_makes = 0
        ft_attempts = 0
        
        for player in roster:
            # Get player projections (would come from data_manager in production)
            player_stats = self._get_sample_player_projections(player)
            
            if player_stats:
                active_players += 1
                
                # Sum counting stats
                for stat in ['points', 'rebounds', 'assists', 'steals', 'blocks', 'three_pointers_made', 'turnovers']:
                    value = player_stats.get(stat, 0)
                    # Handle None values
                    team_projections[stat] += 0 if value is None else float(value)
                
                # Handle percentage stats with None checks
                fg_pct = player_stats.get('fg_percentage')
                fg_att = player_stats.get('fg_attempts')
                if fg_pct is not None and fg_att is not None and fg_pct > 0 and fg_att > 0:
                    fg_makes += float(fg_pct) * float(fg_att)
                    fg_attempts += float(fg_att)
                
                ft_pct = player_stats.get('ft_percentage')
                ft_att = player_stats.get('ft_attempts')
                if ft_pct is not None and ft_att is not None and ft_pct > 0 and ft_att > 0:
                    ft_makes += float(ft_pct) * float(ft_att)
                    ft_attempts += float(ft_att)
        
        # Calculate team shooting percentages
        if fg_attempts > 0:
            team_projections['fg_percentage'] = fg_makes / fg_attempts
        if ft_attempts > 0:
            team_projections['ft_percentage'] = ft_makes / ft_attempts
        
        return team_projections
    
    def _run_simulations(self, my_projections, opponent_projections, league_settings):
        """Run Monte Carlo simulations"""
        
        my_wins = 0
        category_wins = {cat: 0 for cat in my_projections.keys()}
        category_losses = {cat: 0 for cat in my_projections.keys()}
        category_ties = {cat: 0 for cat in my_projections.keys()}
        
        simulation_details = []
        
        for sim in range(self.num_simulations):
            # Generate random outcomes for this simulation
            my_sim_stats = self._simulate_team_performance(my_projections)
            opp_sim_stats = self._simulate_team_performance(opponent_projections)
            
            # Compare categories
            categories_won = 0
            categories_lost = 0
            sim_detail = {'simulation': sim + 1}
            
            for category in my_projections.keys():
                my_value = my_sim_stats[category]
                opp_value = opp_sim_stats[category]
                
                # Turnovers are bad, so lower is better
                if category == 'turnovers':
                    if my_value < opp_value:
                        categories_won += 1
                        category_wins[category] += 1
                    elif my_value > opp_value:
                        categories_lost += 1
                        category_losses[category] += 1
                    else:
                        category_ties[category] += 1
                else:
                    if my_value > opp_value:
                        categories_won += 1
                        category_wins[category] += 1
                    elif my_value < opp_value:
                        categories_lost += 1
                        category_losses[category] += 1
                    else:
                        category_ties[category] += 1
                
                sim_detail[f'my_{category}'] = round(my_value, 3)
                sim_detail[f'opp_{category}'] = round(opp_value, 3)
            
            # Determine matchup winner based on category count (not points)
            sim_detail['categories_won'] = categories_won
            sim_detail['categories_lost'] = categories_lost
            
            if categories_won > categories_lost:
                my_wins += 1
                sim_detail['winner'] = 'me'
            elif categories_lost > categories_won:
                sim_detail['winner'] = 'opponent'
            else:
                # In case of tie, count it as 0.5 win for both
                my_wins += 0.5
                sim_detail['winner'] = 'tie'
            
            # Store first 100 simulations for analysis
            if sim < 100:
                simulation_details.append(sim_detail)
        
        # Calculate results
        win_probability = (my_wins / self.num_simulations) * 100
        
        category_breakdown = {}
        for category in my_projections.keys():
            win_pct = (category_wins[category] / self.num_simulations) * 100
            loss_pct = (category_losses[category] / self.num_simulations) * 100
            tie_pct = (category_ties[category] / self.num_simulations) * 100
            
            category_breakdown[category] = {
                'win_pct': round(win_pct, 1),
                'loss_pct': round(loss_pct, 1),
                'tie_pct': round(tie_pct, 1),
                'strength': 'strong' if win_pct > 60 else 'weak' if win_pct < 40 else 'even'
            }
        
        # Calculate expected categories won/lost (based on win percentages)
        expected_categories_won = sum(1 for cat, data in category_breakdown.items() if data['win_pct'] > 50)
        expected_categories_lost = sum(1 for cat, data in category_breakdown.items() if data['win_pct'] < 50)
        expected_categories_tied = sum(1 for cat, data in category_breakdown.items() if data['win_pct'] == 50)
        
        return {
            'win_probability': round(win_probability, 1),
            'category_breakdown': category_breakdown,
            'expected_categories_won': expected_categories_won,
            'expected_categories_lost': expected_categories_lost,
            'expected_categories_tied': expected_categories_tied,
            'details': simulation_details
        }
    
    def _simulate_team_performance(self, projections):
        """Simulate one week of team performance with variance"""
        simulated_stats = {}
        
        for stat, projection in projections.items():
            # Handle None values by converting to 0
            if projection is None or projection == 0:
                simulated_stats[stat] = 0
                continue
            
            # Ensure projection is a float
            projection = float(projection)
            
            # Add variance based on stat volatility
            volatility = self.stat_volatility.get(stat, 0.25)
            std_dev = projection * volatility
            
            # Use normal distribution for most stats
            if stat in ['fg_percentage', 'ft_percentage']:
                # Constrain percentages to realistic ranges
                simulated_value = np.random.normal(projection, std_dev)
                simulated_value = max(0.2, min(1.0, simulated_value))
            else:
                # Ensure non-negative values for counting stats
                simulated_value = max(0, np.random.normal(projection, std_dev))
            
            simulated_stats[stat] = simulated_value
        
        return simulated_stats
    
    def simulate_points_league(self, my_roster, opponent_roster, scoring_settings):
        """Simulate points league matchup"""
        my_points = 0
        opp_points = 0
        
        for _ in range(self.num_simulations):
            # Simulate team performance
            my_stats = self._simulate_team_performance(
                self._get_team_projections(my_roster)
            )
            opp_stats = self._simulate_team_performance(
                self._get_team_projections(opponent_roster)
            )
            
            # Calculate fantasy points
            my_sim_points = self._calculate_fantasy_points(my_stats, scoring_settings)
            opp_sim_points = self._calculate_fantasy_points(opp_stats, scoring_settings)
            
            if my_sim_points > opp_sim_points:
                my_points += 1
            else:
                opp_points += 1
        
        win_probability = (my_points / self.num_simulations) * 100
        
        return {
            'win_probability': round(win_probability, 1),
            'projected_points': self._calculate_fantasy_points(
                self._get_team_projections(my_roster), scoring_settings
            ),
            'opponent_projected_points': self._calculate_fantasy_points(
                self._get_team_projections(opponent_roster), scoring_settings
            )
        }
    
    def _calculate_fantasy_points(self, stats, scoring_settings):
        """Calculate total fantasy points based on scoring settings"""
        total_points = 0
        
        for stat, points_per in scoring_settings.items():
            if stat in stats:
                total_points += stats[stat] * points_per
        
        return total_points
    
    def _generate_matchup_recommendations(self, simulation_results):
        """Generate strategic recommendations based on simulation"""
        recommendations = []
        
        category_breakdown = simulation_results['category_breakdown']
        
        # Identify weak categories
        weak_categories = [
            cat for cat, data in category_breakdown.items() 
            if data['win_pct'] < 40
        ]
        
        # Identify strong categories
        strong_categories = [
            cat for cat, data in category_breakdown.items() 
            if data['win_pct'] > 60
        ]
        
        if weak_categories:
            recommendations.append({
                'type': 'improve_weakness',
                'message': f"Consider targeting players who excel in: {', '.join(weak_categories)}",
                'categories': weak_categories,
                'priority': 'high'
            })
        
        if strong_categories:
            recommendations.append({
                'type': 'leverage_strength',
                'message': f"You have strong advantages in: {', '.join(strong_categories)}",
                'categories': strong_categories,
                'priority': 'medium'
            })
        
        return recommendations
    
    def _get_sample_player_projections(self, player):
        """Get player projections from real stats data"""
        
        # Use actual player stats from the player dict
        stats = player.get('stats', {})
        
        if not stats:
            # Fallback to defaults if no stats
            return {
                'points': 10.0,
                'rebounds': 4.0,
                'assists': 3.0,
                'steals': 0.8,
                'blocks': 0.5,
                'three_pointers_made': 1.0,
                'fg_percentage': 0.45,
                'ft_percentage': 0.75,
                'turnovers': 1.5,
                'fg_attempts': 8.0,
                'ft_attempts': 3.0
            }
        
        # Helper function to safely get float values (handle None)
        def safe_get(key, default=0.0):
            value = stats.get(key, default)
            return default if value is None else float(value)
        
        # Convert stats to projections format with safe None handling
        projections = {
            'points': safe_get('points', 0.0),
            'rebounds': safe_get('rebounds', 0.0),
            'assists': safe_get('assists', 0.0),
            'steals': safe_get('steals', 0.0),
            'blocks': safe_get('blocks', 0.0),
            'three_pointers_made': safe_get('three_pointers_made', 0.0),
            'fg_percentage': safe_get('fg_percentage', 0.45),
            'ft_percentage': safe_get('ft_percentage', 0.75),
            'turnovers': safe_get('turnovers', 0.0),
            'fg_attempts': safe_get('field_goals_attempted', 10.0),
            'ft_attempts': safe_get('free_throws_attempted', 3.0)
        }
        
        return projections
    
    def _get_default_league_settings(self):
        """Default H2H category league settings"""
        return {
            'scoring_type': 'head2head',
            'categories': [
                'points', 'rebounds', 'assists', 'steals', 'blocks',
                'fg_pct', 'ft_pct', 'fg3m', 'turnovers'
            ]
        }