from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
import json
import os
import requests
from urllib.parse import urlparse

from ..models import City, PointOfInterest

import logging
logger = logging.getLogger(__name__)


def _fetch_wikimedia_images(search_query, limit=10):
    """Helper function to fetch images from Wikimedia Commons."""
    try:
        # Format and encode search query
        search_query = search_query.replace(' ', '+')
        api_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={
            search_query}&srnamespace=6&format=json&origin=*&srlimit={limit}"

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
        logger.info(f"Fetching Pixabay images for query: {search_query}")

        # TODO: Get this from the environment variables, rotate all keys
        api_key = os.environ.get('PIXABAY_KEY')
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


def _download_image(image_url):
    """Helper function to download an image with proper error handling."""
    try:
        logger.info(f"Attempting to download image from: {image_url}")

        # Add headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Check if the response is actually an image
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.error(f"Invalid content type: {content_type}")
            return None, f"Invalid content type: {content_type}"

        return response.content, None

    except requests.exceptions.Timeout:
        logger.error("Request timed out while downloading image")
        return None, "Request timed out"
    except requests.exceptions.TooManyRedirects:
        logger.error("Too many redirects while downloading image")
        return None, "Too many redirects"
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading image: {str(e)}")
        return None, str(e)
    except Exception as e:
        logger.error(f"Unexpected error downloading image: {str(e)}")
        return None, str(e)


@csrf_exempt
@require_http_methods(["POST"])
def fetch_poi_image(request, city_name, poi_id):
    """Fetch image URLs for a POI without saving any."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)

        # Get custom search query from request body if provided
        try:
            data = json.loads(request.body)
            search_query = data.get('search_query', poi.name)
        except json.JSONDecodeError:
            search_query = poi.name  # Default if no query provided

        logger.info(f"Fetching images for POI {
                    poi.name} with query: {search_query}")

        # Get images from both sources
        wikimedia_result = _fetch_wikimedia_images(search_query)
        pixabay_result = _fetch_pixabay_images(search_query)

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

        # Get custom search query from request body if provided
        try:
            data = json.loads(request.body)
            search_query = data.get(
                'search_query', f"{city.name} city skyline")
        except json.JSONDecodeError:
            # Default if no query provided
            search_query = f"{city.name} city skyline"

        logger.info(f"Fetching images for city {
                    city_name} with query: {search_query}")

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
def save_city_image(request, city_name):
    """Save a specific image URL for a city."""
    try:
        city = get_object_or_404(City, name=city_name)
        data = json.loads(request.body)
        image_url = data.get('image_url')

        if not image_url:
            return JsonResponse({'status': 'error', 'message': 'No image URL provided'}, status=400)

        logger.info(f"Attempting to save image for city {
                    city_name} from URL: {image_url}")

        # Download the image
        image_content, error = _download_image(image_url)
        if error:
            return JsonResponse({'status': 'error', 'message': f'Failed to download image: {error}'}, status=400)

        # Get the file extension from the URL
        parsed_url = urlparse(image_url)
        ext = os.path.splitext(parsed_url.path)[1].lower()
        if not ext:
            ext = '.jpg'  # Default to jpg if no extension found

        # Create a temporary file
        img_temp = NamedTemporaryFile(delete=True)
        img_temp.write(image_content)
        img_temp.flush()

        # Delete old image file if it exists
        if city.image_file:
            logger.info(f"Deleting old image file for city {city_name}")
            city.delete_image_file()

        # Save the new image
        filename = f"{city.name}{ext}"
        logger.info(f"Saving new image file for city {city_name}: {filename}")
        city.image_file.save(filename, File(img_temp), save=True)

        return JsonResponse({
            'status': 'success',
            'message': 'Image saved successfully',
            'image_url': city.image_url
        })

    except json.JSONDecodeError:
        logger.error("Invalid JSON data in request")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error saving city image: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
            return JsonResponse({'status': 'error', 'message': 'No image URL provided'}, status=400)

        logger.info(f"Attempting to save image for POI {
                    poi.name} from URL: {image_url}")

        # Download the image
        image_content, error = _download_image(image_url)
        if error:
            return JsonResponse({'status': 'error', 'message': f'Failed to download image: {error}'}, status=400)

        # Get the file extension from the URL
        parsed_url = urlparse(image_url)
        ext = os.path.splitext(parsed_url.path)[1].lower()
        if not ext:
            ext = '.jpg'  # Default to jpg if no extension found

        # Create a temporary file
        img_temp = NamedTemporaryFile(delete=True)
        img_temp.write(image_content)
        img_temp.flush()

        # Delete old image file if it exists
        if poi.image_file:
            logger.info(f"Deleting old image file for POI {poi.name}")
            poi.delete_image_file()

        # Save the new image
        filename = f"{poi.name}{ext}"
        logger.info(f"Saving new image file for POI {poi.name}: {filename}")
        poi.image_file.save(filename, File(img_temp), save=True)

        return JsonResponse({
            'status': 'success',
            'message': 'Image saved successfully',
            'image_url': poi.image_url
        })

    except json.JSONDecodeError:
        logger.error("Invalid JSON data in request")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error saving POI image: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_city_image(request, city_name):
    """Delete the image file from a city."""
    try:
        city = get_object_or_404(City, name=city_name)

        # Delete the image file
        if city.image_file:
            city.delete_image_file()

        return JsonResponse({'status': 'success', 'message': 'Image deleted successfully'})

    except Exception as e:
        logger.error(f"Error deleting city image: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_poi_image(request, city_name, poi_id):
    """Delete the image file from a POI."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)

        # Delete the image file
        if poi.image_file:
            poi.delete_image_file()

        return JsonResponse({'status': 'success', 'message': 'Image deleted successfully'})

    except Exception as e:
        logger.error(f"Error deleting POI image: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
