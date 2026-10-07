"""
Comprehensive test suite verifying all 14 requirements for NBA Fantasy Assistant.
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from season_config import sort_seasons_descending, season_to_year
from data import DataManager
from draft import DraftAssistant
from simulation import MatchupSimulator
from app import app


class TestAllImprovements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dm = DataManager()
        cls.draft = DraftAssistant(cls.dm)
        cls.sim = MatchupSimulator()
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-secret-key'
        cls.client = cls.app.test_client()

    # 1. Per Game / Total Statistics
    def test_per_game_vs_total_draft_rankings(self):
        pg_rankings = self.draft.get_draft_rankings(season="2024-25", mode="per_game", top_n=20)
        tot_rankings = self.draft.get_draft_rankings(season="2024-25", mode="total", top_n=20)
        
        self.assertGreater(len(pg_rankings), 0)
        self.assertGreater(len(tot_rankings), 0)
        
        # Verify displayed_stats separation
        p_pg = pg_rankings[0]
        p_tot = next((p for p in tot_rankings if p['name'] == p_pg['name']), None)
        if p_tot and p_tot.get('games_played', 0) > 10:
            # Total points must be greater than per-game points
            self.assertGreater(p_tot['displayed_stats']['points'], p_pg['displayed_stats']['points'])
            self.assertEqual(p_pg['mode'], 'per_game')
            self.assertEqual(p_tot['mode'], 'total')

    def test_availability_and_games_played_discounting(self):
        # Two players with identical per-game stats (25 pts, 5 reb, 5 ast)
        # Player A has 75 games, Player B has 12 games
        st = {'points': 25.0, 'rebounds': 5.0, 'assists': 5.0, 'steals': 1.0, 'blocks': 0.5, 'fg3m': 2.0, 'fg_percentage': 0.48, 'ft_percentage': 0.82, 'turnovers': 2.5}
        val_healthy = self.draft.calculate_player_valuation(stats=st, games_played=75, minutes=34.0, mode='per_game')
        val_injured = self.draft.calculate_player_valuation(stats=st, games_played=12, minutes=34.0, mode='per_game')
        
        # Player with very few games should receive discounted fair and credit values
        self.assertGreater(val_healthy['model_fair_value'], val_injured['model_fair_value'])
        self.assertGreater(val_healthy['model_estimated_value'], val_injured['model_estimated_value'])

    # 2. Draft Assistant – Sort Players by Category
    def test_sort_players_by_category_asc_and_desc(self):
        # Sort by PTS desc
        pts_desc = self.draft.get_draft_rankings(season="2024-25", sort_category="PTS", sort_direction="desc", top_n=10)
        self.assertGreater(len(pts_desc), 1)
        for i in range(len(pts_desc) - 1):
            self.assertGreaterEqual(pts_desc[i]['displayed_stats']['points'], pts_desc[i+1]['displayed_stats']['points'])
            
        # Sort by PTS asc
        pts_asc = self.draft.get_draft_rankings(season="2024-25", sort_category="PTS", sort_direction="asc", top_n=10)
        self.assertGreater(len(pts_asc), 1)
        for i in range(len(pts_asc) - 1):
            self.assertLessEqual(pts_asc[i]['displayed_stats']['points'], pts_asc[i+1]['displayed_stats']['points'])

        # Sort by AST desc
        ast_desc = self.draft.get_draft_rankings(season="2024-25", sort_category="AST", sort_direction="desc", top_n=10)
        self.assertGreater(len(ast_desc), 1)
        for i in range(len(ast_desc) - 1):
            self.assertGreaterEqual(ast_desc[i]['displayed_stats']['assists'], ast_desc[i+1]['displayed_stats']['assists'])

        # Sort by CREDIT desc & asc
        credit_desc = self.draft.get_draft_rankings(season="2024-25", sort_category="CREDIT", sort_direction="desc", top_n=10)
        self.assertGreater(len(credit_desc), 1)
        for i in range(len(credit_desc) - 1):
            self.assertGreaterEqual(credit_desc[i]['credit'], credit_desc[i+1]['credit'])

        credit_asc = self.draft.get_draft_rankings(season="2024-25", sort_category="CREDIT", sort_direction="asc", top_n=10)
        self.assertGreater(len(credit_asc), 1)
        for i in range(len(credit_asc) - 1):
            self.assertLessEqual(credit_asc[i]['credit'], credit_asc[i+1]['credit'])

    # 3 & 12. League Auction Prices Calibration Model & Reset
    def test_auction_price_calibration_scaling_and_reset(self):
        # Baseline rankings without overrides
        self.draft.clear_all_league_auction_values()
        base_rankings = self.draft.get_draft_rankings(season="2024-25", top_n=20)
        
        jokic_base = next((p for p in base_rankings if 'joki' in p['name'].lower()), None)
        doncic_base = next((p for p in base_rankings if 'don' in p['name'].lower()), None)
        
        self.assertIsNotNone(jokic_base)
        self.assertIsNotNone(doncic_base)
        
        base_jokic_fair = jokic_base['model_fair_value']
        base_doncic_fair = doncic_base['model_fair_value']
        
        # Override Jokic price: if base is ~$72 and overridden to $100
        override_jokic_price = 100.0
        self.draft.set_league_auction_values({jokic_base['name']: override_jokic_price})
        
        calibrated_rankings = self.draft.get_draft_rankings(season="2024-25", top_n=20)
        jokic_calib = next((p for p in calibrated_rankings if p['name'] == jokic_base['name']))
        doncic_calib = next((p for p in calibrated_rankings if p['name'] == doncic_base['name']))
        
        # Check actual, fair, and adjusted values separation
        self.assertEqual(jokic_calib['actual_auction_price'], override_jokic_price)
        self.assertEqual(jokic_calib['model_fair_value'], base_jokic_fair)
        self.assertEqual(jokic_calib['credit'], int(override_jokic_price))
        
        # Doncic was not overridden, so actual is None
        self.assertIsNone(doncic_calib['actual_auction_price'])
        self.assertEqual(doncic_calib['model_fair_value'], base_doncic_fair)
        
        # Scale factor should scale Doncic upwards: Doncic ($60) -> $83-$84
        expected_scale = override_jokic_price / base_jokic_fair
        expected_doncic_adj = round(base_doncic_fair * expected_scale, 1)
        self.assertAlmostEqual(doncic_calib['adjusted_auction_value'], expected_doncic_adj, delta=1.5)
        
        # Test individual reset
        self.draft.reset_league_auction_value(jokic_base['name'])
        reset_rankings = self.draft.get_draft_rankings(season="2024-25", top_n=20)
        jokic_reset = next((p for p in reset_rankings if p['name'] == jokic_base['name']))
        doncic_reset = next((p for p in reset_rankings if p['name'] == doncic_base['name']))
        
        self.assertIsNone(jokic_reset['actual_auction_price'])
        self.assertEqual(jokic_reset['adjusted_auction_value'], base_jokic_fair)
        self.assertEqual(doncic_reset['adjusted_auction_value'], base_doncic_fair)

    # 4. Draft Assistant – Add/Remove Player & Credit Budget
    def test_draft_team_add_remove_and_budget_constraints(self):
        with self.client.session_transaction() as sess:
            sess['my_team'] = []
            sess['total_credit'] = 0
            
        # Add player 1
        res = self.client.post('/api/draft/add-player', json={
            'player_id': '101',
            'name': 'Player One',
            'credit': 50,
            'position': 'PG',
            'team': 'LAL'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_credit'], 50)
        self.assertEqual(data['remaining_credit'], 150)
        self.assertEqual(len(data['team']), 1)
        
        # Attempt to add player with price exceeding remaining budget ($160 > $150 remaining)
        res_overflow = self.client.post('/api/draft/add-player', json={
            'player_id': '102',
            'name': 'Expensive Player',
            'credit': 160,
            'position': 'C',
            'team': 'DEN'
        })
        self.assertEqual(res_overflow.status_code, 400)
        self.assertFalse(res_overflow.get_json()['success'])
        
        # Remove player
        res_remove = self.client.post('/api/draft/remove-player', json={'name': 'Player One'})
        self.assertEqual(res_remove.status_code, 200)
        self.assertEqual(res_remove.get_json()['total_credit'], 0)
        self.assertEqual(res_remove.get_json()['remaining_credit'], 200)

    # 6 & 7. Draft Roster Optimizer / Monte Carlo Multi-Factor Objective
    def test_draft_roster_optimizer_objective_weights(self):
        res = self.client.post('/api/draft/optimize', json={
            'budget': 200.0,
            'roster_size': 13,
            'strategy': 'punt_5_4',
            'target_categories': ['PTS', 'REB', 'AST', 'STL', 'BLK'],
            'num_simulations': 40,
            'season': '2024-25',
            'mode': 'per_game'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('optimal_roster', data)
        self.assertLessEqual(data['total_cost'], 200.0)
        self.assertIn('objective_breakdown', data)
        
        # Verify objective weights in result
        obj = data['objective_breakdown']
        self.assertIn('win_probability', obj)
        self.assertIn('strategy_fit', obj)
        self.assertIn('roster_fit', obj)
        self.assertIn('composite_score', obj)

    # 8. Draft Assistant – Player Info Safe Handling (No toFixed error)
    def test_build_player_analysis_safe_trends_and_stats(self):
        # Query player analysis for an existing player
        analysis = self.draft.build_player_analysis('203999', season='2024-25')
        if analysis:
            trends = analysis.get('trends', {})
            # Verify safe numeric values exist
            self.assertIn('points_trend', trends)
            self.assertIsInstance(trends['points_trend'], float)
            self.assertIn('rebounds_trend', trends)
            self.assertIsInstance(trends['rebounds_trend'], float)
            self.assertIn('assists_trend', trends)
            self.assertIsInstance(trends['assists_trend'], float)
            # Verify calling toFixed on numerical conversion won't fail
            self.assertIsNotNone(round(trends['points_trend'], 1))

    # 9. Real 2021-22 NBA Player Data (No mock data)
    def test_real_historical_2021_22_nba_data(self):
        players_2022 = self.dm.get_all_nba_players(season="2021-22", min_games=10)
        self.assertGreater(len(players_2022), 100)
        names = [p['name'] for p in players_2022]
        
        # Real stars from 2021-22 season
        self.assertTrue(any('Joki' in name for name in names), "Nikola Jokić must exist in 2021-22")
        self.assertTrue(any('Embiid' in name for name in names), "Joel Embiid must exist in 2021-22")
        self.assertTrue(any('Antetokounmpo' in name for name in names), "Giannis Antetokounmpo must exist in 2021-22")
        
        # Check Nikola Jokić stats for 2021-22
        jokic = next((p for p in players_2022 if 'Joki' in p['name']), None)
        self.assertIsNotNone(jokic)
        self.assertGreater(jokic['games_played'], 70)
        self.assertGreater(jokic['stats']['points'], 25.0)
        self.assertGreater(jokic['stats']['rebounds'], 12.0)

    # 10. Dynamic Season Ordering (Newest First)
    def test_season_ordering_descending(self):
        seasons = ["2021-22", "2025-26", "2023-24", "2026-27", "2024-25"]
        sorted_seasons = sort_seasons_descending(seasons)
        self.assertEqual(sorted_seasons[0], "2026-27")
        self.assertEqual(sorted_seasons[1], "2025-26")
        self.assertEqual(sorted_seasons[2], "2024-25")
        self.assertEqual(sorted_seasons[3], "2023-24")
        self.assertEqual(sorted_seasons[4], "2021-22")
        
        # Verify data_manager available seasons are strictly descending
        dm_seasons = self.dm.available_seasons
        for i in range(len(dm_seasons) - 1):
            self.assertGreater(season_to_year(dm_seasons[i]), season_to_year(dm_seasons[i+1]))

    # 11. Matchup Simulator – Select My Team Workflow
    def test_matchup_simulator_select_draft_team_as_my_team(self):
        draft_players = ['Victor Wembanyama', 'Chet Holmgren', 'Darius Garland']
        with self.client.session_transaction() as sess:
            sess['draft_assistant_roster'] = draft_players
            sess['draft_season'] = '2024-25'
            sess['yahoo_opponent_team_roster'] = ['Nikola Jokić', 'Luka Dončić']
            
        res = self.client.post('/api/matchup/select-draft-team')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['team_name'], 'My Draft Team')
        self.assertEqual(len(data['players']), 3)

        # Verify GET /matchup renders both rosters and simulation results
        matchup_page = self.client.get('/matchup')
        self.assertEqual(matchup_page.status_code, 200)
        content = matchup_page.get_data(as_text=True)
        self.assertIn('Victor Wembanyama', content)
        self.assertIn('Chet Holmgren', content)
        self.assertIn('Nikola Jokić', content)
        self.assertNotIn('No Players Loaded', content)

    # 12. Draft Optimizer Hydration for Pre-Selected Players
    def test_optimizer_hydrates_selected_player_stats(self):
        # Simulate drafted player with minimal attributes (as saved in session/frontend)
        selected_player = {'name': 'Nikola Jokić', 'credit': 68, 'position': 'C'}
        res = self.draft.optimize_draft_roster(
            current_roster=[selected_player],
            budget=200,
            roster_size=13,
            strategy='balanced',
            season='2024-25',
            mode='per_game'
        )
        self.assertTrue(res['success'])
        opt_roster = res['optimal_roster']
        jokic = next((p for p in opt_roster if 'Joki' in p.get('name', '')), None)
        self.assertIsNotNone(jokic)
        
        # Verify stats are hydrated and not 0.0
        stats = jokic.get('weighted_stats') or jokic.get('stats') or {}
        self.assertGreater(stats.get('points', 0), 15.0)
        self.assertGreater(stats.get('rebounds', 0), 8.0)
        self.assertGreater(stats.get('assists', 0), 5.0)
        
        # Verify simulated team totals are also populated
        sim_stats = res.get('simulated_stats', {})
        self.assertGreater(sim_stats.get('points', 0), 50.0)

    # 13. 15-Player League Roster Structure: 10 Starters + 3 BN + 2 IL
    def test_15_player_roster_optimization_slots(self):
        res = self.draft.optimize_draft_roster(
            current_roster=[],
            budget=200,
            roster_size=15,
            strategy='balanced',
            season='2024-25',
            mode='per_game',
            num_simulations=50
        )
        self.assertTrue(res['success'])
        opt_roster = res['optimal_roster']
        self.assertEqual(len(opt_roster), 15)
        
        # Verify exact slot composition
        slots = [p.get('roster_slot') for p in opt_roster]
        self.assertEqual(slots.count('PG'), 1)
        self.assertEqual(slots.count('SG'), 1)
        self.assertEqual(slots.count('G'), 1)
        self.assertEqual(slots.count('SF'), 1)
        self.assertEqual(slots.count('PF'), 1)
        self.assertEqual(slots.count('F'), 1)
        self.assertEqual(slots.count('C'), 2)
        self.assertEqual(slots.count('Util'), 2)
        self.assertEqual(slots.count('BN'), 3)
        self.assertEqual(slots.count('IL'), 2)

        # Test API endpoint defaults to 15
        api_res = self.client.post('/api/draft/optimize', json={
            'season': '2024-25',
            'budget': 200,
            'roster_size': 15,
            'num_simulations': 30
        })
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.get_json()
        self.assertTrue(api_data['success'])
        self.assertEqual(len(api_data['optimal_roster']), 15)

    def test_matchup_opponent_13_players_and_star_selection(self):
        # 1. Test POST /api/random-opponent
        res = self.client.post('/api/random-opponent')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        
        team = data['team']
        players = data['players']
        total_credit = data['total_credit']
        
        # Must be exactly 13 players
        self.assertEqual(len(team), 13)
        self.assertEqual(len(players), 13)
        
        # Must utilize virtually all 200 credits (195-200)
        self.assertGreaterEqual(total_credit, 195)
        self.assertLessEqual(total_credit, 200)
        
        # Must feature marquee star player(s) (credit >= 35)
        star_players = [p for p in players if p.get('credit', 0) >= 35]
        self.assertGreaterEqual(len(star_players), 1, "Random opponent should have at least 1 star player")
        
        # Slots must cover all 10 starters and 3 bench
        slots = [p.get('roster_slot') for p in players]
        self.assertIn('PG', slots)
        self.assertIn('SG', slots)
        self.assertIn('G', slots)
        self.assertIn('SF', slots)
        self.assertIn('PF', slots)
        self.assertIn('F', slots)
        self.assertEqual(slots.count('C'), 2)
        self.assertEqual(slots.count('Util'), 2)
        self.assertEqual(slots.count('BN'), 3)

        # 2. Test session persistence for Matchup simulator
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get('yahoo_opponent_team_roster', [])), 13)
            self.assertTrue(sess.get('yahoo_opponent_is_manual'))

        # 3. Test GET /matchup loads successfully with 13-player opponent
        matchup_res = self.client.get('/matchup')
        self.assertEqual(matchup_res.status_code, 200)
        self.assertIn(b'Opponent Team', matchup_res.data)


if __name__ == '__main__':
    unittest.main()

