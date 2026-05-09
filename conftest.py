import sys
import os

# Add project root to path so 'src.python.shared' imports work
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Also add project root for 'python.shared' imports
if project_root not in sys.path:
    sys.path.insert(0, project_root)
