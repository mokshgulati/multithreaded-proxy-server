# High-Performance Multithreaded Proxy Web Server

A production-ready, high-performance HTTP/HTTPS proxy server implemented in Python with threading, Redis caching, and various performance optimizations.

## Features

### Core Functionality
- Handles HTTP/HTTPS requests
- Supports concurrent client connections using Python's threading module
- Forwards client requests to destination servers and relays responses back
- Handles common HTTP methods (GET, POST, PUT, DELETE)

### Threading Implementation
- Thread pool to manage concurrent connections efficiently
- Thread-safe request queue
- Proper thread lifecycle management
- Thread synchronization mechanisms
- Configurable thread pool size based on system resources

### Redis Caching
- Caching for frequently accessed resources
- Configurable cache expiration policies
- Cache invalidation mechanisms
- Efficient storage and retrieval of cached responses
- Cache hit/miss ratio monitoring

### Performance Optimizations
- Connection pooling for backend servers
- Request timeout handling
- Comprehensive error handling and logging
- Optimized memory usage for large responses
- Load balancing for multiple backend servers

### Additional Features
- Basic request filtering capabilities
- Monitoring endpoints for server statistics
- Configurable rate limiting
- Support for compression
- Detailed logging for debugging

## Requirements

- Python 3.7+
- Redis server
- Required Python packages (see `requirements.txt`)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd multithreaded_proxy_server
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Make sure Redis server is running:
```bash
# On most systems
sudo service redis-server start

# Or
redis-server
```

## Configuration

The proxy server can be configured using environment variables or command-line arguments. The default configuration is stored in the `.env` file.

### Environment Variables

- `HOST`: Host to bind to (default: 0.0.0.0)
- `PORT`: Port to bind to (default: 8080)
- `THREAD_POOL_SIZE`: Number of worker threads (default: 50)
- `REQUEST_QUEUE_SIZE`: Maximum size of the request queue (default: 100)
- `CONNECTION_TIMEOUT`: Connection timeout in seconds (default: 30)
- `REDIS_HOST`: Redis server host (default: localhost)
- `REDIS_PORT`: Redis server port (default: 6379)
- `REDIS_DB`: Redis database number (default: 0)
- `CACHE_EXPIRATION`: Cache expiration time in seconds (default: 300)
- `BACKEND_SERVERS`: Comma-separated list of backend servers (default: http://localhost:8000)
- `ENABLE_COMPRESSION`: Enable response compression (default: True)
- `RATE_LIMIT_REQUESTS`: Maximum requests per window for rate limiting (default: 100)
- `RATE_LIMIT_WINDOW`: Rate limiting window in seconds (default: 60)
- `REQUEST_FILTERS`: Comma-separated list of request filters (default: ads,trackers,malware)

## Usage

### Starting the Proxy Server

```bash
python proxy_server.py
```

With custom configuration:

```bash
python proxy_server.py --host localhost --port 8080 --threads 100 --redis-host localhost --redis-port 6379 --cache-expiry 600 --backend "http://backend1.example.com,http://backend2.example.com"
```

### Using the Web Dashboard

The project includes a web-based dashboard for managing the proxy server and running load tests with a user-friendly interface.

#### Starting the Dashboard

```bash
# Install the required dependencies first
pip install -r requirements.txt

# Start the dashboard server
python dashboard.py
```

The dashboard will be available at http://localhost:5000 in your web browser.

#### Dashboard Features

1. **Home Page**
   - View proxy server status (running/stopped)
   - Start and stop the proxy server
   - Monitor server logs in real-time
   - View current server configuration

2. **Configuration Page**
   - Edit all proxy server settings
   - Save configuration changes to the .env file
   - Configure thread pool size, Redis settings, backend servers, etc.

3. **Load Testing Page**
   - Run load tests against the proxy server
   - Configure test parameters (requests, concurrency, HTTP method, etc.)
   - View real-time test results and statistics
   - Visualize performance metrics with charts
   - Review test history

#### Example Workflow

1. Start the dashboard: `python dashboard.py`
2. Open http://localhost:5000 in your browser
3. Go to the Configuration page to set up your proxy server
4. Return to the Home page and click "Start Server"
5. Go to the Load Testing page to run performance tests
6. View the results and adjust your configuration as needed

### Starting the Test Backend Server

For testing purposes, a simple backend server is included:

```bash
python test_backend_server.py --host localhost --port 8000
```

### Running Load Tests

The included load testing script can be used to evaluate the performance of the proxy server:

```bash
# Run a count-based test with 1000 requests and 10 concurrent connections
python load_test.py --url http://localhost:8080 --requests 1000 --concurrency 10

# Run a time-based test for 60 seconds with 20 concurrent connections
python load_test.py --url http://localhost:8080 --concurrency 20 --time-based --duration 60

# Test with different HTTP methods
python load_test.py --url http://localhost:8080 --method POST --requests 500
```

## Monitoring

The proxy server exposes a monitoring endpoint at `/proxy-stats` that returns JSON with various statistics:

- Request counts (total, success, error)
- Active connections
- Bytes transferred
- Cache hit/miss ratio
- Request methods distribution
- Rate limited requests
- Uptime

Example:
```bash
curl http://localhost:8080/proxy-stats
```

## Architecture

The proxy server is designed with the following components:

1. **Main Server**: Accepts client connections and manages the request queue
2. **Thread Pool**: Processes client requests concurrently
3. **Connection Pool**: Manages connections to backend servers
4. **Cache Manager**: Handles caching of responses in Redis
5. **Rate Limiter**: Implements request rate limiting
6. **Request Filter**: Filters requests based on configured rules
7. **Statistics**: Tracks server performance metrics

## Performance Considerations

- The thread pool size should be adjusted based on the available system resources
- Redis caching significantly improves performance for frequently accessed resources
- Connection pooling reduces the overhead of establishing new connections to backend servers
- Compression can reduce bandwidth usage but increases CPU usage
- Rate limiting protects the server from being overwhelmed by too many requests

## Security Considerations

- The proxy server implements basic request filtering to block potentially malicious requests
- Rate limiting helps prevent denial-of-service attacks
- The server does not implement authentication or encryption - use with caution in production environments
- Consider running behind a reverse proxy like Nginx for additional security features

## License

[MIT License](LICENSE)
