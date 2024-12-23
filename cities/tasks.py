from celery import shared_task
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import City, PointOfInterest
from django.db import transaction
from celery import chain
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def import_city_data(self, city_name: str, root_city_name: str = None, parent_task_id: str = None):
    """
    Import POIs for a city or district.
    city_name: The page to scrape
    root_city_name: The main city these POIs belong to (same as city_name for root tasks)
    parent_task_id: ID of the parent task (None for root tasks)
    """
    logger.info(f"Starting import task for {city_name}")
    try:
        scraper = WikivoyageScraper()
        pois, district_pages = scraper.get_city_data(city_name)
        
        with transaction.atomic():
            # For root task, use city_name as root_city_name
            if not root_city_name:
                root_city_name = city_name
            
            # Create/update the root city
            city, created = City.objects.get_or_create(
                name=root_city_name,
                defaults={'country': 'Unknown'}
            )
            
            # Only clear existing POIs if this is a root task
            if not parent_task_id:
                city.points_of_interest.all().delete()
            
            # Create new POIs, all associated with the root city
            db_pois = []
            for poi in pois:
                coords = poi.coordinates or (None, None)
                db_pois.append(PointOfInterest(
                    city=city,  # Always use the root city
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
            
            # Create tasks for district pages, passing along the root city
            current_task_id = self.request.id
            for district in district_pages:
                logger.info(f"Enqueueing district task for {district} (part of {root_city_name})")
                import_city_data.delay(
                    city_name=district,
                    root_city_name=root_city_name,
                    parent_task_id=current_task_id
                )
            
            return {
                'status': 'success',
                'city': city_name,
                'root_city': root_city_name,
                'pois_count': len(db_pois),
                'districts_enqueued': len(district_pages)
            }
            
    except Exception as e:
        logger.error(f"Error processing {city_name}: {str(e)}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise 