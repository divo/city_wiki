from celery import shared_task
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import City, PointOfInterest, District, Validation
from mwapi.errors import APIError
from django.db import transaction
from celery import chain
import logging

logger = logging.getLogger(__name__)

def _fetch_pois(city, depth):
    """Helper function to fetch POIs and handle API errors"""
    try:
        scraper = WikivoyageScraper()
        return scraper.get_city_data(city.name)
    except APIError as response_error:
        logger.error(f"Non fatal API error for {city.name}: {response_error}")
        Validation.objects.create(
            parent_key=city,
            context='WikiImport',
            aggregate='FetchArticleError',
            specialized_aggregate='DistrictFetchError' if depth != 0 else 'CityFetchError',
            description=str(response_error)
        )
        return None, None


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
        scraper = WikivoyageScraper()
        pois, district_pages = scraper.get_city_data(city_name)
 
        # Parse district name if it contains a slash
        if district_name and '/' in district_name:
            district_name = district_name.split('/', 1)[1]

        with transaction.atomic():
            # For root task, use city_name as root_city_name
            if not root_city_name:
                root_city_name = city_name
            
            # Create/update the root city
            city, created = City.objects.get_or_create(
                name=root_city_name,
                defaults={'country': 'Unknown'}
            )
            
            # Create/update district if this is a district page
            current_district = None
            if district_name:
                parent_district = District.objects.get(id=parent_district_id) if parent_district_id else None
                current_district, _ = District.objects.get_or_create(
                    name=district_name,
                    city=city,
                    defaults={'parent_district': parent_district}
                )

            # Only clear existing POIs if this is a root task
            if not parent_task_id:
                city.points_of_interest.all().delete()

            # Create new POIs, associated with both city and district
            db_pois = []
            for poi in pois:
                coords = poi.coordinates or (None, None)
                db_pois.append(PointOfInterest(
                    city=city,
                    district=current_district,  # Will be None for root city POIs
                    name=poi.name,
                    category=poi.category,
                    description=poi.description,
                    latitude=coords[0],
                    longitude=coords[1],
                    address=poi.address,
                    phone=poi.phone,
                    website=poi.website,
                    hours=poi.hours,
                    rank=poi.rank
                ))

            # Bulk create POIs
            PointOfInterest.objects.bulk_create(db_pois)

            # Create tasks for district pages if we haven't reached max_depth
            if current_depth < max_depth:
                current_task_id = self.request.id
                for district in district_pages:
                    logger.info(f"Enqueueing district task for {district} (part of {root_city_name}, depth: {current_depth + 1})")
                    import_city_data.delay(
                        city_name=district,
                        root_city_name=root_city_name,
                        parent_task_id=current_task_id,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        district_name=district,
                        parent_district_id=current_district.id if current_district else None
                    )
            else:
                logger.info(f"Reached maximum depth ({max_depth}) for {city_name}, skipping district pages")

            return {
                'status': 'success',
                'city': city_name,
                'root_city': root_city_name,
                'district': district_name,
                'pois_count': len(db_pois),
                'districts_enqueued': len(district_pages) if current_depth < max_depth else 0,
                'depth': current_depth,
                'max_depth': max_depth
            }

    except Exception as e:
        logger.error(f"Error processing {city_name}: {str(e)}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
