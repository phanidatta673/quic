"""
Simplified QUIC File Transfer Service
Direct integration with QUIC core for testing
"""

import asyncio
import logging
import uuid
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Callable

# Add quic_core to path
current_dir = Path(__file__).parent
quic_core_path = current_dir.parent.parent.parent / "quic_core"
sys.path.insert(0, str(quic_core_path))

from app.utils.config import settings
from app.models.schemas import TransferStatus, TransferProgress

logger = logging.getLogger(__name__)

class SimpleQuicTransferService:
    """Simplified service for QUIC file transfers"""
    
    def __init__(self):
        self.active_transfers: Dict[str, dict] = {}
        self.transfer_results: Dict[str, dict] = {}
    
    async def upload_file_simple(
        self, 
        file_path: Path, 
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Upload file using QUIC core directly"""
        
        transfer_id = str(uuid.uuid4())
        
        try:
            # Import QUIC modules
            from client import send_multiple_files
            
            # Create transfer record
            self.active_transfers[transfer_id] = {
                "filename": file_path.name,
                "file_path": str(file_path),
                "status": TransferStatus.IN_PROGRESS,
                "started_at": datetime.utcnow(),
                "file_size": file_path.stat().st_size,
                "progress": 0
            }
            
            logger.info(f"Starting QUIC transfer for {file_path.name}")
            
            # Start transfer in background
            asyncio.create_task(self._execute_transfer(transfer_id, file_path))
            
            return transfer_id
            
        except Exception as e:
            logger.error(f"Failed to start transfer: {e}")
            self.active_transfers[transfer_id] = {
                "filename": file_path.name,
                "status": TransferStatus.FAILED,
                "error": str(e)
            }
            raise
    
    async def _execute_transfer(self, transfer_id: str, file_path: Path):
        """Execute the actual file transfer"""
        try:
            transfer = self.active_transfers[transfer_id]
            
            # Import the send function
            from client import send_multiple_files
            
            # Execute transfer
            success = await send_multiple_files(
                file_paths=[str(file_path)],
                server_host=settings.QUIC_HOST,
                server_port=settings.QUIC_PORT
            )
            
            if success:
                transfer["status"] = TransferStatus.COMPLETED
                transfer["completed_at"] = datetime.utcnow()
                transfer["progress"] = 100
                logger.info(f"Transfer {transfer_id} completed successfully")
            else:
                transfer["status"] = TransferStatus.FAILED
                transfer["error"] = "Transfer failed"
                logger.error(f"Transfer {transfer_id} failed")
                
        except Exception as e:
            logger.error(f"Transfer execution error: {e}")
            transfer = self.active_transfers.get(transfer_id, {})
            transfer["status"] = TransferStatus.FAILED
            transfer["error"] = str(e)
    
    async def get_transfer_progress(self, transfer_id: str) -> Optional[TransferProgress]:
        """Get transfer progress"""
        transfer = self.active_transfers.get(transfer_id)
        if not transfer:
            return None
        
        # Calculate progress
        if transfer["status"] == TransferStatus.COMPLETED:
            progress_percentage = 100.0
            transferred_bytes = transfer["file_size"]
        elif transfer["status"] == TransferStatus.IN_PROGRESS:
            # For now, just estimate based on time (would be better with real progress)
            elapsed = (datetime.utcnow() - transfer["started_at"]).total_seconds()
            progress_percentage = min(90, elapsed * 10)  # Rough estimate
            transferred_bytes = int(transfer["file_size"] * progress_percentage / 100)
        else:
            progress_percentage = 0.0
            transferred_bytes = 0
        
        return TransferProgress(
            transfer_id=transfer_id,
            filename=transfer["filename"],
            total_size=transfer["file_size"],
            transferred_bytes=transferred_bytes,
            chunks_sent=int(transferred_bytes / 65536) if transferred_bytes > 0 else 0,
            total_chunks=int(transfer["file_size"] / 65536) + 1,
            progress_percentage=progress_percentage
        )
    
    async def list_active_transfers(self) -> list:
        """List all active transfers"""
        result = []
        for transfer_id, transfer in self.active_transfers.items():
            if transfer["status"] in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS]:
                progress = await self.get_transfer_progress(transfer_id)
                if progress:
                    result.append(progress)
        return result
    
    async def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel a transfer"""
        transfer = self.active_transfers.get(transfer_id)
        if transfer and transfer["status"] == TransferStatus.IN_PROGRESS:
            transfer["status"] = TransferStatus.CANCELLED
            return True
        return False

# Global service instance
simple_quic_service = SimpleQuicTransferService()