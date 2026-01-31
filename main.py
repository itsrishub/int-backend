from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import init_db
from endpoints import signup_router, profile_router, generic_router, theai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Include routers
app.include_router(signup_router)
app.include_router(profile_router)
app.include_router(generic_router)
app.include_router(theai_router)


@app.get("/")
def read_root():
    return {"message": "Hello from Interview AI API"}