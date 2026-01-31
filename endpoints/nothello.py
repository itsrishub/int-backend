from flask import Blueprint, jsonify


nothello = Blueprint("nothello_api", __name__)


@nothello.get("/api/haha")
def get_nothello():
    return jsonify(
        {
            "data": [
                {"id": 1, "name": "Sample Item 1", "value": 200},
                {"id": 2, "name": "Sample Item 2", "value": 200},
                {"id": 3, "name": "Sample Item 3", "value": 300},
            ],
            "total": 3,
            "timestamp": "2024-01-01T00:00:00Z",
        }
    )