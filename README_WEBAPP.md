# Phillies Cards Manager Webapp

A modern, responsive web application for managing Phillies baseball card collections.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Virtual environment activated
- All dependencies installed (`pip install -r requirements.txt`)

### Starting the Webapp

1. **Activate your virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Start the webapp:**
   ```bash
   python3 start_webapp.py
   ```

3. **Open your browser:**
   - Main app: http://localhost:8000
   - API docs: http://localhost:8000/docs

## 🎯 Features

### ✅ Implemented
- **Modern UI**: Responsive design that works on desktop and mobile
- **Year/Set/Card Hierarchy**: Clear navigation through the collection structure
- **Visual Card Display**: Cards shown with metadata, checkboxes for ownership
- **Search Functionality**: Search across players, sets, and card details
- **Settings Panel**: Database statistics and scrape latest year functionality
- **Card Details Modal**: Click any card to see full details and TCDB links

### 🔄 Data Structure
- **Years** → **Sets** → **Cards** hierarchy
- Each level shows relevant information and navigation
- Cards display with metadata tags (RC, AU, RELIC, SN, etc.)

### 🎨 UI Components
- **Header**: App title with settings button
- **Search Bar**: Global search functionality
- **Navigation Tabs**: Switch between Years and Search Results
- **Grid Layouts**: Responsive card-based layouts for all views
- **Modals**: Settings and card detail popups

## 🔧 API Endpoints

- `GET /` - Main HTML page
- `GET /api/health` - Health check
- `GET /api/stats` - Database statistics
- `GET /api/years` - Available years
- `GET /api/sets/year/{year}` - Sets for a specific year
- `GET /api/cards/year/{year}` - Cards for a specific year
- `GET /api/cards/search` - Search cards
- `POST /api/scrape/latest` - Trigger scrape of latest year

## 📱 Mobile Support

The webapp is fully responsive and includes:
- Mobile-optimized layouts
- Touch-friendly interactions
- Responsive grids that adapt to screen size
- Mobile-friendly navigation

## 🎨 Customization

### Styling
- CSS variables for easy theming
- Modern design with gradients and shadows
- Consistent spacing and typography
- Hover effects and transitions

### JavaScript
- Modular class-based architecture
- Event-driven interactions
- Async API calls with error handling
- Dynamic content loading

## 🚨 Troubleshooting

### Common Issues

1. **Import Errors**: Make sure you're running from the project root
2. **Port Conflicts**: Change the port in `start_webapp.py` if 8000 is busy
3. **Database Issues**: Ensure the database file exists and is accessible

### Debug Mode

The webapp runs with auto-reload enabled for development. Any changes to Python files will automatically restart the server.

## 🔮 Future Enhancements

- [ ] Card ownership persistence
- [ ] Image downloading and display
- [ ] Advanced filtering and sorting
- [ ] Export functionality
- [ ] User authentication
- [ ] Collection statistics and analytics

## 📁 File Structure

```
static/
├── index.html          # Main HTML page
├── styles.css          # CSS styles
└── app.js             # JavaScript application

backend/
└── api/
    └── main.py        # FastAPI backend

start_webapp.py        # Startup script
```

## 🎉 Success!

Your Phillies Cards Manager webapp is now running! Navigate through years, sets, and cards to explore your collection. Use the search to find specific players or sets, and check out the settings panel to trigger new data scraping.
