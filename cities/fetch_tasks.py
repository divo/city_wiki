from celery import shared_task
from django.db import transaction
from celery import chain
import logging
from .services.city_import import fetch_city_pois, create_or_update_city, process_pois, import_city_data as import_city_data_service

logger = logging.getLogger(__name__)

def _fetch_pois(city_name, depth):
    """
    Helper function to fetch POIs and handle API errors
    Delegating to the service module implementation
    """
    return fetch_city_pois(city_name, depth)


@shared_task(bind=True)
def import_city_data(self, city_name: str, root_city_name: str = None, parent_task_id: str = None,
                     max_depth: int = 2, current_depth: int = 0, district_name: str = None, parent_district_id: int = None):
    """
    Import POIs for a city or district.
    city_name: The page to scrape
    root_city_name: The main city these POIs belong to (same as city_name for root tasks)
    parent_task_id: ID of the parent task (None for root tasks)
    max_depth: Maximum depth of recursion for district pages (default: 2)
    current_depth: Current depth in the recursion (default: 0)
    district_name: Name of the district being processed (None for root city)
    parent_district_id: ID of the parent district (None for root districts)
    """
    logger.info(f"Starting import task for {city_name} (depth: {current_depth}/{max_depth})")
    
    try:
        # Call the service function to handle the import logic
        result = import_city_data_service(
            city_name=city_name,
            root_city_name=root_city_name,
            parent_task_id=parent_task_id,
            max_depth=max_depth,
            current_depth=current_depth,
            district_name=district_name,
            parent_district_id=parent_district_id
        )
        
        # If the import was successful and we haven't reached max_depth,
        # create tasks for the district pages
        if (result['status'] == 'success' and 
            current_depth < max_depth and 
            'district_pages' in result and 
            result['district_pages']):
            
            current_task_id = self.request.id
            
            # Get the district ID if this is a district page
            district_id = None
            if district_name and 'district' in result:
                from .models import District
                try:
                    district = District.objects.get(name=result['district'], city__name=result['root_city'])
                    district_id = district.id
                except District.DoesNotExist:
                    logger.warning(f"District {result['district']} not found for city {result['root_city']}")
            
            # Create tasks for district pages
            for district in result['district_pages']:
                logger.info(f"Enqueueing district task for {district} (part of {result['root_city']}, depth: {current_depth + 1})")
                import_city_data.delay(
                    city_name=district,
                    root_city_name=result['root_city'],
                    parent_task_id=current_task_id,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    district_name=district,
                    parent_district_id=district_id
                )
        
        return result

    except Exception as e:
        logger.error(f"Error processing {city_name}: {str(e)}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
