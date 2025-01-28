"""Module for handling content editing functionality."""

import requests
from django.http import JsonResponse
from django.shortcuts import render

def edit_content_view(request):
    """Render the edit content interface."""
    return render(request, 'cities/edit_content.html')

def generate_reword(request):
    """Send text to local completion endpoint for rewording."""
    with open('debug.log', 'a', encoding='utf-8') as f:
        try:
            text = request.POST.get('text', '')
            if not text:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No text provided'
                }, status=400)

            messages = [
                {
                    "role": "system",
                    "content": "Act as an editor for a travel guide. Your task is to rewrite the input text describing a tourist attraction, making it more consistent and relevant to a reader of a travel guide. It should be rewritten in a more consistent tone, with a more professional style. Remove any extraneous or overly specific information not relevant to someone just looking to get an overview of the attraction.The tone should remain professional, but friendly and approachable."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]

            f.write(f"Sending chat request with messages: {messages}\n")
            response = requests.post('http://localhost:8080/v1/chat/completions', 
                json={
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4000,
                    "presence_penalty": 0.1,
                    "frequency_penalty": 0.1,
                    "stream": False
                },
                timeout=120
            )

            response.raise_for_status()
            data = response.json()
            
            # Clean up the response - chat completions return message content
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            
            f.write(f"Received reworded response: {content}\n")
            return JsonResponse({
                'content': content
            })
        except requests.RequestException as e:
            f.write(f"Request error: {str(e)}\n")
            return JsonResponse({
                'status': 'error',
                'message': f'Completion service error: {str(e)}'
            }, status=500)
        except Exception as e:
            f.write(f"Unexpected error: {str(e)}\n")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500) 