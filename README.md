# QUIC File Transfer System

A high-performance file transfer system built with Python, utilizing the QUIC protocol for fast, reliable, and secure file transfers. The system features a FastAPI backend that coordinates with a QUIC server to handle large file uploads with chunking and parallel streams.

## Architecture

The system consists of two main components:

- **FastAPI Backend** (`backend/`): REST API for file upload coordination and management
- **QUIC Core** (`quic_core/`): QUIC protocol implementation for actual file transfer

```
┌─────────────────┐    HTTP     ┌─────────────────┐    QUIC     ┌─────────────────┐
│                 │   Upload    │                 │  Protocol   │                 │
│     Client      │ ──────────> │ FastAPI Backend │ ──────────> │   QUIC Server   │
│                 │             │                 │             │                 │
└─────────────────┘             └─────────────────┘             └─────────────────┘
```

## Features

- **QUIC Protocol**: Leverages QUIC's multiplexing and low-latency benefits
- **Chunked Transfers**: Large files are split into manageable chunks
- **Parallel Streams**: Multiple files can be transferred concurrently
- **Hash Verification**: SHA-256 checksums ensure data integrity
- **Resumable Transfers**: Failed transfers can be resumed from the last successful chunk
- **Configurable Chunk Size**: Optimize transfer performance based on network conditions
- **Comprehensive Logging**: Detailed logs for debugging and monitoring

## Prerequisites

- Python 3.8+
- OpenSSL for certificate generation
- Virtual environment (recommended)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd quic-file-transfer
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## SSL Certificate Setup

Generate self-signed certificates for QUIC (development only):

```bash
# Create certificates directory
mkdir -p quic_core/certs

# Generate private key
openssl genrsa -out quic_core/certs/key.pem 2048

# Generate certificate
openssl req -new -x509 -key quic_core/certs/key.pem -out quic_core/certs/cert.pem -days 365 -subj "/CN=localhost"
```

**For production**, use proper CA-signed certificates.

## Project Structure

```
quic-file-transfer/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   └── transfers.py     # File upload endpoints
│   │   └── services/
│   │       ├── __init__.py
│   │       └── simple_quic.py   # QUIC client interface
│   ├── uploads/                 # Uploaded files storage
│   └── requirements.txt
├── quic_core/
│   ├── server.py               # QUIC server implementation
│   ├── client.py               # QUIC client implementation
│   ├── certs/                  # SSL certificates
│   │   ├── cert.pem
│   │   └── key.pem
│   └── logs/                   # Server logs
└── test_files/                 # Test files for upload
```

## Usage

### 1. Start the QUIC Server

```bash
cd quic_core
python server.py
```

Expected output:
```
2025-06-03 10:00:00,000 - INFO - Starting QUIC file transfer server on localhost:4433
```

### 2. Start the FastAPI Backend

In a new terminal:

```bash
cd backend
python -m app.main
```

Expected output:
```
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
2025-06-03 10:00:00 - app.main - INFO - Starting FastAPI backend for QUIC File Transfer
```

### 3. Upload Files

#### Using cURL

```bash
# Upload a single file with default chunk size (64KB)
curl -X POST "http://localhost:8000/api/transfers/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@path/to/your/file.txt"

# Upload with custom chunk size (1KB chunks)
curl -X POST "http://localhost:8000/api/transfers/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@path/to/your/file.txt" \
  -F "chunk_size=1024"
```

#### Using Python requests

```python
import requests

# Simple upload
with open('test_file.txt', 'rb') as f:
    files = {'file': f}
    response = requests.post('http://localhost:8000/api/transfers/upload', files=files)
    print(response.json())

# Upload with custom chunk size
with open('large_file.zip', 'rb') as f:
    files = {'file': f}
    data = {'chunk_size': 8192}  # 8KB chunks
    response = requests.post('http://localhost:8000/api/transfers/upload', files=files, data=data)
    print(response.json())
```

## API Endpoints

### POST /api/transfers/upload

Upload a file using QUIC protocol.

**Parameters:**
- `file` (form-data): The file to upload
- `chunk_size` (form-data, optional): Chunk size in bytes (default: 65536)

