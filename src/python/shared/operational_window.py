import yaml
import os
from datetime import datetime
import pytz

def is_operational_window_active() -> bool:
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist)
    current_hour = now_ist.hour

    # Get project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    config_path = os.path.join(project_root, "config", "config.yaml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            window = config.get("operational_window", {})
            start = window.get("start_hour_ist", 0)
            end = window.get("end_hour_ist", 24)
    except Exception:
        start = 0
        end = 24

    if start == end:
        return True # 24/7

    if start > end:
        return current_hour >= start or current_hour < end
    else:
        return current_hour >= start and current_hour < end
