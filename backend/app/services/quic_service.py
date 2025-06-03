"""
QUIC File Transfer Service
Integrates FastAPI backend with QUIC core functionality
"""

import asyncio
import logging
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from app.utils.config import settings
from app.models.schemas import TransferStatus, TransferProgress, TransferResult

logger = logging.getLogger(__name__)

@dataclass
class ActiveTransfer:
    """Track active file transfer state"""
    transfer_id: str
    filename: str
    file_path: Path
    total_size: int
    total_chunks: int
    chunk_size: int
    status: TransferStatus = TransferStatus.PENDING
    started_at: Optional[datetime] = None
    progress_callback: Optional[Callable] = None
    stream_ids: List[int] = field(default_factory=list)
    chunks_sent: int = 0
    bytes_transferred: int = 0
    error_message: Optional[str] = None


class QuicFileTransferService:
    """Service for handling QUIC file transfers"""
    
    def __init__(self):
        self.active_transfers: Dict[str, ActiveTransfer] = {}
        self.transfer_history: List[TransferResult] = []
        self.quic_client = None
        self.quic_connection = None  # Store the context manager
        self._lock = asyncio.Lock()
    
    async def initialize_quic_client(self):
        """Initialize QUIC client connection"""
        try:
            # Import QUIC client here to avoid circular imports
            import sys
            import os
            
            # Add quic_core to path
            quic_core_path = os.path.join(os.path.dirname(__file__), '../../..', 'quic_core')
            sys.path.append(quic_core_path)
            
            from client import MultiStreamQuicFileClient
            from aioquic.asyncio import connect
            from aioquic.quic.configuration import QuicConfiguration
            
            configuration = QuicConfiguration(
                alpn_protocols=["file-transfer"],
                is_client=True,
                verify_mode=False,  # For testing with self-signed certs
            )
            
            # Connect to QUIC server and store the connection
            self.quic_connection = connect(
                host=settings.QUIC_HOST,
                port=settings.QUIC_PORT,
                configuration=configuration,
                create_protocol=MultiStreamQuicFileClient,
            )
            
            # Enter the async context manager
            self.quic_client = await self.quic_connection.__aenter__()
            
            logger.info(f"QUIC client connected to {settings.QUIC_HOST}:{settings.QUIC_PORT}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize QUIC client: {e}")
            return False
    
    async def upload_file(
        self,
        file_path: Path,
        chunk_size: int = 64 * 1024,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Upload a file via QUIC"""
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Generate transfer ID
        transfer_id = str(uuid.uuid4())
        
        # Calculate file info
        file_size = file_path.stat().st_size
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        # Create transfer record
        transfer = ActiveTransfer(
            transfer_id=transfer_id,
            filename=file_path.name,
            file_path=file_path,
            total_size=file_size,
            total_chunks=total_chunks,
            chunk_size=chunk_size,
            progress_callback=progress_callback,
            started_at=datetime.utcnow()
        )
        
        async with self._lock:
            self.active_transfers[transfer_id] = transfer
        
        try:
            # Ensure QUIC client is initialized
            if not self.quic_client:
                if not await self.initialize_quic_client():
                    raise ConnectionError("Failed to connect to QUIC server")
            
            # Update status
            transfer.status = TransferStatus.IN_PROGRESS
            
            # Create progress wrapper
            def internal_progress_callback(stream_id: int, chunks_sent: int, total_chunks: int):
                transfer.chunks_sent = chunks_sent
                transfer.bytes_transferred = chunks_sent * chunk_size
                
                # Call external callback if provided
                if progress_callback:
                    progress_callback(transfer_id, chunks_sent, total_chunks)
            
            # Start file transfer
            stream_id = await self.quic_client.send_file_async(
                file_path,
                chunk_size=chunk_size,
                progress_callback=internal_progress_callback
            )
            
            transfer.stream_ids.append(stream_id)
            logger.info(f"Started transfer {transfer_id} on stream {stream_id}")
            
            # Wait for completion (in background)
            asyncio.create_task(self._monitor_transfer(transfer_id, stream_id))
            
            return transfer_id
            
        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.error_message = str(e)
            logger.error(f"Upload failed for {transfer_id}: {e}")
            raise
    
    async def _monitor_transfer(self, transfer_id: str, stream_id: int):
        """Monitor transfer completion"""
        try:
            transfer = self.active_transfers.get(transfer_id)
            if not transfer:
                return
            
            # Wait for transfer completion
            success = await self.quic_client.wait_for_transfer(stream_id, timeout=300)
            
            if success:
                transfer.status = TransferStatus.COMPLETED
                transfer.bytes_transferred = transfer.total_size
                logger.info(f"Transfer {transfer_id} completed successfully")
            else:
                transfer.status = TransferStatus.FAILED
                transfer.error_message = "Transfer timeout or failed"
                logger.error(f"Transfer {transfer_id} failed")
            
            # Move to history
            await self._finalize_transfer(transfer_id)
            
        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.error_message = str(e)
            logger.error(f"Error monitoring transfer {transfer_id}: {e}")
            await self._finalize_transfer(transfer_id)
    
    async def _finalize_transfer(self, transfer_id: str):
        """Move completed transfer to history"""
        async with self._lock:
            transfer = self.active_transfers.pop(transfer_id, None)
            if transfer:
                duration = (datetime.utcnow() - transfer.started_at).total_seconds()
                avg_speed = transfer.bytes_transferred / duration if duration > 0 else 0
                
                result = TransferResult(
                    transfer_id=transfer_id,
                    status=transfer.status,
                    filename=transfer.filename,
                    total_size=transfer.total_size,
                    transferred_bytes=transfer.bytes_transferred,
                    duration_seconds=duration,
                    average_speed=avg_speed,
                    error_message=transfer.error_message,
                    completed_at=datetime.utcnow()
                )
                
                self.transfer_history.append(result)
    
    async def get_transfer_progress(self, transfer_id: str) -> Optional[TransferProgress]:
        """Get current transfer progress"""
        transfer = self.active_transfers.get(transfer_id)
        if not transfer:
            return None
        
        progress_percentage = (transfer.chunks_sent / transfer.total_chunks * 100) if transfer.total_chunks > 0 else 0
        
        # Calculate transfer rate
        if transfer.started_at:
            elapsed = (datetime.utcnow() - transfer.started_at).total_seconds()
            transfer_rate = transfer.bytes_transferred / elapsed if elapsed > 0 else 0
            
            # Calculate ETA
            remaining_bytes = transfer.total_size - transfer.bytes_transferred
            eta_seconds = int(remaining_bytes / transfer_rate) if transfer_rate > 0 else None
        else:
            transfer_rate = None
            eta_seconds = None
        
        return TransferProgress(
            transfer_id=transfer_id,
            stream_id=transfer.stream_ids[0] if transfer.stream_ids else None,
            filename=transfer.filename,
            total_size=transfer.total_size,
            transferred_bytes=transfer.bytes_transferred,
            chunks_sent=transfer.chunks_sent,
            total_chunks=transfer.total_chunks,
            progress_percentage=progress_percentage,
            transfer_rate=transfer_rate,
            eta_seconds=eta_seconds
        )
    
    async def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel an active transfer"""
        async with self._lock:
            transfer = self.active_transfers.get(transfer_id)
            if not transfer:
                return False
            
            transfer.status = TransferStatus.CANCELLED
            transfer.error_message = "Transfer cancelled by user"
            
            # TODO: Implement actual stream cancellation in QUIC client
            logger.info(f"Transfer {transfer_id} cancelled")
            
            await self._finalize_transfer(transfer_id)
            return True
    
    async def list_active_transfers(self) -> List[TransferProgress]:
        """Get list of all active transfers"""
        progress_list = []
        for transfer_id in list(self.active_transfers.keys()):
            progress = await self.get_transfer_progress(transfer_id)
            if progress:
                progress_list.append(progress)
        return progress_list
    
    async def get_transfer_history(self, limit: int = 50) -> List[TransferResult]:
        """Get transfer history"""
        return self.transfer_history[-limit:]
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.quic_client and self.quic_connection:
            try:
                # Exit the async context manager
                await self.quic_connection.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing QUIC connection: {e}")
        
        logger.info("QUIC service cleanup completed")


# Global service instance
quic_service = QuicFileTransferService()