import os
import sys
import config
import functions.get_files_info
import functions.get_file_content
import functions.run_python_file
import functions.write_files

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++

if len(sys.argv) > 1:
    prompt = sys.argv[1]
else:
    prompt = input("How can I help you now? ")

if not prompt or not prompt.strip():
    print("Please provide a prompt!")
    sys.exit(1)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++

messages = [
    types.Content(
        role="user",
        parts=[types.Part(text=prompt)]
    )
]

functions_map = {
    "get_files_info": functions.get_files_info.get_files_info,
    "get_file_content": functions.get_file_content.get_file_content,
    "run_python_file": functions.run_python_file.run_python_file,
    "write_files": functions.write_files.write_files 
}

available_functions = types.Tool(
    function_declarations=[
        functions.get_files_info.schema_get_files_info,
        functions.get_file_content.schema_get_file_content,
        functions.run_python_file.schema_run_python_file,
        functions.write_files.schema_write_files
    ]
)

response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=messages,
    config=types.GenerateContentConfig(
        system_instruction=config.system_prompt,
        tools=[available_functions]
    )
)

def call_function(function_call_part, verbose=False):
    if function_call_part.name in functions_map:
        if verbose == True:
            print(f"Calling function: {function_call_part.name}({function_call_part.args})")
        else:
            print(f" - Calling function: {function_call_part.name}")
        result = functions_map[function_call_part.name](working_dir=os.path.abspath("./calculator"), **function_call_part.args)
        print(result)
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_call_part.name,
                    response={"result": result},
                )
            ],
        )
    else:
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_call_part.name,
                    response={"error": f"Unknown function: {function_call_part.name}"},
                )
            ],
        )

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++

function_responses = []
if len(sys.argv) > 0:
    call_function(response.function_calls[0], True)
    print(f"User prompt: {prompt}")
    if response.text is not None:
        print(f"AI response: {response.text}")

    for each in response.function_calls:
        result = call_function(each)
        if not result.parts or not result.parts[0].function_response:
            raise Exception("empty function call result")
        if len(sys.argv) > 2 and sys.argv[2] == "--verbose":
            print(f"-> {result.parts[0].function_response.response}")
        function_responses.append(result.parts[0])

        
