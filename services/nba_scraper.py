"""
NBA Player Statistics Scraper
Scrapes per-game statistics from Basketball Reference for multiple seasons.
"""

import logging
import time
from typing import List, Dict, Optional
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

Base = declarative_base()


class PlayerStats(Base):
    """SQLAlchemy model for player statistics"""
    __tablename__ = 'player_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    season = Column(Integer, nullable=False, index=True)
    player_name = Column(String(100), nullable=False, index=True)
    team = Column(String(10))
    position = Column(String(10))
    age = Column(Integer)
    games_played = Column(Integer)
    games_started = Column(Integer)
    minutes_per_game = Column(Float)
    field_goals = Column(Float)
    field_goal_attempts = Column(Float)
    field_goal_pct = Column(Float)
    three_pointers = Column(Float)
    three_point_attempts = Column(Float)
    three_point_pct = Column(Float)
    two_pointers = Column(Float)
    two_point_attempts = Column(Float)
    two_point_pct = Column(Float)
    effective_fg_pct = Column(Float)
    free_throws = Column(Float)
    free_throw_attempts = Column(Float)
    free_throw_pct = Column(Float)
    offensive_rebounds = Column(Float)
    defensive_rebounds = Column(Float)
    total_rebounds = Column(Float)
    assists = Column(Float)
    steals = Column(Float)
    blocks = Column(Float)
    turnovers = Column(Float)
    personal_fouls = Column(Float)
    points = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow)


