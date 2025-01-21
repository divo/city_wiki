from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db.models import Count
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
import json
import os
import requests
from urllib.parse import urlparse
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile

from ..models import City, PointOfInterest
from ..fetch_tasks import import_city_data
from celery.result import AsyncResult
from . import images  # Import the image handling functions

import logging
logger = logging.getLogger(__name__)

ENRICHMENT_TASKS = [
    ('geocode_city_coordinates', 'Lookup City Coordinates'),
    ('geocode_missing_addresses', 'Lookup Missing Addresses from Coordinates'),
    ('geocode_missing_coordinates', 'Lookup Missing Coordinates from Addresses'),
    ('dedup_main_city', 'Merge Duplicates in Main City'),
    ('find_all_duplicates', 'Find All Duplicates'),
    ('find_osm_ids_local', 'Find OpenStreetMap IDs (Local PBF)'),
    ('fetch_osm_ids', 'Fetch OpenStreetMap IDs (Online)'),
    # Add more tasks here as they're implemented
]


def city_list(request):
    cities = City.objects.all()
    return render(request, 'cities/city_list.html', {'cities': cities})


def city_detail(request, city_name):
    city = get_object_or_404(City, name=city_name)

    # Get max_rank filter from query params
    try:
        max_rank = int(request.GET.get('max_rank', 0))
    except ValueError:
        max_rank = 0

    # Get district filter
    district_id = request.GET.get('district', '')

    # Get sort parameters
    sort_by = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')

    # Get all districts for the filter dropdown
    districts = city.districts.all().order_by('name')

    # Calculate additional statistics
    stats = {
        'total_pois': city.points_of_interest.count(),
        'districts_count': city.districts.count(),
        'category_counts': {},
        'district_counts': {},
        'missing_coords': city.points_of_interest.filter(latitude__isnull=True).count(),
        'missing_address': city.points_of_interest.filter(address='').count() + city.points_of_interest.filter(address__isnull=True).count(),
        'missing_both': city.points_of_interest.filter(
            latitude__isnull=True,
            address__isnull=True
        ).count() + city.points_of_interest.filter(
            latitude__isnull=True,
            address=''
        ).count(),
        'missing_description': city.points_of_interest.filter(description='').count() + city.points_of_interest.filter(description__isnull=True).count()
    }

    # Count POIs by category
    for category, name in PointOfInterest.CATEGORIES:
        stats['category_counts'][category] = city.points_of_interest.filter(category=category).count()

    # Count POIs by district
    district_counts = city.points_of_interest.values('district__name').annotate(count=Count('id'))
    for dc in district_counts:
        district_name = dc['district__name'] or 'Main City'
        stats['district_counts'][district_name] = dc['count']

    # Get all POIs for this city, organized by category
    pois_by_category = {}
    category_rank_counts = {}
    for category, _ in PointOfInterest.CATEGORIES:
        # Base query with sorting
        pois = city.points_of_interest.filter(
            category=category
        ).select_related('district')

        # Apply rank filter if specified
        if max_rank > 0:
            pois = pois.filter(rank__lte=max_rank)

        # Apply district filter if specified
        if district_id:
            if district_id == 'main':
                pois = pois.filter(district__isnull=True)
            else:
                pois = pois.filter(district_id=district_id)

        # Apply sorting
        order_by = [f"{'-' if sort_dir == 'desc' else ''}{sort_by}"]
        if sort_by != 'name':  # Add name as secondary sort
            order_by.append('name')
        pois = pois.order_by(*order_by)

        pois_by_category[category] = pois

        # Count POIs by rank (show all ranks even when filtered)
        rank_counts = list(city.points_of_interest.filter(
            category=category
        ).values('rank').annotate(count=Count('rank')).order_by('rank'))
        category_rank_counts[category] = rank_counts

    return render(request, 'cities/city_detail.html', {
        'city': city,
        'pois_by_category': pois_by_category,
        'category_rank_counts': category_rank_counts,
        'max_rank': max_rank,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'districts': districts,
        'selected_district': district_id,
        'enrichment_tasks': ENRICHMENT_TASKS,
        'stats': stats,
    })


