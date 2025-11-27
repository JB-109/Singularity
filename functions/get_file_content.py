import config
import os 
from google.genai import types

def get_file_content(working_dir, file_path):

    joined_path = os.path.join(working_dir, file_path)
    abs_work_path = os.path.abspath(working_dir)
    abs_joined = os.path.abspath(joined_path)

    try:

        if not abs_joined.startswith(abs_work_path):
            return f'Error: Cannot read "{file_path}" as it is outside the permitted working directory'
        if not os.path.isfile(joined_path):
            return f'Error: File not found or is not a regular file: "{file_path}"'

        with open(abs_joined, "r") as f:
            content = f.read()

        if len(content) > config.char_limit:
            content = content[:config.char_limit]
        
        content += f'[...File "{file_path}" truncated at {config.char_limit} characters]'
        return content
        
    except Exception as e:
        return f"Error: {e}"

schema_get_file_content = types.FunctionDeclaration(
    name="get_file_content",
    description="it is used to get the content of the file, constrained to the working directory.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="the filepath to get the content from, relative to the working directory.",
            ),
        },
    ),
)