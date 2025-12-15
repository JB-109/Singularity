import os
import subprocess
from google.genai import types

def run_python_file(working_dir, file_path, args=[]):

    abs_work_path = os.path.abspath(working_dir)
    abs_joined = os.path.abspath(os.path.join(working_dir, file_path))

    try:

        if not abs_joined.startswith(abs_work_path):
            return f'Error: Cannot execute "{file_path}" as it is outside the permitted working directory'
        if not os.path.exists(abs_joined):
            return f'Error: File "{file_path}" not found.'
        if not abs_joined.endswith(".py"):
            return f'Error: "{file_path}" is not a Python file.'
        
        result = subprocess.run(["python3", abs_joined] + args, capture_output=True, text=True, timeout=30)
        final_return = [f'STDOUT: {result.stdout}', f'STDERR: {result.stderr}']

        if result.returncode != 0:
            final_return.append(f'Process exited with code {result.returncode}')
        return "\n".join(final_return)

    except Exception as e:
        return f"Error: executing Python file: {e}"

schema_run_python_file = types.FunctionDeclaration(
    name="run_python_file",
    description="it is used to run a given file, constrained to the working directory.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="filepath to the file which should be run, relative to the working directory.",
            ),
            "args": types.Schema(
                type=types.Type.ARRAY,
                description="additional arguements if any required to run the file",
                items=types.Schema(
                    type=types.Type.STRING
                )
            ),
        },
    ),
)


