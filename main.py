from flask import Flask
from endpoints import api


app = Flask(__name__)


app.register_blueprint(api)


@app.get("/")
def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <body>
        <h1>hello</h1>
    </body>
    </html>
    """