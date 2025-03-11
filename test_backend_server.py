#!/usr/bin/env python3
"""
Test Backend Server

A simple HTTP server for testing the proxy server.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import argparse
import logging
import sys
from urllib.parse import parse_qs, urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backend_server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("BackendServer")

class TestHandler(BaseHTTPRequestHandler):
    """Handler for test backend server requests."""
    
    def _set_response(self, status_code=200, content_type='text/html'):
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Server', 'TestBackendServer')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        logger.info(f"GET request,\nPath: {self.path}\nHeaders:\n{self.headers}")
        
        # Parse URL and query parameters
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        
        # Different responses based on path
        if path == '/':
            self._set_response()
            response = f"""
            <html>
            <head><title>Test Backend Server</title></head>
            <body>
                <h1>Test Backend Server</h1>
                <p>This is a simple test server for the proxy.</p>
                <p>Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Try these endpoints:</p>
                <ul>
                    <li><a href="/delay?seconds=2">Delayed response</a></li>
                    <li><a href="/json">JSON response</a></li>
                    <li><a href="/large">Large response</a></li>
                    <li><a href="/error">Error response</a></li>
                </ul>
            </body>
            </html>
            """
            self.wfile.write(response.encode('utf-8'))
            
        elif path == '/delay':
            # Simulate a slow response
            delay = int(query.get('seconds', [1])[0])
            if delay > 10:  # Cap the delay
                delay = 10
                
            logger.info(f"Delaying response for {delay} seconds")
            time.sleep(delay)
            
            self._set_response()
            response = f"<html><body><h1>Delayed Response</h1><p>Delayed for {delay} seconds</p></body></html>"
            self.wfile.write(response.encode('utf-8'))
            
        elif path == '/json':
            # Return a JSON response
            self._set_response(content_type='application/json')
            data = {
                'message': 'This is a JSON response',
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'success'
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
            
        elif path == '/large':
            # Return a large response
            self._set_response()
            response = "<html><body><h1>Large Response</h1><p>"
            # Generate about 1MB of data
            for i in range(10000):
                response += f"Line {i}: This is some test data to make the response large.\n"
            response += "</p></body></html>"
            self.wfile.write(response.encode('utf-8'))
            
        elif path == '/error':
            # Return an error response
            self._set_response(status_code=500)
            response = "<html><body><h1>500 Internal Server Error</h1><p>This is a simulated error.</p></body></html>"
            self.wfile.write(response.encode('utf-8'))
            
        else:
            # Return a 404 for unknown paths
            self._set_response(status_code=404)
            response = f"<html><body><h1>404 Not Found</h1><p>The path {path} was not found.</p></body></html>"
            self.wfile.write(response.encode('utf-8'))
    
    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers['Content-Length']) if 'Content-Length' in self.headers else 0
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        logger.info(f"POST request,\nPath: {self.path}\nHeaders:\n{self.headers}\nBody:\n{post_data}")
        
        # Echo back the POST data
        self._set_response(content_type='application/json')
        response = {
            'message': 'POST request received',
            'path': self.path,
            'data': post_data,
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_PUT(self):
        """Handle PUT requests."""
        content_length = int(self.headers['Content-Length']) if 'Content-Length' in self.headers else 0
        put_data = self.rfile.read(content_length).decode('utf-8')
        
        logger.info(f"PUT request,\nPath: {self.path}\nHeaders:\n{self.headers}\nBody:\n{put_data}")
        
        # Echo back the PUT data
        self._set_response(content_type='application/json')
        response = {
            'message': 'PUT request received',
            'path': self.path,
            'data': put_data,
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        logger.info(f"DELETE request,\nPath: {self.path}\nHeaders:\n{self.headers}")
        
        # Respond to DELETE request
        self._set_response(content_type='application/json')
        response = {
            'message': 'DELETE request received',
            'path': self.path,
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))


def run_server(host='localhost', port=8000):
    """Run the test backend server."""
    server_address = (host, port)
    httpd = HTTPServer(server_address, TestHandler)
    logger.info(f'Starting test backend server on {host}:{port}')
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    
    httpd.server_close()
    logger.info('Test backend server stopped')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test Backend Server')
    parser.add_argument('--host', default='localhost', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind to')
    
    args = parser.parse_args()
    run_server(args.host, args.port)