**Response:**
```json
{
  "success": true,
  "transfer_id": "uuid-string",
  "filename": "uploaded_file.txt",
  "file_size": 1024,
  "upload_path": "uploads/uploaded_file.txt",
  "chunk_size": 65536,
  "total_chunks": 1
}
```

## Configuration

### Environment Variables

- `UPLOAD_DIR`: Directory for uploaded files (default: `uploads/`)
- `QUIC_HOST`: QUIC server host (default: `localhost`)
- `QUIC_PORT`: QUIC server port (default: `4433`)
- `MAX_FILE_SIZE`: Maximum file size in bytes (default: `100MB`)

### Chunk Size Optimization

Choose chunk size based on your network conditions:

- **Fast, reliable networks**: 64KB - 1MB chunks
- **Slow or unreliable networks**: 1KB - 8KB chunks
- **Mobile networks**: 4KB - 16KB chunks

## Monitoring and Logs

### Server Logs

QUIC server logs are written to:
- Console output
- `quic_core/logs/quic_server.log`

### Backend Logs

FastAPI backend logs include:
- Request/response logging
- Transfer coordination
- Error handling

### Key Log Messages

```bash
# Successful transfer
INFO - Started file transfer: sample.txt (3541 bytes, 4 chunks)
INFO - Received chunk 0 on stream 0 (1/4) - 1000 bytes
INFO - File sample.txt saved successfully (3541 bytes)

# Error conditions
ERROR - File size mismatch: expected 3541, got 3540
ERROR - Hash verification failed
ERROR - Transfer timeout after 30 seconds
```

## Testing

### Test File Upload

1. Create a test file:
   ```bash
   mkdir -p test_files
   echo "Hello, QUIC World!" > test_files/test.txt
   ```

2. Upload the test file:
   ```bash
   curl -X POST "http://localhost:8000/api/transfers/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@test_files/test.txt" \
     -F "chunk_size=1024"
   ```

3. Verify the upload:
   ```bash
   ls -la backend/uploads/
   cat backend/uploads/test.txt
   ```

### Performance Testing

Test with larger files to evaluate performance:

```bash
# Create a 10MB test file
dd if=/dev/zero of=test_files/large_file.bin bs=1024 count=10240

# Upload with different chunk sizes
curl -X POST "http://localhost:8000/api/transfers/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_files/large_file.bin" \
  -F "chunk_size=65536"
```

## Troubleshooting

### Common Issues

1. **Certificate errors:**
   ```
   ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
   ```
   **Solution:** Ensure certificates are properly generated and accessible.

2. **Connection refused:**
   ```
   ConnectionRefusedError: [Errno 61] Connection refused
   ```
   **Solution:** Verify QUIC server is running on the correct port.

3. **File size mismatch:**
   ```
   ERROR - File size mismatch: expected 3541, got 3540
   ```
   **Solution:** Check network stability and try smaller chunk sizes.

### Debug Mode

Enable detailed logging:

```python
# In server.py or client.py
logging.basicConfig(level=logging.DEBUG)
```

### Network Issues

- **Firewall**: Ensure UDP port 4433 is open
- **NAT**: QUIC uses UDP, which may have NAT traversal issues
- **Proxies**: Some corporate proxies block QUIC traffic

## Performance Considerations

### Optimization Tips

1. **Chunk Size**: Larger chunks = fewer round trips, but less resilience
2. **Concurrent Streams**: QUIC supports multiple parallel transfers
3. **Buffer Sizes**: Adjust QUIC buffer sizes for high-bandwidth networks
4. **CPU Usage**: QUIC encryption/decryption is CPU-intensive

### Benchmarking

Compare performance against traditional HTTP uploads:

```bash
# QUIC transfer
time curl -X POST "http://localhost:8000/api/transfers/upload" \
  -F "file=@large_file.bin"

# Traditional HTTP transfer (for comparison)
time curl -X POST "http://localhost:8000/api/transfers/http-upload" \
  -F "file=@large_file.bin"
```

## Security Notes

- Uses TLS 1.3 encryption by default
- Implements SHA-256 file integrity verification
- Self-signed certificates are for development only
- Consider additional authentication/authorization for production

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Your License Here]

## Support

For issues and questions:
- Check the troubleshooting section
- Review server and client logs
- Open an issue in the repository