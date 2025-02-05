"""Module for handling text generation using OpenAI's API."""

import os
import json
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.conf import settings
from openai import OpenAI
from ..models import City
import logging

logger = logging.getLogger(__name__)

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

def generate_text(request, city_name):
    """Generate structured JSON analysis using OpenAI's API based on city data."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Get POIs with coordinates
        pois = city.points_of_interest.filter(
            latitude__isnull=False, 
            longitude__isnull=False,
            category='see'  # Only include POIs in the "see" category
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
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        
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
            model="gpt-4-turbo-preview",  # Use latest model name
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"City data: {json.dumps(poi_data, indent=2)}\n\nPrompt: {prompt}"}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        # Parse the response to ensure it's valid JSON
        try:
            analysis_data = json.loads(response.choices[0].message.content)
            logger.debug(f"OpenAI response: {json.dumps(analysis_data, indent=2)}")
            
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
            
            final_response = {
                'status': 'success',
                'city': city.name,
                'analysis': analysis_data,
                'prompt': prompt,
                'model': "gpt-4-turbo-preview",
            }
            logger.debug(f"Final response: {json.dumps(final_response, indent=2)}")
            return JsonResponse(final_response, json_dumps_params={'indent': 2})
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response: {response.choices[0].message.content}")
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
    with open('debug.log', 'a', encoding='utf-8') as f:
        try:
            f.write("\n\nStarting generate_list function\n")
            city = get_object_or_404(City, name=city_name)
            
            # Get POIs with coordinates
            pois = city.points_of_interest.filter(
                latitude__isnull=False, 
                longitude__isnull=False,
                # Ensure both coordinates are non-zero
                latitude__gt=0,
                longitude__gt=0,
                category='see'  # Only include POIs in the "see" category
            ).select_related('district')
            
            f.write(f"Found {len(pois)} POIs with valid coordinates for {city_name}\n")
            
            # Get count parameter, default to 5 if not provided
            try:
                count = int(request.POST.get('count', 5))
                if count < 1:
                    count = 5
            except ValueError:
                count = 5
            
            # Prepare POI data - include IDs in the structure
            poi_data = {}
            poi_lookup = {}  # Map POI IDs to their full objects
            for poi in pois:
                # Skip POIs with invalid coordinates
                if not poi.latitude or not poi.longitude:
                    continue
                    
                # Ensure all text fields are properly encoded
                category = str(poi.category or '').encode('utf-8').decode('utf-8')
                district = str(poi.district.name if poi.district else 'Main City').encode('utf-8').decode('utf-8')
                name = str(poi.name or '').encode('utf-8').decode('utf-8')
                
                if category not in poi_data:
                    poi_data[category] = {}
                
                if district not in poi_data[category]:
                    poi_data[category][district] = []
                    
                # Include both ID and name in the data structure
                poi_data[category][district].append({
                    "id": poi.id,
                    "name": name
                })
                
                # Store full POI details in lookup
                poi_lookup[poi.id] = {
                    'id': poi.id,
                    'name': name,
                    'category': category,
                    'sub_category': str(poi.sub_category or '').encode('utf-8').decode('utf-8'),
                    'description': str(poi.description or '').encode('utf-8').decode('utf-8'),
                    'latitude': poi.latitude,
                    'longitude': poi.longitude,
                    'address': str(poi.address or '').encode('utf-8').decode('utf-8'),
                    'phone': str(poi.phone or '').encode('utf-8').decode('utf-8'),
                    'website': str(poi.website or '').encode('utf-8').decode('utf-8'),
                    'hours': str(poi.hours or '').encode('utf-8').decode('utf-8'),
                    'rank': poi.rank,
                    'district': district
                }
            
            if not poi_lookup:
                return JsonResponse({
                    'status': 'error',
                    'message': f'No POIs with valid coordinates found for {city_name}'
                }, status=400)
            
            f.write(f"Processed {len(poi_lookup)} POIs with valid coordinates\n")
            
            # Initialize OpenAI client
            try:
                f.write(f"Initializing OpenAI client with key")
                client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
                f.write("OpenAI client initialized successfully\n")
            except Exception as e:
                f.write(f"Failed to initialize OpenAI client: {str(e)}\n")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to initialize AI service: {str(e)}'
                }, status=500)
            
            # Get the prompt from the request
            prompt = request.POST.get('prompt', '').encode('utf-8').decode('utf-8')
            if not prompt:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No prompt provided'
                }, status=400)
                
            f.write(f"Received prompt: {prompt}\n")
            
            # Create system message with city context and JSON structure requirements
            system_message = f"""You are an AI assistant helping to create a curated list of points of interest in {city.name}.
