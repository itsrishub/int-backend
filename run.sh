python3 -m venv venv
source venv/bin/activate
pip install uvicorn fastapi
python3 -m uvicorn main:app --reload