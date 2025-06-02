#!/usr/bin/env python3
"""
Enhanced QUIC File Transfer Client - Multiple concurrent streams
"""

import asyncio
import logging
import hashlib
import math
from pathlib import Path
from typing import Callable, Optional, List

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived

logger = logging.getLogger(__name__)

class MultiStreamQuicFileClient(QuicConnectionProtocol):
    """QUIC protocol handler supporting multiple concurrent file transfers"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response_handlers = {}
        self.chunk_acknowledgments = {}
        self.transfer_complete = {}
        self.transfer_errors = {}
        self.active_transfers = {}  # stream_id -> transfer info
    
    def quic_event_received(self, event: QuicEvent) -> None:
        """Handle QUIC events"""
        if isinstance(event, StreamDataReceived):
            self.handle_response(event.stream_id, event.data)
    
    def handle_response(self, stream_id: int, data: bytes) -> None:
        """Handle server responses"""
        try:
            message = data.decode('utf-8')
            
            if message.startswith('FILE_START_ACK|'):
                logger.info(f"Server acknowledged file start for stream {stream_id}")
            elif message.startswith('CHUNK_ACK|'):
                chunk_id = int(message.split('|')[1])
                if stream_id not in self.chunk_acknowledgments:
                    self.chunk_acknowledgments[stream_id] = set()
                self.chunk_acknowledgments[stream_id].add(chunk_id)
            elif message.startswith('FILE_COMPLETE|'):
                parts = message.split('|')
                filename = parts[1]
                size = int(parts[2])
                logger.info(f"File transfer completed: {filename} ({size} bytes) on stream {stream_id}")
                self.transfer_complete[stream_id] = True
            elif message.startswith('ERROR|'):
                error_msg = message.split('|', 1)[1]
                logger.error(f"Server error for stream {stream_id}: {error_msg}")
                self.transfer_errors[stream_id] = error_msg
                
        except Exception as e:
            logger.error(f"Error handling server response: {e}")
    
    async def send_file_async(
        self, 
        file_path: Path, 
        chunk_size: int = 64 * 1024,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> int:
        """Start sending a file asynchronously, returns stream_id"""
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Calculate file info
        file_size = file_path.stat().st_size
        total_chunks = math.ceil(file_size / chunk_size)
        
        # Calculate file hash
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        
        # Create stream for this file transfer
        stream_id = self._quic.get_next_available_stream_id()
        
        # Initialize stream state
        self.chunk_acknowledgments[stream_id] = set()
        self.transfer_complete[stream_id] = False
        self.active_transfers[stream_id] = {
            'file_path': file_path,
            'total_chunks': total_chunks,
            'file_size': file_size
        }
        
        logger.info(f"Starting async transfer: {file_path.name} on stream {stream_id}")
        
        # Send file metadata
        metadata = f"FILE_START|{file_path.name}|{file_size}|{total_chunks}|{file_hash}"
        self._quic.send_stream_data(stream_id, metadata.encode('utf-8'))
        self.transmit()
        
        # Start sending chunks in background
        asyncio.create_task(self._send_chunks(stream_id, file_path, chunk_size, progress_callback))
        
        return stream_id
    
    async def _send_chunks(
        self, 
        stream_id: int, 
        file_path: Path, 
        chunk_size: int,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ):
        """Send file chunks for a specific stream"""
        try:
            total_chunks = self.active_transfers[stream_id]['total_chunks']
            
            # Wait a bit for server acknowledgment
            await asyncio.sleep(0.1)
            
            # Send file chunks
            with open(file_path, 'rb') as f:
                for chunk_id in range(total_chunks):
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break
                    
                    # Send chunk with ID
                    chunk_msg = b'CHUNK|' + str(chunk_id).encode('utf-8') + b'|' + chunk_data
                    self._quic.send_stream_data(stream_id, chunk_msg)
                    self.transmit()
                    
                    # Update progress (now includes stream_id)
                    if progress_callback:
                        progress_callback(stream_id, chunk_id + 1, total_chunks)
                    
                    # Small delay
                    await asyncio.sleep(0.01)
            
            # Close the stream
            self._quic.send_stream_data(stream_id, b'', end_stream=True)
            self.transmit()
            
            logger.info(f"All chunks sent for {file_path.name} on stream {stream_id}")
            
        except Exception as e:
            logger.error(f"Error sending chunks for stream {stream_id}: {e}")
            self.transfer_errors[stream_id] = str(e)
    
    async def wait_for_transfer(self, stream_id: int, timeout: int = 30) -> bool:
        """Wait for a specific transfer to complete"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            if current_time - start_time > timeout:
                logger.error(f"Timeout waiting for stream {stream_id}")
                return False
            
            if stream_id in self.transfer_errors:
                logger.error(f"Transfer failed on stream {stream_id}: {self.transfer_errors[stream_id]}")
                return False
            
            if self.transfer_complete.get(stream_id, False):
                logger.info(f"Transfer completed successfully on stream {stream_id}")
                return True
            
            await asyncio.sleep(0.1)
    
    async def wait_for_all_transfers(self, stream_ids: List[int], timeout: int = 60) -> bool:
        """Wait for all transfers to complete"""
        tasks = [self.wait_for_transfer(sid, timeout) for sid in stream_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        logger.info(f"Completed {success_count}/{len(stream_ids)} transfers")
        
        return success_count == len(stream_ids)

async def send_multiple_files(
    file_paths: List[str], 
    server_host: str = "localhost", 
    server_port: int = 4433
):
    """Send multiple files concurrently using multiple streams"""
    
    configuration = QuicConfiguration(
        alpn_protocols=["file-transfer"],
        is_client=True,
        verify_mode=False,
    )
    
    def progress_callback(stream_id: int, chunks_sent: int, total_chunks: int):
        progress = (chunks_sent / total_chunks) * 100
        print(f"Stream {stream_id}: {progress:.1f}% ({chunks_sent}/{total_chunks} chunks)")
    
    try:
        async with connect(
            host=server_host,
            port=server_port,
            configuration=configuration,
            create_protocol=MultiStreamQuicFileClient,
        ) as protocol:
            logger.info(f"Connected to server {server_host}:{server_port}")
            
            # Start all transfers concurrently
            stream_ids = []
            for file_path in file_paths:
                path = Path(file_path)
                if path.exists():
                    stream_id = await protocol.send_file_async(path, progress_callback=progress_callback)
                    stream_ids.append(stream_id)
                    print(f"Started transfer: {path.name} on stream {stream_id}")
                else:
                    print(f"File not found: {file_path}")
            
            if not stream_ids:
                print("No files to transfer")
                return False
            
            # Wait for all transfers to complete
            print(f"\nWaiting for {len(stream_ids)} concurrent transfers...")
            success = await protocol.wait_for_all_transfers(stream_ids)
            
            if success:
                print(f"\n✓ All {len(stream_ids)} files sent successfully!")
            else:
                print(f"\n✗ Some transfers failed")
            
            # Keep connection alive briefly
            await asyncio.sleep(1)
            return success
            
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return False

async def main():
    """Example usage"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python multi_client.py <file1> [file2] [file3] ...")
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    success = await send_multiple_files(file_paths)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())