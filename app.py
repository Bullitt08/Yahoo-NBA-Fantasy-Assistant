"""
Yahoo NBA Fantasy Assistant - Main Flask Application
"""
import sys
import io

# Fix emoji/unicode output on Windows terminals (e.g. Turkish cp1254)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask, render_template, session, redirect, url_for, request, jsonify
import os
from dotenv import load_dotenv

from auth import YahooAuth
from data import DataManager
from draft import DraftAssistant
from simulation import MatchupSimulator
from recommendation import RecommendationEngine
from season_config import sort_seasons_descending, season_to_year
from routes.nba_routes import nba_bp
from yahoo_integration.routes import yahoo_bp

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Security & Session Configuration
secret_key = os.getenv('FLASK_SECRET_KEY')
if not secret_key:
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError("FLASK_SECRET_KEY environment variable must be set in production mode!")
    secret_key = 'dev-key-change-in-production'

app.secret_key = secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=(os.getenv('FLASK_ENV') == 'production' or os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true')
)

@app.after_request
def set_security_headers(response):
    """Set standard HTTP security headers"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

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


@app.context_processor
def inject_season_context():
    available = sort_seasons_descending(data_manager.available_seasons)
    current = data_manager.current_season
    selected = request.args.get('season') or session.get('selected_season') or current
    mode = request.args.get('mode') or session.get('selected_mode') or 'per_game'
    return {
        'available_seasons': available,
        'current_nba_season': current,
        'selected_season': selected,
        'current_mode': mode,
        'mode': mode
    }


@app.route('/')
def index():
    """Main dashboard page - Yahoo Fantasy League focused"""
    try:
        # Get season from query parameter or default to current season
        season = request.args.get('season', data_manager.current_season)
        
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
            # Use current season data for player stats even in yahoo-matchup mode
            actual_season = data_manager.current_season
        
        mode = request.args.get('mode') or session.get('selected_mode') or 'per_game'
        session['selected_mode'] = mode
        
        # Get real stats from database - all players
        min_games = 0 if actual_season in [data_manager.current_season, 'yahoo-matchup'] else 1
        all_players = data_manager.get_all_nba_players(season=actual_season, min_games=min_games)
        
        # Get top performers (filter players with at least 20 games for accurate stats)
        qualified_players = all_players if actual_season in [data_manager.current_season, 'yahoo-matchup'] else [p for p in all_players if p.get('games_played', 0) >= 20]
        
        if mode == 'total':
            top_scorers = sorted(
                qualified_players,
                key=lambda x: x.get('total_stats', {}).get('points', (x.get('stats', {}).get('points', 0) * x.get('games_played', 0))) or 0,
                reverse=True
            )[:10]
            top_rebounders = sorted(
                qualified_players,
                key=lambda x: x.get('total_stats', {}).get('rebounds', (x.get('stats', {}).get('rebounds', 0) * x.get('games_played', 0))) or 0,
                reverse=True
            )[:10]
            top_assisters = sorted(
                qualified_players,
                key=lambda x: x.get('total_stats', {}).get('assists', (x.get('stats', {}).get('assists', 0) * x.get('games_played', 0))) or 0,
                reverse=True
            )[:10]
        else:
            top_scorers = sorted(qualified_players, key=lambda x: x['stats'].get('points', 0) or 0, reverse=True)[:10]
            top_rebounders = sorted(qualified_players, key=lambda x: x['stats'].get('rebounds', 0) or 0, reverse=True)[:10]
            top_assisters = sorted(qualified_players, key=lambda x: x['stats'].get('assists', 0) or 0, reverse=True)[:10]
        
        stats_summary = {
            'total_players': len(all_players),
            'current_season': season,
            'available_seasons': data_manager.available_seasons,
            'top_scorers': top_scorers,
            'top_rebounders': top_rebounders,
            'top_assisters': top_assisters,
            'mode': mode
        }
        
        # Clear demo session credits if not in draft mode, but preserve draft assistant team
        session.pop('opponent_team', None)
        session.pop('team_credits', None)
        
        # Get user's team - check Yahoo team first, then draft assistant team
        my_team = []
        yahoo_my_team = session.get('yahoo_my_team_roster', [])
        
        if yahoo_my_team:
            my_team = yahoo_my_team
        elif session.get('my_team'):
            my_team = [p['name'] if isinstance(p, dict) else str(p) for p in session.get('my_team', [])]
        
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
                             mode=mode,
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
        # Get season from query parameter or default to current season
        season = request.args.get('season', data_manager.current_season)
        strategy = request.args.get('strategy', 'balanced')
        mode = request.args.get('mode') or session.get('selected_mode') or 'per_game'
        session['selected_mode'] = mode
        sort_cat = request.args.get('sort_cat') or request.args.get('sort_category')
        sort_dir = request.args.get('sort_dir') or request.args.get('sort_direction', 'desc')
        categories_str = request.args.get('categories', '')
        target_categories = [c.strip().upper() for c in categories_str.split(',') if c.strip()] if categories_str else None
        
        # Load league auction values from session if available
        league_auction_values = session.get('league_auction_values', {})
        if league_auction_values:
            draft_assistant.set_league_auction_values(league_auction_values)
        
        # Get all draft recommendations with selected season, strategy, mode, and category sort
        rankings = draft_assistant.get_draft_rankings(
            top_n=None,
            season=season,
            strategy=strategy,
            target_categories=target_categories,
            mode=mode,
            sort_category=sort_cat,
            sort_direction=sort_dir
        )
        
        # Get position-specific rankings
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        position_rankings = {}
        for pos in positions:
            position_rankings[pos] = [p for p in rankings if pos in p.get('position', '')][:20]
        
        # Get user's credit info
        my_team = session.get('my_team', [])
        total_credit = sum(p.get('credit', 0) for p in my_team) if my_team else 0
        session['total_credit'] = total_credit
        remaining_credit = 200 - total_credit
        
        # Dynamic relative season weights
        from season_config import get_relative_season_weights
        season_weights = get_relative_season_weights(season)
        
        return render_template('draft.html', 
                             rankings=rankings,
                             position_rankings=position_rankings,
                             total_players=len(rankings),
                             season=season,
                             strategy=strategy,
                             mode=mode,
                             sort_cat=sort_cat,
                             sort_dir=sort_dir,
                             target_categories=target_categories or [],
                             season_weights=season_weights,
                             my_team=my_team,
                             total_credit=total_credit,
                             remaining_credit=remaining_credit,
                             league_auction_values=league_auction_values)
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
    original_season = data_manager.current_season
    try:
        # Determine season: query param > session draft/matchup season > data_manager.current_season
        season = request.args.get('season')
        if not season:
            season = session.get('matchup_season') or session.get('draft_season') or data_manager.current_season
        
        # Clear opponent session data only if requested, preserve draft team
        session.pop('opponent_team', None)
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
            actual_season = data_manager.current_season
        
        # Temporarily set data_manager season for simulation
        data_manager.current_season = actual_season
        
        # Get all players for roster building (min_games=0 so no players are excluded)
        all_players = data_manager.get_all_nba_players(season=actual_season, min_games=0)
        
        # If requested season has no real players (e.g. empty future season), fallback to populated season
        if not all_players or len(all_players) <= 5:
            populated_season = (getattr(data_manager, '_discovered_seasons', None) or ['2025-26', '2024-25'])[0]
            if actual_season != populated_season:
                app.logger.info(f"[MATCHUP] Season {actual_season} has only {len(all_players)} players, falling back to {populated_season}")
                actual_season = populated_season
                data_manager.current_season = actual_season
                all_players = data_manager.get_all_nba_players(season=actual_season, min_games=0)
        
        # Get Yahoo teams or draft assistant team
        yahoo_my_team = session.get('yahoo_my_team_roster', [])
        yahoo_opponent_team = session.get('yahoo_opponent_team_roster', [])
        
        app.logger.info(f"[MATCHUP] My team roster: {len(yahoo_my_team)} players - {yahoo_my_team}")
        app.logger.info(f"[MATCHUP] Opponent roster: {len(yahoo_opponent_team)} players - {yahoo_opponent_team}")
        
        # Robust player resolver with case-insensitivity, suffix normalization, and session fallback
        import re
        def strip_suffix(n):
            return re.sub(r'\b(jr\.?|sr\.?|ii|iii|iv)\b', '', str(n).lower()).strip()
        
        def resolve_roster(team_names, is_my_team=False):
            if not team_names:
                return []
            
            exact_map = {p['name'].strip().lower(): p for p in all_players}
            suffix_map = {strip_suffix(p['name']): p for p in all_players}
            
            # Map of full player profiles from session draft team if available
            saved_team_map = {}
            if is_my_team and session.get('my_team'):
                for sp in session.get('my_team'):
                    if isinstance(sp, dict) and sp.get('name'):
                        saved_team_map[sp['name'].strip().lower()] = sp
                        saved_team_map[strip_suffix(sp['name'])] = sp
            
            resolved = []
            for item in team_names:
                name = item if isinstance(item, str) else (item.get('name') if isinstance(item, dict) else str(item))
                if not name:
                    continue
                norm = name.strip().lower()
                clean = strip_suffix(name)
                
                matched = exact_map.get(norm) or suffix_map.get(clean)
                
                if not matched and is_my_team:
                    matched = saved_team_map.get(norm) or saved_team_map.get(clean)
                    
                if not matched:
                    # Search fallback seasons in database
                    for fb in (getattr(data_manager, '_discovered_seasons', None) or ['2025-26', '2024-25', '2023-24']):
                        if fb != actual_season:
                            fb_pool = data_manager.get_all_nba_players(season=fb, min_games=0)
                            for fp in fb_pool:
                                if fp['name'].strip().lower() == norm or strip_suffix(fp['name']) == clean:
                                    matched = fp
                                    break
                            if matched:
                                break
                                
                if matched:
                    resolved.append(dict(matched))
                elif isinstance(item, dict) and item.get('name'):
                    resolved.append(dict(item))
                else:
                    resolved.append({
                        'name': name.strip(),
                        'position': 'UTIL',
                        'team': 'NBA',
                        'stats': {'points': 12.0, 'rebounds': 4.5, 'assists': 2.5, 'steals': 0.8, 'blocks': 0.5, 'fg3m': 1.2, 'fg_percentage': 0.46, 'ft_percentage': 0.78, 'turnovers': 1.5}
                    })
            return resolved

        my_roster = resolve_roster(yahoo_my_team, is_my_team=True)
        opponent_roster = resolve_roster(yahoo_opponent_team, is_my_team=False)
        
        app.logger.info(f"[MATCHUP] My roster matched: {len(my_roster)} players")
        app.logger.info(f"[MATCHUP] Opponent matched: {len(opponent_roster)} players")
        
        # Assign slots and sort both rosters in standard roster slot order
        if my_roster:
            my_roster = draft_assistant._assign_roster_slots(my_roster, len(my_roster))
        if opponent_roster:
            opponent_roster = draft_assistant._assign_roster_slots(opponent_roster, len(opponent_roster))
        
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
                             season=actual_season,
                             available_seasons=data_manager.available_seasons,
                             draft_assistant_roster=session.get('draft_assistant_roster', []),
                             yahoo_my_team_name=session.get('yahoo_my_team_name', 'My Team'),
                             yahoo_matchup_stats=yahoo_matchup_stats,
                             yahoo_my_team_stats=yahoo_my_team_stats,
                             yahoo_opponent_team_stats=yahoo_opponent_team_stats,
                             yahoo_current_week=yahoo_current_week)
    except Exception as e:
        data_manager.current_season = original_season
        app.logger.error(f"Error loading matchup page: {e}")
        return render_template('error.html', error=f"Matchup simulation error: {str(e)}")


@app.route('/recommendations')
def recommendations_page():
    """Roster recommendations page with Yahoo Fantasy team analysis"""
    try:
        # Get season from query parameter or default to current season
        season = request.args.get('season', data_manager.current_season)
        
        # Clear demo session data
        session.pop('my_team', None)
        session.pop('total_credit', None)
        session.pop('team_credits', None)
        
        # Handle yahoo-matchup mode - use current season data for player stats
        actual_season = season
        if season == 'yahoo-matchup':
            actual_season = data_manager.current_season
            app.logger.info(f"[RECOMMENDATIONS] Yahoo Matchup Stats mode active, using {actual_season} data")
        
        # Get all players for recommendations
        min_games = 0 if season in [data_manager.current_season, 'yahoo-matchup'] else 20
        all_players = data_manager.get_all_nba_players(season=actual_season, min_games=min_games)
        
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
        season = request.args.get('season', data_manager.current_season)
        analysis = draft_assistant.build_player_analysis(player_id, season=season)
        if not analysis:
            return jsonify({'success': False, 'error': 'Player not found'}), 404
        return jsonify({'success': True, 'analysis': analysis})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/compare', methods=['POST'])
def api_draft_compare():
    """API endpoint to compare multiple players"""
    try:
        data = request.get_json() or {}
        player_ids = data.get('player_ids', [])
        season = data.get('season') or request.args.get('season', data_manager.current_season)
        
        if not player_ids or len(player_ids) < 2:
            return jsonify({'success': False, 'error': 'Please select at least 2 players'}), 400
        
        if len(player_ids) > 5:
            return jsonify({'success': False, 'error': 'Maximum 5 players allowed'}), 400
        
        comparisons = []
        for player_id in player_ids:
            analysis = draft_assistant.build_player_analysis(player_id, season=season)
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
    """API endpoint to get draft rankings with credits, strategy, mode, and category sort support"""
    try:
        season = request.args.get('season', data_manager.current_season)
        strategy = request.args.get('strategy', 'balanced')
        mode = request.args.get('mode', 'per_game')
        sort_cat = request.args.get('sort_cat') or request.args.get('sort_category')
        sort_dir = request.args.get('sort_dir') or request.args.get('sort_direction', 'desc')
        categories_str = request.args.get('categories', '')
        target_categories = [c.strip().upper() for c in categories_str.split(',') if c.strip()] if categories_str else None
        
        league_auction_values = session.get('league_auction_values', {})
        if league_auction_values:
            draft_assistant.set_league_auction_values(league_auction_values)
            
        rankings = draft_assistant.get_draft_rankings(
            top_n=None,
            season=season,
            strategy=strategy,
            target_categories=target_categories,
            mode=mode,
            sort_category=sort_cat,
            sort_direction=sort_dir
        )
        return jsonify({
            'success': True,
            'rankings': rankings,
            'count': len(rankings),
            'season': season,
            'strategy': strategy,
            'mode': mode,
            'sort_cat': sort_cat,
            'sort_dir': sort_dir
        })
    except Exception as e:
        app.logger.error(f"Error fetching rankings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/optimize', methods=['POST'])
def api_draft_optimize():
    """Run Monte Carlo draft roster optimization under strategy and budget constraints"""
    try:
        data = request.get_json() or {}
        budget = float(data.get('budget', 200.0))
        roster_size = int(data.get('roster_size', 15))
        strategy = data.get('strategy', 'balanced')
        mode = data.get('mode') or session.get('selected_mode') or 'per_game'
        target_categories = data.get('target_categories')
        existing_roster = data.get('existing_roster') or session.get('my_team', [])
        num_simulations = int(data.get('num_simulations', 150))
        season = data.get('season', data_manager.current_season)
        
        league_auction_values = session.get('league_auction_values', {})
        if league_auction_values:
            draft_assistant.set_league_auction_values(league_auction_values)
            
        objective_weights = data.get('objective_weights')
        result = draft_assistant.optimize_draft_roster(
            budget=budget,
            roster_size=roster_size,
            strategy=strategy,
            target_categories=target_categories,
            existing_roster=existing_roster,
            num_simulations=num_simulations,
            season=season,
            mode=mode,
            objective_weights=objective_weights
        )
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in draft optimization: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/auction-values', methods=['GET', 'POST'])
def api_draft_auction_values():
    """Get or update league-specific auction values"""
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            prices = data.get('prices', {})
            current_prices = session.get('league_auction_values', {})
            current_prices.update(prices)
            session['league_auction_values'] = current_prices
            draft_assistant.set_league_auction_values(current_prices)
            return jsonify({'success': True, 'prices': current_prices})
        else:
            current_prices = session.get('league_auction_values', {})
            return jsonify({'success': True, 'prices': current_prices})
    except Exception as e:
        app.logger.error(f"Error handling auction values: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/auction-values/reset-player', methods=['POST'])
def api_draft_reset_player_auction_value():
    """Reset a single player's league auction override back to model value"""
    try:
        data = request.get_json() or {}
        player_name = data.get('player_name') or data.get('name')
        if not player_name:
            return jsonify({'success': False, 'error': 'Player name required'}), 400
            
        current_prices = session.get('league_auction_values', {})
        draft_assistant.reset_league_auction_value(player_name)
        keys_to_remove = [k for k in current_prices if str(k).strip().lower() == str(player_name).strip().lower()]
        for k in keys_to_remove:
            current_prices.pop(k, None)
        session['league_auction_values'] = current_prices
        return jsonify({'success': True, 'player_name': player_name, 'prices': current_prices})
    except Exception as e:
        app.logger.error(f"Error resetting player auction price: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/auction-values/reset-all', methods=['POST'])
def api_draft_reset_all_auction_values():
    """Reset all league auction overrides back to model values"""
    try:
        session.pop('league_auction_values', None)
        draft_assistant.clear_all_league_auction_values()
        return jsonify({'success': True, 'prices': {}})
    except Exception as e:
        app.logger.error(f"Error resetting all auction prices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/my-team', methods=['GET'])
def api_draft_get_my_team():
    """Get current draft assistant team and credit status"""
    my_team = session.get('my_team', [])
    total_credit = sum(p.get('credit', 0) for p in my_team) if my_team else 0
    remaining_credit = 200 - total_credit
    return jsonify({
        'success': True,
        'team': my_team,
        'total_credit': total_credit,
        'remaining_credit': remaining_credit
    })


@app.route('/api/draft/add-player', methods=['POST'])
def api_draft_add_player():
    """Add a player to the user's draft team with credit and roster size validation"""
    try:
        data = request.get_json() or {}
        player_name = data.get('name') or data.get('player_name')
        player_id = data.get('player_id')
        player_credit = int(float(data.get('credit', 1)))
        player_pos = data.get('position', 'UTIL')
        player_team = data.get('team', '')
        
        if not player_name:
            return jsonify({'success': False, 'error': 'Player name required'}), 400
            
        my_team = session.get('my_team', [])
        
        # Check if already added
        if any(p.get('name') == player_name for p in my_team):
            return jsonify({'success': False, 'error': f"{player_name} is already on your team."}), 400
            
        # Max roster size check (15 players)
        if len(my_team) >= 15:
            return jsonify({'success': False, 'error': 'Roster is full (maximum 15 players).'}), 400
            
        # Credit budget check
        current_used = sum(p.get('credit', 0) for p in my_team)
        if current_used + player_credit > 200:
            return jsonify({'success': False, 'error': f"Insufficient budget! Player costs ${player_credit}, but only ${200 - current_used} remaining."}), 400
            
        new_player = {
            'player_id': player_id,
            'name': player_name,
            'position': player_pos,
            'team': player_team,
            'credit': player_credit
        }
        
        # Enrich new player with statistical profile if available
        if player_id or player_name:
            analysis = draft_assistant.build_player_analysis(player_id or player_name)
            if analysis:
                new_player['weighted_stats'] = analysis.get('weighted_stats', {})
                new_player['stats'] = analysis.get('current_season_stats', {})
                new_player['total_stats'] = analysis.get('total_stats', {})
        
        my_team.append(new_player)
        total_credit = sum(p.get('credit', 0) for p in my_team)
        remaining_credit = 200 - total_credit
        
        session['my_team'] = my_team
        session['total_credit'] = total_credit
        session['draft_assistant_roster'] = [p['name'] for p in my_team]
        
        return jsonify({
            'success': True,
            'team': my_team,
            'total_credit': total_credit,
            'remaining_credit': remaining_credit
        })
    except Exception as e:
        app.logger.error(f"Error adding player to draft team: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/remove-player', methods=['POST'])
def api_draft_remove_player():
    """Remove a player from the user's draft team"""
    try:
        data = request.get_json() or {}
        player_name = data.get('name') or data.get('player_name')
        if not player_name:
            return jsonify({'success': False, 'error': 'Player name required'}), 400
            
        my_team = session.get('my_team', [])
        my_team = [p for p in my_team if p.get('name') != player_name]
        total_credit = sum(p.get('credit', 0) for p in my_team)
        remaining_credit = 200 - total_credit
        
        session['my_team'] = my_team
        session['total_credit'] = total_credit
        session['draft_assistant_roster'] = [p['name'] for p in my_team]
        
        return jsonify({
            'success': True,
            'team': my_team,
            'total_credit': total_credit,
            'remaining_credit': remaining_credit
        })
    except Exception as e:
        app.logger.error(f"Error removing player from draft team: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/clear-team', methods=['POST'])
def api_draft_clear_team():
    """Clear all players from user's draft team"""
    try:
        session['my_team'] = []
        session['total_credit'] = 0
        session['draft_assistant_roster'] = []
        return jsonify({'success': True, 'team': [], 'total_credit': 0, 'remaining_credit': 200})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/draft/save-draft-roster', methods=['POST'])
def api_draft_save_draft_roster():
    """Save the current draft roster so it can be selected as 'My Team' in Matchup Simulator"""
    try:
        my_team = session.get('my_team', [])
        player_names = [p['name'] for p in my_team] if my_team else []
        if not player_names:
            return jsonify({'success': False, 'error': 'Draft team is empty. Please add players first.'}), 400
            
        session['draft_assistant_roster'] = player_names
        # Also sync to active My Team for matchup simulator
        session['yahoo_my_team_roster'] = player_names
        session['yahoo_my_team_name'] = "My Draft Team"
        session['yahoo_my_team_logo'] = ""
        
        return jsonify({
            'success': True,
            'team_name': 'My Draft Team',
            'player_count': len(player_names),
            'players': player_names
        })
    except Exception as e:
        app.logger.error(f"Error saving draft roster: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/matchup/select-draft-team', methods=['POST'])
def api_matchup_select_draft_team():
    """Activate the saved draft roster as 'My Team' for Matchup Simulator"""
    try:
        draft_names = session.get('draft_assistant_roster', [])
        if not draft_names and session.get('my_team'):
            draft_names = [p['name'] if isinstance(p, dict) else str(p) for p in session.get('my_team', [])]
            session['draft_assistant_roster'] = draft_names
            
        if not draft_names:
            return jsonify({'success': False, 'error': 'No draft team found. Build one in Draft Assistant first.'}), 400
            
        session['yahoo_my_team_roster'] = draft_names
        session['yahoo_my_team_name'] = "My Draft Team"
        session['yahoo_my_team_logo'] = ""
        season = session.get('draft_season') or session.get('matchup_season') or data_manager.current_season
        session['matchup_season'] = season
        return jsonify({
            'success': True,
            'team_name': 'My Draft Team',
            'players': draft_names,
            'season': season
        })
    except Exception as e:
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
        season = data.get('season') or data_manager.current_season
        all_players = data_manager.get_all_nba_players(season=season, min_games=0)
        rankings = draft_assistant.get_draft_rankings(top_n=None, season=season)
        
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
        session['yahoo_opponent_team_roster'] = team
        session['yahoo_opponent_team_name'] = 'Opponent Team'
        session['yahoo_opponent_is_manual'] = True
        if not team:
            session.pop('yahoo_opponent_team_stats', None)
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
    """Generate random opponent team (13 players with ~195-200 credits, position balanced, with marquee stars)"""
    try:
        import random
        season = data_manager.current_season
        all_players = data_manager.get_all_nba_players(season=season, min_games=0)
        if not all_players or len(all_players) <= 5:
            season = (getattr(data_manager, '_discovered_seasons', None) or ['2025-26', '2024-25'])[0]
            all_players = data_manager.get_all_nba_players(season=season, min_games=0)

        # Get full rankings to have accurate credits and stats
        rankings = draft_assistant.get_draft_rankings(top_n=None, season=season)
        if not rankings:
            rankings = all_players

        # Filter out user's players
        user_players = set()
        for p in session.get('my_team', []) + session.get('yahoo_my_team_roster', []):
            name = p if isinstance(p, str) else (p.get('name') if isinstance(p, dict) else str(p))
            if name:
                user_players.add(name.strip().lower())

        candidates = [
            p for p in rankings 
            if p.get('name', '').strip().lower() not in user_players and (p.get('credit') or 0) >= 1
        ]

        def pos_matches(player_pos, target_slot):
            pos = (player_pos or '').upper()
            if target_slot in ['PG', 'SG', 'SF', 'PF', 'C']:
                return target_slot in pos
            if target_slot == 'G':
                return any(x in pos for x in ['PG', 'SG', 'G'])
            if target_slot == 'F':
                return any(x in pos for x in ['SF', 'PF', 'F'])
            return True  # UTIL or BN

        # Group into tiers for star prioritization
        superstars = [p for p in candidates if (p.get('credit') or 0) >= 55]       # Jokic, Doncic, Wemby, SGA
        elite_stars = [p for p in candidates if 45 <= (p.get('credit') or 0) < 55] # Edwards, Mitchell, Maxey, etc.
        all_stars = [p for p in candidates if 35 <= (p.get('credit') or 0) < 45]   # Durant, Brown, Sengun, Curry, etc.
        solid_players = [p for p in candidates if 15 <= (p.get('credit') or 0) < 35]
        role_players = [p for p in candidates if 5 <= (p.get('credit') or 0) < 15]
        bargains = [p for p in candidates if 1 <= (p.get('credit') or 0) < 5]

        # 13 standard slots: 10 starters + 3 bench
        slots = ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'C', 'UTIL', 'UTIL', 'BN', 'BN', 'BN']

        best_team = None
        best_credit = 0

        for attempt in range(500):
            # 1. Pick 1-2 Marquee Stars:
            style = random.choice([1, 2, 3, 4])
            selected_stars = []
            if style == 1 and superstars:
                mega = random.choice(superstars)
                solid = random.choice([p for p in solid_players if 20 <= (p.get('credit') or 0) <= 32]) if solid_players else None
                selected_stars = [mega] + ([solid] if solid else [])
            elif style == 2 and elite_stars and all_stars:
                selected_stars = [random.choice(elite_stars), random.choice(all_stars)]
            elif style == 3 and len(all_stars) >= 2:
                two_stars = random.sample(all_stars, 2)
                solid = random.choice([p for p in solid_players if 18 <= (p.get('credit') or 0) <= 28]) if solid_players else None
                selected_stars = two_stars + ([solid] if solid else [])
            elif style == 4 and superstars and all_stars:
                selected_stars = [random.choice(superstars), random.choice(all_stars)]
            else:
                top_pool = [p for p in candidates if (p.get('credit') or 0) >= 38]
                if top_pool:
                    selected_stars = [random.choice(top_pool)]

            team = list(selected_stars)
            used_names = set(p['name'] for p in team)
            current_credit = sum(p.get('credit', 0) for p in team)

            remaining_slots_count = 13 - len(team)
            remaining_budget = 200 - current_credit

            if remaining_budget < remaining_slots_count:
                continue

            # Determine unfilled slots
            unfilled_slots = list(slots)
            for p in team:
                for s in unfilled_slots:
                    if pos_matches(p.get('position', ''), s):
                        unfilled_slots.remove(s)
                        break

            # Fill remaining slots
            valid = True
            for slot in list(unfilled_slots):
                rem_slots = len(unfilled_slots)
                max_c = remaining_budget - (rem_slots - 1)
                target_c = remaining_budget / rem_slots

                matching = [
                    p for p in candidates
                    if p['name'] not in used_names 
                    and pos_matches(p.get('position', ''), slot) 
                    and (p.get('credit') or 0) <= max_c
                ]
                if not matching:
                    valid = False
                    break

                matching.sort(key=lambda x: abs((x.get('credit') or 0) - target_c))
                top_pool = matching[:max(3, len(matching) // 4)]
                pick = random.choice(top_pool)

                team.append(pick)
                used_names.add(pick['name'])
                unfilled_slots.remove(slot)
                remaining_budget -= (pick.get('credit') or 0)

            if not valid or len(team) != 13:
                continue

            tot = sum(p.get('credit', 0) for p in team)

            # Optimization pass: Upgrade non-star players with leftover budget to maximize credit (up to 200)
            if tot < 200 and tot >= 180:
                diff = 200 - tot
                for i in range(len(team) - 1, -1, -1):
                    p = team[i]
                    if p in selected_stars:
                        continue
                    desired_c = (p.get('credit') or 0) + diff
                    upgrades = [
                        cand for cand in candidates
                        if cand['name'] not in used_names
                        and pos_matches(cand.get('position', ''), slots[i])
                        and (p.get('credit') or 0) < (cand.get('credit') or 0) <= desired_c
                    ]
                    if upgrades:
                        upgrades.sort(key=lambda x: x.get('credit', 0), reverse=True)
                        best_upgrade = upgrades[0]
                        used_names.remove(p['name'])
                        used_names.add(best_upgrade['name'])
                        team[i] = best_upgrade
                        tot = sum(x.get('credit', 0) for x in team)
                        diff = 200 - tot
                        if diff == 0:
                            break

            if 195 <= tot <= 200:
                best_team = team
                best_credit = tot
                break

            if tot <= 200 and tot > best_credit:
                best_team = team
                best_credit = tot

        if not best_team or len(best_team) != 13:
            # Fallback
            sorted_by_credit = sorted(candidates, key=lambda x: x.get('credit', 0), reverse=True)
            best_team = sorted_by_credit[:1]  # 1 star
            used = set(p['name'] for p in best_team)
            c_left = 200 - sum(p['credit'] for p in best_team)
            for p in sorted(candidates, key=lambda x: x.get('credit', 0)):
                if len(best_team) < 13 and p['name'] not in used and p['credit'] <= c_left - (13 - len(best_team) - 1):
                    best_team.append(p)
                    used.add(p['name'])
                    c_left -= p['credit']
                if len(best_team) == 13:
                    break
            best_credit = sum(p.get('credit', 0) for p in best_team)

        # Assign slots in standard order
        best_team = draft_assistant._assign_roster_slots(best_team, 13)
        random_team_names = [p['name'] for p in best_team]

        session['opponent_team'] = random_team_names
        session['yahoo_opponent_team_roster'] = random_team_names
        session['yahoo_opponent_team_name'] = 'Random Opponent'
        session['yahoo_opponent_is_manual'] = True
        session.pop('yahoo_opponent_team_stats', None)

        app.logger.info(f"Generated 13-player random opponent with {best_credit}/200 credits: {random_team_names}")

        return jsonify({
            'success': True,
            'team': random_team_names,
            'players': best_team,
            'total_credit': best_credit
        })
    except Exception as e:
        app.logger.error(f"Error generating random opponent: {e}")
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
        all_players = data_manager.get_all_nba_players(season=data_manager.current_season, min_games=0)
        
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
        all_players = data_manager.get_all_nba_players(season=data_manager.current_season, min_games=0)
        
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
        all_players = data_manager.get_all_nba_players(season=data_manager.current_season, min_games=0)
        
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
        team_credits_map = {item['name']: item['credit'] for item in session.get('team_credits', []) if isinstance(item, dict) and 'name' in item}
        for p in current_roster:
            if p['name'] in team_credits_map:
                p['credit'] = team_credits_map[p['name']]
            elif 'credit' not in p and draft_assistant:
                p['credit'] = draft_assistant.calculate_player_credit(p.get('stats', {}), p.get('minutes', 0))
        
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
    
    # Host, port and URL configuration
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    protocol = 'https' if ssl_context else 'http'
    site_url = f"{protocol}://{host}:{port}"
    alt_url = f"{protocol}://localhost:{port}" if host == '127.0.0.1' else None

    # Print website link prominently in terminal when server starts
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not debug_mode:
        print("\n" + "=" * 60, flush=True)
        print("  🏀 NBA Fantasy Assistant Başlatıldı!", flush=True)
        print(f"  🔗 Web Sitesi: {site_url}", flush=True)
        if alt_url:
            print(f"  🔗 Alternatif: {alt_url}", flush=True)
        print("=" * 60 + "\n", flush=True)

    # Run with SSL for Yahoo OAuth
    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        ssl_context=ssl_context
    )