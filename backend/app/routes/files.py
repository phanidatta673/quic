"""
File Management API Routes
HTTP endpoints for file operations and management
"""

import logging
import mimetypes
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.models.schemas import FileListResponse, FileInfo, APIResponse
from app.utils.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/list", response_model=FileListResponse)
async def list_files(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(default=None, description="Search filename"),
    sort_by: str = Query(default="name", description="Sort by: name, size, date"),
    sort_order: str = Query(default="asc", description="Sort order: asc, desc")
):
    """
    List uploaded files with pagination and search
    
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **search**: Search term for filename filtering
    - **sort_by**: Sort field (name, size, date)
    - **sort_order**: Sort order (asc, desc)
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        
        if not upload_dir.exists():
            upload_dir.mkdir(exist_ok=True)
            return FileListResponse(
                success=True,
                message="No files found",
                data={
                    "files": [],
                    "total_count": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0
                }
            )
        
        # Get all files
        all_files = []
        for file_path in upload_dir.iterdir():
            if file_path.is_file() and not file_path.name.startswith('.'):
                # Skip if search term doesn't match
                if search and search.lower() not in file_path.name.lower():
                    continue
                
                stat = file_path.stat()
                mime_type, _ = mimetypes.guess_type(str(file_path))
                
                file_info = FileInfo(
                    filename=file_path.name,
                    size=stat.st_size,
                    mime_type=mime_type,
                    upload_date=datetime.fromtimestamp(stat.st_mtime)
                )
                all_files.append(file_info)
        
        # Sort files
        reverse = sort_order.lower() == "desc"
        if sort_by == "name":
            all_files.sort(key=lambda x: x.filename.lower(), reverse=reverse)
        elif sort_by == "size":
            all_files.sort(key=lambda x: x.size, reverse=reverse)
        elif sort_by == "date":
            all_files.sort(key=lambda x: x.upload_date or datetime.min, reverse=reverse)
        
        # Pagination
        total_count = len(all_files)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_files = all_files[start_idx:end_idx]
        total_pages = (total_count + page_size - 1) // page_size
        
        return FileListResponse(
            success=True,
            message=f"Found {total_count} files",
            data={
                "files": [file.dict() for file in page_files],
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "search": search,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        )
        
    except Exception as e:
        logger.error(f"List files error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download a file by filename
    
    - **filename**: Name of the file to download
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        file_path = upload_dir / filename
        
        # Security check - prevent path traversal
        if not file_path.resolve().is_relative_to(upload_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Not a file")
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"
        
        logger.info(f"Downloading file: {filename} ({file_path.stat().st_size} bytes)")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/info/{filename}", response_model=APIResponse)
async def get_file_info(filename: str):
    """
    Get detailed information about a file
    
    - **filename**: Name of the file
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        file_path = upload_dir / filename
        
        # Security check
        if not file_path.resolve().is_relative_to(upload_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        stat = file_path.stat()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        # Calculate file hash (for small files only)
        file_hash = None
        if stat.st_size < 50 * 1024 * 1024:  # Less than 50MB
            import hashlib
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
        
        file_info = FileInfo(
            filename=filename,
            size=stat.st_size,
            mime_type=mime_type,
            hash_sha256=file_hash,
            upload_date=datetime.fromtimestamp(stat.st_mtime)
        )
        
        return APIResponse(
            success=True,
            message="File information retrieved",
            data=file_info.dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File info error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get file info: {str(e)}")


@router.delete("/delete/{filename}", response_model=APIResponse)
async def delete_file(filename: str):
    """
    Delete a file
    
    - **filename**: Name of the file to delete
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        file_path = upload_dir / filename
        
        # Security check
        if not file_path.resolve().is_relative_to(upload_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_size = file_path.stat().st_size
        file_path.unlink()  # Delete the file
        
        logger.info(f"Deleted file: {filename} ({file_size} bytes)")
        
        return APIResponse(
            success=True,
            message=f"File {filename} deleted successfully",
            data={
                "filename": filename,
                "size": file_size
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete file error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


@router.get("/storage-info", response_model=APIResponse)
async def get_storage_info():
    """
    Get storage usage information
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        
        if not upload_dir.exists():
            return APIResponse(
                success=True,
                message="Storage information retrieved",
                data={
                    "total_files": 0,
                    "total_size": 0,
                    "upload_directory": str(upload_dir),
                    "max_file_size": settings.MAX_FILE_SIZE,
                    "allowed_extensions": settings.allowed_extensions_list
                }
            )
        
        total_files = 0
        total_size = 0
        
        for file_path in upload_dir.iterdir():
            if file_path.is_file() and not file_path.name.startswith('.'):
                total_files += 1
                total_size += file_path.stat().st_size
        
        # Format sizes
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024**2:
                return f"{size_bytes/1024:.1f} KB"
            elif size_bytes < 1024**3:
                return f"{size_bytes/(1024**2):.1f} MB"
            else:
                return f"{size_bytes/(1024**3):.1f} GB"
        
        return APIResponse(
            success=True,
            message="Storage information retrieved",
            data={
                "total_files": total_files,
                "total_size": total_size,
                "total_size_formatted": format_size(total_size),
                "upload_directory": str(upload_dir.absolute()),
                "max_file_size": settings.MAX_FILE_SIZE,
                "max_file_size_bytes": settings.max_file_size_bytes,
                "allowed_extensions": settings.allowed_extensions_list
            }
        )
        
    except Exception as e:
        logger.error(f"Storage info error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get storage info: {str(e)}")


@router.post("/cleanup", response_model=APIResponse)
async def cleanup_old_files(
    days_old: int = Query(default=7, ge=1, description="Delete files older than X days")
):
    """
    Clean up old files
    
    - **days_old**: Delete files older than this many days (default: 7)
    """
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        
        if not upload_dir.exists():
            return APIResponse(
                success=True,
                message="No files to clean up",
                data={"deleted_files": 0, "freed_space": 0}
            )
        
        import time
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        
        deleted_files = 0
        freed_space = 0
        
        for file_path in upload_dir.iterdir():
            if file_path.is_file() and not file_path.name.startswith('.'):
                if file_path.stat().st_mtime < cutoff_time:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    deleted_files += 1
                    freed_space += file_size
                    logger.info(f"Cleaned up old file: {file_path.name}")
        
        return APIResponse(
            success=True,
            message=f"Cleanup completed: {deleted_files} files deleted",
            data={
                "deleted_files": deleted_files,
                "freed_space": freed_space,
                "freed_space_formatted": f"{freed_space/(1024**2):.1f} MB",
                "days_old": days_old
            }
        )
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")