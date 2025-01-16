from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from ..models import PointOfInterest, City, District, PoiList
from django.db import transaction, models
from ..fetch_tasks import import_city_data
from celery.result import AsyncResult
from django.contrib import messages
import logging
from django.db.models import Count
import json
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from .. import generation
import reversion
from reversion.models import Version
from .. import enrich_tasks

logger = logging.getLogger(__name__)

def generate_text_view(request):
    """Render the text generation interface."""
    context = generation.generate_text_view(request)
    return render(request, 'cities/generate.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def generate_text(request, city_name):
    """Generate structured JSON analysis using OpenAI's API based on city data."""
    return generation.generate_text(request, city_name)


@csrf_exempt
@require_http_methods(["POST"])
def generate_list(request, city_name):
    """Generate structured JSON lists of POIs using OpenAI's API."""
    return generation.generate_list(request, city_name)


@csrf_exempt
@require_http_methods(["POST"])
def execute_task(request, city_name, task_id):
    """Execute an enrichment task."""
    try:
        city = get_object_or_404(City, name=city_name)

        # Get the task function
        task_func = getattr(enrich_tasks, task_id, None)
        if not task_func:
            return JsonResponse({
                'status': 'error',
                'message': f'Unknown task: {task_id}'
            }, status=400)

        # Start the task
        task = task_func.delay(city.id)

        return JsonResponse({
            'status': 'success',
            'task_id': task.id
        })

    except Exception as e:
        logger.error(f"Error executing task {
                     task_id} for {city_name}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def check_task_status(request, task_id):
    """Check the status of a task."""
    try:
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

    except Exception as e:
        logger.error(f"Error checking task status for {task_id}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


