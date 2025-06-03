"""
Configuration management for FastAPI backend
"""

from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # FastAPI Configuration
    DEBUG: bool = Field(default=True, description="Debug mode")
    HOST: str = Field(default="localhost", description="Host to bind to")
    PORT: int = Field(default=8000, description="Port to bind to")
    RELOAD: bool = Field(default=True, description="Auto-reload on code changes")
    
    # QUIC Server Configuration
    QUIC_HOST: str = Field(default="localhost", description="QUIC server host")
    QUIC_PORT: int = Field(default=4433, description="QUIC server port")
    QUIC_CERT_PATH: str = Field(default="../quic_core/certs/cert.pem", description="QUIC SSL certificate path")
    QUIC_KEY_PATH: str = Field(default="../quic_core/certs/key.pem", description="QUIC SSL key path")
    
    # File Upload Configuration
    UPLOAD_DIR: str = Field(default="./uploads", description="Directory for uploaded files")
    MAX_FILE_SIZE: str = Field(default="100MB", description="Maximum file size")
    ALLOWED_EXTENSIONS: str = Field(
        default=".txt,.pdf,.jpg,.png,.doc,.docx,.zip,.mp4,.mp3,.json,.csv",
        description="Allowed file extensions"
    )
    
    # Database Configuration
    DATABASE_URL: str = Field(default="sqlite:///./transfers.db", description="Database URL")
    
    # Security
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production", description="Secret key for JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration")
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Allowed CORS origins"
    )
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE: str = Field(default="./logs/backend.log", description="Log file path")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Convert comma-separated origins to list"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """Convert comma-separated extensions to list"""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]
    
    @property
    def max_file_size_bytes(self) -> int:
        """Convert MAX_FILE_SIZE string to bytes"""
        size_str = self.MAX_FILE_SIZE.upper()
        if size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)  # Assume bytes
    
    @property
    def quic_cert_path_resolved(self) -> Path:
        """Resolve QUIC certificate path"""
        return Path(self.QUIC_CERT_PATH).resolve()
    
    @property
    def quic_key_path_resolved(self) -> Path:
        """Resolve QUIC key path"""
        return Path(self.QUIC_KEY_PATH).resolve()

# Global settings instance
settings = Settings()