from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from ..models import City
from .. import generation

import logging
import json
import sys

# Configure logging to write to stdout
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Force immediate flushing of logging output
handler.flush = sys.stdout.flush


def validate_analysis_response(response):
    """Validate the analysis response structure."""
    try:
        logger.debug(f"Validating analysis response: {json.dumps(response, indent=2)}")
        
        if not isinstance(response, dict):
            logger.error("Response is not a dictionary")
            return False
        
        required_fields = ['analysis', 'status']
        if not all(field in response for field in required_fields):
            logger.error(f"Missing required fields. Found fields: {list(response.keys())}")
            return False
            
        analysis = response.get('analysis', {})
        if not isinstance(analysis, dict):
            logger.error("Analysis field is not a dictionary")
            return False
            
        # Check for required analysis fields
        required_analysis_fields = ['key_findings', 'category_distribution']
        if not all(field in analysis for field in required_analysis_fields):
            logger.error(f"Missing required analysis fields. Found fields: {list(analysis.keys())}")
            return False
            
        # Ensure key_findings is a list
        if not isinstance(analysis['key_findings'], list):
            logger.warning("key_findings is not a list, converting to empty list")
            analysis['key_findings'] = []
            
        # Ensure category_distribution is a dict
        if not isinstance(analysis['category_distribution'], dict):
            logger.warning("category_distribution is not a dict, converting to empty dict")
            analysis['category_distribution'] = {}
            
        logger.debug("Response validation successful")
        return True
        
    except Exception as e:
        logger.exception("Error validating analysis response")
        return False


def generate_text_view(request):
    """Render the text generation interface."""
    try:
        logger.info("Generating text view")
        context = generation.generate_text_view(request)
        if not context or not isinstance(context, dict):
            logger.error(f"Invalid context returned from generate_text_view: {context}")
            context = {'error': 'Failed to generate context'}
        logger.debug(f"Generated context: {json.dumps(context, indent=2)}")
        return render(request, 'cities/generate.html', context)
    except Exception as e:
        logger.exception("Error in generate_text_view")
        return render(request, 'cities/generate.html', {'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def generate_text(request, city_name):
    """Generate structured JSON analysis using OpenAI's API based on city data."""
    try:
        logger.info(f"Generating text for city: {city_name}")
        logger.debug(f"Request body: {request.body.decode()}")
        
        result = generation.generate_text(request, city_name)
        logger.debug(f"Generation result: {json.dumps(result, indent=2)}")
        
        # If it's already a JsonResponse, return it
        if isinstance(result, JsonResponse):
            logger.debug("Result is already a JsonResponse")
            return result
            
        # Validate the response structure
        if not validate_analysis_response(result):
            logger.error(f"Invalid response structure from generate_text: {json.dumps(result, indent=2)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid response structure from text generation',
                'analysis': {
                    'key_findings': [],
                    'category_distribution': {}
                }
            }, status=200)  # Return 200 with empty data instead of 500
            
        logger.info("Successfully generated and validated text analysis")
        return JsonResponse(result)
        
    except Exception as e:
        logger.exception("Error in generate_text")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'analysis': {
                'key_findings': [],
                'category_distribution': {}
            }
        }, status=200)  # Return 200 with empty data instead of 500


@csrf_exempt
@require_http_methods(["POST"])
def generate_list(request, city_name):
    """Generate structured JSON lists of POIs using OpenAI's API."""
    try:
        logger.info(f"Generating list for city: {city_name}")
        logger.debug(f"Request body: {request.body.decode()}")
        
        result = generation.generate_list(request, city_name)
        logger.debug(f"Generation result: {json.dumps(result, indent=2)}")
        
        # If it's already a JsonResponse, return it
        if isinstance(result, JsonResponse):
            logger.debug("Result is already a JsonResponse")
            return result
            
        # Ensure we have a valid response structure
        if not isinstance(result, dict) or 'status' not in result:
            logger.error(f"Invalid response from generate_list: {json.dumps(result, indent=2)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid response from list generation',
                'lists': []
            }, status=200)  # Return 200 with empty data instead of 500
            
        logger.info("Successfully generated list")
        return JsonResponse(result)
        
    except Exception as e:
        logger.exception("Error in generate_list")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'lists': []
        }, status=200)  # Return 200 with empty data instead of 500 