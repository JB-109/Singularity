import os
import subprocess

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
        
        result = subprocess.run(["python3", abs_joined] + args, cwd=os.path.dirname(abs_joined), capture_output=True, text=True, timeout=30)
        final_return = [f'STDOUT: {result.stdout}', f'STDERR: {result.stderr}']
        if result.returncode != 0:
            final_return.append(f'Process exited with code {result.returncode}')
        return "\n".join(final_return)

    except Exception as e:
        return f"Error: executing Python file: {e}"

    