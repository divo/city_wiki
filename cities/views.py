from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest, City
from django.db import transaction
from .tasks import import_city_data
from celery.result import AsyncResult
from django.contrib import messages
import logging

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
    pois_by_category = {}
    for category, _ in PointOfInterest.CATEGORIES:
        pois_by_category[category] = city.points_of_interest.filter(category=category).order_by('rank')
    
    return render(request, 'cities/city_detail.html', {
        'city': city,
        'pois_by_category': pois_by_category
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
            logger.info(f"Attempting to start Celery task for {city_name}")
            task = import_city_data.delay(city_name)
            logger.info(f"Task created with id: {task.id}")
            messages.success(request, f'Started import for {city_name}')
        except Exception as e:
            logger.error(f"Error starting Celery task: {str(e)}", exc_info=True)
            messages.error(request, f'Error importing {city_name}: {str(e)}')
    
    return redirect('city_list')
