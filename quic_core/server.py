#!/usr/bin/env python3
"""
QUIC File Transfer Server
Handles file transfers using QUIC protocol with chunking and parallel streams
"""

import asyncio
import logging
import os
import hashlib
from typing import Dict, Optional
from dataclasses import dataclass
from pathlib import Path

from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("./logs/quic_server.log"),
        logging.StreamHandler()  # still shows logs in terminal
    ])
logger = logging.getLogger(__name__)

@dataclass
class FileTransfer:
    """Track ongoing file transfer state"""
    filename: str
    total_size: int
    chunks_received: Dict[int, bytes]
    total_chunks: int
    hash_expected: Optional[str] = None

class QuicFileServerProtocol(QuicConnectionProtocol):
    """QUIC protocol handler for file transfers"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_transfers: Dict[int, Dict] = {}  # stream_id -> transfer info
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)
    
    def quic_event_received(self, event: QuicEvent) -> None:
        """Handle QUIC events"""
        if isinstance(event, StreamDataReceived):
            self.handle_stream_data(event.stream_id, event.data, event.end_stream)
    
    def handle_stream_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
        """Handle incoming stream data for file transfers"""
        try:
            # Process the data if there is any
            if data:
                if data.startswith(b"FILE_START|"):
                    message = data.decode("utf-8")
                    parts = message.split("|")
                    filename, size, total_chunks, file_hash = parts[1], int(parts[2]), int(parts[3]), parts[4]
                    logger.info(f"Starting file transfer: {filename} ({size} bytes, {total_chunks} chunks)")

                    # Store transfer metadata
                    self.active_transfers[stream_id] = {
                        "filename": filename,
                        "size": size,
                        "total_chunks": total_chunks,
                        "received_chunks": {},
                        "file_hash": file_hash
                    }

                    # Send FILE_START_ACK
                    ack = f"FILE_START_ACK|{filename}".encode("utf-8")
                    self._quic.send_stream_data(stream_id, ack)
                    self.transmit()  # Actually send the data

                elif data.startswith(b"CHUNK|"):
                    parts = data.split(b"|", 2)
                    if len(parts) < 3:
                        logger.warning(f"Malformed chunk received on stream {stream_id}")
                        return
                    chunk_id = int(parts[1])
                    chunk_data = parts[2]

                    if stream_id in self.active_transfers:
                        self.active_transfers[stream_id]["received_chunks"][chunk_id] = chunk_data
                        chunks_received = len(self.active_transfers[stream_id]["received_chunks"])
                        total_chunks = self.active_transfers[stream_id]["total_chunks"]
                        logger.info(f"Received chunk {chunk_id} on stream {stream_id} ({chunks_received}/{total_chunks})")
                        
                        # Send CHUNK_ACK
                        ack = f"CHUNK_ACK|{chunk_id}".encode("utf-8")
                        self._quic.send_stream_data(stream_id, ack)
                        self.transmit()  # Actually send the data
                    else:
                        logger.warning(f"Chunk received for unknown stream {stream_id}")
                        err = f"ERROR|No active transfer found for stream {stream_id}".encode("utf-8")
                        self._quic.send_stream_data(stream_id, err)
                        self.transmit()  # Actually send the data

                else:
                    logger.warning(f"Unexpected data on stream {stream_id}: {data[:50]}")

            # Handle stream end
            if end_stream:
                logger.info(f"Stream {stream_id} ended")
                self.handle_stream_end(stream_id)

        except Exception as e:
            logger.error(f"Failed to handle stream data: {e}")
            self.send_error_response(stream_id, str(e))
    
    def handle_stream_end(self, stream_id: int) -> None:
        """Handle end of stream - assemble and save file"""
        if stream_id in self.active_transfers:
            transfer = self.active_transfers[stream_id]
            total_received = len(transfer["received_chunks"])
            expected = transfer["total_chunks"]
            filename = transfer["filename"]
            size = transfer["size"]

            logger.info(f"Processing stream end for {filename}: {total_received}/{expected} chunks received")

            if total_received == expected:
                # Assemble the file
                try:
                    file_path = self.upload_dir / filename
                    with open(file_path, 'wb') as f:
                        for chunk_id in sorted(transfer["received_chunks"].keys()):
                            f.write(transfer["received_chunks"][chunk_id])
                    
                    # Verify file size
                    actual_size = file_path.stat().st_size
                    if actual_size == size:
                        logger.info(f"File {filename} saved successfully ({actual_size} bytes)")
                        complete = f"FILE_COMPLETE|{filename}|{actual_size}".encode("utf-8")
                        self._quic.send_stream_data(stream_id, complete)
                        self.transmit()  # Actually send the data
                    else:
                        logger.error(f"File size mismatch: expected {size}, got {actual_size}")
                        error = f"ERROR|File size mismatch".encode("utf-8")
                        self._quic.send_stream_data(stream_id, error)
                        self.transmit()  # Actually send the data
                        
                except Exception as e:
                    logger.error(f"Error saving file {filename}: {e}")
                    error = f"ERROR|Failed to save file: {str(e)}".encode("utf-8")
                    self._quic.send_stream_data(stream_id, error)
                    self.transmit()  # Actually send the data
            else:
                logger.warning(f"Incomplete transfer for {filename}: {total_received}/{expected} chunks received")
                error = f"ERROR|Incomplete transfer. Received {total_received}/{expected} chunks.".encode("utf-8")
                self._quic.send_stream_data(stream_id, error)
                self.transmit()  # Actually send the data
            
            # Clean up
            del self.active_transfers[stream_id]
        else:
            logger.warning(f"Stream end received for unknown stream {stream_id}")
    
    def send_error_response(self, stream_id: int, error_msg: str) -> None:
        """Send error response to client"""
        response = f"ERROR|{error_msg}".encode('utf-8')
        self._quic.send_stream_data(stream_id, response)
        self.transmit()  # Actually send the data

async def main():
    """Start the QUIC file transfer server"""
    # Generate self-signed certificate for testing
    configuration = QuicConfiguration(
        alpn_protocols=["file-transfer"],
        is_client=False,
        max_datagram_frame_size=65536,
    )
    
    # For production, use proper certificates
    configuration.load_cert_chain("./certs/cert.pem", "./certs/key.pem")
    
    # Start server
    logger.info("Starting QUIC file transfer server on localhost:4433")
    await serve(
        host="localhost",
        port=4433,
        configuration=configuration,
        create_protocol=QuicFileServerProtocol,
    )

    # Keep the server running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")