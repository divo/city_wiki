from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from ..models import City, PointOfInterest

import logging
logger = logging.getLogger(__name__)


def _fetch_wikimedia_images(search_query, limit=10):
    """Helper function to fetch images from Wikimedia Commons."""
    try:
        import requests
        
        # Format and encode search query
        search_query = search_query.replace(' ', '+')
        api_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={search_query}&srnamespace=6&format=json&origin=*&srlimit={limit}"
        
        response = requests.get(api_url)
        data = response.json()
        
        image_urls = []
        if data.get('query', {}).get('search'):
            # Get up to limit results
            for result in data['query']['search'][:limit]:
                title = result['title']
                
                # Get image info for each result
                file_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={title}&prop=imageinfo&iiprop=url&format=json&origin=*"
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
        api_url = f"https://pixabay.com/api/?key={api_key}&q={search_query}&image_type=photo&per_page={limit}"
        logger.info(f"Making request to Pixabay API: {api_url.replace(api_key, '[REDACTED]')}")
        
        response = requests.get(api_url)
        logger.info(f"Pixabay API response status code: {response.status_code}")
        
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


@csrf_exempt
@require_http_methods(["POST"])
def fetch_poi_image(request, city_name, poi_id):
    """Fetch image URLs for a POI without saving any."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)
        
        # Get images from both sources
        wikimedia_result = _fetch_wikimedia_images(poi.name)
        pixabay_result = _fetch_pixabay_images(poi.name)
        
        # Combine results
        result = _combine_image_results(wikimedia_result, pixabay_result)
        return JsonResponse(result, status=404 if result['status'] == 'error' else 200)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def fetch_city_image(request, city_name):
    """Fetch image URLs for a city without saving any."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        search_query = f"{city.name} city skyline"
        wikimedia_result = _fetch_wikimedia_images(search_query)
        pixabay_result = _fetch_pixabay_images(search_query)

        result = _combine_image_results(wikimedia_result, pixabay_result)
        return JsonResponse(result, status=404 if result['status'] == 'error' else 200)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_poi_image(request, city_name, poi_id):
    """Save a specific image URL for a POI."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)
        
        data = json.loads(request.body)
        image_url = data.get('image_url')
        
        if not image_url:
            return JsonResponse({
                'status': 'error',
                'message': 'Image URL is required'
            }, status=400)
        
        # Save the image URL
        poi.image_url = image_url
        poi.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Image URL saved'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_poi_image(request, city_name, poi_id):
    """Delete the image URL from a POI."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)
        
        # Clear the image URL
        poi.image_url = None
        poi.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Image URL removed'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_city_image(request, city_name):
    """Save a specific image URL for a city."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        data = json.loads(request.body)
        image_url = data.get('image_url')
        
        if not image_url:
            return JsonResponse({
                'status': 'error',
                'message': 'Image URL is required'
            }, status=400)
        
        # Save the image URL
        city.image_url = image_url
        city.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Image URL saved'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_city_image(request, city_name):
    """Delete the image URL from a city."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Clear the image URL
        city.image_url = None
        city.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Image URL removed'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500) 