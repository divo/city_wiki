"""
Service module for city import functionality.

This module encapsulates the core business logic of importing city data from
Wikivoyage, including POI processing, city creation/updates, and district handling.
This allows the same logic to be used by both Celery tasks and Prefect workflows.
"""

from django.db import transaction
from ..models import City, PointOfInterest, District, Validation
from mwapi.errors import APIError
from data_processing.wikivoyage_scraper import WikivoyageScraper
from typing import List, Tuple, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


def fetch_city_pois(city_name: str, depth: int = 0) -> Tuple[Optional[List], Optional[List], Optional[str]]:
    """
    Helper function to fetch POIs and handle API errors.
    
    Args:
        city_name: The name of the city to fetch data for
        depth: Current depth of recursion (used for error reporting)
        
    Returns:
        Tuple of (pois, district_pages, about_text) or (None, None, None) on error
    """
    try:
        scraper = WikivoyageScraper()
        return scraper.get_city_data(city_name)
    except APIError as response_error:
        logger.error(f"Non fatal API error for {city_name}: {response_error}")
        try:
            city = City.objects.get(name=city_name)
        except City.DoesNotExist:
            city = None
            logger.warning(f"Creating validation without city: {city_name} does not exist yet")
        
        Validation.objects.create(
            parent=city,  # Can be None now
            context='WikiImport',
            aggregate='FetchArticleError',
            specialized_aggregate='DistrictFetchError' if depth != 0 else 'CityFetchError',
            description=str(response_error)
        )
        return None, None, None
    except Exception as e:
        logger.error(f"Error fetching data for {city_name}: {str(e)}")
        return None, None, None


@transaction.atomic
def create_or_update_city(city_name: str, root_city_name: Optional[str] = None, about_text: Optional[str] = None) -> City:
    """
    Create or update a city record.
    
    Args:
        city_name: The name of the city or district
        root_city_name: The name of the root city (same as city_name for root tasks)
        about_text: The about text to save (only for root city)
        
    Returns:
        City object
    """
    # For root task, use city_name as root_city_name if not provided
    if not root_city_name:
        root_city_name = city_name
    
    # Create/update the root city
    city, created = City.objects.get_or_create(
        name=root_city_name,
        defaults={'country': 'Unknown'}
    )
    
    # Save about text only for the root city on first import
    if about_text and city_name == root_city_name:
        city.about = about_text
        city.save()
        logger.info(f"Saved about text for {city_name}")
        
    return city


@transaction.atomic
def create_or_get_district(district_name: str, city: City, parent_district_id: Optional[int] = None) -> District:
    """
    Create or get a district for a city.
    
    Args:
        district_name: Name of the district
        city: City object the district belongs to
        parent_district_id: ID of the parent district (None for root districts)
        
    Returns:
        District object
    """
    # Parse district name if it contains a slash
    if district_name and '/' in district_name:
        district_name = district_name.split('/', 1)[1]
    
    # Get parent district if specified
    parent_district = None
    if parent_district_id:
        try:
            parent_district = District.objects.get(id=parent_district_id)
        except District.DoesNotExist:
            logger.warning(f"Parent district with ID {parent_district_id} not found")
    
    # Create or get the district
    district, created = District.objects.get_or_create(
        name=district_name,
        city=city,
        defaults={'parent_district': parent_district}
    )
    
    return district


@transaction.atomic
def process_pois(city: City, pois: List, clear_existing: bool = False, 
                district_name: Optional[str] = None, parent_district_id: Optional[int] = None) -> List[PointOfInterest]:
    """
    Process POIs for a city or district.
    
    Args:
        city: City object
        pois: List of POI objects from WikivoyageScraper
        clear_existing: Whether to clear existing POIs for this city
        district_name: Name of the district (None for root city)
        parent_district_id: ID of the parent district (None for root districts)
        
    Returns:
        List of created PointOfInterest objects
    """
    # Create/update district if this is a district page
    current_district = None
    if district_name:
        current_district = create_or_get_district(district_name, city, parent_district_id)
    
    # Clear existing POIs if requested
    if clear_existing and not district_name:  # Only clear for root city
        city.points_of_interest.all().delete()
        logger.info(f"Cleared existing POIs for {city.name}")
    
    # Helper function to convert empty strings to None
    def clean_value(val):
        if val is None or val == "None" or (isinstance(val, str) and val.strip() == ""):
            return None
        return val.strip() if isinstance(val, str) else val
    
    # Create new POIs
    db_pois = []
    for poi in pois:
        coords = poi.coordinates or (None, None)
        
        db_pois.append(PointOfInterest(
            city=city,
            district=current_district,  # Will be None for root city POIs
            name=poi.name,
            category=poi.category,
            sub_category=clean_value(poi.sub_category),
            description=clean_value(poi.description) or '',
            latitude=coords[0],
            longitude=coords[1],
            address=clean_value(poi.address),
            phone=clean_value(poi.phone),
            website=clean_value(poi.website),
            hours=clean_value(poi.hours),
            rank=poi.rank
        ))

    # Bulk create POIs
    if db_pois:
        PointOfInterest.objects.bulk_create(db_pois)
        logger.info(f"Created {len(db_pois)} POIs for {city.name}{' / ' + district_name if district_name else ''}")
    
    return db_pois


def import_city_data(city_name: str, root_city_name: Optional[str] = None, parent_task_id: Optional[str] = None,
                   max_depth: int = 2, current_depth: int = 0, district_name: Optional[str] = None, 
                   parent_district_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Import POIs for a city or district.
    
    This is the main service function that orchestrates the import process.
    It can be called by both Celery tasks and Prefect workflows.
    
    Args:
        city_name: The page to scrape
        root_city_name: The main city these POIs belong to (same as city_name for root tasks)
        parent_task_id: ID of the parent task (None for root tasks)
        max_depth: Maximum depth of recursion for district pages (default: 2)
        current_depth: Current depth in the recursion (default: 0)
        district_name: Name of the district being processed (None for root city)
        parent_district_id: ID of the parent district (None for root districts)
        
    Returns:
        Dictionary with status information
    """
    logger.info(f"Starting import for {city_name} (depth: {current_depth}/{max_depth})")
    
    try:
        # Fetch POIs for the city or district
        pois, district_pages, about_text = fetch_city_pois(city_name, current_depth)

        if pois is None:
            logger.error(f"Error fetching POIs for {city_name}")
            return {
                'status': 'error',
                'city': city_name,
                'error': 'Error fetching POIs'
            }
        
        with transaction.atomic():
            # For root task, use city_name as root_city_name
            if not root_city_name:
                root_city_name = city_name
            
            # Create/update the city
            city = create_or_update_city(city_name, root_city_name, about_text)
            
            # Process POIs
            clear_existing = not parent_task_id  # Only clear existing POIs for root task
            db_pois = process_pois(
                city=city,
                pois=pois,
                clear_existing=clear_existing,
                district_name=district_name,
                parent_district_id=parent_district_id
            )
            
            # Return the result
            return {
                'status': 'success',
                'city': city_name,
                'root_city': root_city_name,
                'district': district_name,
                'pois_count': len(db_pois),
                'districts_enqueued': len(district_pages) if current_depth < max_depth else 0,
                'district_pages': district_pages if current_depth < max_depth else [],
                'depth': current_depth,
                'max_depth': max_depth
            }

    except Exception as e:
        logger.error(f"Error processing {city_name}: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'city': city_name,
            'error': str(e)
        }