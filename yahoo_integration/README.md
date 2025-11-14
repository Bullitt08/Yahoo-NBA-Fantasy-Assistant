# Yahoo Fantasy Basketball Integration

Complete Yahoo Fantasy Sports API v2 integration for NBA fantasy basketball leagues.

## Features

- **OAuth 2.0 Authentication**: Secure Yahoo login with automatic token refresh
- **League Management**: Fetch user's leagues, teams, rosters, and standings
- **Player Data Merging**: Combines Yahoo Fantasy data with real NBA stats from Basketball Reference
- **Database Storage**: Saves all data to SQLite/PostgreSQL for analysis
- **RESTful API**: Clean Flask endpoints for frontend integration
- **Smart Caching**: Reduces API calls with intelligent caching
- **Player Matching**: Fuzzy matching algorithm to link Yahoo players with NBA database

## Installation

### 1. Install Dependencies

```bash
pip install requests-oauthlib sqlalchemy
```

### 2. Set Up Yahoo API Credentials

1. Go to [Yahoo Developer Network](https://developer.yahoo.com/apps/)
2. Create a new app with the following:
   - **App Name**: Your app name
   - **Application Type**: Web Application
   - **Redirect URI**: `http://localhost:5000/yahoo/auth/callback`
   - **API Permissions**: Fantasy Sports (Read)

3. Copy your Client ID and Client Secret

### 3. Configure Environment Variables

Add to your `.env` file:

```env
YAHOO_CLIENT_ID=your_client_id_here
YAHOO_CLIENT_SECRET=your_client_secret_here
YAHOO_REDIRECT_URI=http://localhost:5000/yahoo/auth/callback
YAHOO_DATABASE_URL=sqlite:///yahoo_fantasy.db
```

### 4. Register Blueprint in Flask App

In `app.py`:

```python
from yahoo_integration.routes import yahoo_bp

app.register_blueprint(yahoo_bp)
```

## Usage

### Authentication Flow

1. **User clicks "Login with Yahoo"** → redirects to `/yahoo/auth/login`
2. **Yahoo authorization page** → user grants permissions
3. **Yahoo redirects back** → `/yahoo/auth/callback` handles token exchange
4. **User is authenticated** → token stored in session

### API Endpoints

#### Authentication

```http
GET /yahoo/auth/login
```
Start Yahoo OAuth flow

```http
GET /yahoo/auth/callback?code=...
```
Handle OAuth callback

```http
GET /yahoo/auth/status
```
Check if user is authenticated

#### Leagues

```http
GET /yahoo/leagues?season=2024-25
```
Get user's fantasy leagues

**Response:**
```json
{
  "success": true,
  "leagues": [
    {
      "league_key": "428.l.12345",
      "league_id": "12345",
      "name": "My Fantasy League",
      "season": "2024-25",
      "num_teams": 12,
      "scoring_type": "head",
      "current_week": 5
    }
  ]
}
```

#### Teams

```http
GET /yahoo/league/428.l.12345/teams?include_roster=true
```
Get all teams in a league (optionally with rosters)

**Response:**
```json
{
  "success": true,
  "teams": [
    {
      "team_key": "428.l.12345.t.1",
      "name": "Team Name",
      "managers": [{"nickname": "Manager Name"}],
      "roster": [...]
    }
  ]
}
```

#### Roster

```http
GET /yahoo/team/428.l.12345.t.1/roster
```
Get team roster with merged NBA stats

**Response:**
```json
{
  "success": true,
  "roster": [
    {
      "player_key": "428.p.1234",
      "name": "Luka Dončić",
      "position": "PG,SG",
      "team": "DAL",
      "is_undroppable": true,
      "nba_stats": {
        "games_played": 70,
        "minutes": 36.2,
        "stats": {
          "points": 33.9,
          "rebounds": 9.2,
          "assists": 9.8,
          "steals": 1.4,
          "blocks": 0.5
        }
      }
    }
  ],
  "match_report": {
    "total_players": 13,
    "matched": 12,
    "match_rate": 92.3
  }
}
```

#### Free Agents

```http
GET /yahoo/league/428.l.12345/free_agents?position=PG&count=25
```
Get available free agents

## Frontend Integration

### Login Button

```html
<a href="/yahoo/auth/login" class="btn btn-primary">
  Login with Yahoo Fantasy
</a>
```

### JavaScript Example

```javascript
// Check auth status
async function checkYahooAuth() {
    const response = await fetch('/yahoo/auth/status');
    const data = await response.json();
    return data.authenticated;
}

// Load leagues
async function loadLeagues() {
    const response = await fetch('/yahoo/leagues?season=2024-25');
    const data = await response.json();
    
    if (data.success) {
        data.leagues.forEach(league => {
            console.log(league.name, league.num_teams);
        });
    }
}

// Load team roster with NBA stats
async function loadRoster(teamKey) {
    const response = await fetch(`/yahoo/team/${teamKey}/roster`);
    const data = await response.json();
    
    if (data.success) {
        data.roster.forEach(player => {
            console.log(
                `${player.name}: ${player.nba_stats?.stats.points || 'N/A'} PPG`
            );
        });
    }
}
```

## Data Models

### League
- `league_key`: Unique Yahoo league identifier
- `name`: League name
- `season`: Season year
- `num_teams`: Number of teams
- `scoring_type`: head, point, or headpoint
- `stat_categories`: Scoring categories
- `roster_positions`: Position requirements

### Team
- `team_key`: Unique Yahoo team identifier
- `name`: Team name
- `managers`: List of team managers
- `roster`: List of players on team
- `team_standings`: Ranking and record

### YahooPlayer
- `player_key`: Unique Yahoo player identifier
- `name`: Player full name
- `position`: Eligible positions (comma-separated)
- `team`: NBA team abbreviation
- `is_undroppable`: Whether player can be dropped
- `percent_owned`: Ownership percentage
- `nba_stats`: Merged real NBA statistics

## Database Schema

All data is automatically saved to the database:

- **yahoo_leagues**: League information
- **yahoo_teams**: Team details and managers
- **yahoo_players**: Player data with NBA stats
- **yahoo_roster_players**: Team roster links
- **yahoo_transactions**: League transactions

## Player Matching

The integration automatically matches Yahoo Fantasy players with real NBA stats:

1. **Exact name matching** (fastest)
2. **Fuzzy name matching** using difflib (handles spelling variations)
3. **Team + position matching** (for edge cases)

Match rate typically exceeds 90% for active rosters.

## Rate Limiting

- Automatic rate limiting: 100ms between requests
- Yahoo API limit: 10,000 calls per day
- Intelligent caching reduces API calls

## Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message here"
}
```

Common errors:
- `401`: Not authenticated
- `404`: Resource not found
- `500`: API or server error

## Example: Complete Workflow

```python
from yahoo_integration import YahooFantasyClient, YahooDatabase
from yahoo_integration.player_matcher import PlayerMatcher
from data import DataManager

# 1. Initialize
client = YahooFantasyClient()
db = YahooDatabase()
data_manager = DataManager()

# 2. Authenticate (in web flow)
# User visits /yahoo/auth/login, completes OAuth, returns to callback

# 3. Get leagues
leagues = client.get_user_leagues(season='2024-25')
for league in leagues:
    db.save_league(league.__dict__)

# 4. Get teams and rosters
teams = client.get_league_teams(leagues[0].league_key)
for team in teams:
    roster = client.get_team_roster(team.team_key)
    
    # 5. Merge with NBA stats
    nba_players = data_manager.get_all_nba_players(season='2024-25')
    matcher = PlayerMatcher(nba_players)
    merged_roster = matcher.batch_merge(roster)
    
    # 6. Save to database
    for player in merged_roster:
        db.save_player(player.__dict__)
```

## Testing

Test the integration without Yahoo credentials:

```bash
# Check API documentation
curl http://localhost:5000/yahoo/docs

# Test endpoints (after authentication)
curl http://localhost:5000/yahoo/leagues
curl http://localhost:5000/yahoo/league/428.l.12345/teams
```

**Note**: This application is still under development. Some features may not be fully functional yet.