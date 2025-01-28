import requests

# Define the server URL
server_url = "http://localhost:8080/completion"

# Define a single request
request_data = {
    "prompt": "What is the capital of France?",
    "max_tokens": 50
}

# Send the request
response = requests.post(server_url, json=request_data)

# Check the response
if response.status_code == 200:
    print(response.json())
else:
    print(f"Error: {response.status_code} - {response.text}")
