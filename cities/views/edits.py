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

            # Format prompt for rewording
            prompt = f"""Rewrite this text in a different way while preserving its meaning:

{text}

Rewritten version:"""

            f.write(f"Sending reword request with prompt: {prompt}\n")
            response = requests.post('http://localhost:8080/completion', 
                json={
                    "prompt": prompt,
                    "temperature": 0.7,  # Balanced creativity
                    "top_k": 40,
                    "top_p": 0.9,
                    "n_predict": 500,  # Shorter for rewording
                    "stop": ["\n\n", "###", "Rewritten version:", "Original text:"],
                    "presence_penalty": 0.1,
                    "frequency_penalty": 0.1,
                    "cache_prompt": True,
                    "samplers": ["top_k", "top_p", "temperature"],
                    "stream": False
                },
                timeout=30
            )

            response.raise_for_status()
            data = response.json()
            
            # Clean up the response
            content = data.get('content', '').strip()
            
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