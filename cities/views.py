from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest, City, District
from django.db import transaction, models
from .tasks import import_city_data
from celery.result import AsyncResult
from django.contrib import messages
import logging
from django.db.models import Count
import json
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from openai import OpenAI

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

@require_http_methods(["GET"])
def dump_city(request, city_name):
    """Return a JSON dump of all data for a specific city."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Prepare the data structure
        data = {
            'city': model_to_dict(city, exclude=['id']),
            'districts': [],
            'points_of_interest': []
        }

        # Add districts
        for district in city.districts.all():
            district_data = model_to_dict(district, exclude=['id', 'city'])
            if district.parent_district:
                district_data['parent_district'] = district.parent_district.name
            data['districts'].append(district_data)

        # Add POIs - only those with coordinates
        for poi in city.points_of_interest.filter(latitude__isnull=False, longitude__isnull=False):
            poi_data = model_to_dict(poi, exclude=['id', 'city'])
            if poi.district:
                poi_data['district'] = poi.district.name
            data['points_of_interest'].append(poi_data)

        return JsonResponse(data, encoder=DjangoJSONEncoder, json_dumps_params={'indent': 2})
        
    except Exception as e:
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
            poi_count = city.points_of_interest.filter(latitude__isnull=False, longitude__isnull=False).count()
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

@csrf_exempt
@require_http_methods(["POST"])
def generate_text(request, city_name):
    """Generate structured JSON analysis using OpenAI's API based on city data."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Get POIs with coordinates
        pois = city.points_of_interest.filter(
            latitude__isnull=False, 
            longitude__isnull=False
        ).select_related('district')
        
        # Prepare POI data - just names grouped by category and district
        poi_data = {}
        all_poi_names = set()  # Track all POI names for validation
        for poi in pois:
            category = poi.category
            district = poi.district.name if poi.district else 'Main City'
            
            if category not in poi_data:
                poi_data[category] = {}
            
            if district not in poi_data[category]:
                poi_data[category][district] = []
                
            poi_data[category][district].append(poi.name)
            all_poi_names.add(poi.name)
        
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Get the prompt from the request
        prompt = request.POST.get('prompt', '')
        if not prompt:
            return JsonResponse({
                'status': 'error',
                'message': 'No prompt provided'
            }, status=400)
            
        # Create system message with city context and JSON structure requirements
        system_message = f"""You are an AI assistant helping to analyze data about {city.name}.
The city has {len(pois)} points of interest with valid coordinates, organized by category and district.

CRITICAL: When mentioning specific locations in your analysis, you MUST ONLY use the exact names of POIs provided in the data. Do not make up or reference any locations that aren't in the provided dataset.

Your task is to provide insights and analysis based on this data.

IMPORTANT: You must respond with valid JSON only. Your response should follow this structure:
{{
    "summary": "A brief overview of the analysis",
    "key_findings": [
        "Finding 1 (reference specific POIs by their exact names)",
        "Finding 2 (reference specific POIs by their exact names)",
        ...
    ],
    "analysis": {{
        "category_distribution": {{
            "description": "Analysis of POI distribution across categories",
            "highlights": [
                "Highlight 1 (reference specific POIs by their exact names)",
                ...
            ]
        }},
        "district_insights": {{
            "description": "Analysis of district-specific patterns",
            "highlights": [
                "Highlight 1 (reference specific POIs by their exact names)",
                ...
            ]
        }},
        "recommendations": [
            {{
                "title": "Recommendation title (reference specific POIs)",
                "description": "Detailed explanation (reference specific POIs)"
            }},
            ...
        ]
    }}
}}

Remember: All POIs mentioned must be from this exact list: {sorted(list(all_poi_names))}"""
        
        # Make the API call
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"City data: {json.dumps(poi_data, indent=2)}\n\nPrompt: {prompt}"}
            ],
            temperature=0.7,
            response_format={ "type": "json_object" }
        )
        
        # Parse the response to ensure it's valid JSON
        try:
            analysis_data = json.loads(response.choices[0].message.content)
            
            # Validate that all POIs mentioned exist in our dataset
            response_text = json.dumps(analysis_data)
            mentioned_pois = set()
            for poi_name in all_poi_names:
                if poi_name in response_text:
                    mentioned_pois.add(poi_name)
            
            # Add validation info to the response
            analysis_data['_validation'] = {
                'total_pois': len(all_poi_names),
                'mentioned_pois': len(mentioned_pois),
                'mentioned_poi_names': sorted(list(mentioned_pois))
            }
            
            return JsonResponse({
                'status': 'success',
                'city': city.name,
                'analysis': analysis_data,
                'prompt': prompt,
                'model': settings.OPENAI_MODEL,
            }, json_dumps_params={'indent': 2})
        except json.JSONDecodeError as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to parse AI response as JSON',
                'raw_response': response.choices[0].message.content
            }, status=500)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def generate_text_view(request):
    """Render the text generation interface."""
    # Get all cities with their POI counts
    cities = []
    for city in City.objects.all():
        poi_count = city.points_of_interest.filter(
            latitude__isnull=False, 
            longitude__isnull=False
        ).count()
        cities.append({
            'name': city.name,
            'poi_count': poi_count
        })
    
    return render(request, 'cities/generate.html', {
        'cities': sorted(cities, key=lambda x: x['name'])
    })

@csrf_exempt
@require_http_methods(["POST"])
def generate_list(request, city_name):
    """Generate structured JSON lists of POIs using OpenAI's API."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Get POIs with coordinates
        pois = city.points_of_interest.filter(
            latitude__isnull=False, 
            longitude__isnull=False
        ).select_related('district')
        
        # Get count parameter, default to 5 if not provided
        try:
            count = int(request.POST.get('count', 5))
            if count < 1:
                count = 5
        except ValueError:
            count = 5
        
        # Prepare POI data - just names grouped by category and district
        poi_data = {}
        all_poi_names = set()  # Track all POI names for validation
        for poi in pois:
            category = poi.category
            district = poi.district.name if poi.district else 'Main City'
            
            if category not in poi_data:
                poi_data[category] = {}
            
            if district not in poi_data[category]:
                poi_data[category][district] = []
                
            poi_data[category][district].append(poi.name)
            all_poi_names.add(poi.name)
        
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Get the prompt from the request
        prompt = request.POST.get('prompt', '')
        if not prompt:
            return JsonResponse({
                'status': 'error',
                'message': 'No prompt provided'
            }, status=400)
            
        # Create system message with city context and JSON structure requirements
        system_message = f"""You are an AI assistant helping to create a curated list of points of interest in {city.name}.
The city has {len(pois)} points of interest with valid coordinates, organized by category and district.

CRITICAL: When mentioning specific locations, you MUST ONLY use the exact names of POIs provided in the data. Do not make up or reference any locations that aren't in the provided dataset.

Your task is to create a single themed list with EXACTLY {count} points of interest based on the user's prompt.

IMPORTANT: You must respond with valid JSON only. Your response should follow this structure:
{{
    "title": "A descriptive title for the list",
    "description": "A brief explanation of the list's theme or purpose",
    "pois": [
        {{
            "name": "Exact POI name from the dataset",
            "reason": "Brief explanation of why this POI is included"
        }},
        // EXACTLY {count} POIs must be included, no more, no less
    ]
}}

Remember: 
1. All POIs mentioned must be from this exact list: {sorted(list(all_poi_names))}
2. You MUST include EXACTLY {count} POIs in your response, no more, no less
3. Do not create multiple sublists - just one single list with {count} items"""
        
        # Make the API call
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"City data: {json.dumps(poi_data, indent=2)}\n\nPrompt: {prompt}"}
            ],
            temperature=0.7,
            response_format={ "type": "json_object" }
        )
        
        # Parse the response to ensure it's valid JSON
        try:
            list_data = json.loads(response.choices[0].message.content)
            
            # Validate that exactly count POIs are included
            if len(list_data.get('pois', [])) != count:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Generated list does not contain exactly {count} POIs'
                }, status=500)
            
            # Validate that all POIs mentioned exist in our dataset
            response_text = json.dumps(list_data)
            mentioned_pois = set()
            for poi_name in all_poi_names:
                if poi_name in response_text:
                    mentioned_pois.add(poi_name)
            
            # Add validation info to the response
            list_data['_validation'] = {
                'total_pois': len(all_poi_names),
                'mentioned_pois': len(mentioned_pois),
                'mentioned_poi_names': sorted(list(mentioned_pois))
            }
            
            return JsonResponse({
                'status': 'success',
                'city': city.name,
                'list': list_data,
                'prompt': prompt,
                'model': settings.OPENAI_MODEL,
            }, json_dumps_params={'indent': 2})
        except json.JSONDecodeError as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to parse AI response as JSON',
                'raw_response': response.choices[0].message.content
            }, status=500)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
