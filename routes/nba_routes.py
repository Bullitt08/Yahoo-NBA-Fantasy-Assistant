"""
NBA Statistics Routes
Flask routes for managing NBA player statistics scraping and retrieval.
"""

from flask import Blueprint, jsonify, request, render_template
from typing import Dict, Any
import logging
from services.nba_scraper import NBAStatsScraper
import traceback

logger = logging.getLogger(__name__)

# Create Blueprint
nba_bp = Blueprint('nba', __name__, url_prefix='/nba')

# Initialize scraper (singleton pattern)
scraper = None


def get_scraper() -> NBAStatsScraper:
    """Get or create scraper instance"""
    global scraper
    if scraper is None:
        scraper = NBAStatsScraper()
    return scraper


@nba_bp.route('/update-stats', methods=['POST'])
def update_stats():
    """
    Automatically download and import NBA stats using PowerShell (bypasses 403 errors)
    
    Request JSON:
        {
            "seasons": [2026]
        }
    
    Returns:
        JSON response with status and import results
    """
    try:
        import os
        import subprocess
        from bs4 import BeautifulSoup
        from pathlib import Path
        
        data = request.get_json() or {}
        
        # Get parameters
        seasons = data.get('seasons', [2026])
        
        # Validate seasons
        if not isinstance(seasons, list) or not seasons:
            return jsonify({
                'success': False,
                'error': 'Invalid seasons parameter. Must be a non-empty list.'
            }), 400
        
        # Validate season years (reasonable range)
        current_year = 2026
        valid_seasons = [s for s in seasons if isinstance(s, int) and 2000 <= s <= current_year]
        
        if not valid_seasons:
            return jsonify({
                'success': False,
                'error': f'No valid seasons provided. Must be between 2000 and {current_year}.'
            }), 400
        
        logger.info(f"Starting automated download and import for seasons: {valid_seasons}")
        
        # Create temp directory if it doesn't exist
        temp_dir = Path('temp')
        temp_dir.mkdir(exist_ok=True)
        
        scraper_instance = get_scraper()
        season_results = {}
        
        # Process each season
        for season in valid_seasons:
            html_file = temp_dir / f'nba_{season}_totals.html'
            
            try:
                # Step 1: Download HTML using PowerShell
                logger.info(f"Downloading HTML for season {season}...")
                
                ps_script = f'''
$url = "https://www.basketball-reference.com/leagues/NBA_{season}_totals.html"
$headers = @{{
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    "Accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    "Accept-Language" = "en-US,en;q=0.9"
    "Accept-Encoding" = "gzip, deflate, br"
    "Referer" = "https://www.basketball-reference.com/"
    "Sec-Ch-Ua" = '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"'
    "Sec-Ch-Ua-Mobile" = "?0"
    "Sec-Ch-Ua-Platform" = '"Windows"'
    "Sec-Fetch-Dest" = "document"
    "Sec-Fetch-Mode" = "navigate"
    "Sec-Fetch-Site" = "same-origin"
}}
$response = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing
# Get raw content bytes and decode as UTF-8
$htmlBytes = $response.RawContentStream.ToArray()
$htmlText = [System.Text.Encoding]::UTF8.GetString($htmlBytes)
# Find where actual HTML starts (after HTTP headers)
$htmlStart = $htmlText.IndexOf('<!DOCTYPE')
if ($htmlStart -eq -1) {{ $htmlStart = $htmlText.IndexOf('<html') }}
if ($htmlStart -gt 0) {{ $htmlText = $htmlText.Substring($htmlStart) }}
# Write as UTF-8
[System.IO.File]::WriteAllText("{html_file.absolute()}", $htmlText, [System.Text.Encoding]::UTF8)
'''
                
                result = subprocess.run(
                    ['powershell', '-Command', ps_script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.getcwd()
                )
                
                if result.returncode != 0:
                    raise Exception(f"PowerShell download failed: {result.stderr}")
                
                if not html_file.exists():
                    raise Exception("HTML file was not created")
                
                file_size = html_file.stat().st_size
                logger.info(f"✓ Downloaded {file_size} bytes for season {season}")
                
                # Step 2: Parse HTML
                logger.info(f"Parsing HTML for season {season}...")
                with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
                    html_content = f.read()
                
                soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')
                df = scraper_instance.parse_player_stats(soup, season)
                
                if df.empty:
                    raise Exception('No player data found in HTML file')
                
                # Handle duplicates
                df = scraper_instance.handle_duplicates(df)
                
                # Step 3: Save to CSV
                csv_path = scraper_instance.save_to_csv(df, season)
                
                # Step 4: Save to database
                count = scraper_instance.save_to_database(df, season)
                
                season_results[season] = {
                    'success': True,
                    'players_count': count,
                    'csv_path': str(csv_path)
                }
                
                logger.info(f"✓ Successfully imported {count} players for season {season}")
                
                # Step 5: Delete temp HTML file
                try:
                    html_file.unlink()
                    logger.info(f"✓ Cleaned up temp file for season {season}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file: {e}")
                
            except Exception as e:
                logger.error(f"Error processing season {season}: {str(e)}")
                season_results[season] = {
                    'success': False,
                    'error': str(e),
                    'players_count': 0
                }
                
                # Try to cleanup temp file even on error
                try:
                    if html_file.exists():
                        html_file.unlink()
                except:
                    pass
        
        # Cleanup temp directory if empty
        try:
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
                logger.info("✓ Removed empty temp directory")
        except:
            pass
        
        # Prepare response
        successful_seasons = [s for s, r in season_results.items() if r.get('success')]
        failed_seasons = [s for s, r in season_results.items() if not r.get('success')]
        
        total_players = sum(r.get('players_count', 0) for r in season_results.values())
        
        logger.info(f"Stats update completed: {len(successful_seasons)} successful, {len(failed_seasons)} failed")
        
        # Clear DataManager cache after successful update
        if successful_seasons:
            try:
                from app import data_manager
                # Clear all cached season data
                data_manager.season_players_cache.clear()
                logger.info("✓ Cleared DataManager cache after stats update")
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")
        
        return jsonify({
            'success': len(successful_seasons) > 0,
            'message': f'Successfully updated stats for {len(successful_seasons)} season(s)' if successful_seasons else 'Failed to update any seasons',
            'seasons_processed': len(successful_seasons),
            'seasons_requested': len(valid_seasons),
            'total_players_imported': total_players,
            'results': season_results,
            'cache_cleared': len(successful_seasons) > 0
        })
        
    except Exception as e:
        logger.error(f"Error in update_stats: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@nba_bp.route('/players')
def players_page():
    """Render the players page"""
    return render_template('players.html')


@nba_bp.route('/get-stats', methods=['GET'])
def get_stats():
    """
    Get player stats for a specific season
    
    Query Parameters:
        season (int): NBA season year (e.g., 2024)
        limit (int, optional): Number of records to return (default: all)
        sort_by (str, optional): Stat to sort by (default: points)
        order (str, optional): 'asc' or 'desc' (default: desc)
    
    Returns:
        JSON response with player stats
    """
    try:
        # Get parameters
        season = request.args.get('season', type=int)
        limit = request.args.get('limit', type=int)
        sort_by = request.args.get('sort_by', 'points')
        order = request.args.get('order', 'desc').lower()
        
        if not season:
            return jsonify({
                'success': False,
                'error': 'Season parameter is required'
            }), 400
        
        # Validate season
        if season < 2000 or season > 2026:
            return jsonify({
                'success': False,
                'error': 'Invalid season. Must be between 2000 and 2026.'
            }), 400
        
        logger.info(f"Fetching stats for season {season}")
        
        # Get data from database
        scraper_instance = get_scraper()
        df = scraper_instance.get_season_stats(season)
        
        if df is None or df.empty:
            return jsonify({
                'success': False,
                'error': f'No data found for season {season}. Please update stats first.',
                'season': season
            }), 404
        
        # Sort data
        if sort_by in df.columns:
            ascending = (order == 'asc')
            df = df.sort_values(by=sort_by, ascending=ascending)
        
        # Limit results
        if limit and limit > 0:
            df = df.head(limit)
        
        # Convert to JSON-friendly format
        # Drop SQLAlchemy metadata columns
        columns_to_drop = ['id', 'updated_at']
        df = df.drop(columns=[col for col in columns_to_drop if col in df.columns])
        
        # Convert to dict
        players = df.to_dict(orient='records')
        
        response = {
            'success': True,
            'season': season,
            'total_players': len(players),
            'players': players
        }
        
        logger.info(f"Returning {len(players)} players for season {season}")
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve stats. Check server logs for details.'
        }), 500


