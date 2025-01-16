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


def _fetch_wikimedia_images(search_query, limit=10):
    """Helper function to fetch images from Wikimedia Commons."""
    try:
        # Format and encode search query
        search_query = search_query.replace(' ', '+')
        api_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={
            search_query}&srnamespace=6&format=json&origin=*&srlimit={limit}"

        import requests
        response = requests.get(api_url)
        data = response.json()

        image_urls = []
        if data.get('query', {}).get('search'):
            # Get up to limit results
            for result in data['query']['search'][:limit]:
                title = result['title']

                # Get image info for each result
                file_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={
                    title}&prop=imageinfo&iiprop=url&format=json&origin=*"
                file_response = requests.get(file_url)
                file_data = file_response.json()

                # Extract the image URL
                pages = file_data.get('query', {}).get('pages', {})
                if pages:
                    page = next(iter(pages.values()))
                    image_info = page.get('imageinfo', [{}])[0]
                    image_url = image_info.get('url')

                    if image_url:
                        image_urls.append(image_url)

            if image_urls:
                return {
                    'status': 'success',
                    'message': 'Image URLs found',
                    'image_urls': image_urls
                }

        return {
            'status': 'error',
            'message': 'No suitable images found'
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


def _fetch_pixabay_images(search_query, limit=10):
    """Helper function to fetch images from Pixabay."""
    try:
        import requests
        import os

        logger.info(f"Fetching Pixabay images for query: {search_query}")

        # TODO: Get this from the environment variables, rotate all keys
        api_key = '48260974-6b7ee5fa9113ac3f114f83ece'
        if not api_key:
            logger.error("Pixabay API key not found in environment variables")
            return {
                'status': 'error',
                'message': 'Pixabay API key not configured'
            }

        # Format search query
        search_query = search_query.replace(' ', '+')
        api_url = f"https://pixabay.com/api/?key={api_key}&q={
            search_query}&image_type=photo&per_page={limit}"
        logger.info(f"Making request to Pixabay API: {
                    api_url.replace(api_key, '[REDACTED]')}")

        response = requests.get(api_url)
        logger.info(f"Pixabay API response status code: {
                    response.status_code}")

        if response.status_code != 200:
            logger.error(f"Pixabay API error: {response.text}")
            return {
                'status': 'error',
                'message': f'Pixabay API error: {response.status_code}'
            }

        data = response.json()
        logger.info(f"Pixabay API response: {data.get('total', 0)} total hits")

        image_urls = []
        if data.get('hits'):
            for hit in data['hits']:
                image_urls.append(hit['largeImageURL'])

            if image_urls:
                logger.info(f"Found {len(image_urls)} images from Pixabay")
                return {
                    'status': 'success',
                    'message': 'Image URLs found',
                    'image_urls': image_urls
                }

        logger.warning("No images found in Pixabay response")
        return {
            'status': 'error',
            'message': 'No suitable images found'
        }

    except Exception as e:
        logger.exception(f"Error fetching images from Pixabay: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


def _combine_image_results(*results):
    """Helper function to combine image results from multiple sources."""
    combined_urls = []
    for result in results:
        if result.get('status') == 'success':
            combined_urls.extend(result.get('image_urls', []))

    if combined_urls:
        return {
            'status': 'success',
            'message': 'Image URLs found',
            'image_urls': combined_urls[:20]  # Limit total results
        }

    return {
        'status': 'error',
        'message': 'No suitable images found'
    }
