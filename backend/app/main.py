#!/usr/bin/env python3
"""
FastAPI Backend for QUIC File Transfer
Main application entry point
"""

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.utils.config import settings
from app.utils.logger import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    # Startup
    logger.info("Starting FastAPI backend for QUIC File Transfer")
    
    # Create necessary directories
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(exist_ok=True)
    
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    logger.info(f"Upload directory: {upload_dir.absolute()}")
    logger.info(f"QUIC server configured for: {settings.QUIC_HOST}:{settings.QUIC_PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI backend")

# Create FastAPI application
app = FastAPI(
    title="QUIC File Transfer API",
    description="FastAPI backend for QUIC-based file transfers with real-time progress tracking",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "internal_error"}
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "quic-file-transfer-backend",
        "version": "1.0.0",
        "quic_server": f"{settings.QUIC_HOST}:{settings.QUIC_PORT}"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "QUIC File Transfer API",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }

# Include routers
from app.routes import transfers, files
app.include_router(transfers.router, prefix="/api/transfers", tags=["transfers"])
app.include_router(files.router, prefix="/api/files", tags=["files"])

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )