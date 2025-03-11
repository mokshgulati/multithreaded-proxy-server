#!/usr/bin/env python3
"""
Multithreaded Proxy Web Server

A high-performance HTTP/HTTPS proxy server with threading, Redis caching,
and various performance optimizations.
"""

import socket
import threading
import logging
import time
import os
import sys
import queue
import json
import gzip
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import requests
from requests.exceptions import RequestException, Timeout
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("proxy_server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ProxyServer")

# Server configuration
DEFAULT_CONFIG = {
    "HOST": "0.0.0.0",
    "PORT": 8080,
    "THREAD_POOL_SIZE": 50,
    "REQUEST_QUEUE_SIZE": 100,
    "CONNECTION_TIMEOUT": 30,
    "REDIS_HOST": "localhost",
    "REDIS_PORT": 6379,
    "REDIS_DB": 0,
    "CACHE_EXPIRATION": 300,  # 5 minutes
    "BACKEND_SERVERS": ["http://localhost:8000"],
    "ENABLE_COMPRESSION": True,
    "RATE_LIMIT_REQUESTS": 100,
    "RATE_LIMIT_WINDOW": 60,  # 1 minute
    "REQUEST_FILTERS": ["ads", "trackers", "malware"]
}

# Load configuration from environment variables or use defaults
CONFIG = {}
for key, default_value in DEFAULT_CONFIG.items():
    env_value = os.environ.get(key)
    if env_value is not None:
        CONFIG[key] = env_value
    else:
        CONFIG[key] = default_value

# Convert numeric values
for key in ["PORT", "THREAD_POOL_SIZE", "REQUEST_QUEUE_SIZE", 
           "CONNECTION_TIMEOUT", "REDIS_PORT", "REDIS_DB", 
           "CACHE_EXPIRATION", "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW"]:
    if key in CONFIG:
        try:
            CONFIG[key] = int(CONFIG[key])
        except (ValueError, TypeError):
            CONFIG[key] = DEFAULT_CONFIG[key]

# Convert boolean values
for key in ["ENABLE_COMPRESSION"]:
    if key in CONFIG:
        if isinstance(CONFIG[key], str):
            CONFIG[key] = CONFIG[key].lower() in ('true', 'yes', '1', 't', 'y')

# Parse backend servers list
if isinstance(CONFIG["BACKEND_SERVERS"], str):
    CONFIG["BACKEND_SERVERS"] = [s.strip() for s in CONFIG["BACKEND_SERVERS"].split(",") if s.strip()]
    if not CONFIG["BACKEND_SERVERS"]:  # If empty after parsing
        CONFIG["BACKEND_SERVERS"] = DEFAULT_CONFIG["BACKEND_SERVERS"]

# Parse request filters
if isinstance(CONFIG["REQUEST_FILTERS"], str):
    CONFIG["REQUEST_FILTERS"] = [s.strip() for s in CONFIG["REQUEST_FILTERS"].split(",") if s.strip()]


