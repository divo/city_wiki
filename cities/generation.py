"""Module for handling text generation using OpenAI's API."""

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.conf import settings
from openai import OpenAI
import json
from .models import City

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
    
    return {
        'cities': sorted(cities, key=lambda x: x['name'])
    }

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