@nba_bp.route('/top-players', methods=['GET'])
def get_top_players():
    """
    Get top players for a specific season and stat
    
    Query Parameters:
        season (int): NBA season year (e.g., 2024)
        stat (str, optional): Stat to rank by (default: points)
        limit (int, optional): Number of players to return (default: 20)
    
    Returns:
        JSON response with top players
    """
    try:
        # Get parameters
        season = request.args.get('season', type=int)
        stat = request.args.get('stat', 'points')
        limit = request.args.get('limit', 20, type=int)
        
        if not season:
            return jsonify({
                'success': False,
                'error': 'Season parameter is required'
            }), 400
        
        # Validate limit
        if limit < 1 or limit > 100:
            limit = 20
        
        logger.info(f"Fetching top {limit} players by {stat} for season {season}")
        
        # Get top players
        scraper_instance = get_scraper()
        df = scraper_instance.get_top_players(season, stat=stat, limit=limit)
        
        if df is None or df.empty:
            return jsonify({
                'success': False,
                'error': f'No data found for season {season} or invalid stat: {stat}',
                'season': season
            }), 404
        
        # Convert to JSON
        players = df.to_dict(orient='records')
        
        response = {
            'success': True,
            'season': season,
            'stat': stat,
            'limit': limit,
            'players': players
        }
        
        logger.info(f"Returning top {len(players)} players")
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error getting top players: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve top players. Check server logs for details.'
        }), 500