@csrf_exempt
@require_http_methods(["POST"])
def import_city_data_view(request, city_name):
    try:
        # Start the Celery task
        task = import_city_data.delay(city_name)

        return JsonResponse({
            'status': 'success',
            'message': f'Started import for {city_name}',
            'task_id': task.id
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def check_import_status(request, task_id):
    """Check the status of an import task"""
    task_result = AsyncResult(task_id)

    if task_result.ready():
        if task_result.successful():
            result = task_result.get()
            return JsonResponse({
                'status': 'completed',
                'result': result
            })
        else:
            return JsonResponse({
                'status': 'failed',
                'error': str(task_result.result)
            }, status=500)

    return JsonResponse({
        'status': 'processing'
    })


@csrf_exempt  # TODO: Replace with proper admin authentication
@require_http_methods(["DELETE"])
def delete_city(request, city_name):
    try:
        city = get_object_or_404(City, name=city_name)
        city.delete()  # This will cascade delete all POIs due to the ForeignKey relationship

        return JsonResponse({
            'status': 'success',
            'message': f'Deleted {city_name} and all its points of interest'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def import_city(request):
    if request.method == "POST":
        city_name = request.POST.get('city_name')
        try:
            # Default to 2 if not provided
            max_depth = int(request.POST.get('max_depth', 2))
            task = import_city_data.delay(city_name, max_depth=max_depth)
            messages.success(request, f'Started import for {
                             city_name} (Task ID: {task.id})')
        except ValueError:
            messages.error(request, 'Invalid max depth value')
        except Exception as e:
            messages.error(request, f'Error importing {city_name}: {str(e)}')

    return redirect('city_list')


@require_http_methods(["GET"])
def dump_city(request, city_name):
    """Return a JSON dump of all data for a specific city."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        data = {
            'city': city.to_dict(),
            'districts': [],
            'points_of_interest': [],
            'poi_lists': []
        }

        # Add districts
        for district in city.districts.all():
            district_data = model_to_dict(district, exclude=['id', 'city'])
            if district.parent_district:
                district_data['parent_district'] = district.parent_district.name
            data['districts'].append(district_data)

        # Add POIs - only those with coordinates
        for poi in city.points_of_interest.filter(latitude__isnull=False, longitude__isnull=False):
            data['points_of_interest'].append(poi.to_dict())

        # Add POI lists
        for poi_list in city.poi_lists.all():
            list_data = {
                'title': poi_list.title,
                'created_at': poi_list.created_at,
                'updated_at': poi_list.updated_at,
                'pois': [poi.to_dict() for poi in poi_list.pois.all()]
            }
            data['poi_lists'].append(list_data)

        return JsonResponse(data, encoder=DjangoJSONEncoder, json_dumps_params={'indent': 2})

    except Exception as e:
        logger.error(f"Error dumping city data: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def city_list_json(request):
    """Return a JSON list of all cities in the database."""
    try:
        cities = City.objects.all()
        city_data = []

        for city in cities:
            poi_count = city.points_of_interest.filter(
                latitude__isnull=False, longitude__isnull=False).count()
            city_data.append({
                'name': city.name,
                'country': city.country,
                'latitude': city.latitude,
                'longitude': city.longitude,
                'district_count': city.districts.count(),
                'poi_count': poi_count,
                'created_at': city.created_at,
                'updated_at': city.updated_at,
            })

        return JsonResponse({
            'cities': city_data
        }, encoder=DjangoJSONEncoder, json_dumps_params={'indent': 2})

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def city_map(request, city_name):
    city = get_object_or_404(City, name=city_name)

    # Get mapbox token from environment
    mapbox_token = os.environ.get('MAPBOX_TOKEN')
    if not mapbox_token:
        logger.error("MAPBOX_TOKEN environment variable not set")
        mapbox_token = ''  # Fallback to empty to show error in template

    # Get max_rank filter from query params
    try:
        max_rank = int(request.GET.get('max_rank', 0))
    except ValueError:
        max_rank = 0

    # Get district filter
    district_id = request.GET.get('district', '')

    # Get selected categories (default to all if none selected)
    selected_categories = request.GET.getlist(
        'categories') or [cat[0] for cat in PointOfInterest.CATEGORIES]

    # Get all districts for the filter dropdown
    districts = city.districts.all().order_by('name')

    # Filter POIs by rank and categories
    pois = city.points_of_interest.filter(category__in=selected_categories)
    if max_rank > 0:
        pois = pois.filter(rank__lte=max_rank)

    # Apply district filter if specified
    if district_id:
        if district_id == 'main':
            pois = pois.filter(district__isnull=True)
        else:
            pois = pois.filter(district_id=district_id)

    # Find first POI with coordinates to center the map
    center_poi = pois.exclude(latitude=None, longitude=None).first()
    center = {
        'longitude': center_poi.longitude if center_poi else 2.3522,  # Paris default
        'latitude': center_poi.latitude if center_poi else 48.8566
    }

    # Get rank counts for the filter UI
    rank_counts = list(city.points_of_interest.filter(category__in=selected_categories)
                       .values('rank')
                       .annotate(count=Count('rank'))
                       .order_by('rank'))

    # Get category counts
    category_counts = list(city.points_of_interest.values('category')
                           .annotate(count=Count('category'))
                           .order_by('category'))

    # Convert POIs to JSON for the template
    pois_json = json.dumps([{
        'name': poi.name,
        'category': poi.category,
        'sub_category': poi.sub_category,
        'description': poi.description,
        'latitude': poi.latitude,
        'longitude': poi.longitude,
        'address': poi.address,
        'website': poi.website
    } for poi in pois])

    return render(request, 'cities/city_map.html', {
        'city': city,
        'pois_json': pois_json,
        'center': center,
        'max_rank': max_rank,
        'rank_counts': rank_counts,
        'categories': PointOfInterest.CATEGORIES,
        'selected_categories': selected_categories,
        'category_counts': {item['category']: item['count'] for item in category_counts},
        'districts': districts,
        'selected_district': district_id,
        'mapbox_token': mapbox_token,  # Pass token to template
    })

@csrf_exempt
@require_http_methods(["POST"])
def fetch_city_image(request, city_name):
    """Fetch image URLs for a city without saving any."""
    return images.fetch_city_image(request, city_name)

@csrf_exempt
@require_http_methods(["POST"])
def save_city_image(request, city_name):
    """Save a specific image URL for a city."""
    return images.save_city_image(request, city_name)

@csrf_exempt
@require_http_methods(["POST"])
def delete_city_image(request, city_name):
    """Delete the image URL from a city."""
    return images.delete_city_image(request, city_name)

@csrf_exempt
@require_http_methods(["POST"])
def update_about(request, city_name):
    try:
        city = get_object_or_404(City, name=city_name)
        data = json.loads(request.body)
        about_text = data.get('about', '').strip()
        
        city.about = about_text
        city.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'About text updated successfully'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
