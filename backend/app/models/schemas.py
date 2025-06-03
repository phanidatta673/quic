"""
Pydantic models for QUIC File Transfer API
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator


class TransferStatus(str, Enum):
    """File transfer status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransferType(str, Enum):
    """File transfer type enumeration"""
    UPLOAD = "upload"
    DOWNLOAD = "download"


# Request Models
class FileUploadRequest(BaseModel):
    """Request model for file upload"""
    chunk_size: Optional[int] = Field(default=64*1024, ge=1024, le=1024*1024, description="Chunk size in bytes")
    use_parallel_streams: Optional[bool] = Field(default=True, description="Use multiple parallel streams")
    max_parallel_streams: Optional[int] = Field(default=4, ge=1, le=10, description="Maximum parallel streams")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_size": 65536,
                "use_parallel_streams": True,
                "max_parallel_streams": 4
            }
        }


class MultipleFileUploadRequest(BaseModel):
    """Request model for multiple file upload"""
    file_paths: List[str] = Field(..., min_items=1, description="List of file paths to upload")
    chunk_size: Optional[int] = Field(default=64*1024, ge=1024, le=1024*1024)
    concurrent_transfers: Optional[bool] = Field(default=True, description="Transfer files concurrently")
    
    @validator('file_paths')
    def validate_file_paths(cls, v):
        if not v:
            raise ValueError('At least one file path is required')
        return v


class TransferCancelRequest(BaseModel):
    """Request model to cancel a transfer"""
    transfer_id: str = Field(..., description="Transfer ID to cancel")
    reason: Optional[str] = Field(default="User cancelled", description="Cancellation reason")


# Response Models
class TransferProgress(BaseModel):
    """Transfer progress information"""
    transfer_id: str
    stream_id: Optional[int] = None
    filename: str
    total_size: int
    transferred_bytes: int
    chunks_sent: int
    total_chunks: int
    progress_percentage: float = Field(..., ge=0, le=100)
    transfer_rate: Optional[float] = Field(default=None, description="Transfer rate in bytes/second")
    eta_seconds: Optional[int] = Field(default=None, description="Estimated time to completion")
    
    class Config:
        json_schema_extra = {
            "example": {
                "transfer_id": "transfer_123",
                "stream_id": 1,
                "filename": "document.pdf",
                "total_size": 1048576,
                "transferred_bytes": 524288,
                "chunks_sent": 8,
                "total_chunks": 16,
                "progress_percentage": 50.0,
                "transfer_rate": 65536.0,
                "eta_seconds": 8
            }
        }


class FileInfo(BaseModel):
    """File information model"""
    filename: str
    size: int
    mime_type: Optional[str] = None
    hash_sha256: Optional[str] = None
    upload_date: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "document.pdf",
                "size": 1048576,
                "mime_type": "application/pdf",
                "hash_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "upload_date": "2024-01-15T10:30:00Z"
            }
        }


class TransferResult(BaseModel):
    """Transfer completion result"""
    transfer_id: str
    status: TransferStatus
    filename: str
    total_size: int
    transferred_bytes: int
    duration_seconds: float
    average_speed: float = Field(..., description="Average transfer speed in bytes/second")
    error_message: Optional[str] = None
    completed_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "transfer_id": "transfer_123",
                "status": "completed",
                "filename": "document.pdf",
                "total_size": 1048576,
                "transferred_bytes": 1048576,
                "duration_seconds": 16.5,
                "average_speed": 63548.0,
                "error_message": None,
                "completed_at": "2024-01-15T10:30:16Z"
            }
        }


class TransferSession(BaseModel):
    """Complete transfer session information"""
    session_id: str
    transfer_type: TransferType
    status: TransferStatus
    files: List[FileInfo]
    progress: List[TransferProgress]
    total_files: int
    completed_files: int
    total_size: int
    transferred_size: int
    overall_progress: float = Field(..., ge=0, le=100)
    started_at: datetime
    estimated_completion: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_456",
                "transfer_type": "upload",
                "status": "in_progress",
                "files": [
                    {
                        "filename": "doc1.pdf",
                        "size": 1048576,
                        "mime_type": "application/pdf"
                    }
                ],
                "progress": [],
                "total_files": 3,
                "completed_files": 1,
                "total_size": 3145728,
                "transferred_size": 1048576,
                "overall_progress": 33.3,
                "started_at": "2024-01-15T10:30:00Z",
                "estimated_completion": "2024-01-15T10:32:00Z"
            }
        }


# API Response Models
class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {},
                "error": None,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class FileUploadResponse(APIResponse):
    """Response model for file upload initiation"""
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contains transfer_id, session_id, and initial progress"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "File upload initiated",
                "data": {
                    "transfer_id": "transfer_123",
                    "session_id": "session_456",
                    "filename": "document.pdf",
                    "file_size": 1048576,
                    "chunk_size": 65536,
                    "total_chunks": 16
                },
                "error": None,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class TransferListResponse(APIResponse):
    """Response model for transfer list"""
    data: Optional[List[TransferSession]] = None


class TransferStatusResponse(APIResponse):
    """Response model for transfer status check"""
    data: Optional[TransferProgress] = None


class FileListResponse(APIResponse):
    """Response model for file listing"""
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contains files list and pagination info"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Files retrieved successfully",
                "data": {
                    "files": [],
                    "total_count": 10,
                    "page": 1,
                    "page_size": 20
                },
                "error": None,
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


# Error Models
class ValidationError(BaseModel):
    """Validation error details"""
    field: str
    message: str
    invalid_value: Any


class ErrorResponse(APIResponse):
    """Error response model"""
    success: bool = False
    data: None = None
    validation_errors: Optional[List[ValidationError]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "message": "Validation failed",
                "data": None,
                "error": "Invalid file format",
                "validation_errors": [
                    {
                        "field": "file",
                        "message": "File type not allowed",
                        "invalid_value": "script.exe"
                    }
                ],
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }