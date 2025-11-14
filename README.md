# Yahoo NBA Fantasy Assistant 🏀

A comprehensive full-stack web application for Yahoo NBA Fantasy Basketball that integrates Yahoo Fantasy Sports API with real NBA statistics to provide intelligent draft assistance, Monte Carlo matchup simulation, and data-driven player recommendations. Built with Flask/Python backend, featuring OAuth 2.0 authentication, multi-season weighted statistical analysis, and interactive data visualization.

## 🌟 Features

### ✅ Real NBA Data Integration
- **Live NBA Player Database**: 450+ active NBA players with real 2025-26 season statistics
- **Stats.NBA.com API Integration**: Official NBA statistics including points, rebounds, assists, shooting percentages
- **Real-time Updates**: Fresh data from the most current NBA season
- **Comprehensive Stats**: Complete player profiles with advanced metrics

### 🎯 Core Features
- **Draft Assistant**: Historical analysis with weighted averages (2024-25: 60%, 2023-24: 30%, 2022-23: 10%)
- **Matchup Simulator**: Monte Carlo simulation with 10,000 iterations
- **Recommendation Engine**: Intelligent player recommendations based on team needs
- **Interactive NBA Players Database**: Searchable, filterable player database with live stats
- **Yahoo OAuth2 Integration**: Secure authentication with Yahoo Fantasy Sports API

### 📊 Dashboard Features
- **Live NBA Stats Overview**: Top scorers, rebounders, and assist leaders
- **Player Search & Filtering**: Advanced filtering by position, team, and performance metrics
- **Real-time Fantasy Scoring**: Calculated using official NBA statistics
- **Responsive Design**: Mobile-friendly interface with Bootstrap 5

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Flask 3.1.2
- NBA Stats API access (built-in)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd "National Zaza Association Helper"
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your Yahoo API credentials (optional for demo mode)
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Open your browser**
   ```
   http://127.0.0.1:5000
   ```

## 🔧 Configuration

### Environment Variables
Create a `.env` file with the following variables:

```env
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True

# Yahoo Fantasy Sports API (Optional - Demo mode available)
YAHOO_CLIENT_ID=your-yahoo-client-id
YAHOO_CLIENT_SECRET=your-yahoo-client-secret
```

### Yahoo API Setup (Optional)
1. Create a Yahoo Developer account at [developer.yahoo.com](https://developer.yahoo.com)
2. Create a new application
3. Get your Client ID and Client Secret
4. Set redirect URI to `http://localhost:5000/callback`

## 📱 API Endpoints

### NBA Players API
```http
GET /api/players?limit=50&position=PG&season=2023-24
```
Returns real NBA player data with statistics.

### Free Agents API
```http
GET /api/free_agents?count=20&position=C
```
Returns available players ranked by fantasy value.

### Player Details API
```http
GET /api/player/<player_id>
```
Returns detailed player statistics and history.

## 🏗️ Architecture

### Backend Modules
- `app.py` - Flask application with real NBA data integration
- `auth.py` - Yahoo OAuth2 authentication
- `data.py` - **NBA Stats API integration** with Stats.NBA.com
- `draft.py` - Historical analysis using real player data
- `simulation.py` - Monte Carlo matchup simulation
- `recommendation.py` - AI-powered player recommendations

### Frontend
- `templates/` - Responsive HTML templates with Bootstrap 5
- `players.html` - **Interactive NBA player database**
- Real-time JavaScript for dynamic content loading

## 📈 NBA Data Integration

### Data Sources
1. **Primary**: Stats.NBA.com official API
2. **Coverage**: 500+ active NBA players
3. **Statistics**: Complete 2023-24 season data
4. **Update Frequency**: Real-time during NBA season

### Supported Statistics
- Basic Stats: Points, Rebounds, Assists, Steals, Blocks
- Shooting: FG%, 3P%, FT%, FGM/FGA, 3PM/3PA, FTM/FTA
- Advanced: Minutes, Games Played, Turnovers
- Fantasy: Calculated fantasy scores based on league settings

## 🎮 Demo Mode

The application includes a **demo mode** that works without Yahoo API credentials:
- Pre-loaded with real NBA player data
- Sample fantasy teams and matchups
- Full functionality demonstration
- Perfect for testing and development

## 🔄 Season Data

**Current Season**: 2025-26 NBA Fantasy Season  
**Data Baseline**: 2024-25 season (most recent completed)  
**Historical Analysis**: Weighted across 3 seasons
- 2024-25 season: 60% weight
- 2023-24 season: 30% weight  
- 2022-23 season: 10% weight

## 🧪 Testing

### Run Tests
```bash
# Test NBA data integration
python -c "from data import DataManager; dm = DataManager(); print(f'Loaded {len(dm.get_all_nba_players())} NBA players')"

# Test API endpoints
curl http://127.0.0.1:5000/api/players?limit=5
curl http://127.0.0.1:5000/api/free_agents?count=5
```

### Verify Installation
1. Check if all 500+ NBA players load correctly
2. Verify real statistics display properly
3. Test filtering and search functionality
4. Confirm fantasy scoring calculations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add real NBA data integration'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This application is for educational and personal use only. It is not affiliated with Yahoo, NBA, or any official fantasy sports platforms. NBA statistics are used in accordance with publicly available data policies.

---

**Built with ❤️ using Flask, NBA Stats API, and real NBA data integration**