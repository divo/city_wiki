# Tech Stack

## Dataset Creation Tool (This Codebase)

### Framework & Runtime

- **Application Framework:** Django 4.2+
- **Language/Runtime:** Python 3.x
- **Package Manager:** uv (fast Python package manager)

### Frontend (Web Console)

- **Templating:** Django Templates
- **CSS Framework:** Custom/minimal styling
- **JavaScript:** Vanilla JS for interactive features

### Database & Storage

- **Database:** SQLite (local development database)
- **ORM:** Django ORM
- **Media Storage:** Local filesystem (`media/` directory)

### Background Processing

- **Task Queue:** Celery 5.5+
- **Message Broker:** Redis
- **Workflow Orchestration:** Prefect 3.4+

### External APIs & Services

- **LLM Provider:** OpenAI API (GPT-4 Turbo)
- **Geocoding:** Mapbox Geocoding API
- **Wiki Data:** MediaWiki API (WikiVoyage)
- **Map Data:** OpenStreetMap (via local PBF files with Pyrosm)

### Key Libraries

- **Wiki Parsing:** wikitextparser, mwapi
- **Geospatial:** geopy, shapely, geopandas, pyrosm
- **Text Matching:** thefuzz (fuzzy string matching)
- **Image Processing:** Pillow
- **HTTP Client:** requests
- **Data Processing:** pandas

### Version Tracking

- **Model History:** django-reversion (tracks POI edit history)

---

## Mobile App (Separate Codebase)

### Framework & Runtime

- **Application Framework:** React Native
- **Language:** TypeScript/JavaScript

### Data Consumption

- **Data Source:** Pre-built JSON datasets from S3
- **Offline Support:** Local storage of downloaded city data

---

## Distribution & Infrastructure

### Data Distribution

- **Storage:** AWS S3 (city dataset hosting)
- **Format:** JSON exports optimized for mobile consumption

### Web Access (User Guide)

- **Authentication:** Basic auth for guide access
- **Hosting:** Minimal web server (specifics TBD)

---

## Development Environment

### Local Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv sync

# Run Django development server
python manage.py runserver

# Run Redis (required for Celery)
redis-server

# Run Celery worker
celery -A city_wiki worker -l INFO --pool=solo

# Run Prefect server and worker
uv run prefect server start
uv run prefect worker start --pool "import-pool"
```

### Environment Variables

- `OPENAI_API_KEY` - OpenAI API key for LLM features
- `MAPBOX_TOKEN` - Mapbox API key for geocoding

### External Data Files

- **OSM PBF Files:** Downloaded from Geofabrik for local OSM ID matching
  - Example: `./pbf/greater-london-latest.osm.pbf`
  - Source: https://download.geofabrik.de/
