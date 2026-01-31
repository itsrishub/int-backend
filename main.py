from flask import Flask
from endpoints import hello, nothello


app = Flask(__name__)


app.register_blueprint(hello)
app.register_blueprint(nothello)


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