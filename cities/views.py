from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest, City
from django.db import transaction, models
from .tasks import import_city_data
from celery.result import AsyncResult
from django.contrib import messages
import logging
from django.db.models import Count
import json
logger = logging.getLogger(__name__)

def city_list(request):
    cities = City.objects.all()
    return render(request, 'cities/city_list.html', {'cities': cities})

# TODO: Make this admin only
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
            max_depth = int(request.POST.get('max_depth', 2))  # Default to 2 if not provided
            task = import_city_data.delay(city_name, max_depth=max_depth)
            messages.success(request, f'Started import for {city_name} (Task ID: {task.id})')
        except ValueError:
            messages.error(request, 'Invalid max depth value')
        except Exception as e:
            messages.error(request, f'Error importing {city_name}: {str(e)}')
    
    return redirect('city_list')

def city_map(request, city_name):
    city = get_object_or_404(City, name=city_name)
    
    # Get max_rank filter from query params
    try:
        max_rank = int(request.GET.get('max_rank', 0))
    except ValueError:
        max_rank = 0
    
    # Get district filter
    district_id = request.GET.get('district', '')
    
    # Get selected categories (default to all if none selected)
    selected_categories = request.GET.getlist('categories') or [cat[0] for cat in PointOfInterest.CATEGORIES]
    
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
    })
