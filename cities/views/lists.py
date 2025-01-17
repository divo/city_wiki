from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from ..models import City, PoiList, PointOfInterest

import logging
logger = logging.getLogger(__name__)


def poi_lists(request, city_name):
    """Display all POI lists for a city."""
    city = get_object_or_404(City, name=city_name)
    poi_lists = city.poi_lists.all()
    
    return render(request, 'cities/poi_lists.html', {
        'city': city,
        'poi_lists': poi_lists,
    }) 


@csrf_exempt
@require_http_methods(["POST"])
def create_poi_list(request, city_name):
    """Create a new POI list."""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        poi_ids = data.get('poi_ids', [])

        if not title:
            return JsonResponse({
                'status': 'error',
                'message': 'Title is required'
            }, status=400)

        if not poi_ids:
            return JsonResponse({
                'status': 'error',
                'message': 'At least one POI must be selected'
            }, status=400)

        city = get_object_or_404(City, name=city_name)

        # Create the list
        poi_list = PoiList.objects.create(
            title=title,
            city=city
        )

        # Add POIs to the list
        pois = PointOfInterest.objects.filter(id__in=poi_ids, city=city)
        poi_list.pois.add(*pois)

        return JsonResponse({
            'status': 'success',
            'message': 'List created successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_poi_list(request, city_name, list_id):
    """Delete a POI list."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi_list = get_object_or_404(PoiList, id=list_id, city=city)
        poi_list.delete()

        return JsonResponse({
            'status': 'success',
            'message': 'List deleted successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)