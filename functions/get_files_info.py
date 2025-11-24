import os

def get_files_info(working_dir, dir="."):

    full_path = os.path.join(working_dir, dir)
    abs_working = os.path.abspath(working_dir)
    abs_full = os.path.abspath(full_path)
    
    try:
        if not abs_full.startswith(abs_working):
            return f'Error: Cannot list "{dir}" as it is outside the permitted working directory'
        elif not os.path.isdir(full_path):
            return f'Error: "{dir}" is not a directory'
        else:
            final_string = []
            for each in os.listdir(full_path):
                final_string.append(f"{each} file_size = {os.path.getsize(os.path.join(abs_full, each))} bytes, is_dir={os.path.isdir((os.path.join(abs_full, each)))}")
            return "\n".join(final_string)

    except Exception as e:
        return f"Error: {e}"