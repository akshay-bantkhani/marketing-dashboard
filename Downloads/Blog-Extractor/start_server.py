"""Start the blog extractor web server (auto-installs dependencies)."""
import subprocess
import sys
import os

# Install dependencies if missing
project_dir = os.path.dirname(os.path.abspath(__file__))
subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."], cwd=project_dir)

# Start the app
from blog_extractor.app import main
main()