class Statistics:
    """Thread-safe statistics tracking for the proxy server."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "bytes_transferred": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "active_connections": 0,
            "rate_limited_requests": 0,
            "request_methods": {
                "GET": 0,
                "POST": 0,
                "PUT": 0,
                "DELETE": 0,
                "OTHER": 0
            },
            "start_time": time.time()
        }
    
    def increment(self, stat, value=1):
        """Increment a statistic by the given value."""
        with self._lock:
            if stat in self._stats:
                self._stats[stat] += value
    
    def decrement(self, stat, value=1):
        """Decrement a statistic by the given value."""
        with self._lock:
            if stat in self._stats:
                self._stats[stat] -= value
    
    def update_method_stat(self, method):
        """Update request method statistics."""
        with self._lock:
            if method in self._stats["request_methods"]:
                self._stats["request_methods"][method] += 1
            else:
                self._stats["request_methods"]["OTHER"] += 1
    
    def get_stats(self):
        """Get a copy of the current statistics."""
        with self._lock:
            stats_copy = self._stats.copy()
            stats_copy["uptime_seconds"] = time.time() - stats_copy["start_time"]
            if stats_copy["cache_hits"] + stats_copy["cache_misses"] > 0:
                stats_copy["cache_hit_ratio"] = (
                    stats_copy["cache_hits"] / 
                    (stats_copy["cache_hits"] + stats_copy["cache_misses"])
                )
            else:
                stats_copy["cache_hit_ratio"] = 0
            return stats_copy


class RateLimiter:
    """Thread-safe rate limiter for client requests."""
    
    def __init__(self, redis_client, requests_limit, time_window):
        self._redis = redis_client
        self._requests_limit = requests_limit
        self._time_window = time_window
    
    def is_rate_limited(self, client_ip):
        """
        Check if a client IP is rate limited.
        Returns True if rate limited, False otherwise.
        """
        current_time = int(time.time())
        key = f"rate_limit:{client_ip}"
        
        # Use Redis pipeline for atomic operations
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, current_time - self._time_window)
        pipe.zadd(key, {str(current_time): current_time})
        pipe.zcard(key)
        pipe.expire(key, self._time_window)
        _, _, request_count, _ = pipe.execute()
        
        return request_count > self._requests_limit


class CacheManager:
    """Manages caching of HTTP responses in Redis."""
    
    def __init__(self, redis_client, expiration_time, statistics):
        self._redis = redis_client
        self._expiration_time = expiration_time
        self._stats = statistics
    
    def _generate_cache_key(self, method, url, headers, body=None):
        """Generate a unique cache key for the request."""
        # Only include relevant headers that could affect the response
        cache_headers = {k.lower(): v for k, v in headers.items() 
                         if k.lower() in ['accept', 'accept-language', 'accept-encoding']}
        
        # Create a dictionary of components to hash
        key_components = {
            'method': method,
            'url': url,
            'headers': cache_headers
        }
        
        # Include body for non-GET requests if present
        if method != 'GET' and body:
            if isinstance(body, bytes):
                key_components['body'] = body.decode('utf-8', errors='ignore')
            else:
                key_components['body'] = body
            
        # Create a JSON string and hash it
        key_str = json.dumps(key_components, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get_cached_response(self, method, url, headers, body=None):
        """
        Try to get a cached response for the request.
        Returns None if not found or expired.
        """
        if method != 'GET':  # Only cache GET requests by default
            return None
            
        cache_key = self._generate_cache_key(method, url, headers, body)
        cached_data = self._redis.get(cache_key)
        
        if cached_data:
            self._stats.increment("cache_hits")
            try:
                cached_response = json.loads(cached_data)
                # Convert content back to bytes if it was stored as base64
                if 'content_base64' in cached_response:
                    import base64
                    cached_response['content'] = base64.b64decode(cached_response['content_base64'])
                    del cached_response['content_base64']
                return cached_response
            except json.JSONDecodeError:
                # If we can't decode the cached data, treat it as a cache miss
                self._stats.increment("cache_misses")
                return None
        else:
            self._stats.increment("cache_misses")
            return None
    
    def cache_response(self, method, url, headers, response_data, body=None):
        """Cache a response with the configured expiration time."""
        if method != 'GET':  # Only cache GET requests by default
            return
            
        cache_key = self._generate_cache_key(method, url, headers, body)
        
        # Don't cache error responses
        if response_data.get('status_code', 500) >= 400:
            return
            
        # Don't cache responses that say not to cache
        response_headers = response_data.get('headers', {})
        cache_control = response_headers.get('Cache-Control', '')
        if 'no-store' in cache_control or 'no-cache' in cache_control:
            return
        
        # Make a copy of the response data to avoid modifying the original
        cache_data = response_data.copy()
        
        # Convert binary content to base64 for JSON serialization
        if 'content' in cache_data and isinstance(cache_data['content'], bytes):
            import base64
            cache_data['content_base64'] = base64.b64encode(cache_data['content']).decode('ascii')
            del cache_data['content']
            
        try:
            # Store the response in Redis
            self._redis.setex(
                cache_key,
                self._expiration_time,
                json.dumps(cache_data)
            )
        except (TypeError, json.JSONDecodeError) as e:
            logger.error(f"Error caching response: {e}")
    
    def invalidate_cache(self, url_pattern=None):
        """
        Invalidate cache entries matching the given URL pattern.
        If no pattern is provided, invalidate all cache entries.
        """
        if url_pattern:
            # This is a simplified approach - in production, you might want
            # to use more sophisticated pattern matching
            for key in self._redis.scan_iter("*"):
                try:
                    cached_data = self._redis.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        if url_pattern in data.get('url', ''):
                            self._redis.delete(key)
                except (json.JSONDecodeError, TypeError):
                    # If we can't parse the cached data, skip it
                    continue
        else:
            # Flush all cache keys (dangerous in production)
            for key in self._redis.scan_iter("*"):
                self._redis.delete(key)


class RequestFilter:
    """Filters requests based on configured rules."""
    
    def __init__(self, filter_rules):
        self._filter_rules = filter_rules if isinstance(filter_rules, list) else []
    
    def should_filter(self, url, headers):
        """
        Check if a request should be filtered based on URL and headers.
        Returns True if the request should be blocked, False otherwise.
        """
        # If no filter rules defined, don't filter anything
        if not self._filter_rules or len(self._filter_rules) == 0:
            return False
            
        url_lower = url.lower()
        
        # Check URL against filter rules
        for rule in self._filter_rules:
            if rule and rule.lower() in url_lower:
                return True
                
        # Check for suspicious headers - disabled for now
        # for header, value in headers.items():
        #     header_lower = header.lower()
        #     value_lower = value.lower()
        #     
        #     # Example: Block requests with suspicious user agents
        #     if header_lower == 'user-agent' and ('bot' in value_lower or 'crawler' in value_lower):
        #         return True
                
        return False


class ConnectionPool:
    """Manages connection pooling to backend servers."""
    
    def __init__(self, backend_servers, max_connections_per_server=10):
        self._backend_servers = backend_servers
        self._session_pools = {}
        self._max_connections = max_connections_per_server
        
        # Create session pools for each backend server
        for server in backend_servers:
            self._session_pools[server] = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=max_connections_per_server,
                pool_maxsize=max_connections_per_server
            )
            self._session_pools[server].mount('http://', adapter)
            self._session_pools[server].mount('https://', adapter)
    
    def get_session(self, backend_server=None):
        """
        Get a session for the specified backend server.
        If no server is specified, one is chosen using load balancing.
        """
        if not backend_server:
            backend_server = self._select_backend_server()
            
        return self._session_pools.get(backend_server)
    
    def _select_backend_server(self):
        """
        Select a backend server using a simple round-robin load balancing strategy.
        In a production environment, this could be enhanced with health checks
        and weighted selection based on server performance.
        """
        return random.choice(self._backend_servers)


class ProxyServer:
    """
    Multithreaded HTTP/HTTPS Proxy Server with Redis caching
    and various performance optimizations.
    """
    
    def __init__(self, config=None):
        """Initialize the proxy server with the given configuration."""
        self.config = config or CONFIG
        self.host = self.config["HOST"]
        self.port = self.config["PORT"]
        self.thread_pool_size = self.config["THREAD_POOL_SIZE"]
        self.request_queue_size = self.config["REQUEST_QUEUE_SIZE"]
        self.connection_timeout = self.config["CONNECTION_TIMEOUT"]
        
        # Initialize components
        self.statistics = Statistics()
        
        # Initialize Redis connection
        self.redis_client = redis.Redis(
            host=self.config["REDIS_HOST"],
            port=self.config["REDIS_PORT"],
            db=self.config["REDIS_DB"],
            decode_responses=True
        )
        
        # Initialize managers and utilities
        self.cache_manager = CacheManager(
            self.redis_client,
            self.config["CACHE_EXPIRATION"],
            self.statistics
        )
        
        self.rate_limiter = RateLimiter(
            self.redis_client,
            self.config["RATE_LIMIT_REQUESTS"],
            self.config["RATE_LIMIT_WINDOW"]
        )
        
        self.request_filter = RequestFilter(self.config["REQUEST_FILTERS"])
        
        self.connection_pool = ConnectionPool(
            self.config["BACKEND_SERVERS"]
        )
        
        # Initialize thread pool and request queue
        self.thread_pool = ThreadPoolExecutor(max_workers=self.thread_pool_size)
        self.request_queue = queue.Queue(maxsize=self.request_queue_size)
        
        # Create a server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Flag to signal server shutdown
        self.running = False
        
        # Worker threads
        self.workers = []
    
    def start(self):
        """Start the proxy server."""
        try:
            # Bind and listen
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            logger.info(f"Proxy server started on {self.host}:{self.port}")
            logger.info(f"Thread pool size: {self.thread_pool_size}")
            
            # Start worker threads
            for _ in range(self.thread_pool_size):
                worker = threading.Thread(target=self._worker_thread)
                worker.daemon = True
                worker.start()
                self.workers.append(worker)
            
            # Start monitoring thread
            monitor = threading.Thread(target=self._monitoring_thread)
            monitor.daemon = True
            monitor.start()
            
            # Accept connections and put them in the queue
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.settimeout(self.connection_timeout)
                    
                    # Check rate limiting
                    client_ip = client_address[0]
                    if self.rate_limiter.is_rate_limited(client_ip):
                        logger.warning(f"Rate limited client: {client_ip}")
                        self.statistics.increment("rate_limited_requests")
                        client_socket.close()
                        continue
                    
                    # Add to request queue
                    self.request_queue.put((client_socket, client_address))
                    self.statistics.increment("active_connections")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error accepting connection: {e}")
        
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the proxy server."""
        self.running = False
        self.server_socket.close()
        
        # Clear the request queue
        while not self.request_queue.empty():
            try:
                client_socket, _ = self.request_queue.get_nowait()
                client_socket.close()
            except queue.Empty:
                break
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=False)
        
        logger.info("Proxy server stopped")
    
    def _worker_thread(self):
        """Worker thread to process client requests from the queue."""
        while self.running:
            try:
                # Get a client connection from the queue
                client_socket, client_address = self.request_queue.get(timeout=1)
                
                # Process the request in the thread pool
                self.thread_pool.submit(
                    self._handle_client_request, 
                    client_socket, 
                    client_address
                )
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker thread error: {e}")
    
    def _monitoring_thread(self):
        """Thread to periodically log server statistics."""
        while self.running:
            try:
                stats = self.statistics.get_stats()
                logger.info(f"Server stats: {json.dumps(stats)}")
                time.sleep(60)  # Log stats every minute
            except Exception as e:
                logger.error(f"Monitoring thread error: {e}")
    
    def _handle_client_request(self, client_socket, client_address):
        """Handle a client request."""
        client_ip = client_address[0]
        request_data = b""
        
        try:
            # Receive the request data
            while self.running:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                
                # Check if we've received the complete HTTP request
                if b"\r\n\r\n" in request_data:
                    break
            
            if not request_data:
                return
                
            # Parse the HTTP request
            request_lines = request_data.split(b"\r\n")
            request_line = request_lines[0].decode('utf-8', errors='ignore')
            
            # Extract method, URL, and HTTP version
            try:
                method, path, version = request_line.split()
            except ValueError:
                logger.error(f"Invalid request line: {request_line}")
                self._send_error_response(client_socket, 400, "Bad Request")
                return
                
            # Parse headers
            headers = {}
            for line in request_lines[1:]:
                line = line.strip()
                if not line:
                    break
                    
                try:
                    header_name, header_value = line.decode(
                        'utf-8', errors='ignore'
                    ).split(':', 1)
                    headers[header_name.strip()] = header_value.strip()
                except ValueError:
                    continue
            
            # Extract the body if present
            body = None
            header_end = request_data.find(b"\r\n\r\n")
            if header_end != -1 and header_end + 4 < len(request_data):
                body = request_data[header_end + 4:]
            
            # Update statistics
            self.statistics.increment("requests_total")
            self.statistics.update_method_stat(method)
            
            # Check if the request should be filtered
            if self.request_filter.should_filter(path, headers):
                logger.info(f"Filtered request: {method} {path}")
                self._send_error_response(client_socket, 403, "Forbidden")
                return
            
            # Handle special monitoring endpoint
            if path == "/proxy-stats":
                self._handle_stats_request(client_socket)
                return
                
            # Check cache for GET requests
            cached_response = None
            if method == "GET":
                cached_response = self.cache_manager.get_cached_response(
                    method, path, headers, body
                )
            
            if cached_response:
                # Send cached response
                self._send_response_to_client(client_socket, cached_response)
            else:
                # Forward the request to the backend server
                self._forward_request(
                    client_socket, method, path, headers, body
                )
                
        except socket.timeout:
            logger.warning(f"Connection timeout from {client_ip}")
            self._send_error_response(client_socket, 408, "Request Timeout")
        except Exception as e:
            logger.error(f"Error handling request from {client_ip}: {e}")
            self._send_error_response(client_socket, 500, "Internal Server Error")
        finally:
            # Clean up
            try:
                client_socket.close()
            except:
                pass
            self.statistics.decrement("active_connections")
    
    def _forward_request(self, client_socket, method, path, headers, body):
        """Forward the request to a backend server and relay the response."""
        try:
            # Select a backend server
            backend_server = self.connection_pool._select_backend_server()
            
            # Get a session from the connection pool
            session = self.connection_pool.get_session(backend_server)
            
            # Construct the full URL
            if path.startswith('http'):
                url = path  # The path is already a full URL
            else:
                url = f"{backend_server}{path}"
            
            logger.info(f"Forwarding request: {method} {url}")
            
            # Prepare the request
            request_kwargs = {
                'method': method,
                'url': url,
                'headers': headers,
                'timeout': self.connection_timeout,
                'allow_redirects': False,  # Let the client handle redirects
                'verify': False  # Disable SSL verification for testing
            }
            
            if body:
                request_kwargs['data'] = body
            
            # Send the request to the backend server
            response = session.request(**request_kwargs)
            
            # Prepare the response data
            response_data = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'content': response.content,
                'url': url
            }
            
            # Cache the response if appropriate (only cache successful responses)
            if method == "GET" and 200 <= response.status_code < 400:
                self.cache_manager.cache_response(
                    method, path, headers, response_data, body
                )
            
            # Send the response back to the client
            self._send_response_to_client(client_socket, response_data)
            
            # Update statistics - count as success even if backend returns error code
            # since we successfully proxied the request
            self.statistics.increment("requests_success")
            self.statistics.increment("bytes_transferred", len(response.content))
            
        except Timeout:
            logger.warning(f"Backend request timeout: {url}")
            self._send_error_response(client_socket, 504, "Gateway Timeout")
            self.statistics.increment("requests_error")
        except RequestException as e:
            logger.error(f"Backend request error: {url} - {e}")
            self._send_error_response(client_socket, 502, "Bad Gateway")
            self.statistics.increment("requests_error")
        except Exception as e:
            logger.error(f"Error forwarding request: {e}")
            self._send_error_response(client_socket, 500, "Internal Server Error")
            self.statistics.increment("requests_error")
    
    def _send_response_to_client(self, client_socket, response_data):
        """Send an HTTP response to the client."""
        try:
            status_code = response_data.get('status_code', 200)
            headers = response_data.get('headers', {})
            content = response_data.get('content', b'')
            
            # Prepare the response
            status_line = f"HTTP/1.1 {status_code} {requests.status_codes._codes[status_code][0]}\r\n"
            
            # Apply compression if enabled and content is compressible
            if (self.config["ENABLE_COMPRESSION"] and 
                len(content) > 1024 and  # Only compress content larger than 1KB
                'gzip' in headers.get('Accept-Encoding', '') and
                'text' in headers.get('Content-Type', '')):
                
                content = gzip.compress(content)
                headers['Content-Encoding'] = 'gzip'
            
            # Update content length
            headers['Content-Length'] = str(len(content))
            
            # Convert headers to string
            header_lines = [f"{k}: {v}" for k, v in headers.items()]
            header_str = "\r\n".join(header_lines)
            
            # Construct the full response
            response = f"{status_line}{header_str}\r\n\r\n".encode('utf-8')
            response += content
            
            # Send the response
            client_socket.sendall(response)
            
        except Exception as e:
            logger.error(f"Error sending response to client: {e}")
    
    def _send_error_response(self, client_socket, status_code, reason):
        """Send an error response to the client."""
        try:
            response = (
                f"HTTP/1.1 {status_code} {reason}\r\n"
                f"Content-Type: text/html\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"<html><body><h1>{status_code} {reason}</h1></body></html>"
            ).encode('utf-8')
            
            client_socket.sendall(response)
        except:
            pass  # If we can't send the error, just ignore it
    
    def _handle_stats_request(self, client_socket):
        """Handle a request to the statistics endpoint."""
        stats = self.statistics.get_stats()
        stats_json = json.dumps(stats, indent=2)
        
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(stats_json)}\r\n"
            f"\r\n"
            f"{stats_json}"
        ).encode('utf-8')
        
        client_socket.sendall(response)


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description="Multithreaded Proxy Server")
    parser.add_argument("--host", help="Host to bind to", default=CONFIG["HOST"])
    parser.add_argument("--port", type=int, help="Port to bind to", default=CONFIG["PORT"])
    parser.add_argument("--threads", type=int, help="Thread pool size", default=CONFIG["THREAD_POOL_SIZE"])
    parser.add_argument("--redis-host", help="Redis host", default=CONFIG["REDIS_HOST"])
    parser.add_argument("--redis-port", type=int, help="Redis port", default=CONFIG["REDIS_PORT"])
    parser.add_argument("--cache-expiry", type=int, help="Cache expiration in seconds", default=CONFIG["CACHE_EXPIRATION"])
    parser.add_argument("--backend", help="Backend servers (comma-separated)", default=",".join(CONFIG["BACKEND_SERVERS"]))
    
    args = parser.parse_args()
    
    # Update configuration with command line arguments
    CONFIG["HOST"] = args.host
    CONFIG["PORT"] = args.port
    CONFIG["THREAD_POOL_SIZE"] = args.threads
    CONFIG["REDIS_HOST"] = args.redis_host
    CONFIG["REDIS_PORT"] = args.redis_port
    CONFIG["CACHE_EXPIRATION"] = args.cache_expiry
    CONFIG["BACKEND_SERVERS"] = args.backend.split(",")
    
    # Create and start the proxy server
    proxy_server = ProxyServer(CONFIG)
    
    try:
        proxy_server.start()
    except KeyboardInterrupt:
        print("\nShutting down the proxy server...")
    finally:
        proxy_server.stop()
