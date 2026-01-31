from flask import Blueprint

api = Blueprint('api', __name__)

@api.route('/api/hello')
def hello():
    return {"message": "Hello from API!"}