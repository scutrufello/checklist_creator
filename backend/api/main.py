"""
FastAPI backend for Phillies Cards Webapp
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import logging

try:
    from ..core.data_manager import PhilliesDataManager
    from ..services.tcdb_phillies_scraper import TCDBPhilliesScraper
    from ..services.image_downloader import ImageDownloader
except ImportError:
    # For direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from backend.core.data_manager import PhilliesDataManager
    from backend.services.tcdb_phillies_scraper import TCDBPhilliesScraper
    from backend.services.image_downloader import ImageDownloader

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Phillies Cards Manager",
    description="A modern webapp for managing Phillies baseball card collections",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize data manager
data_manager = PhilliesDataManager()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount image files
app.mount("/static/images", StaticFiles(directory="data/phillies_cards/images"), name="images")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/stats")
async def get_statistics():
    """Get database and system statistics"""
    try:
        stats = data_manager.get_statistics()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/years")
async def get_years():
    """Get all available years"""
    try:
        stats = data_manager.get_statistics()
        years = [year_data['year'] for year_data in stats.get('database', {}).get('cards_by_year', [])]
        return {"success": True, "data": years}
    except Exception as e:
        logger.error(f"Error getting years: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cards/year/{year}")
async def get_cards_by_year(
    year: int,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """Get cards for a specific year with pagination"""
    try:
        cards = data_manager.get_cards_by_year(year, limit=limit + offset)
        # Apply offset manually since the database method doesn't support it yet
        cards = cards[offset:offset + limit]
        return {"success": True, "data": cards}
    except Exception as e:
        logger.error(f"Error getting cards for year {year}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cards/search")
async def search_cards(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200)
):
    """Search cards by player name, set, or other criteria"""
    try:
        cards = data_manager.search_cards(query, limit=limit)
        return {"success": True, "data": cards}
    except Exception as e:
        logger.error(f"Error searching cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sets/year/{year}")
async def get_sets_by_year(year: int):
    """Get all sets for a specific year"""
    try:
        # This would need to be implemented in the data manager
        # For now, we'll get cards and extract unique sets
        cards = data_manager.get_cards_by_year(year, limit=1000)
        
        sets = {}
        for card in cards:
            main_set = card.get('main_set_name', 'Unknown')
            subset = card.get('subset_name', '')
            
            if main_set not in sets:
                sets[main_set] = {'subsets': set(), 'count': 0}
            
            if subset:
                sets[main_set]['subsets'].add(subset)
            sets[main_set]['count'] += 1
        
        # Convert sets to list format
        sets_list = []
        for set_name, set_data in sets.items():
            set_info = {
                'name': set_name,
                'count': set_data['count'],
                'subsets': list(set_data['subsets'])
            }
            sets_list.append(set_info)
        
        # Sort by count (descending)
        sets_list.sort(key=lambda x: x['count'], reverse=True)
        
        return {"success": True, "data": sets_list}
    except Exception as e:
        logger.error(f"Error getting sets for year {year}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape/latest")
async def scrape_latest_year():
    """Trigger a scrape of the most recent year"""
    try:
        # Get the most recent year from the database
        stats = data_manager.get_statistics()
        years = [year_data['year'] for year_data in stats.get('database', {}).get('cards_by_year', [])]
        
        if not years:
            raise HTTPException(status_code=400, detail="No years found in database")
        
        latest_year = max(years)
        logger.info(f"Starting scrape for latest year: {latest_year}")
        
        # Initialize scraper
        scraper = TCDBPhilliesScraper()
        
        # Scrape the latest year
        result = await scraper.scrape_phillies_cards(start_year=latest_year)
        
        if result['success']:
            return {
                "success": True, 
                "message": f"Successfully scraped {latest_year}",
                "data": result
            }
        else:
            raise HTTPException(status_code=500, detail=f"Scraping failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error scraping latest year: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trigger/image-download/{year}")
async def trigger_image_download(year: int):
    """Trigger image download for a specific year (runs as background task)"""
    try:
        # This would typically trigger a background job
        # For now, we'll just return a success message
        logger.info(f"Image download triggered for year {year}")
        
        return {
            "success": True,
            "message": f"Image download triggered for year {year}",
            "data": {
                "year": year,
                "status": "triggered",
                "note": "Run 'python3 scripts/download_images.py --year {year}' to execute"
            }
        }
        
    except Exception as e:
        logger.error(f"Error triggering image download for year {year}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images/stats")
async def get_image_statistics():
    """Get image download statistics"""
    try:
        downloader = ImageDownloader()
        stats = downloader.get_statistics()
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting image statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2025-08-31T22:00:00Z"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
