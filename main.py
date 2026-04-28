from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.database import connect_db, close_db
from routers import auth, users, volunteers, ngos, posts, ai, uploads

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()

app = FastAPI(
    title="NGO Platform API",
    description=(
        "Backend for the NGO community platform. "
        "Supports Users, Volunteers, NGOs, Problems, Posts, Resources & Donations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow Flutter / Dart web + mobile) ──────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production to your actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(volunteers.router)
app.include_router(ngos.router)
app.include_router(posts.router)
app.include_router(ai.router)
app.include_router(uploads.router)

@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "NGO Platform API is running"}

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}