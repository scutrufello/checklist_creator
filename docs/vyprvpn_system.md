# VyprVPN Dynamic Server Update System

## Overview

The VyprVPN Dynamic Server Update System automatically fetches and maintains an up-to-date list of VyprVPN server hostnames from their official support page. This ensures your VPN configurations always use the latest, most reliable server endpoints.

## Features

- **🔄 Automatic Updates**: Daily updates at 2 AM to keep server list current
- **📊 Change Detection**: Tracks added, removed, and modified servers
- **💾 Smart Caching**: Caches server data to reduce API calls
- **🌍 Geographic Organization**: Servers organized by region and country
- **🔍 Search & Filter**: Find servers by hostname, region, or country
- **📡 API Integration**: RESTful API endpoints for programmatic access
- **⏰ Scheduled Tasks**: Background scheduler for automated operations

## How It Works

### 1. Data Source
The system scrapes server information from the official VyprVPN support page:
[VyprVPN Server Addresses](https://support.vyprvpn.com/hc/en-us/articles/360037728912-What-are-the-VyprVPN-server-addresses)

### 2. Update Schedule
- **Automatic**: Daily at 2:00 AM
- **Manual**: On-demand via API or CLI
- **Smart**: Only updates when changes are detected

### 3. Data Processing
- Parses HTML table data
- Extracts region, country, city, and hostname information
- Validates and cleans data
- Stores in structured format

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   VyprVPN      │    │   Scraper       │    │   Cache        │
│   Support Page │───▶│   Service       │───▶│   Storage      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Scheduler      │
                       │   Service        │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   API           │
                       │   Endpoints     │
                       └──────────────────┘
```

## Components

### 1. VyprVPN Scraper Service (`backend/services/vyprvpn_scraper.py`)
- Fetches HTML content from VyprVPN support page
- Parses server table data
- Manages server data cache
- Detects changes between updates

### 2. Task Scheduler (`backend/services/scheduler.py`)
- Manages scheduled tasks
- Runs daily VyprVPN server updates
- Provides task status and control

### 3. API Endpoints (`backend/api/vyprvpn.py`)
- RESTful API for server management
- Server listing and search
- Update control and status

### 4. Management Scripts
- `scripts/manage_vyprvpn.py` - CLI management tool
- `scripts/test_vyprvpn_scraper.py` - Testing and validation

## API Endpoints

### Server Management
- `GET /api/v1/vyprvpn/servers` - List all servers
- `GET /api/v1/vyprvpn/servers/region/{region}` - Servers by region
- `GET /api/v1/vyprvpn/servers/country/{country}` - Servers by country
- `GET /api/v1/vyprvpn/servers/search/{hostname}` - Search by hostname
- `GET /api/v1/vyprvpn/servers/count` - Total server count

### System Control
- `POST /api/v1/vyprvpn/update` - Update server list
- `GET /api/v1/vyprvpn/status` - System status
- `GET /api/v1/vyprvpn/scheduler/status` - Scheduler status
- `GET /api/v1/vyprvpn/health` - Health check

### Utility Endpoints
- `GET /api/v1/vyprvpn/servers/random` - Random server
- `GET /api/v1/vyprvpn/servers/fastest` - Fastest servers (US-based)
- `GET /api/v1/vyprvpn/regions` - Available regions
- `GET /api/v1/vyprvpn/countries` - Available countries

## Usage

### Command Line Interface

#### Show System Status
```bash
python scripts/manage_vyprvpn.py status
```

#### Update Server List
```bash
# Normal update (only if needed)
python scripts/manage_vyprvpn.py update

# Force update (ignore cache)
python scripts/manage_vyprvpn.py update --force
```

#### List Servers
```bash
# All servers
python scripts/manage_vyprvpn.py list

# By region
python scripts/manage_vyprvpn.py list --region "North America"

# By country
python scripts/manage_vyprvpn.py list --country "U.S."

# Limit results
python scripts/manage_vyprvpn.py list --limit 50
```

#### Search for Server
```bash
python scripts/manage_vyprvpn.py search us1.vyprvpn.com
```

#### Check Scheduler
```bash
python scripts/manage_vyprvpn.py scheduler
```

#### Test Connectivity
```bash
python scripts/manage_vyprvpn.py test
```

#### Export Data
```bash
python scripts/manage_vyprvpn.py export --output my_servers.json
```

### API Usage

#### Update Server List
```bash
curl -X POST "http://localhost:8000/api/v1/vyprvpn/update"
```

#### Get All Servers
```bash
curl "http://localhost:8000/api/v1/vyprvpn/servers"
```

#### Get Servers by Region
```bash
curl "http://localhost:8000/api/v1/vyprvpn/servers/region/North%20America"
```

#### Get System Status
```bash
curl "http://localhost:8000/api/v1/vyprvpn/status"
```

## Configuration

### Environment Variables
```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=False

# Scheduler Configuration
VYPRVPN_UPDATE_HOUR=2  # Daily update hour (0-23)
VYPRVPN_CACHE_FILE=vyprvpn_servers.json
```

### Cache File Location
Server data is cached in:
- **Default**: `vyprvpn_servers.json` (in working directory)
- **Custom**: Set via `VYPRVPN_CACHE_FILE` environment variable

## Data Structure

### Server Object
```json
{
  "region": "North America",
  "country": "U.S.",
  "city": "Austin, TX",
  "hostname": "us3.vyprvpn.com",
  "last_verified": "2024-08-24T10:00:00Z"
}
```

### Cache File Format
```json
{
  "last_update": "2024-08-24T10:00:00Z",
  "servers": {
    "U.S._Austin_TX": {
      "region": "North America",
      "country": "U.S.",
      "city": "Austin, TX",
      "hostname": "us3.vyprvpn.com",
      "last_verified": "2024-08-24T10:00:00Z"
    }
  }
}
```

## Monitoring and Logging

### Log Files
- Application logs: Check your application logging configuration
- Scheduler logs: Integrated with application logging
- Cache operations: Logged for debugging

### Health Checks
```bash
# API health check
curl "http://localhost:8000/api/v1/vyprvpn/health"

# System status
curl "http://localhost:8000/api/v1/vyprvpn/status"
```

### Metrics
- Total server count
- Last update timestamp
- Update frequency
- Change detection statistics

## Troubleshooting

### Common Issues

#### 1. Update Fails
```bash
# Check logs for errors
python scripts/manage_vyprvpn.py update --force

# Verify internet connectivity
python scripts/manage_vyprvpn.py test
```

#### 2. No Servers Available
```bash
# Check cache file
ls -la vyprvpn_servers.json

# Force refresh
python scripts/manage_vyprvpn.py update --force
```

#### 3. Scheduler Not Running
```bash
# Check scheduler status
python scripts/manage_vyprvpn.py scheduler

# Verify application startup
curl "http://localhost:8000/api/v1/vyprvpn/scheduler/status"
```

### Debug Mode
Enable debug logging by setting `DEBUG=True` in environment variables.

## Security Considerations

### Data Privacy
- No personal data is collected or stored
- Only public server information is cached
- Cache files contain only hostname and location data

### Rate Limiting
- Respects VyprVPN's servers
- Implements reasonable update intervals
- Uses appropriate User-Agent headers

### Access Control
- API endpoints are public (configure as needed)
- No authentication required (add if needed for production)
- Cache files are readable by application user

## Performance

### Update Frequency
- **Recommended**: Daily updates (default)
- **Maximum**: No hard limit, but respect server resources
- **Minimum**: Once per week for critical systems

### Cache Efficiency
- Reduces unnecessary API calls
- Only updates when changes detected
- Efficient change detection algorithm

### Resource Usage
- **Memory**: Minimal (server list in memory)
- **Storage**: Small JSON cache file
- **Network**: One HTTP request per update

## Integration

### With VPN Management
The VyprVPN server list integrates with your existing VPN management system:

1. **OpenVPN Configs**: Use hostnames from the server list
2. **Connection Management**: Select servers based on location/performance
3. **Failover**: Automatic server switching using updated hostnames

### With Web Scraping
- Use different server locations for scraping
- Rotate through available servers
- Maintain geographic diversity

## Development

### Adding New Features
1. Extend the `VyprVPNServerScraper` class
2. Add new API endpoints in `vyprvpn.py`
3. Update the management script
4. Add tests and documentation

### Testing
```bash
# Run comprehensive tests
python scripts/test_vyprvpn_scraper.py

# Test specific components
python -m pytest backend/tests/test_vyprvpn.py
```

### Contributing
1. Follow existing code patterns
2. Add appropriate logging
3. Include error handling
4. Update documentation

## Roadmap

### Phase 1: Core Functionality ✅
- [x] Basic server scraping
- [x] Daily updates
- [x] API endpoints
- [x] CLI management

### Phase 2: Enhanced Features
- [ ] Server performance monitoring
- [ ] Geographic load balancing
- [ ] Multiple VPN provider support
- [ ] Advanced filtering options

### Phase 3: Production Features
- [ ] Authentication and authorization
- [ ] Rate limiting and quotas
- [ ] Metrics and monitoring
- [ ] High availability support

## Support

### Getting Help
- Check the troubleshooting section above
- Review application logs
- Use the health check endpoints
- Test with the management scripts

### Reporting Issues
- Include error messages and logs
- Specify your environment details
- Provide steps to reproduce
- Check if it's a known issue

### Contributing
- Submit pull requests with clear descriptions
- Include tests for new functionality
- Update documentation as needed
- Follow the project's coding standards

---

**Last Updated**: August 24, 2024  
**Version**: 1.0.0  
**Status**: Production Ready
