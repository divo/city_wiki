from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest, City
from django.db import transaction

def city_list(request):
    cities = City.objects.all()
    return render(request, 'cities/city_list.html', {'cities': cities})

# TODO: Make this admin only
@csrf_exempt
@require_http_methods(["POST"])
def import_city_data(request, city_name):
    try:
        scraper = WikivoyageScraper()
        pois = scraper.get_city_data(city_name)
        
        with transaction.atomic():
            # Get or create the city
            city, created = City.objects.get_or_create(
                name=city_name,
                defaults={'country': 'Unknown'}  # You might want to fetch this from WikiVoyage
            )
            
            # Clear existing POIs for this city
            city.points_of_interest.all().delete()
            
            # Convert scraped POIs to database models
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

def city_detail(request, city_name):
    city = get_object_or_404(City, name=city_name)
    pois_by_category = {}
    for category, _ in PointOfInterest.CATEGORIES:
        pois_by_category[category] = city.points_of_interest.filter(category=category).order_by('rank')
    
    return render(request, 'cities/city_detail.html', {
        'city': city,
        'pois_by_category': pois_by_category
    })
