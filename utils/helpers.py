from bson import ObjectId
from datetime import datetime
import json

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for handling MongoDB ObjectId and datetime"""
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)