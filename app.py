"""
Yahoo NBA Fantasy Assistant - Main Flask Application
"""

from flask import Flask, render_template, session, redirect, url_for, request, jsonify
import os
from dotenv import load_dotenv

from auth import YahooAuth
from data import DataManager
from draft import DraftAssistant
from simulation import MatchupSimulator
from recommendation import RecommendationEngine
from routes.nba_routes import nba_bp
from yahoo_integration.routes import yahoo_bp

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')

# Register blueprints
app.register_blueprint(nba_bp)
app.register_blueprint(yahoo_bp)

# Initialize components
yahoo_auth = YahooAuth(
    client_id=os.getenv('YAHOO_CLIENT_ID'),
    client_secret=os.getenv('YAHOO_CLIENT_SECRET')
)
data_manager = DataManager()
draft_assistant = DraftAssistant(data_manager)
matchup_simulator = MatchupSimulator()
recommendation_engine = RecommendationEngine(data_manager, matchup_simulator, draft_assistant)


@app.route('/')
def index():
    """Main dashboard page - Yahoo Fantasy League focused"""
    try:
        # Get season from query parameter or default to 2025-26
        season = request.args.get('season', '2025-26')
        
        # Check if Yahoo Matchup Stats is selected
        yahoo_matchup_stats = None
        yahoo_my_team_stats = None
        yahoo_current_week = None
        actual_season = season
        if season == 'yahoo-matchup':
            yahoo_matchup_stats = session.get('yahoo_matchup_stats')
            yahoo_my_team_stats = session.get('yahoo_my_team_stats')
            yahoo_current_week = session.get('yahoo_current_week')
            app.logger.info(f"[INDEX] Yahoo Matchup Stats mode active: {yahoo_matchup_stats is not None}")
            app.logger.info(f"[INDEX] Yahoo My Team Stats: {yahoo_my_team_stats is not None}")
            app.logger.info(f"[INDEX] Current week: {yahoo_current_week}")
            # Use 2025-26 data for player stats even in yahoo-matchup mode
            actual_season = '2025-26'
        
        # Get real stats from database - all players
        # For 2025-26 season (upcoming), don't filter by games_played since season hasn't started
        min_games = 0 if actual_season in ['2025-26', 'yahoo-matchup'] else 1
        all_players = data_manager.get_all_nba_players(season=actual_season, min_games=min_games)
        
        # Get top performers (filter players with at least 20 games for accurate stats)
        # For 2025-26 and yahoo-matchup, use all players since it's based on projections/previous season
        qualified_players = all_players if actual_season in ['2025-26', 'yahoo-matchup'] else [p for p in all_players if p.get('games_played', 0) >= 20]
        top_scorers = sorted(qualified_players, key=lambda x: x['stats'].get('points', 0), reverse=True)[:10]
        top_rebounders = sorted(qualified_players, key=lambda x: x['stats'].get('rebounds', 0), reverse=True)[:10]
        top_assisters = sorted(qualified_players, key=lambda x: x['stats'].get('assists', 0), reverse=True)[:10]
        
        stats_summary = {
            'total_players': len(all_players),
            'current_season': season,
            'available_seasons': data_manager.available_seasons,
            'top_scorers': top_scorers,
            'top_rebounders': top_rebounders,
            'top_assisters': top_assisters
        }
        
        # Clear ALL demo session data on every page load
        session.pop('my_team', None)
        session.pop('total_credit', None)
        session.pop('team_credits', None)
        
        # Get user's team - ONLY Yahoo team, NO demo mode
        my_team = []
        yahoo_my_team = session.get('yahoo_my_team_roster', [])
        
        if yahoo_my_team:
            my_team = yahoo_my_team
        
        # Get full player data for my team
        my_roster = []
        if my_team:
            my_roster = [p for p in qualified_players if p['name'] in my_team]
        
        return render_template('index.html', 
                             stats=stats_summary, 
                             my_team=my_team,
                             my_roster=my_roster,
                             all_players=qualified_players,
                             season=season,
                             yahoo_matchup_stats=yahoo_matchup_stats,
                             yahoo_my_team_stats=yahoo_my_team_stats,
                             yahoo_current_week=yahoo_current_week)
    except Exception as e:
        app.logger.error(f"Error loading dashboard: {e}")
        return render_template('error.html', error=str(e))


@app.route('/login')
def login():
    """Direct access - no OAuth needed for local data"""
    return redirect(url_for('index'))


@app.route('/callback')
def callback():
    """Handle Yahoo OAuth callback"""
    code = request.args.get('code')
    if not code:
        return render_template('error.html', error="Authorization failed")
    
    try:
        tokens = yahoo_auth.get_access_token(code)
        session['access_token'] = tokens['access_token']
        session['refresh_token'] = tokens['refresh_token']
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"OAuth callback error: {e}")
        return render_template('error.html', error="Authentication failed")


