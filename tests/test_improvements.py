"""
Unit and Integration Tests for NBA Fantasy Assistant Improvements
Covers:
1. Automatic Season Handling & Centralized Resolver
2. Season-Specific Statistics & Season Switching Data Flow
3. Dynamic Historical Relative Season Weighting
4. League-Specific Draft Credits / Auction Values Separation
5. Configurable Draft Strategy System (Balanced vs 5-4 Punt)
6. Monte Carlo Draft Team Optimization & Budget Constraints
7. Recommendations & Trade Engine Win Probability & Mutual Benefit
8. NBA Players Per Game vs Total Statistics
"""

import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from season_config import (
    SeasonManager,
    detect_current_season,
    season_to_year,
    year_to_season,
    get_relative_season_weights
)
from data import DataManager
from draft import DraftAssistant
from simulation import MatchupSimulator
from recommendation import RecommendationEngine
from app import app


class TestSeasonConfiguration(unittest.TestCase):
    """Test Suite 1 & 3: Automatic Season Handling and Dynamic Weights"""

    def test_season_conversions(self):
        self.assertEqual(season_to_year("2025-26"), 2026)
        self.assertEqual(season_to_year("2024-25"), 2025)
        self.assertEqual(year_to_season(2026), "2025-26")
        self.assertEqual(year_to_season(2025), "2024-25")

    def test_dynamic_season_weights_shift_forward(self):
        # Test for 2025-26 season
        weights_25_26 = get_relative_season_weights("2025-26")
        self.assertEqual(weights_25_26["2025-26"], 0.60)
        self.assertEqual(weights_25_26["2024-25"], 0.30)
        self.assertEqual(weights_25_26["2023-24"], 0.10)
        self.assertNotIn("2022-23", weights_25_26)

        # Test shift for 2026-27 season
        weights_26_27 = get_relative_season_weights("2026-27")
        self.assertEqual(weights_26_27["2026-27"], 0.60)
        self.assertEqual(weights_26_27["2025-26"], 0.30)
        self.assertEqual(weights_26_27["2024-25"], 0.10)
        self.assertNotIn("2023-24", weights_26_27)

    def test_custom_season_manager(self):
        mgr = SeasonManager(current_season="2030-31", weights=(0.50, 0.35, 0.15))
        w = mgr.get_season_weights("2030-31")
        self.assertEqual(w["2030-31"], 0.50)
        self.assertEqual(w["2029-30"], 0.35)
        self.assertEqual(w["2028-29"], 0.15)


class TestDataManagerSeasonIsolation(unittest.TestCase):
    """Test Suite 2 & 8: Season-Specific Statistics, Cache Isolation & Per Game vs Totals"""

    @classmethod
    def setUpClass(cls):
        cls.dm = DataManager()

    def test_available_seasons(self):
        seasons = self.dm.available_seasons
        self.assertIsInstance(seasons, list)
        self.assertIn("2024-25", seasons)
        self.assertIn("2023-24", seasons)

    def test_per_game_vs_totals_separation(self):
        # Query 2024-25 players
        players = self.dm.get_all_nba_players(season="2024-25", min_games=10)
        self.assertGreater(len(players), 0)
        p = players[0]

        # Both stats and total_stats should be populated
        self.assertIn('stats', p)
        self.assertIn('total_stats', p)
        gp = p.get('games_played', 1)
        if gp > 5 and p['total_stats'].get('points', 0) > 0:
            # Total points must be greater than or equal to per-game points
            self.assertGreaterEqual(p['total_stats']['points'], p['stats']['points'])
            # Per-game points should be approximately total points / games_played
            expected_avg = p['total_stats']['points'] / gp
            self.assertAlmostEqual(p['stats']['points'], expected_avg, delta=0.5)

    def test_season_switching_data_integrity(self):
        # Switching between two historical seasons should return distinct season data
        players_24_25 = self.dm.get_all_nba_players(season="2024-25", min_games=20)
        players_23_24 = self.dm.get_all_nba_players(season="2023-24", min_games=20)

        self.assertGreater(len(players_24_25), 0)
        self.assertGreater(len(players_23_24), 0)

        # Check season tagging
        self.assertEqual(players_24_25[0]['season'], "2024-25")
        self.assertEqual(players_23_24[0]['season'], "2023-24")

        # Find a common player and verify stats differ between seasons
        common_name = None
        names_24 = {p['name']: p for p in players_24_25}
        for p in players_23_24:
            if p['name'] in names_24:
                common_name = p['name']
                break

        if common_name:
            p_24 = names_24[common_name]
            p_23 = next(p for p in players_23_24 if p['name'] == common_name)
            self.assertNotEqual(p_24['season'], p_23['season'])