@nba_bp.route('/available-seasons', methods=['GET'])
def get_available_seasons():
    """
    Get list of seasons that have data in the database
    
    Returns:
        JSON response with available seasons
    """
    try:
        scraper_instance = get_scraper()
        session = scraper_instance.Session()
        
        try:
            from sqlalchemy import distinct
            from services.nba_scraper import PlayerStats
            
            # Query distinct seasons
            seasons = session.query(distinct(PlayerStats.season)).order_by(PlayerStats.season.desc()).all()
            season_list = [s[0] for s in seasons]
            
            response = {
                'success': True,
                'seasons': season_list,
                'count': len(season_list)
            }
            
            return jsonify(response), 200
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error getting available seasons: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@nba_bp.route('/player-search', methods=['GET'])
def search_players():
    """
    Search for players by name across all seasons
    
    Query Parameters:
        query (str): Search query for player name
        season (int, optional): Filter by specific season
        limit (int, optional): Max results (default: 50)
    
    Returns:
        JSON response with matching players
    """
    try:
        query = request.args.get('query', '').strip()
        season = request.args.get('season', type=int)
        limit = request.args.get('limit', 50, type=int)
        
        if not query or len(query) < 2:
            return jsonify({
                'success': False,
                'error': 'Query must be at least 2 characters'
            }), 400
        
        scraper_instance = get_scraper()
        session = scraper_instance.Session()
        
        try:
            from services.nba_scraper import PlayerStats
            
            # Build query
            db_query = session.query(PlayerStats).filter(
                PlayerStats.player_name.ilike(f'%{query}%')
            )
            
            if season:
                db_query = db_query.filter(PlayerStats.season == season)
            
            db_query = db_query.order_by(PlayerStats.season.desc(), PlayerStats.points.desc())
            
            # Execute and convert to DataFrame
            import pandas as pd
            df = pd.read_sql(db_query.limit(limit).statement, session.bind)
            
            if df.empty:
                return jsonify({
                    'success': True,
                    'query': query,
                    'results': [],
                    'count': 0
                }), 200
            
            # Drop metadata columns
            df = df.drop(columns=['id', 'updated_at'], errors='ignore')
            players = df.to_dict(orient='records')
            
            response = {
                'success': True,
                'query': query,
                'results': players,
                'count': len(players)
            }
            
            return jsonify(response), 200
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error searching players: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@nba_bp.route('/stats-summary', methods=['GET'])
def get_stats_summary():
    """
    Get summary statistics for a season
    
    Query Parameters:
        season (int): NBA season year
    
    Returns:
        JSON with aggregated stats
    """
    try:
        season = request.args.get('season', type=int)
        
        if not season:
            return jsonify({
                'success': False,
                'error': 'Season parameter is required'
            }), 400
        
        scraper_instance = get_scraper()
        df = scraper_instance.get_season_stats(season)
        
        if df is None or df.empty:
            return jsonify({
                'success': False,
                'error': f'No data found for season {season}'
            }), 404
        
        # Calculate summary statistics
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        summary = {
            'season': season,
            'total_players': len(df),
            'avg_stats': {},
            'top_stats': {}
        }
        
        # Average stats
        for col in ['points', 'assists', 'total_rebounds', 'steals', 'blocks']:
            if col in df.columns:
                summary['avg_stats'][col] = round(df[col].mean(), 2)
        
        # Top values
        for col in ['points', 'assists', 'total_rebounds']:
            if col in df.columns:
                top_player = df.nlargest(1, col).iloc[0]
                summary['top_stats'][col] = {
                    'player': top_player.get('player_name', 'Unknown'),
                    'value': round(top_player[col], 2)
                }
        
        return jsonify({
            'success': True,
            'summary': summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting stats summary: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