@app.route('/draft')
def draft_page():
    """Draft assistant page with real data - all active players"""
    try:
        # Get season from query parameter or default to 2025-26
        season = request.args.get('season', '2025-26')
        
        # Temporarily set data_manager season for draft analysis
        original_season = data_manager.current_season
        data_manager.current_season = season
        
        # Get all draft recommendations (no limit)
        rankings = draft_assistant.get_draft_rankings(top_n=None)
        
        # Get position-specific rankings
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        position_rankings = {}
        for pos in positions:
            position_rankings[pos] = [p for p in rankings if pos in p.get('position', '')][:20]
        
        # Get user's credit info
        my_team = session.get('my_team', [])
        total_credit = session.get('total_credit', 0)
        remaining_credit = 200 - total_credit
        
        # Restore original season
        data_manager.current_season = original_season
        
        return render_template('draft.html', 
                             rankings=rankings,
                             position_rankings=position_rankings,
                             total_players=len(rankings),
                             season=season,
                             my_team=my_team,
                             total_credit=total_credit,
                             remaining_credit=remaining_credit)
    except Exception as e:
        app.logger.error(f"Error loading draft page: {e}")
        return render_template('error.html', error=f"Draft analysis error: {str(e)}")


def sort_roster_by_position(roster):
    """Sort roster by position (PG, SG, SF, PF, C)"""
    position_order = {'PG': 1, 'SG': 2, 'SF': 3, 'PF': 4, 'C': 5}
    
    def get_position_sort_key(player):
        # Get primary position (first one if multiple positions like PG-SG)
        position = player.get('position', 'C').split('-')[0]
        return position_order.get(position, 6)  # Unknown positions go to end
    
    return sorted(roster, key=get_position_sort_key)

@app.route('/matchup')
def matchup_page():
    """Matchup simulation page with Yahoo Fantasy teams"""
    try:
        # Get season from query parameter or default to 2025-26
        season = request.args.get('season', '2025-26')
        
        # Clear demo session data
        session.pop('my_team', None)
        session.pop('opponent_team', None)
        session.pop('total_credit', None)
        session.pop('team_credits', None)
        
        # Check if Yahoo Matchup Stats is selected
        yahoo_matchup_stats = None
        yahoo_my_team_stats = None
        yahoo_opponent_team_stats = None
        yahoo_current_week = None
        actual_season = season
        if season == 'yahoo-matchup':
            yahoo_matchup_stats = session.get('yahoo_matchup_stats')
            yahoo_my_team_stats = session.get('yahoo_my_team_stats', {})
            yahoo_opponent_team_stats = session.get('yahoo_opponent_team_stats', {})
            yahoo_current_week = session.get('yahoo_current_week')
            app.logger.info(f"[MATCHUP] Yahoo Matchup Stats mode active: {yahoo_matchup_stats is not None}")
            app.logger.info(f"[MATCHUP] Current week: {yahoo_current_week}")
            app.logger.info(f"[MATCHUP] My team stats keys: {list(yahoo_my_team_stats.keys()) if yahoo_my_team_stats else []}")
            app.logger.info(f"[MATCHUP] My team PTS: {yahoo_my_team_stats.get('12', 'N/A')}, REB: {yahoo_my_team_stats.get('15', 'N/A')}, 3PM: {yahoo_my_team_stats.get('10', 'N/A')}")
            app.logger.info(f"[MATCHUP] Opponent stats keys: {list(yahoo_opponent_team_stats.keys()) if yahoo_opponent_team_stats else []}")
            app.logger.info(f"[MATCHUP] Opponent PTS: {yahoo_opponent_team_stats.get('12', 'N/A')}, REB: {yahoo_opponent_team_stats.get('15', 'N/A')}, 3PM: {yahoo_opponent_team_stats.get('10', 'N/A')}")
            # Use 2025-26 data for simulation even in yahoo-matchup mode
            actual_season = '2025-26'
        
        # Temporarily set data_manager season for simulation
        original_season = data_manager.current_season
        data_manager.current_season = actual_season
        
        # Get all players for roster building
        # For 2025-26, use all players (no min_games filter)
        min_games = 0 if season in ['2025-26', 'yahoo-matchup'] else 20
        all_players = data_manager.get_all_nba_players(season='2025-26' if season == 'yahoo-matchup' else season, min_games=min_games)
        
        # Get ONLY Yahoo teams (no demo mode)
        yahoo_my_team = session.get('yahoo_my_team_roster', [])  # List of player names from Yahoo
        yahoo_opponent_team = session.get('yahoo_opponent_team_roster', [])
        
        app.logger.info(f"[MATCHUP] My team roster: {len(yahoo_my_team)} players - {yahoo_my_team}")
        app.logger.info(f"[MATCHUP] Opponent roster: {len(yahoo_opponent_team)} players - {yahoo_opponent_team}")
        
        # Get full player data for Yahoo teams
        my_roster = [p for p in all_players if p['name'] in yahoo_my_team] if yahoo_my_team else []
        opponent_roster = [p for p in all_players if p['name'] in yahoo_opponent_team] if yahoo_opponent_team else []
        
        app.logger.info(f"[MATCHUP] My roster matched: {len(my_roster)} players")
        app.logger.info(f"[MATCHUP] Opponent matched: {len(opponent_roster)} players")
        
        # Sort both rosters by position
        my_roster = sort_roster_by_position(my_roster)
        opponent_roster = sort_roster_by_position(opponent_roster)
        
        # Run simulation only if both teams are set
        simulation_results = None
        if my_roster and opponent_roster:
            simulation_results = matchup_simulator.simulate_matchup(my_roster, opponent_roster)
        
        # Restore original season
        data_manager.current_season = original_season
        
        return render_template('matchup.html', 
                             all_players=all_players,
                             my_roster=my_roster,
                             opponent_roster=opponent_roster,
                             simulation=simulation_results,
                             season=season,
                             yahoo_matchup_stats=yahoo_matchup_stats,
                             yahoo_my_team_stats=yahoo_my_team_stats,
                             yahoo_opponent_team_stats=yahoo_opponent_team_stats,
                             yahoo_current_week=yahoo_current_week)
    except Exception as e:
        # Restore original season even on error
        data_manager.current_season = original_season
        app.logger.error(f"Error loading matchup page: {e}")
        return render_template('error.html', error=f"Matchup simulation error: {str(e)}")


@app.route('/recommendations')
def recommendations_page():
    """Roster recommendations page with Yahoo Fantasy team analysis"""
    try:
        # Get season from query parameter or default to 2025-26
        season = request.args.get('season', '2025-26')
        
        # Clear demo session data
        session.pop('my_team', None)
        session.pop('total_credit', None)
        session.pop('team_credits', None)
        
        # Get all players for recommendations
        # For 2025-26, use all players (no min_games filter)
        min_games = 0 if season == '2025-26' else 20
        all_players = data_manager.get_all_nba_players(season=season, min_games=min_games)
        
        # Get ONLY Yahoo team (no demo mode)
        yahoo_my_team = session.get('yahoo_my_team_roster', [])  # List of player names from Yahoo
        
        # Get user's roster from Yahoo (if team is selected)
        current_roster = []
        recommendations = []
        other_teams_rosters = []
        
        if yahoo_my_team:
            # Mark user's roster with their team name
            user_team_name = session.get('yahoo_team_name', 'My Team')
            current_roster = []
            for p in all_players:
                if p['name'] in yahoo_my_team:
                    # Create a deep copy
                    player_copy = {
                        'name': p.get('name'),
                        'team': p.get('team'),
                        'position': p.get('position'),
                        'stats': p.get('stats', {}),
                        'fantasy_team': user_team_name
                    }
                    current_roster.append(player_copy)
            print(f"✅ User roster: {len(current_roster)} players in {user_team_name}")
            
            # Try to get league data from Yahoo API
            free_agents = []
            yahoo_free_agent_names = set()
            player_to_fantasy_team = {}  # Map player name to fantasy team name
            
            try:
                from yahoo_integration.yahoo_client import yahoo_client
                token = session.get('yahoo_token')
                league_key = session.get('yahoo_league_key')
                user_team_name = session.get('yahoo_team_name')
                
                print(f"🔍 Yahoo session data:")
                print(f"   - Token exists: {token is not None}")
                print(f"   - League key: {league_key}")
                print(f"   - User team name: {user_team_name}")
                
                if token and league_key:
                    yahoo_client.set_token(token)
                    
                    # First, get all teams and build ownership map
                    print(f"🔍 Building player ownership map for league {league_key}...")
                    teams = yahoo_client.get_league_teams(league_key, include_rosters=True)
                    print(f"✅ Got {len(teams)} teams from Yahoo API")
                    
                    all_owned_player_names = set()
                    for team in teams:
                        print(f"   Processing team: {team.name} (key: {team.team_key})")
                        roster = yahoo_client.get_team_roster(team.team_key)
                        print(f"      Roster size: {len(roster)} players")
                        
                        for player in roster:
                            if player and player.name:
                                all_owned_player_names.add(player.name)
                                player_to_fantasy_team[player.name] = team.name
                        
                        # Skip user's own team for trade analysis
                        print(f"      Checking if {team.name} == {user_team_name}")
                        if team.name != user_team_name:
                            team_player_names = [p.name for p in roster if p and p.name]
                            team_roster_objects = []
                            
                            for p in all_players:
                                if p['name'] in team_player_names:
                                    # Create a deep copy to avoid reference issues
                                    player_copy = {
                                        'name': p.get('name'),
                                        'team': p.get('team'),
                                        'position': p.get('position'),
                                        'stats': p.get('stats', {}),
                                        'fantasy_team': team.name  # CRITICAL: Set fantasy team
                                    }
                                    team_roster_objects.append(player_copy)
                                    print(f"      ✅ Added {p['name']} to {team.name}")
                            
                            if team_roster_objects:
                                other_teams_rosters.append({
                                    'team_name': team.name,
                                    'roster': team_roster_objects
                                })
                                # Debug: Show which players are in this team
                                print(f"   📋 {team.name}: {len(team_roster_objects)} players")
                    
                    print(f"✅ Found {len(all_owned_player_names)} owned players across {len(teams)} teams")
                    print(f"✅ Loaded {len(other_teams_rosters)} other teams for trade analysis")
                    
                    # Get TRUE free agents from Yahoo API (not owned by anyone)
                    print(f"🔍 Fetching free agents from Yahoo API...")
                    yahoo_free_agents = yahoo_client.get_free_agents(league_key, count=300)
                    yahoo_free_agent_names = set([p.name for p in yahoo_free_agents if p and p.name])
                    print(f"✅ Yahoo API returned {len(yahoo_free_agent_names)} free agents")
                    
                    # Double-check: Remove any owned players from free agent list
                    yahoo_free_agent_names = yahoo_free_agent_names - all_owned_player_names
                    print(f"✅ After filtering owned players: {len(yahoo_free_agent_names)} true free agents")
                    
                    # Convert Yahoo free agents to our player objects
                    free_agents = []
                    for p in all_players:
                        if p['name'] in yahoo_free_agent_names:
                            # Create a deep copy
                            player_copy = {
                                'name': p.get('name'),
                                'team': p.get('team'),
                                'position': p.get('position'),
                                'stats': p.get('stats', {}),
                                'fantasy_team': 'Free Agent'
                            }
                            free_agents.append(player_copy)
                    
                    print(f"✅ Matched {len(free_agents)} free agents with NBA stats")
                    
                    # Debug: Show sample free agents
                    if free_agents:
                        sample_names = [p['name'] for p in free_agents[:5]]
                        print(f"📋 Sample free agents: {', '.join(sample_names)}")
                    
            except Exception as e:
                print(f"⚠️ Could not load Yahoo league data: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: Get all players not in user's roster
                free_agents = []
                for p in all_players:
                    if p['name'] not in yahoo_my_team:
                        player_copy = {
                            'name': p.get('name'),
                            'team': p.get('team'),
                            'position': p.get('position'),
                            'stats': p.get('stats', {}),
                            'fantasy_team': 'Unknown'
                        }
                        free_agents.append(player_copy)
                print(f"⚠️ Using fallback: {len(free_agents)} players not in roster")
            
            # Get recommendations (show up to 100 recommendations)
            recommendations = recommendation_engine.get_recommendations_for_roster(
                current_roster, free_agents, all_players, 
                max_recommendations=100,
                other_teams_rosters=other_teams_rosters if other_teams_rosters else None
            )
        
        return render_template('recommendations.html', 
                             recommendations=recommendations,
                             current_roster=current_roster,
                             season=season,
                             all_players=all_players)
    except Exception as e:
        app.logger.error(f"Error loading recommendations: {e}")
        import traceback
        traceback.print_exc()
        return render_template('error.html', error=f"Recommendation error: {str(e)}")


@app.route('/api/player/<player_id>')
def player_api(player_id):
    """API endpoint for player data"""
    try:
        player_data = data_manager.get_player_stats(player_id)
        return jsonify(player_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/draft/player/<player_id>')
def api_draft_player(player_id):
    """API endpoint to get draft analysis details for a player."""
    try:
        analysis = draft_assistant.build_player_analysis(player_id)
        if not analysis:
            return jsonify({'success': False, 'error': 'Player not found'}), 404
        return jsonify({'success': True, 'analysis': analysis})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/compare', methods=['POST'])
def api_draft_compare():
    """API endpoint to compare multiple players"""
    try:
        data = request.get_json()
        player_ids = data.get('player_ids', [])
        
        if not player_ids or len(player_ids) < 2:
            return jsonify({'success': False, 'error': 'Please select at least 2 players'}), 400
        
        if len(player_ids) > 5:
            return jsonify({'success': False, 'error': 'Maximum 5 players allowed'}), 400
        
        comparisons = []
        for player_id in player_ids:
            analysis = draft_assistant.build_player_analysis(player_id)
            if analysis:
                comparisons.append(analysis)
        
        if not comparisons:
            return jsonify({'success': False, 'error': 'No valid players found'}), 404
        
        return jsonify({'success': True, 'comparisons': comparisons})
    except Exception as e:
        app.logger.error(f"Error comparing players: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/rankings')
def api_draft_rankings():
    """API endpoint to get draft rankings with credits"""
    try:
        rankings = draft_assistant.get_draft_rankings(top_n=None)
        return jsonify({
            'success': True,
            'rankings': rankings,
            'count': len(rankings)
        })
    except Exception as e:
        app.logger.error(f"Error fetching rankings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/players')
def api_players():
    """API endpoint to get NBA players data"""
    position = request.args.get('position')
    season = request.args.get('season', data_manager.current_season)
    limit_param = request.args.get('limit', '1000')
    limit = None if str(limit_param).lower() == 'all' else int(limit_param)
    
    try:
        players = data_manager.get_all_nba_players(season=season, min_games=0)
        # Ensure only players who actually played in that season are returned
        players = [
            p for p in players
            if (p.get('games_played', 0) or 0) > 0 and p.get('is_active', True)
        ]
        
        # Filter by position if specified
        if position:
            players = [p for p in players if p['position'] == position]
        
        # Limit results (if numeric limit provided)
        if isinstance(limit, int):
            players = players[:limit]
        
        return jsonify({
            'success': True,
            'players': players,
            'count': len(players)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/free_agents')
def api_free_agents():
    """API endpoint to get free agents"""
    position = request.args.get('position')
    season = request.args.get('season', '2023-24')
    count = int(request.args.get('count', 50))
    
    try:
        free_agents = data_manager.get_free_agents(
            access_token=None,  # Demo mode
            league_key='426.l.12345',
            position=position,
            count=count,
            season=season
        )
        
        return jsonify({
            'success': True,
            'free_agents': free_agents,
            'count': len(free_agents)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/save-team', methods=['POST'])
def api_save_team():
    """Save user's team to session with credit validation"""
    try:
        data = request.get_json()
        team = data.get('team', [])
        
        if len(team) > 15:
            return jsonify({'success': False, 'error': 'Maksimum 15 oyuncu seçebilirsiniz'}), 400
        
        # Get all players and calculate total credit
        all_players = data_manager.get_all_nba_players(season='2024-25', min_games=0)
        rankings = draft_assistant.get_draft_rankings(top_n=None)
        
        total_credit = 0
        selected_players_data = []
        
        for player_name in team:
            # Find player in rankings to get credit value
            player_data = next((p for p in rankings if p['name'] == player_name), None)
            if player_data:
                total_credit += player_data.get('credit', 0)
                selected_players_data.append({
                    'name': player_name,
                    'credit': player_data.get('credit', 0)
                })
        
        # Check credit limit (200)
        if total_credit > 200:
            return jsonify({
                'success': False, 
                'error': f'Kredi limiti aşıldı! Toplam: {total_credit}, Limit: 200'
            }), 400
        
        session['my_team'] = team
        session['team_credits'] = selected_players_data
        session['total_credit'] = total_credit
        
        return jsonify({
            'success': True, 
            'team_size': len(team),
            'total_credit': total_credit,
            'remaining_credit': 200 - total_credit
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-team', methods=['GET'])
def api_get_team():
    """Get user's current team from session"""
    try:
        team = session.get('my_team', [])
        total_credit = session.get('total_credit', 0)
        
        return jsonify({
            'success': True,
            'team': team,
            'total_credit': total_credit,
            'team_size': len(team)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-opponent', methods=['POST'])
def api_save_opponent():
    """Save opponent's team to session"""
    try:
        data = request.get_json()
        team = data.get('team', [])
        
        if len(team) > 15:
            return jsonify({'success': False, 'error': 'Maximum 15 players allowed'}), 400
        
        session['opponent_team'] = team
        return jsonify({'success': True, 'team_size': len(team)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-yahoo-teams', methods=['POST'])
def api_save_yahoo_teams():
    """Save Yahoo Fantasy teams (my team and opponent) to session"""
    try:
        data = request.get_json()
        my_team_roster = data.get('my_team', [])
        opponent_roster = data.get('opponent_team', [])
        
        session['yahoo_my_team_roster'] = my_team_roster
        session['yahoo_opponent_team_roster'] = opponent_roster
        
        return jsonify({
            'success': True,
            'my_team_size': len(my_team_roster),
            'opponent_team_size': len(opponent_roster)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-yahoo-my-team', methods=['POST'])
def api_save_yahoo_my_team():
    """Save Yahoo Fantasy my team to session"""
    try:
        data = request.get_json()
        team_roster = data.get('team', [])
        team_name = data.get('team_name', 'My Team')
        team_key = data.get('team_key', '')
        league_key = data.get('league_key', '')
        team_logo = data.get('logo_url', '')
        team_stats = data.get('stats', {})  # Week stats from Yahoo
        current_week = data.get('week')  # Current week number
        
        print(f"📊 [SAVE-MY-TEAM] Team: {team_name}")
        print(f"📊 [SAVE-MY-TEAM] Stats received: {team_stats}")
        print(f"📊 [SAVE-MY-TEAM] Stats keys: {list(team_stats.keys()) if team_stats else 'Empty'}")
        print(f"📊 [SAVE-MY-TEAM] Week: {current_week}")
        
        session['yahoo_my_team_roster'] = team_roster
        session['yahoo_my_team_name'] = team_name
        session['yahoo_my_team_logo'] = team_logo
        session['yahoo_team_key'] = team_key
        session['yahoo_league_key'] = league_key
        session['yahoo_my_team_stats'] = team_stats  # Save team stats
        if current_week:
            session['yahoo_current_week'] = current_week  # Save current week
        
        # Also set these for backward compatibility
        session['yahoo_team_name'] = team_name
        session['yahoo_team_logo'] = team_logo
        
        print(f"✅ Saved to session: Team={team_name}, League={league_key}, Players={len(team_roster)}")
        
        # Clear demo mode team when Yahoo team is loaded
        session.pop('my_team', None)
        session.pop('total_credit', None)
        session.pop('team_credits', None)
        
        return jsonify({
            'success': True,
            'team_size': len(team_roster),
            'team_name': team_name
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear-yahoo-success', methods=['POST'])
def api_clear_yahoo_success():
    """Clear Yahoo success message flag"""
    session.pop('show_yahoo_success', None)
    return jsonify({'success': True})


@app.route('/api/save-yahoo-opponent', methods=['POST'])
def api_save_yahoo_opponent():
    """Save Yahoo Fantasy opponent team to session"""
    try:
        data = request.get_json()
        team_roster = data.get('team', [])
        team_name = data.get('team_name', 'Opponent')
        team_logo = data.get('logo_url', '')
        is_manual = data.get('is_manual', False)  # Flag for manual selection
        team_stats = data.get('stats', {})  # Week stats from Yahoo
        
        print(f"📊 [SAVE-OPPONENT] Team: {team_name}")
        print(f"📊 [SAVE-OPPONENT] Stats received: {team_stats}")
        print(f"📊 [SAVE-OPPONENT] Stats keys: {list(team_stats.keys()) if team_stats else 'Empty'}")
        
        session['yahoo_opponent_team_roster'] = team_roster
        session['yahoo_opponent_team_name'] = team_name if not is_manual else 'Opponent Team'
        session['yahoo_opponent_team_logo'] = team_logo if not is_manual else ''
        session['yahoo_opponent_is_manual'] = is_manual
        session['yahoo_opponent_team_stats'] = team_stats  # Save opponent stats
        
        return jsonify({
            'success': True,
            'team_size': len(team_roster),
            'team_name': session['yahoo_opponent_team_name']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-yahoo-matchup', methods=['POST'])
def api_save_yahoo_matchup():
    """Save Yahoo Fantasy matchup data to session"""
    try:
        data = request.get_json()
        matchup = data.get('matchup', {})
        league_name = data.get('league_name', 'Yahoo League')
        week = data.get('week', 1)
        
        # Extract team data from matchup
        teams = matchup.get('teams', [])
        if len(teams) < 2:
            return jsonify({'success': False, 'error': 'Invalid matchup data'}), 400
        
        team1 = teams[0]
        team2 = teams[1]
        
        # Save matchup info to session
        session['yahoo_matchup_data'] = matchup
        session['yahoo_matchup_week'] = week
        session['yahoo_league_name'] = league_name
        
        # Save stats for display (9-cat stats with IDs)
        session['yahoo_matchup_stats'] = {
            'team1': {
                'name': team1.get('name', 'Team 1'),
                'logo': team1.get('team_logo_url', ''),
                'stats': team1.get('stats', {}),
                'projected_stats': team1.get('projected_stats', {})
            },
            'team2': {
                'name': team2.get('name', 'Team 2'),
                'logo': team2.get('team_logo_url', ''),
                'stats': team2.get('stats', {}),
                'projected_stats': team2.get('projected_stats', {})
            }
        }
        
        return jsonify({
            'success': True,
            'week': week,
            'league': league_name,
            'team1': team1.get('name'),
            'team2': team2.get('name')
        })
    except Exception as e:
        app.logger.error(f"Error saving Yahoo matchup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/random-opponent', methods=['POST'])
def api_random_opponent():
    """Generate random opponent team (10 players with 180-200 credits, position balanced)"""
    try:
        import random
        all_players = data_manager.get_all_nba_players(season='2024-25', min_games=20)
        my_team = session.get('my_team', [])
        
        # Filter out user's players and calculate credits for all
        available_players = []
        for p in all_players:
            if p['name'] not in my_team:
                credit = draft_assistant.calculate_player_credit(p.get('stats', {}), p.get('minutes', 0))
                p['credit'] = credit
                available_players.append(p)
        
        # Group players by position and sort by credit
        by_position = {
            'PG': sorted([p for p in available_players if 'PG' in p.get('position', '')], 
                        key=lambda x: x['credit'], reverse=True),
            'SG': sorted([p for p in available_players if 'SG' in p.get('position', '')], 
                        key=lambda x: x['credit'], reverse=True),
            'SF': sorted([p for p in available_players if 'SF' in p.get('position', '')], 
                        key=lambda x: x['credit'], reverse=True),
            'PF': sorted([p for p in available_players if 'PF' in p.get('position', '')], 
                        key=lambda x: x['credit'], reverse=True),
            'C': sorted([p for p in available_players if 'C' in p.get('position', '')], 
                       key=lambda x: x['credit'], reverse=True)
        }
        
        # Try to build a team with 180-200 total credits (strict limit: max 200)
        max_attempts = 100
        best_team = None
        best_credit = 0
        
        app.logger.info(f"Starting random opponent generation. Available players: {len(available_players)}")
        app.logger.info(f"Sample player credits: {[(p['name'], p['credit']) for p in available_players[:5]]}")
        
        for attempt in range(max_attempts):
            random_team = []
            used_names = set()
            total_credit = 0
            
            # Define exact roster slots: PG, SG, G, SF, PF, F, C, C, UTIL, UTIL
            roster_slots = [
                ('PG', ['PG']),           # Pure PG
                ('SG', ['SG']),           # Pure SG  
                ('G', ['PG', 'SG']),      # Any guard (PG or SG)
                ('SF', ['SF']),           # Pure SF
                ('PF', ['PF']),           # Pure PF
                ('F', ['SF', 'PF']),      # Any forward (SF or PF)
                ('C', ['C']),             # Center
                ('C', ['C']),             # Center
                ('UTIL', ['PG', 'SG', 'SF', 'PF', 'C']),  # Any position
                ('UTIL', ['PG', 'SG', 'SF', 'PF', 'C'])   # Any position
            ]
            target_avg_per_player = 190 / 10  # Target ~19 credits per player
            
            # Fill each roster slot in order
            for slot_name, allowed_positions in roster_slots:
                credits_left = 200 - total_credit
                slots_remaining = 10 - len(random_team)
                
                # Don't use all credits on early picks
                max_credit_for_slot = credits_left - (slots_remaining - 1) if slots_remaining > 1 else credits_left
                
                # Find candidates that match this slot's position requirements
                candidates = []
                for p in available_players:
                    if p['name'] in used_names:
                        continue
                    if p['credit'] > max_credit_for_slot:
                        continue
                    
                    # Check if player's position matches any allowed position for this slot
                    player_pos = p.get('position', '')
                    if any(allowed_pos in player_pos for allowed_pos in allowed_positions):
                        candidates.append(p)
                
                if not candidates:
                    # If no candidates, try with relaxed credit limit
                    candidates = [p for p in available_players 
                                if p['name'] not in used_names 
                                and any(pos in p.get('position', '') for pos in allowed_positions)]
                    if not candidates:
                        break  # Can't fill this slot
                
                # Target credit for this slot
                avg_needed = (190 - total_credit) / slots_remaining if slots_remaining > 0 else 10
                avg_needed = max(1, min(avg_needed, max_credit_for_slot))
                
                # Sort by proximity to needed average
                candidates_sorted = sorted(candidates, 
                                         key=lambda x: abs(x['credit'] - avg_needed))
                
                # Pick from top candidates
                pool_size = max(1, len(candidates_sorted) // 3)
                selected = random.choice(candidates_sorted[:pool_size])
                
                random_team.append(selected)
                used_names.add(selected['name'])
                total_credit += selected['credit']
            
            # Check if this team is valid and good
            if len(random_team) == 10 and total_credit <= 200:
                app.logger.info(f"Attempt {attempt}: Generated team with {total_credit} credits")
                if 180 <= total_credit <= 200:
                    best_team = random_team
                    best_credit = total_credit
                    app.logger.info(f"Perfect team found with {total_credit} credits!")
                    break  # Perfect team found
                elif total_credit <= 200 and (best_team is None or abs(total_credit - 190) < abs(best_credit - 190)):
                    best_team = random_team
                    best_credit = total_credit
            elif len(random_team) == 10:
                app.logger.warning(f"Attempt {attempt}: Team exceeds limit! Credits: {total_credit}/200")
        
        # Use best team found or fallback
        if not best_team or len(best_team) < 10:
            app.logger.warning("Using fallback algorithm - main loop failed")
            # Fallback: pick low-credit players to ensure we don't exceed 200
            sorted_by_credit = sorted([p for p in available_players], key=lambda x: x['credit'])
            random_team = []
            total_credit = 0
            for player in sorted_by_credit:
                if len(random_team) < 10 and total_credit + player['credit'] <= 200:
                    random_team.append(player)
                    total_credit += player['credit']
                if len(random_team) == 10:
                    break
            app.logger.info(f"Fallback team created with {total_credit} credits")
        else:
            random_team = best_team
            total_credit = best_credit
            app.logger.info(f"Using best team with {total_credit} credits")
        
        # Final validation
        final_total = sum(p['credit'] for p in random_team)
        app.logger.info(f"Final team: {len(random_team)} players, Total credit: {final_total}")
        app.logger.info(f"Team credits breakdown: {[(p['name'], p['credit']) for p in random_team]}")
        
        if final_total > 200:
            app.logger.error(f"ERROR: Final team exceeds 200 credits! Total: {final_total}")
        
        random_team_names = [p['name'] for p in random_team]
        session['opponent_team'] = random_team_names
        
        return jsonify({
            'success': True, 
            'team': random_team_names,
            'players': random_team,
            'total_credit': final_total  # Use recalculated total
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/logout')
def logout():
    """Clear session and logout"""
    session.clear()
    return redirect(url_for('index'))


@app.route('/players')
def nba_players():
    """NBA Players database page"""
    return render_template('players.html', 
                           seasons=data_manager.available_seasons, 
                           current_season=data_manager.current_season)


@app.route('/demo')
def demo_mode():
    """Demo mode - Test features without Yahoo Fantasy League"""
    try:
        # Get all players for demo mode
        all_players = data_manager.get_all_nba_players(season='2024-25', min_games=20)
        
        return render_template('demo.html', 
                             all_players=all_players,
                             season=data_manager.current_season)
    except Exception as e:
        app.logger.error(f"Error loading demo mode: {e}")
        return render_template('error.html', error=str(e))


@app.route('/demo/matchup')
def demo_matchup():
    """Demo mode matchup simulator"""
    try:
        # Get all players for roster building
        all_players = data_manager.get_all_nba_players(season='2024-25', min_games=20)
        
        # Get user's team from session
        my_team = session.get('my_team', [])
        opponent_team = session.get('opponent_team', [])
        
        # Get full player data for selected teams
        my_roster = [p for p in all_players if p['name'] in my_team] if my_team else []
        opponent_roster = [p for p in all_players if p['name'] in opponent_team] if opponent_team else []
        
        # Calculate total credits for both teams
        my_team_credit = 0
        for player in my_roster:
            credit = draft_assistant.calculate_player_credit(player.get('stats', {}), player.get('minutes', 0))
            my_team_credit += credit
        
        opponent_team_credit = 0
        for player in opponent_roster:
            stats = player.get('stats', {})
            credit = draft_assistant.calculate_player_credit(stats, player.get('minutes', 0))
            opponent_team_credit += credit
        
        # Sort both rosters by position
        my_roster = sort_roster_by_position(my_roster)
        opponent_roster = sort_roster_by_position(opponent_roster)
        
        # Run simulation only if both teams are set
        simulation_results = None
        if my_roster and opponent_roster:
            simulation_results = matchup_simulator.simulate_matchup(my_roster, opponent_roster)
        
        return render_template('demo_matchup.html', 
                             all_players=all_players,
                             my_roster=my_roster,
                             opponent_roster=opponent_roster,
                             simulation=simulation_results,
                             my_team_credit=my_team_credit,
                             opponent_team_credit=opponent_team_credit,
                             season=data_manager.current_season)
    except Exception as e:
        app.logger.error(f"Error loading demo matchup: {e}")
        return render_template('error.html', error=f"Matchup simulation error: {str(e)}")


@app.route('/demo/recommendations')
def demo_recommendations():
    """Demo mode recommendations"""
    try:
        # Get all players for recommendations
        all_players = data_manager.get_all_nba_players(season='2024-25', min_games=20)
        
        # Get user's team from session
        my_team = session.get('my_team', [])
        total_credit = session.get('total_credit', 0)
        remaining_credit = 200 - total_credit
        
        if not my_team:
            # No team selected
            return render_template('demo_recommendations.html', 
                                 recommendations=[],
                                 current_roster=[],
                                 no_team=True,
                                 season=data_manager.current_season,
                                 total_credit=total_credit,
                                 remaining_credit=remaining_credit)
        
        # Get user's roster
        current_roster = [p for p in all_players if p['name'] in my_team]
        
        # Get available free agents (players not on user's team)
        free_agents = [p for p in all_players if p['name'] not in my_team]
        
        # Get recommendations with credit constraint (show up to 100 recommendations)
        recommendations = recommendation_engine.get_recommendations_for_roster(
            current_roster, free_agents, all_players, max_recommendations=100, remaining_credit=remaining_credit
        )
        
        return render_template('demo_recommendations.html', 
                             recommendations=recommendations,
                             current_roster=current_roster,
                             season=data_manager.current_season,
                             no_team=False,
                             total_credit=total_credit,
                             remaining_credit=remaining_credit)
    except Exception as e:
        app.logger.error(f"Error loading demo recommendations: {e}")
        return render_template('error.html', error=f"Recommendation error: {str(e)}")


def auto_update_stats():
    """Automatically update stats on startup if data is old or missing"""
    try:
        from services.nba_scraper import NBAStatsScraper
        from datetime import datetime, timedelta
        import subprocess
        from pathlib import Path
        from bs4 import BeautifulSoup
        
        scraper = NBAStatsScraper()
        current_season = 2026  # 2025-26 season
        
        # Check if we need to update
        session = scraper.Session()
        try:
            from services.nba_scraper import PlayerStats
            from sqlalchemy import func
            
            # Get count and last update time
            count = session.query(func.count(PlayerStats.id)).filter(
                PlayerStats.season == current_season
            ).scalar()
            
            last_update = session.query(func.max(PlayerStats.updated_at)).filter(
                PlayerStats.season == current_season
            ).scalar()
            
            # Decide if update is needed
            needs_update = False
            if count == 0:
                print(f"📊 No data found for season {current_season}. Updating...")
                needs_update = True
            elif last_update and (datetime.now() - last_update) > timedelta(days=1):
                print(f"📊 Data is older than 1 day. Updating...")
                needs_update = True
            else:
                print(f"✓ Stats are up to date ({count} players, last update: {last_update})")
            
            if not needs_update:
                return
            
            # Perform update
            print(f"\n🔄 Auto-updating stats for season {current_season}...")
            
            temp_dir = Path('temp')
            temp_dir.mkdir(exist_ok=True)
            html_file = temp_dir / f'nba_{current_season}_totals.html'
            
            # Download using PowerShell
            ps_script = f'''
$url = "https://www.basketball-reference.com/leagues/NBA_{current_season}_totals.html"
$headers = @{{
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    "Accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}}
$response = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing
$htmlBytes = $response.RawContentStream.ToArray()
$htmlText = [System.Text.Encoding]::UTF8.GetString($htmlBytes)
$htmlStart = $htmlText.IndexOf('<!DOCTYPE')
if ($htmlStart -eq -1) {{ $htmlStart = $htmlText.IndexOf('<html') }}
if ($htmlStart -gt 0) {{ $htmlText = $htmlText.Substring($htmlStart) }}
[System.IO.File]::WriteAllText("{html_file.absolute()}", $htmlText, [System.Text.Encoding]::UTF8)
'''
            
            result = subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0 or not html_file.exists():
                print(f"⚠️  Auto-update failed: Could not download data")
                return
            
            # Parse and save
            with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')
            df = scraper.parse_player_stats(soup, current_season)
            
            if not df.empty:
                df = scraper.handle_duplicates(df)
                scraper.save_to_csv(df, current_season)
                count = scraper.save_to_database(df, current_season)
                print(f"✓ Auto-update complete: {count} players imported for season {current_season}")
                
                # Clear cache
                data_manager.season_players_cache.clear()
            
            # Cleanup
            try:
                html_file.unlink()
                if temp_dir.exists() and not any(temp_dir.iterdir()):
                    temp_dir.rmdir()
            except:
                pass
                
        finally:
            session.close()
            
    except Exception as e:
        print(f"⚠️  Auto-update error: {e}")
        # Don't fail the app startup if auto-update fails


if __name__ == '__main__':
    # Create frontend templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Auto-update stats on startup (only in main process, not reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        auto_update_stats()
    
    # SSL Configuration with mkcert (trusted local certificates)
    ssl_cert_path = os.path.join('ssl', 'localhost.pem')
    ssl_key_path = os.path.join('ssl', 'localhost-key.pem')
    
    # Check if SSL certificates exist
    if os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        ssl_context = (ssl_cert_path, ssl_key_path)
        app.logger.info("🔒 Running with trusted SSL certificates (mkcert)")
    else:
        # Fallback to adhoc if certificates don't exist
        ssl_context = 'adhoc'
        app.logger.warning("⚠️ SSL certificates not found! Using self-signed (adhoc) - Browser will show warnings")
        app.logger.warning("💡 Run 'mkcert localhost 127.0.0.1' in project root to generate trusted certificates")
    
    # Run with SSL for Yahoo OAuth
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        ssl_context=ssl_context
    )