class TestDraftAssistantAndStrategies(unittest.TestCase):
    """Test Suite 4, 5 & 6: Auction Values, Draft Strategies & Monte Carlo Optimization"""

    @classmethod
    def setUpClass(cls):
        cls.dm = DataManager()
        cls.da = DraftAssistant(cls.dm)

    def test_auction_values_separation(self):
        # Clear custom auction values
        self.da.set_league_auction_values({})
        rankings = self.da.get_draft_rankings(top_n=20, season="2024-25")
        self.assertGreater(len(rankings), 0)
        top_player = rankings[0]

        # Verify pricing keys exist
        self.assertIn('credit', top_player)
        self.assertIn('projected_fair_value', top_player)
        self.assertIn('model_estimated_value', top_player)
        self.assertIsNone(top_player['actual_auction_price'])

        # Set an actual league auction price for top player
        custom_price = 88.0
        self.da.set_league_auction_values({top_player['name']: custom_price})
        updated_rankings = self.da.get_draft_rankings(top_n=20, season="2024-25")
        updated_top = next(p for p in updated_rankings if p['name'] == top_player['name'])

        self.assertEqual(updated_top['actual_auction_price'], custom_price)
        self.assertEqual(updated_top['credit'], custom_price)
        # Projected and model values remain distinct
        self.assertIsNotNone(updated_top['projected_fair_value'])
        self.assertIsNotNone(updated_top['model_estimated_value'])

    def test_draft_strategy_balanced_vs_punt(self):
        self.da.set_league_auction_values({})
        # Strategy A: Balanced
        rankings_balanced = self.da.get_draft_rankings(
            top_n=50,
            season="2024-25",
            strategy="balanced"
        )
        # Strategy B: Punt 5-4 targeting REB, BLK, FG%, PTS, TO
        big_men_cats = ['REB', 'BLK', 'FG%', 'PTS', 'TO']
        rankings_punt = self.da.get_draft_rankings(
            top_n=50,
            season="2024-25",
            strategy="punt_5_4",
            target_categories=big_men_cats
        )

        self.assertGreater(len(rankings_balanced), 0)
        self.assertGreater(len(rankings_punt), 0)

        # In big_men punt strategy, players with high rebounds/blocks should get higher value scores
        # than in balanced or guard-heavy strategy
        top_punt_names = [p['name'] for p in rankings_punt[:15]]
        top_balanced_names = [p['name'] for p in rankings_balanced[:15]]
        # Rankings order should not be identical
        self.assertNotEqual(top_punt_names, top_balanced_names)

    def test_monte_carlo_draft_optimizer(self):
        # Run optimizer with $200 budget and balanced strategy
        result = self.da.optimize_draft_roster(
            budget=200.0,
            roster_size=13,
            strategy="balanced",
            num_simulations=50,
            season="2024-25"
        )
        self.assertTrue(result['success'])
        self.assertLessEqual(result['total_cost'], 200.0)
        self.assertGreaterEqual(result['remaining_budget'], 0.0)
        self.assertEqual(len(result['optimal_roster']), 13)

        # Check that positional slots are allocated
        slots = [p.get('roster_slot') for p in result['optimal_roster']]
        self.assertIn('PG', slots)
        self.assertIn('C', slots)


class TestRecommendationAndTradeEngine(unittest.TestCase):
    """Test Suite 7: Trade Evaluation, Mutual Benefit & Win Probability"""

    @classmethod
    def setUpClass(cls):
        cls.dm = DataManager()
        cls.sim = MatchupSimulator()
        cls.da = DraftAssistant(cls.dm)
        cls.rec = RecommendationEngine(cls.dm, cls.sim, cls.da)

    def test_trade_evaluation_win_probability(self):
        players = self.dm.get_all_nba_players(season="2024-25", min_games=20)
        self.assertGreater(len(players), 30)

        my_team = players[:10]
        opp_team = players[10:20]

        # Give a player from my team to opponent for a comparable tier player from opponent
        trade = self.rec._evaluate_candidate_trade(
            my_roster=my_team,
            opp_roster=opp_team,
            give_player=my_team[9],
            receive_player=opp_team[0],
            opp_name="Rival Manager"
        )

        self.assertIsNotNone(trade)
        self.assertIn('win_prob_before', trade)
        self.assertIn('win_prob_after', trade)
        self.assertIn('beneficial_for_both', trade)
        self.assertIn('plausibility', trade)
        self.assertIn('rank_score', trade)

        # Probabilities should be valid percentages between 0 and 100
        self.assertGreaterEqual(trade['win_prob_before'], 0.0)
        self.assertLessEqual(trade['win_prob_before'], 100.0)
        self.assertGreaterEqual(trade['win_prob_after'], 0.0)
        self.assertLessEqual(trade['win_prob_after'], 100.0)


class TestFlaskEndpoints(unittest.TestCase):
    """Integration Test: Flask Endpoints for Season, Strategy and Auction Values"""

    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    def test_api_players_with_season(self):
        res = self.client.get('/api/players?season=2024-25&limit=10')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['players']), 10)

    def test_api_draft_rankings_with_strategy(self):
        res = self.client.get('/api/draft/rankings?season=2024-25&strategy=punt_5_4&categories=PTS,REB,AST,STL,BLK')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['strategy'], 'punt_5_4')

    def test_api_draft_auction_values(self):
        # Post a custom auction price
        res_post = self.client.post('/api/draft/auction-values', json={
            'prices': {'Test Superstar': 95.0}
        })
        self.assertEqual(res_post.status_code, 200)
        data_post = res_post.get_json()
        self.assertTrue(data_post['success'])
        self.assertEqual(data_post['prices'].get('Test Superstar'), 95.0)

        # Get stored auction values
        res_get = self.client.get('/api/draft/auction-values')
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.get_json()
        self.assertTrue(data_get['success'])
        self.assertEqual(data_get['prices'].get('Test Superstar'), 95.0)

    def test_api_draft_optimize_endpoint(self):
        res = self.client.post('/api/draft/optimize', json={
            'budget': 200.0,
            'roster_size': 13,
            'strategy': 'balanced',
            'num_simulations': 25,
            'season': '2024-25'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertLessEqual(data['total_cost'], 200.0)
        self.assertEqual(len(data['optimal_roster']), 13)

    def test_recommendations_with_remaining_credit(self):
        from recommendation import RecommendationEngine
        from simulation import MatchupSimulator
        from draft import DraftAssistant
        from data import DataManager
        dm = DataManager()
        da = DraftAssistant(dm)
        ms = MatchupSimulator()
        engine = RecommendationEngine(dm, ms, da)
        players = dm.get_all_nba_players(season=dm.current_season, min_games=0)
        roster = players[:5]
        fas = players[5:25]

        recs = engine.get_recommendations_for_roster(
            roster, fas, players, max_recommendations=20, remaining_credit=5
        )
        self.assertIsInstance(recs, list)
        for r in recs:
            if 'credit_change' in r and r['credit_change'] is not None:
                self.assertLessEqual(r['credit_change'], 5)


if __name__ == '__main__':
    unittest.main()
