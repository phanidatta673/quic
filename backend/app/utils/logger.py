"""
Logging configuration for FastAPI backend
"""

import logging
import logging.handlers
from pathlib import Path
from app.utils.config import settings


def setup_logging():
    """Configure logging for the application"""
    
    # Create logs directory if it doesn't exist
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    root_logger.addHandler(file_handler)
    
    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    
    return root_logger