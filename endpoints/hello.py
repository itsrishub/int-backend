from flask import Blueprint, jsonify


hello = Blueprint("api", __name__)


@hello.get("/api/data")
def get_sample_data():
    return jsonify(
        {
            "data": [
                {"id": 1, "name": "Sample Item 1", "value": 100},
                {"id": 2, "name": "Sample Item 2", "value": 200},
                {"id": 3, "name": "Sample Item 3", "value": 300},
            ],
            "total": 3,
            "timestamp": "2024-01-01T00:00:00Z",
        }
    )