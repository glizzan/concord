import json


def can_jsonify(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False
