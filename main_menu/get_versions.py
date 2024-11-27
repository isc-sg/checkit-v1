
import os
import importlib
import sys
import subprocess

sys.path.append('/home/checkit/camera_checker')

# Set the DJANGO_SETTINGS_MODULE environment variable to point to your Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_checker.settings')

# Import Django to configure it
try:
    import django
    django.setup()
except ImportError as e:
    raise ImportError("Couldn't import Django. Are you sure it's installed and "
                      "available on your PYTHONPATH environment variable? Did you "
                      "forget to activate a virtual environment?") from e

def get_version_from_so_file(file_path):
    """Try to import the module from the given file path and return the version."""
    try:
        # Extract the base name of the file without extension
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        new_name = base_name.split(".")[0]
        # Import the module using importlib
        module = importlib.import_module("main_menu." + new_name)
        # Return the __version__ attribute if it exists
        return getattr(module, '__version__', 'Version not found')
    except (ModuleNotFoundError, ImportError):
        return 'Import failed'
    except AttributeError:
        return 'Version not found'

def get_version_from_py_file(file_path):
    """Use grep to find the __version__ in a .py file."""
    try:
        # Run grep command to extract the version
        result = subprocess.run(['grep', '__version__', file_path], capture_output=True, text=True)
        if result.returncode == 0:
            # Extract version from the output
            for line in result.stdout.splitlines():
                parts = line.split('=')
                if len(parts) > 1:
                    version = parts[1].strip().strip('"').strip("'")
                    return version
        return 'Version not found'
    except Exception as e:
        print(f"An error occurred while reading {file_path}: {e}")
        return 'Error extracting version'

def scan_directory_for_versions(directory):
    """Scan the directory for .so and .py files and print their names and versions."""
    try:
        # List all files in the directory
        files = os.listdir(directory)
        for file in files:
            # Check if the file is a .so or .py file
            file_path = os.path.join(directory, file)
            if file.endswith('.so'):
                version = get_version_from_so_file(file_path)
            elif file.endswith('.py'):
                version = get_version_from_py_file(file_path)
            else:
                continue  # Skip files that are neither .so nor .py
            print(f"{file:<50} {version}")
    except FileNotFoundError:
        print("Directory not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Replace 'your_directory_path' with the path to your main directory
    scan_directory_for_versions('/home/checkit/camera_checker/main_menu')