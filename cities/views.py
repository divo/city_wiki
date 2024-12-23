from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

# Create your views here.

# TODO: Make this admin only
@csrf_exempt
@require_http_methods(["POST"])
def import_city_data(request, city_name):
    try:
        scraper = WikivoyageScraper()
        pois = scraper.get_city_data(city_name)
        
        with transaction.atomic():
            # Clear existing POIs for this city to avoid duplicates
            PointOfInterest.objects.filter(city_name=city_name).delete()
            
            # Convert scraped POIs to database models
            db_pois = []
            for poi in pois:
                coords = poi.coordinates or (None, None)
                db_pois.append(PointOfInterest(
                    name=poi.name,
                    category=poi.category,
                    description=poi.description,
                    latitude=coords[0],
                    longitude=coords[1],
                    address=poi.address,
                    phone=poi.phone,
                    website=poi.website,
                    hours=poi.hours,
                    rank=poi.rank,
                    city_name=city_name
                ))
            
            # Bulk create all POIs
            PointOfInterest.objects.bulk_create(db_pois)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Imported {len(db_pois)} points of interest for {city_name}',
            'count': len(db_pois)
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
