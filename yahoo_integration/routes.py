"""
Yahoo Fantasy Basketball Integration Routes

Flask blueprint for handling Yahoo OAuth and fantasy data endpoints
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, flash
from typing import Dict, Optional
import os

from yahoo_integration import YahooFantasyClient, YahooDatabase
from yahoo_integration.player_matcher import PlayerMatcher
from yahoo_integration.config import YAHOO_REDIRECT_URI
from data import DataManager

# Create blueprint
yahoo_bp = Blueprint('yahoo', __name__, url_prefix='/yahoo')

# Initialize components
yahoo_client = YahooFantasyClient()
yahoo_db = YahooDatabase()
data_manager = DataManager()


def auto_load_user_team():
    """
    Automatically load user's fantasy team from Yahoo
    Finds the team managed by the logged-in user and loads it to session
    """
    try:
        token = session.get('yahoo_token')
        if not token:
            print("❌ No Yahoo token found in session")
            return False
        
        yahoo_client.set_token(token)
        user_guid = session.get('yahoo_user_guid', '')
        print(f"🔍 Searching teams for user GUID: {user_guid}")
        
        # Get current season leagues
        leagues = yahoo_client.get_user_leagues(season='2024-25')
        
        if not leagues:
            print("❌ No leagues found for 2024-25 season")
            return False
        
        print(f"✅ Found {len(leagues)} league(s)")
        
        # Find first league and get user's team
        for league in leagues:
            league_key = league.league_key
            print(f"📋 Checking league: {league.name} ({league_key})")
            
            if not league_key:
                continue
            
            # Get all teams in this league
            teams = yahoo_client.get_league_teams(league_key)
            
            if not teams:
                print(f"  ⚠️ No teams found in {league.name}")
                continue
            
            print(f"  ✅ Found {len(teams)} teams in {league.name}")
            
            # Find user's team (where user is manager)
            for team in teams:
                print(f"    🏀 Team: {team.name} (managers: {team.managers})")
                
                # Check if this team belongs to current user
                managers = team.managers or []
                is_user_team = False
                
                for manager in managers:
                    print(f"      👤 Manager GUID: {manager.get('guid')}, is_current_login: {manager.get('is_current_login')}")
                    # Match by GUID or check if user is current login
                    if manager.get('guid') == user_guid or manager.get('is_current_login', False):
                        is_user_team = True
                        print(f"      ✅ MATCH! This is user's team!")
                        break
                
                if is_user_team:
                    # Found user's team! Save basic info first
                    session['yahoo_league_name'] = league.name
                    session['yahoo_team_name'] = team.name
                    session['yahoo_team_logo'] = team.team_logo_url or ''
                    session['yahoo_my_team_logo'] = team.team_logo_url or ''
                    print(f"✅ Team info saved: {team.name} from {league.name}")
                    print(f"   Logo URL: {team.team_logo_url}")
                    
                    # Try to get roster
                    try:
                        print(f"    📥 Loading roster for {team.name}...")
                        roster = yahoo_client.get_team_roster(team.team_key)
                        player_names = [p.name for p in roster if p and p.name]
                        
                        if player_names:
                            session['yahoo_my_team_roster'] = player_names
                            session['show_yahoo_success'] = True  # Show success message
                            print(f"✅✅✅ Auto-loaded team: {team.name} from {league.name} ({len(player_names)} players)")
                            print(f"Players: {', '.join(player_names[:5])}...")
                            return True
                        else:
                            print(f"⚠️ No players found in roster, but team info saved")
                            session['yahoo_my_team_roster'] = []
                            session['show_yahoo_success'] = True
                            return True
                    except Exception as e:
                        print(f"❌ Error loading roster for team {team.team_key}: {e}")
                        import traceback
                        traceback.print_exc()
                        # Still return True since we have team info
                        session['yahoo_my_team_roster'] = []
                        session['show_yahoo_success'] = True
                        return True
        
        print("❌ No team found for current user")
        return False
    except Exception as e:
        print(f"❌ Error in auto_load_user_team: {e}")
        import traceback
        traceback.print_exc()
        return False


@yahoo_bp.route('/auth/login')
def yahoo_login():
    """
    Start Yahoo OAuth 2.0 login flow
    
    Returns user to Yahoo authorization page
    """
    try:
        authorization_url, state = yahoo_client.get_authorization_url()
        
        # Store state in session for security
        session['yahoo_oauth_state'] = state
        
        return redirect(authorization_url)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to initiate Yahoo login: {str(e)}'
        }), 500


@yahoo_bp.route('/auth/callback')
def yahoo_callback():
    """
    Handle Yahoo OAuth callback
    
    Exchanges authorization code for access token
    """
    try:
        print("=" * 80)
        print("🔔 YAHOO CALLBACK TRIGGERED!")
        print("=" * 80)
        
        # Get authorization response
        authorization_response = request.url
        print(f"📥 Authorization response URL: {authorization_response}")
        
        # Verify state (optional but recommended)
        state = request.args.get('state')
        session_state = session.get('yahoo_oauth_state')
        print(f"🔐 State verification - Request: {state}, Session: {session_state}")
        
        if state != session_state:
            print("❌ INVALID STATE!")
            return jsonify({
                'success': False,
                'error': 'Invalid OAuth state'
            }), 400
        
        print("✅ State verified!")
        
        # Exchange code for token
        print("🔄 Exchanging authorization code for token...")
        token = yahoo_client.fetch_token(authorization_response)
        print(f"✅ Token received! Expires at: {token.get('expires_at', 'unknown')}")
        
        # Store token in session
        session['yahoo_token'] = token
        session['yahoo_authenticated'] = True
        print("✅ Token stored in session")
        
        # Load user info
        print("👤 Loading user info...")
        yahoo_client.set_token(token)
        user_info = yahoo_client.get_user_info()
        if user_info:
            session['yahoo_user_guid'] = user_info.get('guid', '')
            session['yahoo_user_email'] = user_info.get('email', '')
            print(f"✅ User info loaded - GUID: {user_info.get('guid')}, Email: {user_info.get('email')}")
        else:
            print("⚠️ No user info returned")
        
        # Auto-load user's team
        print("\n" + "=" * 80)
        print("🚀 STARTING AUTO-LOAD USER TEAM")
        print("=" * 80)
        try:
            team_loaded = auto_load_user_team()
            if team_loaded:
                print("=" * 80)
                print("✅✅✅ TEAM LOADED SUCCESSFULLY!")
                print("=" * 80)
            else:
                print("=" * 80)
                print("⚠️⚠️⚠️ NO TEAM WAS LOADED")
                print("=" * 80)
        except Exception as e:
            print(f"❌ Error auto-loading team: {e}")
            import traceback
            traceback.print_exc()
        
        # Redirect to home page to show team
        print(f"🔄 Redirecting to index page...")
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"❌❌❌ CALLBACK ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'OAuth callback failed: {str(e)}'
        }), 500


@yahoo_bp.route('/auth/logout')
def yahoo_logout():
    """Logout from Yahoo Fantasy"""
    session.pop('yahoo_token', None)
    session.pop('yahoo_authenticated', None)
    session.pop('yahoo_oauth_state', None)
    session.pop('yahoo_team_name', None)
    session.pop('yahoo_team_logo', None)
    session.pop('yahoo_my_team_logo', None)
    session.pop('yahoo_my_team_name', None)
    session.pop('yahoo_my_team_roster', None)
    session.pop('yahoo_league_key', None)
    session.pop('yahoo_league_name', None)
    
    # Redirect to home page with success message
    from flask import redirect, url_for, flash
    flash('Successfully disconnected from Yahoo Fantasy', 'success')
    return redirect(url_for('index'))


@yahoo_bp.route('/auth/status')
def auth_status():
    """Check Yahoo authentication status"""
    authenticated = session.get('yahoo_authenticated', False)
    
    return jsonify({
        'authenticated': authenticated,
        'token_exists': 'yahoo_token' in session
    })


@yahoo_bp.route('/leagues')
def list_leagues():
    """
    Get user's Yahoo Fantasy Basketball leagues
    
    Query params:
    - season: Season year (default: 2024-25)
    - format: json or html (default: json)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated. Please login first.',
                'error_code': 'not_authenticated',
                'login_url': url_for('yahoo.yahoo_login', _external=True)
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get season from query params
        season = request.args.get('season', '2024-25')
        
        # Log attempt
        app = __import__('flask').current_app
        app.logger.info(f"Fetching leagues for season: {season}")
        app.logger.info(f"Token exists: {token is not None}")
        
        # Check token expiration before making request
        if token and 'expires_at' in token:
            import time
            if time.time() > (token['expires_at'] - 300):
                app.logger.info("Token expiring soon, will be auto-refreshed...")
        
        # First, get all available games for this user
        endpoint = '/users;use_login=1/games;game_codes=nba'
        try:
            xml_response = yahoo_client._make_request(endpoint)
            
            # Update session token if it was refreshed
            if yahoo_client.token != token:
                session['yahoo_token'] = yahoo_client.token
                app.logger.info("✅ Updated session with refreshed token")
        except Exception as req_error:
            if 'token' in str(req_error).lower():
                app.logger.error(f"Token error, clearing session: {req_error}")
                session.pop('yahoo_token', None)
                session.pop('yahoo_authenticated', None)
                raise Exception("token_expired_please_relogin")
            raise
        games_data = yahoo_client._parse_xml_to_dict(xml_response)
        
        # Extract all game_keys
        all_leagues = []
        try:
            users = games_data.get('users', {})
            user = users.get('user', {})
            games = user.get('games', {})
            game_list = games.get('game', [])
            
            if not isinstance(game_list, list):
                game_list = [game_list] if game_list else []
            
            # For each game, fetch leagues
            for game in game_list:
                game_key = game.get('game_key')
                if game_key:
                    leagues_endpoint = f'/users;use_login=1/games;game_keys={game_key}/leagues'
                    leagues_xml = yahoo_client._make_request(leagues_endpoint)
                    leagues_data = yahoo_client._parse_xml_to_dict(leagues_xml)
                    
                    # Parse leagues
                    try:
                        l_users = leagues_data.get('users', {})
                        l_user = l_users.get('user', {})
                        l_games = l_user.get('games', {})
                        l_game = l_games.get('game', {})
                        l_leagues_data = l_game.get('leagues', {})
                        league_list = l_leagues_data.get('league', [])
                        
                        if league_list and league_list is not None:
                            if not isinstance(league_list, list):
                                league_list = [league_list]
                            
                            for league_data in league_list:
                                from yahoo_integration.yahoo_client import YahooFantasyClient
                                temp_client = YahooFantasyClient()
                                league = temp_client._parse_league(league_data)
                                all_leagues.append(league)
                    except:
                        pass  # No leagues in this game
        except Exception as e:
            app.logger.error(f"Error fetching games: {e}")
        
        app.logger.info(f"Found {len(all_leagues)} total leagues across all games")
        
        # Save to database
        for league in all_leagues:
            league_dict = {
                'league_key': league.league_key,
                'league_id': league.league_id,
                'name': league.name,
                'season': league.season,
                'game_code': league.game_code,
                'num_teams': league.num_teams,
                'scoring_type': league.scoring_type,
                'draft_status': league.draft_status,
                'current_week': league.current_week,
                'start_week': league.start_week,
                'end_week': league.end_week,
                'start_date': league.start_date,
                'end_date': league.end_date,
                'is_finished': league.is_finished,
                'url': league.url,
            }
            yahoo_db.save_league(league_dict)
        
        # Return format - default to JSON for AJAX requests
        format_type = request.args.get('format', 'json')
        
        if format_type == 'html':
            return render_template('yahoo_leagues.html', leagues=all_leagues, season='2024-25')
        
        # Update session with potentially refreshed token
        if yahoo_client.token:
            session['yahoo_token'] = yahoo_client.token
        
        return jsonify({
            'success': True,
            'leagues': [
                {
                    'league_key': l.league_key,
                    'league_id': l.league_id,
                    'name': l.name,
                    'season': l.season,
                    'num_teams': l.num_teams,
                    'scoring_type': l.scoring_type,
                    'draft_status': l.draft_status,
                    'current_week': l.current_week,
                    'url': l.url
                }
                for l in all_leagues
            ],
            'count': len(all_leagues),
            'message': 'Fetched leagues from all available NBA seasons'
        })
        
    except Exception as e:
        app = __import__('flask').current_app
        app.logger.error(f"Error fetching leagues: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        
        # Check if token expired
        error_msg = str(e)
        if 'token_expired' in error_msg.lower():
            # Clear authentication
            session.pop('yahoo_token', None)
            session.pop('yahoo_authenticated', None)
            return jsonify({
                'success': False,
                'error': 'Yahoo session expired. Please login again.',
                'error_code': 'token_expired',
                'login_url': url_for('yahoo.yahoo_login', _external=True)
            }), 401
        
        return jsonify({
            'success': False,
            'error': str(e),
            'error_code': 'server_error'
        }), 500


@yahoo_bp.route('/league/<league_key>')
def league_details(league_key: str):
    """
    Get detailed information about a specific league
    
    Args:
        league_key: Yahoo league key (e.g., '418.l.12345')
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Fetch league details
        league = yahoo_client.get_league_details(league_key)
        
        # Save to database with full details
        league_dict = {
            'league_key': league.league_key,
            'league_id': league.league_id,
            'name': league.name,
            'season': league.season,
            'game_code': league.game_code,
            'num_teams': league.num_teams,
            'scoring_type': league.scoring_type,
            'draft_status': league.draft_status,
            'current_week': league.current_week,
            'start_week': league.start_week,
            'end_week': league.end_week,
            'start_date': league.start_date,
            'end_date': league.end_date,
            'is_finished': league.is_finished,
            'url': league.url,
            'stat_categories': league.stat_categories,
            'roster_positions': league.roster_positions,
        }
        yahoo_db.save_league(league_dict)
        
        return jsonify({
            'success': True,
            'league': {
                'league_key': league.league_key,
                'league_id': league.league_id,
                'name': league.name,
                'season': league.season,
                'num_teams': league.num_teams,
                'scoring_type': league.scoring_type,
                'draft_status': league.draft_status,
                'current_week': league.current_week,
                'start_date': league.start_date,
                'end_date': league.end_date,
                'stat_categories': league.stat_categories,
                'roster_positions': league.roster_positions,
                'url': league.url
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/league/<league_key>/teams')
def league_teams(league_key: str):
    """
    Get all teams in a league
    
    Args:
        league_key: Yahoo league key
        
    Query params:
    - include_roster: Include player rosters (default: false)
    - debug: Show raw API response (default: false)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Debug mode
        debug_mode = request.args.get('debug', 'false').lower() == 'true'
        
        if debug_mode:
            # Return raw API response for debugging
            endpoint = f'/league/{league_key}/teams'
            xml_response = yahoo_client._make_request(endpoint)
            data = yahoo_client._parse_xml_to_dict(xml_response)
            
            return jsonify({
                'success': True,
                'debug': True,
                'endpoint': endpoint,
                'raw_xml_preview': xml_response[:1000],
                'parsed_data': data,
                'parsed_keys': list(data.keys()) if isinstance(data, dict) else str(type(data))
            })
        
        # Fetch teams
        include_roster = request.args.get('include_roster', 'false').lower() == 'true'
        teams = yahoo_client.get_league_teams(league_key, include_rosters=include_roster)
        
        app = __import__('flask').current_app
        app.logger.info(f"Found {len(teams)} teams in league {league_key}")
        
        # Get NBA players for matching
        nba_players = data_manager.get_all_nba_players(season='2024-25', min_games=0)
        player_matcher = PlayerMatcher(nba_players)
        
        # Save teams to database
        teams_data = []
        
        for team in teams:
            # Save team
            team_dict = {
                'team_key': team.team_key,
                'team_id': team.team_id,
                'league_key': league_key,
                'name': team.name,
                'team_logo_url': team.team_logo_url,
                'waiver_priority': team.waiver_priority,
                'number_of_moves': team.number_of_moves,
                'number_of_trades': team.number_of_trades,
                'managers': team.managers,
            }
            yahoo_db.save_team(team_dict)
            
            # Build response
            team_response = {
                'team_key': team.team_key,
                'team_id': team.team_id,
                'name': team.name,
                'logo_url': team.team_logo_url,
                'team_logo_url': team.team_logo_url,
                'waiver_priority': team.waiver_priority,
                'managers': [m.get('nickname', 'Unknown') for m in team.managers] if team.managers else ['Unknown'],
                'wins': team.wins if hasattr(team, 'wins') else 0,
                'losses': team.losses if hasattr(team, 'losses') else 0,
                'standing': team.standing if hasattr(team, 'standing') else None,
            }
            
            # Include roster if requested and available
            if include_roster and hasattr(team, 'roster') and team.roster:
                roster = team.roster
                
                # Merge with NBA stats
                merged_roster = player_matcher.batch_merge(roster)
                
                # Save players
                for player in merged_roster:
                    player_dict = {
                        'player_key': player.player_key,
                        'player_id': player.player_id,
                        'name': player.name,
                        'first_name': player.first_name,
                        'last_name': player.last_name,
                        'position': player.position,
                        'team': player.team,
                        'team_abbr': player.team_abbr,
                        'is_undroppable': player.is_undroppable,
                        'nba_stats': player.nba_stats,
                    }
                    yahoo_db.save_player(player_dict)
                
                # Save roster links
                yahoo_db.save_roster(team.team_key, [p.player_key for p in roster])
                
                team_response['roster'] = [
                    {
                        'player_key': p.player_key,
                        'player_name': p.name,
                        'name': p.name,
                        'position': p.position,
                        'nba_team': p.team_abbr or p.team,
                        'stats': {
                            'ppg': p.nba_stats.get('ppg') if p.nba_stats else None,
                            'rpg': p.nba_stats.get('rpg') if p.nba_stats else None,
                            'apg': p.nba_stats.get('apg') if p.nba_stats else None,
                            'spg': p.nba_stats.get('spg') if p.nba_stats else None,
                            'bpg': p.nba_stats.get('bpg') if p.nba_stats else None,
                            'fg_pct': p.nba_stats.get('fg_pct') if p.nba_stats else None,
                            'ft_pct': p.nba_stats.get('ft_pct') if p.nba_stats else None,
                            'tpg': p.nba_stats.get('tpg') if p.nba_stats else None,
                        } if p.nba_stats else {}
                    }
                    for p in merged_roster
                ]
            
            teams_data.append(team_response)
        
        # Check if HTML format requested
        format_type = request.args.get('format', 'json')
        
        if format_type == 'html':
            # Get league name for breadcrumb
            league_details = yahoo_client.get_league_details(league_key)
            return render_template('yahoo_league_teams.html', 
                                   teams=teams_data, 
                                   league_key=league_key,
                                   league_name=league_details.name if league_details else league_key)
        
        return jsonify({
            'success': True,
            'league_key': league_key,
            'teams': teams_data,
            'count': len(teams_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/team/<team_key>/roster')
def team_roster(team_key: str):
    """
    Get roster for a specific team with merged NBA stats
    
    Args:
        team_key: Yahoo team key (e.g., '418.l.12345.t.1')
        
    Query params:
    - format: json or html (default: json)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Fetch roster
        roster = yahoo_client.get_team_roster(team_key)
        
        # Get NBA players for matching
        nba_players = data_manager.get_all_nba_players(season='2024-25', min_games=0)
        player_matcher = PlayerMatcher(nba_players)
        
        # Merge with NBA stats
        merged_roster = player_matcher.batch_merge(roster)
        
        # Get match report
        match_report = player_matcher.get_match_report(roster)
        
        # Save to database
        for player in merged_roster:
            player_dict = {
                'player_key': player.player_key,
                'player_id': player.player_id,
                'name': player.name,
                'first_name': player.first_name,
                'last_name': player.last_name,
                'position': player.position,
                'team': player.team,
                'team_abbr': player.team_abbr,
                'is_undroppable': player.is_undroppable,
                'nba_stats': player.nba_stats,
            }
            yahoo_db.save_player(player_dict)
        
        yahoo_db.save_roster(team_key, [p.player_key for p in roster])
        
        # Check if HTML format requested
        format_type = request.args.get('format', 'json')
        
        if format_type == 'html':
            # Get team info
            from yahoo_integration.yahoo_client import YahooFantasyClient
            client = YahooFantasyClient()
            client.set_token(token)
            
            # Extract league_key and team_id from team_key (format: game_key.l.league_id.t.team_id)
            parts = team_key.split('.')
            league_key = f"{parts[0]}.l.{parts[2]}"
            
            # Fetch team details and league details
            teams = client.get_league_teams(league_key)
            my_team = next((t for t in teams if t.team_key == team_key), None)
            league = client.get_league_details(league_key)
            
            roster_data = [
                {
                    'player_key': p.player_key,
                    'player_name': p.name,
                    'position': p.position,
                    'nba_team': p.team_abbr or p.team,
                    'is_undroppable': p.is_undroppable,
                    'stats': {
                        'ppg': p.nba_stats.get('ppg') if p.nba_stats else None,
                        'rpg': p.nba_stats.get('rpg') if p.nba_stats else None,
                        'apg': p.nba_stats.get('apg') if p.nba_stats else None,
                        'spg': p.nba_stats.get('spg') if p.nba_stats else None,
                        'bpg': p.nba_stats.get('bpg') if p.nba_stats else None,
                        'tpg': p.nba_stats.get('tpg') if p.nba_stats else None,
                        'fg_pct': p.nba_stats.get('fg_pct') if p.nba_stats else None,
                        'ft_pct': p.nba_stats.get('ft_pct') if p.nba_stats else None,
                        'tov': p.nba_stats.get('tov') if p.nba_stats else None,
                    } if p.nba_stats else {}
                }
                for p in merged_roster
            ]
            
            return render_template('yahoo_my_team.html',
                                 team_key=team_key,
                                 team_name=my_team.name if my_team else 'My Team',
                                 league_key=league_key,
                                 league_name=league.name if league else 'League',
                                 roster=roster_data,
                                 wins=my_team.wins if my_team and hasattr(my_team, 'wins') else 0,
                                 losses=my_team.losses if my_team and hasattr(my_team, 'losses') else 0,
                                 standing=my_team.standing if my_team and hasattr(my_team, 'standing') else '-',
                                 waiver_priority=my_team.waiver_priority if my_team else '-')
        
        return jsonify({
            'success': True,
            'team_key': team_key,
            'roster': [
                {
                    'player_key': p.player_key,
                    'player_id': p.player_id,
                    'name': p.name,
                    'position': p.position,
                    'team': p.team_abbr,
                    'is_undroppable': p.is_undroppable,
                    'nba_stats': p.nba_stats
                }
                for p in merged_roster
            ],
            'match_report': match_report,
            'count': len(merged_roster)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/league/<league_key>/standings')
def league_standings(league_key: str):
    """Get league standings - JSON API"""
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Fetch standings
        teams = yahoo_client.get_league_standings(league_key)
        
        return jsonify({
            'success': True,
            'league_key': league_key,
            'teams': [
                {
                    'team_key': t.team_key,
                    'team_name': t.name,
                    'wins': t.wins,
                    'losses': t.losses,
                    'ties': t.ties,
                    'points': t.team_standings.get('points_for', 0) if t.team_standings else 0,
                    'games_back': t.team_standings.get('games_back', '-') if t.team_standings else '-'
                }
                for t in teams
            ]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/league/<path:league_key>/view')
def league_view(league_key: str):
    """League view page - redirects to first team's page with appropriate tab"""
    try:
        # Clean league_key if it contains team info (e.g., 466.l.92258.t.1 -> 466.l.92258)
        if '.t.' in league_key:
            league_key = league_key.split('.t.')[0]
        
        # Check authentication
        if not session.get('yahoo_authenticated'):
            flash('Please login to Yahoo Fantasy first', 'warning')
            return redirect(url_for('yahoo.yahoo_login'))
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get teams
        teams = yahoo_client.get_league_teams(league_key)
        
        if not teams or len(teams) == 0:
            flash('No teams found in this league', 'warning')
            return redirect(url_for('yahoo.list_leagues') + '?format=html')
        
        # Get first team (usually user's team)
        first_team = teams[0]
        
        # Get tab parameter
        tab = request.args.get('tab', '')
        
        # Redirect to first team's roster page with tab parameter
        if tab:
            return redirect(f'/yahoo/team/{first_team.team_key}/roster?tab={tab}')
        else:
            return redirect(f'/yahoo/team/{first_team.team_key}/roster')
        
    except Exception as e:
        print(f"❌ Error in league_view: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading league: {str(e)}', 'danger')
        return redirect(url_for('yahoo.list_leagues') + '?format=html')


@yahoo_bp.route('/league/<league_key>/free_agents')
def league_free_agents(league_key: str):
    """
    Get available free agents in a league
    
    Query params:
    - position: Filter by position (optional)
    - count: Number of players (default: 25)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get query params
        position = request.args.get('position')
        count = int(request.args.get('count', 25))
        
        # Fetch free agents
        free_agents = yahoo_client.get_free_agents(league_key, position=position, count=count)
        
        # Get NBA players for matching
        nba_players = data_manager.get_all_nba_players(season='2024-25', min_games=0)
        player_matcher = PlayerMatcher(nba_players)
        
        # Merge with NBA stats
        merged_players = player_matcher.batch_merge(free_agents)
        
        return jsonify({
            'success': True,
            'league_key': league_key,
            'free_agents': [
                {
                    'player_key': p.player_key,
                    'name': p.name,
                    'position': p.position,
                    'team': p.team_abbr,
                    'percent_owned': p.percent_owned,
                    'nba_stats': p.nba_stats
                }
                for p in merged_players
            ],
            'count': len(merged_players)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/league/<league_key>/scoreboard')
def league_scoreboard(league_key: str):
    """
    Get league scoreboard with all matchups for a week
    
    Query params:
    - week: Week number (optional, defaults to current week)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get query params
        week = request.args.get('week', type=int)
        
        # Fetch scoreboard
        scoreboard = yahoo_client.get_league_scoreboard(league_key, week=week)
        
        return jsonify({
            'success': True,
            **scoreboard
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/team/<team_key>/matchup')
def team_matchup(team_key: str):
    """
    Get team's matchup for a specific week with detailed 9-cat stats
    
    Query params:
    - week: Week number (optional, defaults to current week)
    
    Returns matchup with stat IDs:
    - 5: FG% (Field Goal Percentage)
    - 8: FT% (Free Throw Percentage)
    - 10: 3PTM (3-Pointers Made)
    - 12: PTS (Points)
    - 15: REB (Rebounds)
    - 16: AST (Assists)
    - 17: ST (Steals)
    - 18: BLK (Blocks)
    - 19: TO (Turnovers)
    """
    try:
        # Check authentication
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401
        
        # Set token
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get query params
        week = request.args.get('week', type=int)
        
        # Fetch matchup
        matchup = yahoo_client.get_team_matchup(team_key, week=week)
        
        if not matchup:
            return jsonify({
                'success': False,
                'error': 'No matchup found for this week'
            }), 404
        
        # Save matchup to session for easy access
        session['yahoo_current_matchup'] = matchup
        session['yahoo_matchup_week'] = matchup.get('week')
        
        return jsonify({
            'success': True,
            'matchup': matchup,
            'stat_legend': {
                '5': 'FG%',
                '8': 'FT%',
                '10': '3PTM',
                '12': 'PTS',
                '15': 'REB',
                '16': 'AST',
                '17': 'ST',
                '18': 'BLK',
                '19': 'TO'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@yahoo_bp.route('/games')
def list_available_games():
    """Get all available NBA games/seasons for authenticated user"""
    try:
        if not session.get('yahoo_authenticated'):
            return jsonify({
                'error': 'Not authenticated',
                'authenticated': False
            }), 401
        
        token = session.get('yahoo_token')
        yahoo_client.set_token(token)
        
        # Get all NBA games (all seasons)
        endpoint = '/users;use_login=1/games;game_codes=nba'
        xml_response = yahoo_client._make_request(endpoint)
        data = yahoo_client._parse_xml_to_dict(xml_response)
        
        # Extract games
        games_list = []
        try:
            users = data.get('users', {})
            user = users.get('user', {})
            games = user.get('games', {})
            game_data = games.get('game', [])
            
            # Ensure it's a list
            if not isinstance(game_data, list):
                game_data = [game_data] if game_data else []
            
            for game in game_data:
                games_list.append({
                    'game_key': game.get('game_key'),
                    'game_id': game.get('game_id'),
                    'season': game.get('season'),
                    'name': game.get('name'),
                    'code': game.get('code'),
                    'is_offseason': game.get('is_offseason') == '1',
                    'is_game_over': game.get('is_game_over') == '1',
                    'url': game.get('url')
                })
        except Exception as e:
            return jsonify({'error': f'Failed to parse games: {e}'}), 500
        
        return jsonify({
            'success': True,
            'games': games_list,
            'count': len(games_list)
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@yahoo_bp.route('/debug')
def debug_api():
    """Debug Yahoo API connection"""
    try:
        authenticated = session.get('yahoo_authenticated', False)
        token = session.get('yahoo_token')
        
        if not authenticated:
            return jsonify({
                'error': 'Not authenticated',
                'session_keys': list(session.keys()),
                'authenticated': authenticated
            })
        
        # Set token
        yahoo_client.set_token(token)
        
        # Try to make a simple API request
        from yahoo_integration.config import NBA_GAME_KEYS
        game_code = NBA_GAME_KEYS.get('2023-24')  # Use confirmed season
        endpoint = f'/users;use_login=1/games;game_keys={game_code}/leagues'
        
        # Make raw request
        xml_response = yahoo_client._make_request(endpoint)
        
        # Parse it
        data = yahoo_client._parse_xml_to_dict(xml_response)
        
        return jsonify({
            'success': True,
            'authenticated': authenticated,
            'token_type': token.get('token_type') if token else None,
            'has_access_token': 'access_token' in token if token else False,
            'endpoint': endpoint,
            'raw_xml_length': len(xml_response),
            'raw_xml_preview': xml_response[:500],
            'parsed_keys': list(data.keys()) if isinstance(data, dict) else str(type(data)),
            'parsed_data': data
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


# Example usage and documentation endpoint
@yahoo_bp.route('/docs')
def api_docs():
    """API documentation and examples"""
    docs = {
        'title': 'Yahoo Fantasy Basketball Integration API',
        'version': '1.0.0',
        'description': 'Comprehensive Yahoo Fantasy Sports API integration with real NBA stats',
        'endpoints': [
            {
                'path': '/yahoo/auth/login',
                'method': 'GET',
                'description': 'Start Yahoo OAuth login flow',
                'authentication': 'None',
                'returns': 'Redirect to Yahoo authorization page'
            },
            {
                'path': '/yahoo/auth/callback',
                'method': 'GET',
                'description': 'Handle Yahoo OAuth callback',
                'authentication': 'None',
                'parameters': {'code': 'Authorization code from Yahoo', 'state': 'OAuth state'},
                'returns': 'Redirect to leagues page'
            },
            {
                'path': '/yahoo/auth/status',
                'method': 'GET',
                'description': 'Check authentication status',
                'returns': {'authenticated': 'boolean', 'token_exists': 'boolean'}
            },
            {
                'path': '/yahoo/leagues',
                'method': 'GET',
                'description': 'Get user\'s fantasy leagues',
                'authentication': 'Required',
                'parameters': {'season': '2024-25', 'format': 'json or html'},
                'returns': 'List of leagues'
            },
            {
                'path': '/yahoo/league/<league_key>',
                'method': 'GET',
                'description': 'Get league details',
                'authentication': 'Required',
                'returns': 'League object with settings'
            },
            {
                'path': '/yahoo/league/<league_key>/teams',
                'method': 'GET',
                'description': 'Get teams in league',
                'authentication': 'Required',
                'parameters': {'include_roster': 'true/false'},
                'returns': 'List of teams'
            },
            {
                'path': '/yahoo/team/<team_key>/roster',
                'method': 'GET',
                'description': 'Get team roster with merged NBA stats',
                'authentication': 'Required',
                'returns': 'List of players with stats'
            },
            {
                'path': '/yahoo/league/<league_key>/standings',
                'method': 'GET',
                'description': 'Get league standings',
                'authentication': 'Required',
                'returns': 'Standings with rankings and records'
            },
            {
                'path': '/yahoo/league/<league_key>/free_agents',
                'method': 'GET',
                'description': 'Get available free agents',
                'authentication': 'Required',
                'parameters': {'position': 'PG/SG/SF/PF/C', 'count': '25'},
                'returns': 'List of available players'
            },
            {
                'path': '/yahoo/league/<league_key>/scoreboard',
                'method': 'GET',
                'description': 'Get league scoreboard with all matchups',
                'authentication': 'Required',
                'parameters': {'week': 'Week number (optional)'},
                'returns': 'All matchups with team stats'
            },
            {
                'path': '/yahoo/team/<team_key>/matchup',
                'method': 'GET',
                'description': 'Get team matchup with detailed 9-cat stats',
                'authentication': 'Required',
                'parameters': {'week': 'Week number (optional)'},
                'returns': 'Matchup details with category stats'
            }
        ],
        'example_requests': {
            'get_leagues': {
                'url': '/yahoo/leagues?season=2024-25',
                'method': 'GET',
                'headers': {'Cookie': 'session=...'}
            },
            'get_team_roster': {
                'url': '/yahoo/team/418.l.12345.t.1/roster',
                'method': 'GET',
                'headers': {'Cookie': 'session=...'}
            },
            'get_matchup': {
                'url': '/yahoo/team/418.l.12345.t.1/matchup?week=1',
                'method': 'GET',
                'headers': {'Cookie': 'session=...'}
            }
        }
    }
    
    return jsonify(docs)


@yahoo_bp.route('/api/save-yahoo-matchup', methods=['POST'])
def save_yahoo_matchup():
    """Save Yahoo matchup data to session"""
    try:
        data = request.get_json()
        
        if not data or 'matchup' not in data:
            return jsonify({
                'success': False,
                'error': 'No matchup data provided'
            }), 400
        
        # Save matchup data to session
        session['yahoo_matchup_stats'] = {
            'teams': data['matchup']['teams'],
            'week': data.get('week', 1),
            'league_name': data.get('league_name', 'Unknown League')
        }
        
        print(f"✅ Saved Yahoo matchup to session: Week {data.get('week')}, {len(data['matchup']['teams'])} teams")
        print(f"📊 Team 1: {data['matchup']['teams'][0]['name']}")
        print(f"   Stats: {data['matchup']['teams'][0].get('stats', {})}")
        print(f"📊 Team 2: {data['matchup']['teams'][1]['name']}")
        print(f"   Stats: {data['matchup']['teams'][1].get('stats', {})}")
        
        return jsonify({
            'success': True,
            'message': 'Matchup data saved to session'
        })
        
    except Exception as e:
        print(f"❌ Error saving matchup: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
