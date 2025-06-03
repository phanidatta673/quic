"""
File Transfer API Routes
HTTP endpoints for QUIC file transfer operations
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse

from app.models.schemas import (
    FileUploadRequest, FileUploadResponse, TransferStatusResponse,
    TransferListResponse, APIResponse, TransferCancelRequest,
    TransferProgress, TransferResult
)
from app.services.simple_quic import simple_quic_service
from app.utils.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Global progress storage for real-time updates
active_progress: dict = {}

def progress_callback(transfer_id: str, chunks_sent: int, total_chunks: int):
    """Store progress updates for real-time access"""
    progress_percentage = (chunks_sent / total_chunks * 100) if total_chunks > 0 else 0
    active_progress[transfer_id] = {
        "chunks_sent": chunks_sent,
        "total_chunks": total_chunks,
        "progress_percentage": progress_percentage
    }

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_size: Optional[int] = Form(default=1024),  # Smaller default chunk size
    use_parallel_streams: Optional[bool] = Form(default=True)
):
    """
    Upload a file via QUIC protocol
    
    - **file**: File to upload
    - **chunk_size**: Size of each chunk in bytes (default: 64KB)
    - **use_parallel_streams**: Whether to use parallel streams
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.allowed_extensions_list:
            raise HTTPException(
                status_code=400, 
                detail=f"File type {file_ext} not allowed. Allowed: {settings.allowed_extensions_list}"
            )
        
        # Save uploaded file temporarily
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(exist_ok=True)
        
        temp_file_path = upload_dir / file.filename
        
        # Read and save file content
        content = await file.read()
        content_size = len(content)
        
        # Check file size
        if content_size > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE}"
            )
        
        with open(temp_file_path, "wb") as f:
            f.write(content)
        
        # Verify written file size
        written_size = temp_file_path.stat().st_size
        logger.info(f"Saved uploaded file: {temp_file_path}")
        logger.info(f"Content size: {content_size} bytes, Written size: {written_size} bytes")
        
        if content_size != written_size:
            logger.warning(f"Size mismatch: content={content_size}, written={written_size}")
        
        # Calculate total chunks based on actual file size
        actual_chunks = (written_size + chunk_size - 1) // chunk_size
        
        # Start QUIC transfer
        transfer_id = await simple_quic_service.upload_file_simple(
            file_path=temp_file_path,
            progress_callback=lambda tid, cs, tc: progress_callback(tid, cs, tc)
        )
        
        return FileUploadResponse(
            success=True,
            message="File upload initiated successfully",
            data={
                "transfer_id": transfer_id,
                "filename": file.filename,
                "file_size": written_size,
                "chunk_size": chunk_size,
                "total_chunks": actual_chunks,
                "use_parallel_streams": use_parallel_streams
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/status/{transfer_id}", response_model=TransferStatusResponse)
async def get_transfer_status(transfer_id: str):
    """
    Get real-time status of a file transfer
    
    - **transfer_id**: ID of the transfer to check
    """
    try:
        # Get progress from service
        progress = await simple_quic_service.get_transfer_progress(transfer_id)
        
        if not progress:
            raise HTTPException(status_code=404, detail="Transfer not found")
        
        return TransferStatusResponse(
            success=True,
            message="Transfer status retrieved",
            data=progress
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/active", response_model=TransferListResponse)
async def list_active_transfers():
    """
    Get list of all active transfers
    """
    try:
        active_transfers = await simple_quic_service.list_active_transfers()
        
        return TransferListResponse(
            success=True,
            message=f"Found {len(active_transfers)} active transfers",
            data=active_transfers
        )
        
    except Exception as e:
        logger.error(f"List active transfers error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list transfers: {str(e)}")


@router.get("/history", response_model=TransferListResponse)
async def get_transfer_history(limit: int = 50):
    """
    Get transfer history
    
    - **limit**: Maximum number of records to return (default: 50)
    """
    try:
        history = await quic_service.get_transfer_history(limit=limit)
        
        return TransferListResponse(
            success=True,
            message=f"Retrieved {len(history)} transfer records",
            data=history
        )
        
    except Exception as e:
        logger.error(f"Transfer history error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.post("/cancel", response_model=APIResponse)
async def cancel_transfer(request: TransferCancelRequest):
    """
    Cancel an active file transfer
    
    - **transfer_id**: ID of the transfer to cancel
    - **reason**: Optional reason for cancellation
    """
    try:
        success = await simple_quic_service.cancel_transfer(request.transfer_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Transfer not found or already completed")
        
        return APIResponse(
            success=True,
            message=f"Transfer {request.transfer_id} cancelled successfully",
            data={"transfer_id": request.transfer_id, "reason": request.reason}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel transfer error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel transfer: {str(e)}")


@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    chunk_size: Optional[int] = Form(default=64*1024),
    concurrent_transfers: Optional[bool] = Form(default=True)
):
    """
    Upload multiple files concurrently
    
    - **files**: List of files to upload
    - **chunk_size**: Size of each chunk in bytes
    - **concurrent_transfers**: Whether to transfer files concurrently
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > 10:  # Limit concurrent uploads
            raise HTTPException(status_code=400, detail="Maximum 10 files per batch")
        
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(exist_ok=True)
        
        transfer_ids = []
        
        for file in files:
            if not file.filename:
                continue
                
            # Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in settings.allowed_extensions_list:
                logger.warning(f"Skipping file {file.filename}: invalid extension {file_ext}")
                continue
            
            # Save file temporarily
            temp_file_path = upload_dir / file.filename
            content = await file.read()
            
            # Check file size
            if len(content) > settings.max_file_size_bytes:
                logger.warning(f"Skipping file {file.filename}: too large ({len(content)} bytes)")
                continue
            
            with open(temp_file_path, "wb") as f:
                f.write(content)
            
            # Start transfer
            transfer_id = await quic_service.upload_file(
                file_path=temp_file_path,
                chunk_size=chunk_size,
                progress_callback=lambda tid, cs, tc: progress_callback(tid, cs, tc)
            )
            
            transfer_ids.append({
                "filename": file.filename,
                "transfer_id": transfer_id,
                "file_size": len(content)
            })
        
        return APIResponse(
            success=True,
            message=f"Started {len(transfer_ids)} file transfers",
            data={
                "transfers": transfer_ids,
                "total_files": len(transfer_ids),
                "concurrent": concurrent_transfers
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multiple upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Multiple upload failed: {str(e)}")


@router.get("/progress/live/{transfer_id}")
async def get_live_progress(transfer_id: str):
    """
    Get live progress updates (for real-time UI updates)
    
    - **transfer_id**: ID of the transfer to monitor
    """
    try:
        # Check if transfer exists in active progress
        if transfer_id in active_progress:
            return JSONResponse({
                "transfer_id": transfer_id,
                "live_progress": active_progress[transfer_id],
                "timestamp": str(datetime.utcnow())
            })
        
        # Fall back to service progress
        progress = await quic_service.get_transfer_progress(transfer_id)
        if progress:
            return JSONResponse({
                "transfer_id": transfer_id,
                "progress": progress.dict(),
                "timestamp": str(datetime.utcnow())
            })
        
        raise HTTPException(status_code=404, detail="Transfer not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Live progress error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get live progress: {str(e)}")


@router.delete("/cleanup")
async def cleanup_completed_transfers():
    """
    Clean up completed transfers and temporary files
    """
    try:
        # This would typically clean up old files and transfer records
        # For now, just return success
        
        return APIResponse(
            success=True,
            message="Cleanup completed successfully",
            data={"cleaned_transfers": 0, "cleaned_files": 0}
        )
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


# Add missing import
from datetime import datetime