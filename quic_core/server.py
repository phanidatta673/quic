#!/usr/bin/env python3
"""
QUIC File Transfer Server
Handles file transfers using QUIC protocol with chunking and parallel streams
"""

import asyncio
import logging
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
        logging.StreamHandler()
    ])
logger = logging.getLogger(__name__)

@dataclass
class FileTransfer:
    filename: str
    total_size: int
    total_chunks: int
    received_chunks: Dict[int, bytes]
    file_hash: Optional[str] = None
    buffer: bytes = b""

class QuicFileServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_transfers: Dict[int, FileTransfer] = {}
        self.stream_buffers: Dict[int, bytes] = {}  # stream_id -> buffered data
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            self.handle_stream_data(event.stream_id, event.data, event.end_stream)

    def handle_stream_data(self, stream_id: int, data: bytes, end_stream: bool) -> None:
        try:
            buffer = self.stream_buffers.get(stream_id, b"") + data
            self.stream_buffers[stream_id] = buffer

            while b"|" in buffer:
                if buffer.startswith(b"FILE_START|"):
                    try:
                        terminator = buffer.find(b"\n")
                        if terminator == -1:
                            return  # Wait for complete message
                        message = buffer[:terminator].decode("utf-8")
                        buffer = buffer[terminator + 1:]
                        self.stream_buffers[stream_id] = buffer

                        parts = message.split("|")
                        if len(parts) != 5:
                            raise ValueError("Invalid FILE_START format")

                        _, filename, size, total_chunks, file_hash = parts
                        self.active_transfers[stream_id] = FileTransfer(
                            filename=filename,
                            total_size=int(size),
                            total_chunks=int(total_chunks),
                            received_chunks={},
                            file_hash=file_hash,
                            buffer=b""
                        )
                        logger.info(f"Started file transfer: {filename} ({size} bytes, {total_chunks} chunks)")
                        ack = f"FILE_START_ACK|{filename}".encode("utf-8")
                        self._quic.send_stream_data(stream_id, ack)
                        self.transmit()
                    except Exception as e:
                        logger.error(f"FILE_START error: {e}")
                        self.send_error_response(stream_id, str(e))
                        return
                elif buffer.startswith(b"CHUNK|"):
                    parts = buffer.split(b"|", 2)
                    if len(parts) < 3:
                        return  # Wait for more data
                    chunk_id_str = parts[1].decode("utf-8")
                    try:
                        chunk_id = int(chunk_id_str)
                    except ValueError:
                        self.send_error_response(stream_id, "Invalid CHUNK ID")
                        return
                    chunk_data = parts[2]

                    if stream_id in self.active_transfers:
                        self.active_transfers[stream_id].received_chunks[chunk_id] = chunk_data
                        del self.stream_buffers[stream_id]

                        logger.info(f"Received chunk {chunk_id} on stream {stream_id} ({len(self.active_transfers[stream_id].received_chunks)}/{self.active_transfers[stream_id].total_chunks})")

                        ack = f"CHUNK_ACK|{chunk_id}".encode("utf-8")
                        self._quic.send_stream_data(stream_id, ack)
                        self.transmit()
                    else:
                        logger.warning(f"Chunk received for unknown stream {stream_id}")
                        self.send_error_response(stream_id, f"No active transfer found for stream {stream_id}")
                        return
                else:
                    break  # Wait for more data

            if end_stream:
                logger.info(f"Stream {stream_id} ended")
                self.handle_stream_end(stream_id)

        except Exception as e:
            logger.error(f"Failed to handle stream data: {e}")
            self.send_error_response(stream_id, str(e))

    def handle_stream_end(self, stream_id: int) -> None:
        if stream_id in self.active_transfers:
            transfer = self.active_transfers[stream_id]
            total_received = len(transfer.received_chunks)
            if total_received == transfer.total_chunks:
                try:
                    file_path = self.upload_dir / transfer.filename
                    with open(file_path, 'wb') as f:
                        for chunk_id in sorted(transfer.received_chunks):
                            f.write(transfer.received_chunks[chunk_id])

                    # Verify file size
                    actual_size = file_path.stat().st_size
                    if actual_size != transfer.total_size:
                        raise ValueError("File size mismatch")

                    # Verify hash
                    if transfer.file_hash:
                        with open(file_path, 'rb') as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                        if file_hash != transfer.file_hash:
                            raise ValueError("Hash verification failed")

                    logger.info(f"File {transfer.filename} saved successfully ({actual_size} bytes)")
                    complete = f"FILE_COMPLETE|{transfer.filename}|{actual_size}".encode("utf-8")
                    self._quic.send_stream_data(stream_id, complete)
                    self.transmit()
                except Exception as e:
                    logger.error(f"Error saving file: {e}")
                    self.send_error_response(stream_id, str(e))
            else:
                self.send_error_response(stream_id, f"Incomplete transfer. Received {total_received}/{transfer.total_chunks} chunks.")
            del self.active_transfers[stream_id]
            self.stream_buffers.pop(stream_id, None)

    def send_error_response(self, stream_id: int, error_msg: str) -> None:
        response = f"ERROR|{error_msg}".encode("utf-8")
        self._quic.send_stream_data(stream_id, response)
        self.transmit()

async def main():
    configuration = QuicConfiguration(
        alpn_protocols=["file-transfer"],
        is_client=False,
        max_datagram_frame_size=65536,
    )
    configuration.load_cert_chain("./certs/cert.pem", "./certs/key.pem")
    logger.info("Starting QUIC file transfer server on localhost:4433")
    await serve(
        host="localhost",
        port=4433,
        configuration=configuration,
        create_protocol=QuicFileServerProtocol,
    )
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")