class NBAStatsScraper:
    """Scraper for NBA player statistics from Basketball Reference"""
    
    BASE_URL = "https://www.basketball-reference.com/leagues/NBA_{season}_totals.html"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://www.google.com/',
    }
    
    def __init__(self, db_path: str = "database/nba_stats.db", data_dir: str = "data"):
        """
        Initialize the scraper
        
        Args:
            db_path: Path to SQLite database
            data_dir: Directory to store CSV files
        """
        self.db_path = db_path
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Setup database
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
        # Setup persistent session with cookies
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        
        logger.info(f"Initialized NBAStatsScraper with database: {db_path}")
    
    def fetch_season_data(self, season: int, max_retries: int = 5) -> Optional[BeautifulSoup]:
        """
        Fetch HTML data for a specific season with retry logic and anti-bot measures
        
        Args:
            season: NBA season year (e.g., 2024)
            max_retries: Maximum number of retry attempts
            
        Returns:
            BeautifulSoup object or None if failed
        """
        url = self.BASE_URL.format(season=season)
        
        # First, visit the homepage to get cookies
        try:
            logger.info("Visiting Basketball Reference homepage to establish session...")
            home_response = self.session.get("https://www.basketball-reference.com/", timeout=30)
            time.sleep(2)  # Wait before actual request
        except:
            logger.warning("Failed to visit homepage, continuing anyway...")
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching data for {season} season (attempt {attempt + 1}/{max_retries})")
                
                # Add random delay to appear more human-like
                delay = 2 + (attempt * 1.5)
                time.sleep(delay)
                
                response = self.session.get(url, timeout=30)
                
                # Check if we got blocked
                if response.status_code == 403:
                    logger.warning(f"403 Forbidden - trying with different approach...")
                    # Try with minimal headers
                    minimal_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
                    }
                    response = requests.get(url, headers=minimal_headers, timeout=30)
                
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                logger.info(f"Successfully fetched data for {season} season")
                return soup
                
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {season}: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + 2  # Longer exponential backoff
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch data for {season} after {max_retries} attempts")
                    return None
    
    def parse_player_stats(self, soup: BeautifulSoup, season: int) -> pd.DataFrame:
        """
        Parse player statistics from HTML table
        
        Args:
            soup: BeautifulSoup object containing the page
            season: NBA season year
            
        Returns:
            DataFrame with player statistics
        """
        try:
            # Find the totals_stats table
            table = soup.find('table', {'id': 'totals_stats'})
            if not table:
                logger.error(f"Could not find totals_stats table for {season}")
                return pd.DataFrame()
            
            # Parse table headers
            headers = []
            thead = table.find('thead')
            if thead:
                header_row = thead.find_all('tr')[-1]  # Get the last header row
                headers = [th.get('data-stat', th.text.strip()) for th in header_row.find_all('th')]
            
            # Parse table rows
            rows = []
            tbody = table.find('tbody')
            if tbody:
                for tr in tbody.find_all('tr', class_=lambda x: x != 'thead'):
                    # Skip header rows within tbody
                    if tr.find('th', {'scope': 'row'}) is None:
                        continue
                    
                    row_data = {}
                    for td in tr.find_all(['th', 'td']):
                        stat = td.get('data-stat', '')
                        if stat:
                            row_data[stat] = td.text.strip()
                    
                    if row_data:
                        rows.append(row_data)
            
            df = pd.DataFrame(rows)
            
            if df.empty:
                logger.warning(f"No data found for {season}")
                return df
            
            # Add season column
            df['season'] = season
            
            # Clean and convert data types
            df = self._clean_dataframe(df)
            
            logger.info(f"Parsed {len(df)} player records for {season}")
            return df
            
        except Exception as e:
            logger.error(f"Error parsing player stats for {season}: {str(e)}")
            return pd.DataFrame()
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and convert DataFrame columns to appropriate types
        
        Args:
            df: Raw DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        # Rename columns FIRST (before numeric conversion)
        column_mapping = {
            # API format (data-stat attributes from HTML)
            'player': 'player_name',
            'team_id': 'team',
            'pos': 'position',
            'g': 'games_played',
            'gs': 'games_started',
            'mp': 'minutes_total',
            'fg': 'field_goals_total',
            'fga': 'field_goal_attempts_total',
            'fg_pct': 'field_goal_pct',
            'fg3': 'three_pointers_total',
            'fg3a': 'three_point_attempts_total',
            'fg3_pct': 'three_point_pct',
            'fg2': 'two_pointers_total',
            'fg2a': 'two_point_attempts_total',
            'fg2_pct': 'two_point_pct',
            'efg_pct': 'effective_fg_pct',
            'ft': 'free_throws_total',
            'fta': 'free_throw_attempts_total',
            'ft_pct': 'free_throw_pct',
            'orb': 'offensive_rebounds_total',
            'drb': 'defensive_rebounds_total',
            'trb': 'total_rebounds_total',
            'ast': 'assists_total',
            'stl': 'steals_total',
            'blk': 'blocks_total',
            'tov': 'turnovers_total',
            'pf': 'personal_fouls_total',
            'pts': 'points_total',
            # HTML CSV export format (when already has descriptive names)
            'name_display': 'player_name',
            'team_name_abbr': 'team',
            'games': 'games_played'
        }
        
        df = df.rename(columns=column_mapping)
        
        # NOW convert numeric columns (after renaming)
        numeric_cols = [
            'age', 'games_played', 'games_started', 'minutes_total',
            'field_goals_total', 'field_goal_attempts_total', 'field_goal_pct',
            'three_pointers_total', 'three_point_attempts_total', 'three_point_pct',
            'two_pointers_total', 'two_point_attempts_total', 'two_point_pct',
            'effective_fg_pct', 'free_throws_total', 'free_throw_attempts_total', 'free_throw_pct',
            'offensive_rebounds_total', 'defensive_rebounds_total', 'total_rebounds_total',
            'assists_total', 'steals_total', 'blocks_total', 'turnovers_total',
            'personal_fouls_total', 'points_total'
        ]
        
        # Convert numeric columns
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Use TOTAL stats (no per-game conversion)
        # Just rename _total columns to standard names for compatibility
        if 'games_played' in df.columns:
            total_to_standard = {
                'field_goals_total': 'field_goals',
                'field_goal_attempts_total': 'field_goal_attempts',
                'three_pointers_total': 'three_pointers',
                'three_point_attempts_total': 'three_point_attempts',
                'two_pointers_total': 'two_pointers',
                'two_point_attempts_total': 'two_point_attempts',
                'free_throws_total': 'free_throws',
                'free_throw_attempts_total': 'free_throw_attempts',
                'offensive_rebounds_total': 'offensive_rebounds',
                'defensive_rebounds_total': 'defensive_rebounds',
                'total_rebounds_total': 'total_rebounds',
                'assists_total': 'assists',
                'steals_total': 'steals',
                'blocks_total': 'blocks',
                'turnovers_total': 'turnovers',
                'personal_fouls_total': 'personal_fouls',
                'points_total': 'points'
            }
            
            for total_col, standard_col in total_to_standard.items():
                if total_col in df.columns:
                    df[standard_col] = df[total_col]
            
            # Keep minutes_total as is (total minutes)
            if 'minutes_total' in df.columns:
                df['minutes_per_game'] = df['minutes_total']
        
        return df
    
    def handle_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle duplicate players (traded mid-season) by averaging their stats
        
        Args:
            df: DataFrame with potential duplicates
            
        Returns:
            DataFrame with duplicates resolved
        """
        if df.empty:
            return df
        
        # Check if required columns exist
        if 'player_name' not in df.columns:
            logger.warning("player_name column not found, skipping duplicate handling")
            return df
        
        # Identify players with multiple entries (traded players)
        # They usually have 'TOT' (total) row and team-specific rows
        if 'season' in df.columns:
            duplicated_players = df[df.duplicated(subset=['player_name', 'season'], keep=False)]
        else:
            duplicated_players = df[df.duplicated(subset=['player_name'], keep=False)]
        
        if duplicated_players.empty:
            return df
        
        logger.info(f"Found {len(duplicated_players['player_name'].unique())} players with multiple teams")
        
        # Keep only the 'TOT' rows for traded players, or average if no TOT
        cleaned_rows = []
        
        for player_name in df['player_name'].unique():
            player_data = df[df['player_name'] == player_name]
            
            if len(player_data) == 1:
                cleaned_rows.append(player_data.iloc[0])
            else:
                # Check if there's a TOT row
                tot_row = player_data[player_data['team'] == 'TOT']
                if not tot_row.empty:
                    cleaned_rows.append(tot_row.iloc[0])
                else:
                    # Average the stats (weighted by games played if available)
                    if 'games_played' in player_data.columns:
                        total_games = player_data['games_played'].sum()
                        if total_games > 0:
                            # Weighted average
                            numeric_cols = player_data.select_dtypes(include=['float64', 'int64']).columns
                            averaged = player_data[numeric_cols].multiply(
                                player_data['games_played'], axis=0
                            ).sum() / total_games
                            
                            result = player_data.iloc[0].copy()
                            result[numeric_cols] = averaged
                            result['team'] = 'Multiple'
                            cleaned_rows.append(result)
                        else:
                            cleaned_rows.append(player_data.iloc[0])
                    else:
                        cleaned_rows.append(player_data.iloc[0])
        
        result_df = pd.DataFrame(cleaned_rows)
        logger.info(f"Resolved duplicates: {len(df)} -> {len(result_df)} records")
        
        return result_df.reset_index(drop=True)
    
    def save_to_csv(self, df: pd.DataFrame, season: int) -> str:
        """
        Save DataFrame to CSV file
        
        Args:
            df: DataFrame to save
            season: NBA season year
            
        Returns:
            Path to saved CSV file
        """
        csv_path = self.data_dir / f"players_{season}.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(df)} records to {csv_path}")
        return str(csv_path)
    
    def save_to_database(self, df: pd.DataFrame, season: int) -> int:
        """
        Save DataFrame to SQLite database
        
        Args:
            df: DataFrame to save
            season: NBA season year
            
        Returns:
            Number of records saved
        """
        session = self.Session()
        try:
            # Delete existing records for this season
            session.query(PlayerStats).filter(PlayerStats.season == season).delete()
            
            # Convert DataFrame to database records
            records = []
            for _, row in df.iterrows():
                record = PlayerStats(
                    season=season,
                    player_name=row.get('player_name', ''),
                    team=row.get('team', ''),
                    position=row.get('position', ''),
                    age=row.get('age'),
                    games_played=row.get('games_played'),
                    games_started=row.get('games_started'),
                    minutes_per_game=row.get('minutes_per_game'),
                    field_goals=row.get('field_goals'),
                    field_goal_attempts=row.get('field_goal_attempts'),
                    field_goal_pct=row.get('field_goal_pct'),
                    three_pointers=row.get('three_pointers'),
                    three_point_attempts=row.get('three_point_attempts'),
                    three_point_pct=row.get('three_point_pct'),
                    two_pointers=row.get('two_pointers'),
                    two_point_attempts=row.get('two_point_attempts'),
                    two_point_pct=row.get('two_point_pct'),
                    effective_fg_pct=row.get('effective_fg_pct'),
                    free_throws=row.get('free_throws'),
                    free_throw_attempts=row.get('free_throw_attempts'),
                    free_throw_pct=row.get('free_throw_pct'),
                    offensive_rebounds=row.get('offensive_rebounds'),
                    defensive_rebounds=row.get('defensive_rebounds'),
                    total_rebounds=row.get('total_rebounds'),
                    assists=row.get('assists'),
                    steals=row.get('steals'),
                    blocks=row.get('blocks'),
                    turnovers=row.get('turnovers'),
                    personal_fouls=row.get('personal_fouls'),
                    points=row.get('points'),
                    updated_at=datetime.utcnow()
                )
                records.append(record)
            
            session.bulk_save_objects(records)
            session.commit()
            
            logger.info(f"Saved {len(records)} records to database for season {season}")
            return len(records)
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            session.close()
    
    def scrape_seasons(self, seasons: List[int], save_csv: bool = True, save_db: bool = True) -> Dict[int, pd.DataFrame]:
        """
        Scrape data for multiple seasons
        
        Args:
            seasons: List of season years to scrape
            save_csv: Whether to save data to CSV files
            save_db: Whether to save data to database
            
        Returns:
            Dictionary mapping season to DataFrame
        """
        results = {}
        
        for season in seasons:
            logger.info(f"Processing season {season}")
            
            # Fetch data
            soup = self.fetch_season_data(season)
            if soup is None:
                logger.error(f"Skipping season {season} due to fetch failure")
                continue
            
            # Parse data
            df = self.parse_player_stats(soup, season)
            if df.empty:
                logger.error(f"No data parsed for season {season}")
                continue
            
            # Handle duplicates
            df = self.handle_duplicates(df)
            
            # Save data
            if save_csv:
                self.save_to_csv(df, season)
            
            if save_db:
                self.save_to_database(df, season)
            
            results[season] = df
            
            # Be respectful to the server
            time.sleep(3)
        
        logger.info(f"Completed scraping {len(results)} seasons")
        return results
    
    def get_season_stats(self, season: int) -> Optional[pd.DataFrame]:
        """
        Retrieve stats for a specific season from database
        
        Args:
            season: NBA season year
            
        Returns:
            DataFrame with season stats or None
        """
        session = self.Session()
        try:
            query = session.query(PlayerStats).filter(PlayerStats.season == season)
            df = pd.read_sql(query.statement, session.bind)
            logger.info(f"Retrieved {len(df)} records for season {season}")
            return df
        except Exception as e:
            logger.error(f"Error retrieving season stats: {str(e)}")
            return None
        finally:
            session.close()
    
    def get_top_players(self, season: int, stat: str = 'points', limit: int = 20) -> Optional[pd.DataFrame]:
        """
        Get top players for a specific season and stat
        
        Args:
            season: NBA season year
            stat: Stat to sort by (e.g., 'points', 'assists', 'rebounds')
            limit: Number of players to return
            
        Returns:
            DataFrame with top players
        """
        df = self.get_season_stats(season)
        if df is None or df.empty:
            return None
        
        # Map common stat names to column names
        stat_mapping = {
            'points': 'points',
            'pts': 'points',
            'assists': 'assists',
            'ast': 'assists',
            'rebounds': 'total_rebounds',
            'reb': 'total_rebounds',
            'steals': 'steals',
            'stl': 'steals',
            'blocks': 'blocks',
            'blk': 'blocks'
        }
        
        column_name = stat_mapping.get(stat.lower(), stat)
        
        if column_name not in df.columns:
            logger.warning(f"Stat '{stat}' not found in data")
            return None
        
        top_players = df.nlargest(limit, column_name)
        return top_players[['player_name', 'team', 'position', column_name, 'games_played', 'minutes_per_game']]


# Example usage
if __name__ == "__main__":
    scraper = NBAStatsScraper()
    
    # Scrape recent seasons
    seasons_to_scrape = [2022, 2023, 2024]
    results = scraper.scrape_seasons(seasons_to_scrape)
    
    # Get top scorers for 2024
    top_scorers = scraper.get_top_players(2024, stat='points', limit=10)
    if top_scorers is not None:
        print("\nTop 10 Scorers (2024 Season):")
        print(top_scorers.to_string(index=False))
