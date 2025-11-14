"""
Database module for storing Yahoo Fantasy Basketball data

Uses SQLAlchemy for ORM and supports both SQLite and PostgreSQL
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

from .config import DATABASE_URL

Base = declarative_base()


class YahooLeague(Base):
    """Yahoo League database model"""
    __tablename__ = 'yahoo_leagues'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    league_key = Column(String(100), unique=True, nullable=False, index=True)
    league_id = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    season = Column(String(20), nullable=False)
    game_code = Column(String(20), default='nba')
    
    # League settings
    num_teams = Column(Integer, default=0)
    scoring_type = Column(String(50), default='head')
    draft_status = Column(String(50))
    current_week = Column(Integer, default=1)
    start_week = Column(Integer, default=1)
    end_week = Column(Integer, default=24)
    start_date = Column(String(20))
    end_date = Column(String(20))
    is_finished = Column(Boolean, default=False)
    
    # Additional data
    url = Column(String(500))
    stat_categories = Column(JSON)
    roster_positions = Column(JSON)
    settings = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    teams = relationship('YahooTeam', back_populates='league', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'league_key': self.league_key,
            'league_id': self.league_id,
            'name': self.name,
            'season': self.season,
            'game_code': self.game_code,
            'num_teams': self.num_teams,
            'scoring_type': self.scoring_type,
            'draft_status': self.draft_status,
            'current_week': self.current_week,
            'start_week': self.start_week,
            'end_week': self.end_week,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'is_finished': self.is_finished,
            'url': self.url,
            'stat_categories': self.stat_categories,
            'roster_positions': self.roster_positions,
            'settings': self.settings,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class YahooTeam(Base):
    """Yahoo Team database model"""
    __tablename__ = 'yahoo_teams'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_key = Column(String(100), unique=True, nullable=False, index=True)
    team_id = Column(String(50), nullable=False)
    league_key = Column(String(100), ForeignKey('yahoo_leagues.league_key'))
    
    # Team info
    name = Column(String(200), nullable=False)
    team_logo_url = Column(String(500))
    
    # Team stats
    waiver_priority = Column(Integer, default=0)
    number_of_moves = Column(Integer, default=0)
    number_of_trades = Column(Integer, default=0)
    clinched_playoffs = Column(Boolean, default=False)
    
    # Managers and standings (stored as JSON)
    managers = Column(JSON)
    team_standings = Column(JSON)
    team_points = Column(JSON)
    team_projected_points = Column(JSON)
    roster_adds = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    league = relationship('YahooLeague', back_populates='teams')
    roster_players = relationship('YahooRosterPlayer', back_populates='team', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'team_key': self.team_key,
            'team_id': self.team_id,
            'league_key': self.league_key,
            'name': self.name,
            'team_logo_url': self.team_logo_url,
            'waiver_priority': self.waiver_priority,
            'number_of_moves': self.number_of_moves,
            'number_of_trades': self.number_of_trades,
            'clinched_playoffs': self.clinched_playoffs,
            'managers': self.managers,
            'team_standings': self.team_standings,
            'team_points': self.team_points,
            'team_projected_points': self.team_projected_points,
            'roster_adds': self.roster_adds,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class YahooPlayerDB(Base):
    """Yahoo Player database model (cached player data)"""
    __tablename__ = 'yahoo_players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_key = Column(String(100), unique=True, nullable=False, index=True)
    player_id = Column(String(50), nullable=False, index=True)
    
    # Player info
    name = Column(String(200), nullable=False, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    position = Column(String(50))
    team = Column(String(50))
    team_abbr = Column(String(10))
    editorial_team_abbr = Column(String(10))
    
    # Additional info
    uniform_number = Column(String(10))
    display_position = Column(String(50))
    image_url = Column(String(500))
    is_undroppable = Column(Boolean, default=False)
    position_type = Column(String(10), default='P')
    
    # Ownership data
    percent_owned = Column(Float)
    ownership_data = Column(JSON)
    
    # Merged NBA stats from our database
    nba_stats = Column(JSON)
    season = Column(String(20), default='2024-25')
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'player_key': self.player_key,
            'player_id': self.player_id,
            'name': self.name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'position': self.position,
            'team': self.team,
            'team_abbr': self.team_abbr,
            'editorial_team_abbr': self.editorial_team_abbr,
            'uniform_number': self.uniform_number,
            'display_position': self.display_position,
            'image_url': self.image_url,
            'is_undroppable': self.is_undroppable,
            'position_type': self.position_type,
            'percent_owned': self.percent_owned,
            'ownership_data': self.ownership_data,
            'nba_stats': self.nba_stats,
            'season': self.season,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class YahooRosterPlayer(Base):
    """Link table for team rosters"""
    __tablename__ = 'yahoo_roster_players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_key = Column(String(100), ForeignKey('yahoo_teams.team_key'), nullable=False)
    player_key = Column(String(100), nullable=False, index=True)
    
    # Roster slot info
    selected_position = Column(String(50))
    is_starting = Column(Boolean, default=True)
    acquisition_type = Column(String(50))  # draft, add, trade, etc.
    acquisition_date = Column(DateTime)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    team = relationship('YahooTeam', back_populates='roster_players')


class YahooTransaction(Base):
    """Yahoo Fantasy Transactions"""
    __tablename__ = 'yahoo_transactions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_key = Column(String(100), unique=True, nullable=False, index=True)
    transaction_id = Column(String(50), nullable=False)
    league_key = Column(String(100), nullable=False, index=True)
    
    # Transaction details
    type = Column(String(50))  # add, drop, trade, etc.
    status = Column(String(50))
    timestamp = Column(DateTime)
    
    # Players and teams involved (stored as JSON)
    players = Column(JSON)
    teams = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'transaction_key': self.transaction_key,
            'transaction_id': self.transaction_id,
            'league_key': self.league_key,
            'type': self.type,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'players': self.players,
            'teams': self.teams,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class YahooDatabase:
    """Database manager for Yahoo Fantasy data"""
    
    def __init__(self, database_url: str = None):
        """Initialize database connection"""
        self.database_url = database_url or DATABASE_URL
        self.engine = create_engine(self.database_url, echo=False)
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get new database session"""
        return self.SessionLocal()
    
    # League operations
    def save_league(self, league_data: Dict) -> YahooLeague:
        """Save or update league data"""
        session = self.get_session()
        try:
            league = session.query(YahooLeague).filter_by(
                league_key=league_data['league_key']
            ).first()
            
            if league:
                # Update existing
                for key, value in league_data.items():
                    if hasattr(league, key):
                        setattr(league, key, value)
            else:
                # Create new
                league = YahooLeague(**league_data)
                session.add(league)
            
            session.commit()
            session.refresh(league)
            return league
        finally:
            session.close()
    
    def get_league(self, league_key: str) -> Optional[YahooLeague]:
        """Get league by key"""
        session = self.get_session()
        try:
            return session.query(YahooLeague).filter_by(league_key=league_key).first()
        finally:
            session.close()
    
    def get_all_leagues(self, season: str = None) -> List[YahooLeague]:
        """Get all leagues, optionally filtered by season"""
        session = self.get_session()
        try:
            query = session.query(YahooLeague)
            if season:
                query = query.filter_by(season=season)
            return query.all()
        finally:
            session.close()
    
    # Team operations
    def save_team(self, team_data: Dict) -> YahooTeam:
        """Save or update team data"""
        session = self.get_session()
        try:
            team = session.query(YahooTeam).filter_by(
                team_key=team_data['team_key']
            ).first()
            
            if team:
                # Update existing
                for key, value in team_data.items():
                    if hasattr(team, key):
                        setattr(team, key, value)
            else:
                # Create new
                team = YahooTeam(**team_data)
                session.add(team)
            
            session.commit()
            session.refresh(team)
            return team
        finally:
            session.close()
    
    def get_team(self, team_key: str) -> Optional[YahooTeam]:
        """Get team by key"""
        session = self.get_session()
        try:
            return session.query(YahooTeam).filter_by(team_key=team_key).first()
        finally:
            session.close()
    
    def get_league_teams(self, league_key: str) -> List[YahooTeam]:
        """Get all teams in a league"""
        session = self.get_session()
        try:
            return session.query(YahooTeam).filter_by(league_key=league_key).all()
        finally:
            session.close()
    
    # Player operations
    def save_player(self, player_data: Dict) -> YahooPlayerDB:
        """Save or update player data"""
        session = self.get_session()
        try:
            player = session.query(YahooPlayerDB).filter_by(
                player_key=player_data['player_key']
            ).first()
            
            if player:
                # Update existing
                for key, value in player_data.items():
                    if hasattr(player, key):
                        setattr(player, key, value)
            else:
                # Create new
                player = YahooPlayerDB(**player_data)
                session.add(player)
            
            session.commit()
            session.refresh(player)
            return player
        finally:
            session.close()
    
    def get_player(self, player_key: str) -> Optional[YahooPlayerDB]:
        """Get player by key"""
        session = self.get_session()
        try:
            return session.query(YahooPlayerDB).filter_by(player_key=player_key).first()
        finally:
            session.close()
    
    def get_player_by_name(self, name: str) -> Optional[YahooPlayerDB]:
        """Get player by name"""
        session = self.get_session()
        try:
            return session.query(YahooPlayerDB).filter_by(name=name).first()
        finally:
            session.close()
    
    # Roster operations
    def save_roster(self, team_key: str, player_keys: List[str]):
        """Save team roster"""
        session = self.get_session()
        try:
            # Remove old roster
            session.query(YahooRosterPlayer).filter_by(team_key=team_key).delete()
            
            # Add new roster
            for player_key in player_keys:
                roster_entry = YahooRosterPlayer(
                    team_key=team_key,
                    player_key=player_key
                )
                session.add(roster_entry)
            
            session.commit()
        finally:
            session.close()
    
    def get_roster(self, team_key: str) -> List[str]:
        """Get team roster (player keys)"""
        session = self.get_session()
        try:
            roster = session.query(YahooRosterPlayer).filter_by(team_key=team_key).all()
            return [r.player_key for r in roster]
        finally:
            session.close()
    
    # Transaction operations
    def save_transaction(self, transaction_data: Dict) -> YahooTransaction:
        """Save transaction"""
        session = self.get_session()
        try:
            transaction = YahooTransaction(**transaction_data)
            session.add(transaction)
            session.commit()
            session.refresh(transaction)
            return transaction
        finally:
            session.close()
    
    def get_league_transactions(self, league_key: str, limit: int = 50) -> List[YahooTransaction]:
        """Get recent transactions for a league"""
        session = self.get_session()
        try:
            return session.query(YahooTransaction).filter_by(
                league_key=league_key
            ).order_by(
                YahooTransaction.timestamp.desc()
            ).limit(limit).all()
        finally:
            session.close()
