import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

#++++++++++

if len(sys.argv) > 1:
    prompt = sys.argv[1]
else:
    prompt = input("How can I help you now? ")

if not prompt or not prompt.strip():
    print("Please provide a prompt!")
    sys.exit(1)

messages = [
    types.Content(role="user", parts=[types.Part(text=prompt)]),
]
#++++++++++

response = client.models.generate_content(
    model='gemini-2.0-flash', contents=messages
)

if len(sys.argv) > 2 and sys.argv[2] == "--verbose":
    print(f"User prompt: {prompt}")
    print(f"AI response: {response.text}")
    print(f"Prompt tokens: {response.usage_metadata.prompt_token_count}")
    print(f"Response tokens: {response.usage_metadata.candidates_token_count}")
else:
    print(response.text)
    