The city has {len(pois)} points of interest with valid coordinates, organized by category and district.

CRITICAL: You MUST use the exact POI IDs provided in the data. Each POI in the data has an "id" field - you must use these IDs in your response.
DO NOT try to reference POIs by name alone, you must use their IDs.

Your task is to create a single themed list with EXACTLY {count} points of interest based on the user's prompt.

IMPORTANT: You must respond with valid JSON only. Your response should follow this structure:
{{
    "title": "A descriptive title for the list",
    "description": "A brief explanation of the list's theme or purpose",
    "pois": [
        {{
            "id": "The exact POI ID from the dataset",
            "reason": "Brief explanation of why this POI is included"
        }},
        // EXACTLY {count} POIs must be included, no more, no less
    ]
}}

Remember: 
1. You MUST use the exact POI IDs from the dataset in your response
2. You MUST include EXACTLY {count} POIs in your response, no more, no less
3. Do not create multiple sublists - just one single list with {count} items
4. The POI data is structured as: category -> district -> list of POIs with IDs and names"""

            f.write("Making OpenAI API call...\n")
            
            try:
                # Make the API call with timeout
                f.write(f"Using model: gpt-4-turbo-preview\n")
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",  # Use explicit model name
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": f"City data: {json.dumps(poi_data, indent=2, ensure_ascii=False)}\n\nPrompt: {prompt}"}
                    ],
                    temperature=0.7,
                    response_format={ "type": "json_object" },
                    timeout=60  # 60 second timeout
                )
                f.write("OpenAI API call completed successfully\n")
                
            except Exception as e:
                f.write(f"OpenAI API call failed with error: {str(e)}\n")
                return JsonResponse({
                    'status': 'error',
                    'message': f'AI service error: {str(e)}'
                }, status=500)
            
            # Parse the response to ensure it's valid JSON
            try:
                f.write("Parsing response...\n")
                response_content = response.choices[0].message.content.encode('utf-8').decode('utf-8')
                list_data = json.loads(response_content)
                f.write("Successfully parsed OpenAI response as JSON\n")
                
                # Validate that exactly count POIs are included
                if len(list_data.get('pois', [])) != count:
                    f.write(f"POI count mismatch: got {len(list_data.get('pois', []))}, expected {count}\n")
                
                # Track missing POIs and add details to existing ones
                missing_pois = []
                valid_pois = []
                for poi in list_data['pois']:
                    poi_id = int(poi['id']) if isinstance(poi['id'], str) else poi['id']
                    if poi_id in poi_lookup:
                        poi_details = poi_lookup[poi_id]
                        valid_pois.append({
                            'name': poi_details['name'],
                            'reason': poi['reason'],
                            'details': poi_details
                        })
                    else:
                        missing_pois.append(f"ID: {poi['id']}")
                
                # Replace the POIs list with only valid POIs
                list_data['pois'] = valid_pois
                
                # Add validation info to the response
                list_data['_validation'] = {
                    'total_pois': len(poi_lookup),
                    'mentioned_pois': len(valid_pois),
                    'mentioned_poi_names': sorted(poi['name'] for poi in valid_pois),
                    'missing_pois': missing_pois
                }
                
                f.write(f"Successfully processed list with {len(valid_pois)} valid POIs and {len(missing_pois)} missing POIs\n")
                
                return JsonResponse({
                    'status': 'success',
                    'city': city.name,
                    'list': list_data,
                    'prompt': prompt,
                    'model': settings.OPENAI_MODEL,
                }, json_dumps_params={'indent': 2, 'ensure_ascii': False})
                
            except json.JSONDecodeError as e:
                f.write(f"Failed to parse OpenAI response as JSON: {str(e)}\n")
                f.write(f"Raw response: {response.choices[0].message.content}\n")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to parse AI response as JSON',
                    'raw_response': response.choices[0].message.content
                }, status=500)
            
        except Exception as e:
            f.write(f"Unexpected error in generate_list: {str(e)}\n")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500) 