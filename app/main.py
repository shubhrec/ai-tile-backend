"""
FastAPI main application entrypoint for AI Tile Visualization Tool.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
import os

# Load environment variables from .env file
load_dotenv()

from app.api import routes_health, routes_generate, routes_gallery, routes_uploads, routes_tiles, routes_homes, routes_chats

app = FastAPI(
    title="AI Tile Visualization API",
    description="Backend service for generating AI-powered tile visualizations",
    version="1.0.0"
)

app.mount(
    "/generated",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../generated")),
    name="generated",
)


# CORS middleware - configure for your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(routes_health.router, tags=["health"])
app.include_router(routes_generate.router, tags=["generation"])
app.include_router(routes_gallery.router, tags=["gallery"])
app.include_router(routes_uploads.router, prefix="/api", tags=["uploads"])
app.include_router(routes_tiles.router, tags=["tiles"])
app.include_router(routes_homes.router, tags=["homes"])
app.include_router(routes_chats.router, tags=["chats"])


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    print("🚀 AI Tile Visualization API starting up...")
    print(f"📍 Environment: {os.getenv('ENVIRONMENT', 'development')}")

    # Debug: Check if API key is loaded
    api_key = os.getenv('NANO_BANANA_API_KEY')
    if api_key:
        print(f"✅ NANO_BANANA_API_KEY loaded ({len(api_key)} characters)")
    else:
        print("⚠️  WARNING: NANO_BANANA_API_KEY not found in environment!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("👋 AI Tile Visualization API shutting down...")
