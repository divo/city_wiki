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
    
    # Get all POIs for this city, organized by category
    pois_by_category = {}
    category_rank_counts = {}
    for category, _ in PointOfInterest.CATEGORIES:
        pois = city.points_of_interest.filter(
            category=category
        ).select_related('district').order_by('rank')
        pois_by_category[category] = pois
        # Count POIs by rank
        rank_counts = list(pois.values('rank').annotate(count=Count('rank')).order_by('rank'))
        category_rank_counts[category] = rank_counts
    
    return render(request, 'cities/city_detail.html', {
        'city': city,
        'pois_by_category': pois_by_category,
        'category_rank_counts': category_rank_counts,
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
            messages.success(request, f'Started import for {city_name} with max depth {max_depth}')
        except ValueError:
            messages.error(request, 'Invalid max depth value')
        except Exception as e:
            messages.error(request, f'Error importing {city_name}: {str(e)}')
    
    return redirect('city_list')
