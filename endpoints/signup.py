from fastapi import APIRouter

router = APIRouter(prefix="/api/signup", tags=["Signup"])

@router.post("/")
def create_user():
    return {"message": "User created"}


@router.get("/{user_id}")
def get_user(user_id: int):
    return {"user_id": user_id}