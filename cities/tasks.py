from celery import shared_task
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import City, PointOfInterest
from django.db import transaction
from celery import chain
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def import_city_data(self, city_name: str, parent_task_id: str = None):
    """
    Import POIs for a city. Can be chained with other city imports for districts.
    """
    logger.info(f"Starting import task for {city_name}")
    try:
        scraper = WikivoyageScraper()
        pois = scraper.get_city_data(city_name)
        
        with transaction.atomic():
            # Create/update city
            city, created = City.objects.get_or_create(
                name=city_name,
                defaults={'country': 'Unknown'}
            )
            
            # If this is a root task (no parent), clear existing POIs
            if not parent_task_id:
                city.points_of_interest.all().delete()
            
            # Create new POIs
            db_pois = []
            for poi in pois:
                coords = poi.coordinates or (None, None)
                db_pois.append(PointOfInterest(
                    city=city,
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
            
            # TODO: Find district pages and create child tasks
            # district_pages = scraper.find_district_pages(city_name)
            # for district in district_pages:
            #     import_city_data.delay(district, self.request.id)
            
            return {
                'status': 'success',
                'city': city_name,
                'pois_count': len(db_pois)
            }
            
    except Exception as e:
        # Log the error and re-raise it for Celery to handle
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise 