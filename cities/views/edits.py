"""Module for handling content editing functionality."""

import os
import re
import json
import requests
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.core.serializers.json import DjangoJSONEncoder
from django.views.decorators.http import require_http_methods
from groq import Groq
from ..models import City, PoiList, PointOfInterest

def edit_content_view(request):
    """Render the edit content interface."""
    # Get all cities for the dropdown
    cities = City.objects.all().order_by('name')
    
    # Prepare city data with POI lists for JavaScript
    city_data = []
    for city in cities:
        poi_lists = PoiList.objects.filter(city=city).order_by('title')
        poi_list_data = []
        for poi_list in poi_lists:
            pois = poi_list.pois.all().values('id', 'name', 'description')
            poi_list_data.append({
                'id': poi_list.id,
                'title': poi_list.title,
                'pois': list(pois)
            })
        
        city_data.append({
            'id': city.id,
            'name': city.name,
            'poi_lists': poi_list_data
        })
    
    return render(request, 'cities/edit_content.html', {
        'cities': cities,  # For the initial city dropdown
        'city_data_json': json.dumps(city_data, cls=DjangoJSONEncoder)  # For JavaScript
    })

#def generate_reword_local(request):
#    """[DEPRECATED] Send text to local completion endpoint for rewording."""
#    with open('debug.log', 'a', encoding='utf-8') as f:
#        try:
#            text = request.POST.get('text', '')
#            if not text:
#                return JsonResponse({
#                    'status': 'error',
#                    'message': 'No text provided'
#                }, status=400)
#
#            messages = [
#                {
#                    "role": "system",
#                    "content": (
#                        "Act as an editor for a travel guide. Your task is to rewrite the input text "
#                        "describing a tourist attraction, making it more consistent and relevant to a reader "
#                        "of a travel guide. It should be rewritten in a more consistent tone, with a more "
#                        "professional style. Remove any extraneous or overly specific information not relevant "
#                        "to someone just looking to get an overview of the attraction. The tone should remain "
#                        "professional, but friendly and approachable. Make sure to use multiple paragraphs to break up the text."
#                    )
#                },
#                {
#                    "role": "user",
#                    "content": text
#                }
#            ]
#
#            f.write(f"Sending chat request with messages: {messages}\n")
#            response = requests.post('http://localhost:8080/v1/chat/completions', 
#                json={
#                    "messages": messages,
#                    "temperature": 0.7,
#                    "max_tokens": 4000,
#                    "presence_penalty": 0.1,
#                    "frequency_penalty": 0.1,
#                    "stream": False
#                },
#                timeout=120
#            )
#
#            response.raise_for_status()
#            data = response.json()
#            
#            # Clean up the response - chat completions return message content
#            content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
#            
#            f.write(f"Received reworded response: {content}\n")
#            return JsonResponse({
#                'content': content
#            })
#        except requests.RequestException as e:
#            f.write(f"Request error: {str(e)}\n")
#            return JsonResponse({
#                'status': 'error',
#                'message': f'Completion service error: {str(e)}'
#            }, status=500)
#        except Exception as e:
#            f.write(f"Unexpected error: {str(e)}\n")
#            return JsonResponse({
#                'status': 'error',
#                'message': str(e)
#            }, status=500)


def generate_reword(request):
    """Send text to Groq's API for rewording or creating new descriptions."""
    try:
        text = request.POST.get('text', '')
        name = request.POST.get('name', '')
        
        if not name:
            return JsonResponse({
                'status': 'error',
                'message': 'No POI name provided'
            }, status=400)

        client = Groq(api_key=os.environ.get('GROQ_KEY'))
        
        # Different prompts based on whether we're rewriting or creating new
        if text.strip():
            # Rewriting existing description
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Act as an editor for a travel guide. Your task is to rewrite the input text "
                        "describing a tourist attraction, making it more consistent and relevant to a reader "
                        "of a travel guide. It should be rewritten in a more consistent tone, with a more "
                        "professional style. Remove any extraneous or overly specific information not relevant "
                        "to someone just looking to get an overview of the attraction. The tone should remain "
                        "professional, but friendly and approachable. Make sure to use multiple paragraphs to break up the text. "
                        "Do not include any markdown or html in the response. Do not include the attractions name as a title, but you can use it in the description."
                    )
                },
                {
                    "role": "user",
                    "content": f"Please rewrite this description of {name}:\n\n{text}"
                }
            ]
        else:
            # Creating new description
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Act as a travel writer for a guide book. Your task is to write a new description "
                        "for a tourist attraction. The description should be informative, engaging, and relevant "
                        "to readers of a travel guide. Write in a professional yet approachable style. "
                        "Since we don't have specific details, focus on creating a general, inviting description "
                        "that encourages visitors to explore the attraction. Use multiple paragraphs to break up the text. "
                        "Do not include any markdown or html in the response. Do not include the attraction's name as a title, "
                        "but you can use it in the description. Keep the description general but enticing, since we don't have "
                        "specific details about opening hours, prices, or exact features."
                    )
                },
                {
                    "role": "user",
                    "content": f"Please write a new description for a tourist attraction named {name}."
                }
            ]

        completion = client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            messages=messages,
            temperature=0.6,
            max_completion_tokens=4096,
            top_p=0.95,
            stream=False,
            stop=None
        )
        
        content = completion.choices[0].message.content
        
        # Strip out thinking process
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        return JsonResponse({
            'content': content
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500) 

@require_http_methods(["POST"])
def update_poi_description(request, poi_id):
    """Update a POI's description."""
    try:
        poi = get_object_or_404(PointOfInterest, id=poi_id)
        description = request.POST.get('description', '').strip()
        
        if not description:
            return JsonResponse({
                'status': 'error',
                'message': 'No description provided'
            }, status=400)
        
        poi.description = description
        poi.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Description updated successfully'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500) 