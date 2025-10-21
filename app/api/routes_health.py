"""
Health check endpoint.
"""
from fastapi import APIRouter
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    Returns service status.
    """
    return HealthResponse(status="ok", version="1.0.0")
