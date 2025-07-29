# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

**Django Commands:**
- `python manage.py runserver` - Start the development server
- `python manage.py migrate` - Apply database migrations
- `python manage.py makemigrations` - Create new database migrations
- `python manage.py createsuperuser` - Create Django admin user
- `python manage.py collectstatic` - Collect static files for deployment
- `python manage.py shell` - Open Django shell

**Custom Management Commands:**
- `python manage.py dump_city <city_name>` - Export city data to JSON (located in cities/management/commands/)

**Development Environment:**
- `source .venv/bin/activate` - Activate virtual environment
- `uv sync` - Install dependencies (uses uv package manager)
- `uv add <package>` - Add a new dependency

**Celery (Background Tasks):**
- `celery -A city_wiki worker -l info` - Start Celery worker
- Redis must be running on localhost:6379 for Celery to work

**Prefect (Workflow Orchestration):**
- `uv run prefect server start` - Start Prefect server UI (http://localhost:4200)
- `uv run prefect worker start --pool "import-pool"` - Start Prefect worker
- `prefect deploy` - Deploy workflows defined in prefect.yaml
- Workflows are defined in the `workflow/` directory

## High-Level Architecture

**Core Structure:**
This is a Django-based city wiki application that scrapes and manages travel information from WikiVoyage and other sources.

**Key Apps:**
- `cities/` - Main Django app containing city, district, and point-of-interest models
- `workflow/` - Prefect workflow definitions for data import and processing
- `data_processing/` - Contains scrapers for Wikipedia and Wikivoyage
- `llm/` - LLM integration for content generation and processing

**Data Models (cities/models.py):**
- `City` - Represents cities with coordinates, images, WikiVoyage content
- `District` - City districts/neighborhoods with hierarchical relationships
- `PointOfInterest` - POIs categorized as see/eat/sleep/shop/drink/play
- `Validation` - Tracks data import errors and validation issues
- `PoiList` - Curated lists of POIs for cities

**Key Features:**
- Django Reversion integration for model history tracking
- Image management with automatic file path generation
- Celery for asynchronous task processing
- Prefect for workflow orchestration
- OpenAI API integration for content enhancement

**Database:** SQLite (db.sqlite3) - configured in settings.py

**Media Storage:** 
- City images: `media/cities/images/`
- POI images: `media/cities/images/pois/{city_name}/`

**Static Files:** Collected in `staticfiles/` directory

**Environment Variables:**
- `OPENAI_AI_KEY` - OpenAI API key for LLM features
- Uses python-dotenv to load from .env file

**Background Processing:**
- Celery with Redis backend for async tasks
- Import/enrichment tasks defined in cities/enrich_tasks.py and cities/fetch_tasks.py
- Prefect workflows in workflow/ directory for complex data processing pipelines

## Current Work (from Plan.md)

**Active Task:** Implement a full automated cleanup flow using Prefect in the `workflow/` folder.

**Main Entry Point:** `workflow/city_import.py#import_city` - ties the entire workflow together

**Completed Steps:**
- ✅ Fetch raw data from WikiVoyage
- ✅ Pause and wait to continue, geocode the main city coordinates
- ✅ Geocode missing addresses from GPS coords
- ✅ Geocode missing coordinates from addresses
- ✅ Find all duplicate POIs

**Remaining Steps:**
- ❌ De-duplicate POIs
- ❌ De-duplicate main city POIs
- ❌ Fetch OSM IDs for POIs (remote or local)
- ❌ Get hero image and pick the best of 10
- ❌ Use LLM to generate 10 things the city is famous for, then generate lists using POIs
- ❌ Cleanup all descriptions using LLM

**Current Focus - POI Deduplication Logic:**
- `enrich_tasks.py#dedup_main_city` finds all "Main City" POIs and duplicates
- Uses `detect_duplicate_pois` for duplicate detection
- Calls `/city/<city_name>/poi/merge` endpoint for merging
- `cities/views/pois.py#poi_merge` handles the merge logic (same as UI)
- Expects `keep_poi` and `remove_poi` parameters with `field_selections` for field overrides
- Automation logic should use best available values (non-null, longer text, highest rank)

**Branch Context:** Working on `prefect-workflow` branch with uncommitted changes to resolve.