import asyncio
import httpx

# Define the server URL
server_url = "http://localhost:8080/completion"

# Define the prompts
prompts = [
    {"prompt": "What is the capital of France?", "max_tokens": 50},
]

# Function to send a request asynchronously


async def send_request(client, payload):
    try:
        response = await client.post(server_url, json=payload)
        response.raise_for_status()
        return {"prompt": payload["prompt"], "response": response.json()}
    except httpx.RequestError as exc:
        return {"prompt": payload["prompt"], "error": str(exc)}

# Main async function


async def main():
    async with httpx.AsyncClient() as client:
        # Schedule all requests
        tasks = [send_request(client, prompt) for prompt in prompts]

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)

        # Print results
        for result in results:
            if "error" in result:
                print(f"Error for prompt: {
                      result['prompt']} - {result}")
            else:
                print(f"Prompt: {result['prompt']}")
                print(f"Response: {result['response']['choices'][0]['text']}")
                print()

# Run the main function
asyncio.run(main())
