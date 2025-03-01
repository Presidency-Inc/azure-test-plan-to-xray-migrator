import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def save_json_data(data: Any, filename: str, base_path: str = "data/extraction"):
    """Save data to a JSON file in the specified directory"""
    # Create directory if it doesn't exist
    path = Path(base_path)
    path.mkdir(parents=True, exist_ok=True)
    
    file_path = path / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, cls=DateTimeEncoder, indent=2, ensure_ascii=False) 