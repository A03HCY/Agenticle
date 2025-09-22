import os
import shutil
import subprocess
import sys

# Get the root directory of the project
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def clean():
    """
    Removes previous build artifacts.
    """
    print("--- Cleaning up old build artifacts ---")
    folders_to_remove = ["build", "dist"]
    
    for folder in folders_to_remove:
        path = os.path.join(ROOT_DIR, folder)
        if os.path.isdir(path):
            print(f"Removing directory: {path}")
            shutil.rmtree(path)

    # Also remove .egg-info directories
    for item in os.listdir(ROOT_DIR):
        if item.endswith(".egg-info"):
            path = os.path.join(ROOT_DIR, item)
            print(f"Removing directory: {path}")
            shutil.rmtree(path)
    
    print("--- Cleanup complete ---\n")

def build_package():
    """
    Builds the source distribution and wheel for the package.
    """
    print("--- Building package (sdist and wheel) ---")
    
    # The command to execute
    # We use sys.executable to ensure we're using the same python interpreter
    # that is running the script.
    command = [sys.executable, "setup.py", "sdist", "bdist_wheel"]
    
    try:
        # Run the command
        process = subprocess.Popen(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8',
            cwd=ROOT_DIR
        )

        # Print output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        # Check for errors
        if process.returncode != 0:
            print(f"\n--- Build failed with exit code {process.returncode} ---")
            sys.exit(process.returncode)
        else:
            print("\n--- Build successful ---")
            print("Package created in 'dist/' directory.")

    except FileNotFoundError:
        print("Error: 'setup.py' not found. Make sure you are in the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    """
    Main execution block to run the build process.
    """
    # 1. Clean up previous builds
    clean()
    
    # 2. Build the new package
    build_package()
