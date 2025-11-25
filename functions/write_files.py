import os

def write_files(working_dir, file_path, content):

    joined_path = os.path.join(working_dir, file_path)
    abs_work_path = os.path.abspath(working_dir)
    abs_joined = os.path.abspath(joined_path)

    try:

        if not abs_joined.startswith(abs_work_path):
            return f'Error: Cannot write to "{file_path}" as it is outside the permitted working directory'
        
        if not os.path.exists(joined_path):
            os.makedirs(os.path.dirname(abs_joined), exist_ok=True)
        with open(joined_path, "w") as f:
            f.write(content)
            return f'Successfully wrote to "{file_path}" ({len(content)} characters written)'

    except Exception as e:
            return f"Error: {e}"
        

