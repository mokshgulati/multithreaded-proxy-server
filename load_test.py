#!/usr/bin/env python3
"""
Load Testing Script for Proxy Server

This script generates concurrent requests to test the performance
of the multithreaded proxy server under load.
"""

import requests
import time
import threading
import argparse
import random
import statistics
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib3.exceptions import InsecureRequestWarning

# Suppress only the single InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LoadTest")

# Test endpoints
TEST_ENDPOINTS = [
    "/",
    "/json",
    "/delay?seconds=1",
    "/large",
    "/error"
]

# HTTP methods to test
HTTP_METHODS = {
    "GET": requests.get,
    "POST": requests.post,
    "PUT": requests.put,
    "DELETE": requests.delete
}

class LoadTest:
    """Load test for the proxy server."""
    
    def __init__(self, proxy_url, num_requests=100, concurrency=10, 
                 test_duration=60, method="GET"):
        """Initialize the load test."""
        self.proxy_url = proxy_url
        self.num_requests = num_requests
        self.concurrency = concurrency
        self.test_duration = test_duration
        self.method = method
        self.http_method = HTTP_METHODS.get(method, requests.get)
        
        # Results
        self.response_times = []
        self.status_codes = {}
        self.errors = []
        self.start_time = None
        self.end_time = None
        
        # Synchronization
        self.lock = threading.Lock()
        self.completed_requests = 0
    
    def make_request(self):
        """Make a single request to the proxy server."""
        # Select a random endpoint
        endpoint = random.choice(TEST_ENDPOINTS)
        url = f"{self.proxy_url}{endpoint}"
        
        # Prepare request data for non-GET methods
        data = None
        if self.method != "GET":
            data = {"test": "data", "timestamp": time.time()}
        
        start_time = time.time()
        try:
            response = self.http_method(
                url, 
                data=data,
                timeout=10,
                verify=False  # Disable SSL verification for testing
            )
            
            # Record response time
            response_time = time.time() - start_time
            
            with self.lock:
                self.response_times.append(response_time)
                
                # Record status code
                status_code = response.status_code
                if status_code in self.status_codes:
                    self.status_codes[status_code] += 1
                else:
                    self.status_codes[status_code] = 1
                
                self.completed_requests += 1
                
            return response.status_code, response_time
            
        except Exception as e:
            error_time = time.time() - start_time
            
            with self.lock:
                self.errors.append(str(e))
                self.completed_requests += 1
            
            return "Error", error_time
    
    def run_time_based_test(self):
        """Run a time-based load test."""
        logger.info(f"Starting time-based load test for {self.test_duration} seconds")
        logger.info(f"Method: {self.method}, Concurrency: {self.concurrency}")
        
        self.start_time = time.time()
        end_time = self.start_time + self.test_duration
        
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = []
            
            # Keep submitting requests until the test duration is reached
            while time.time() < end_time:
                # Submit requests up to concurrency limit
                while len(futures) < self.concurrency and time.time() < end_time:
                    futures.append(executor.submit(self.make_request))
                
                # Check for completed futures
                completed = [f for f in futures if f.done()]
                for future in completed:
                    futures.remove(future)
                    try:
                        future.result()  # Get the result to handle any exceptions
                    except Exception as e:
                        logger.error(f"Request error: {e}")
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.01)
        
        self.end_time = time.time()
    
    def run_count_based_test(self):
        """Run a count-based load test."""
        logger.info(f"Starting count-based load test for {self.num_requests} requests")
        logger.info(f"Method: {self.method}, Concurrency: {self.concurrency}")
        
        self.start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            # Submit all requests at once
            futures = [executor.submit(self.make_request) for _ in range(self.num_requests)]
            
            # Wait for all requests to complete
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Request error: {e}")
        
        self.end_time = time.time()
    
    def print_results(self):
        """Print the test results."""
        if not self.response_times:
            logger.error("No response times recorded. Test may have failed.")
            return
            
        # Calculate statistics
        total_time = self.end_time - self.start_time
        total_requests = len(self.response_times)
        requests_per_second = total_requests / total_time
        
        # Response time statistics
        min_time = min(self.response_times)
        max_time = max(self.response_times)
        avg_time = sum(self.response_times) / len(self.response_times)
        median_time = statistics.median(self.response_times)
        p95_time = sorted(self.response_times)[int(len(self.response_times) * 0.95)]
        
        # Count successful requests (any valid HTTP response is a success from proxy perspective)
        successful_responses = sum(1 for code in self.status_codes.keys() if code != "Error")
        success_rate = (successful_responses / total_requests) * 100 if total_requests > 0 else 0
        
        # Print results
        print("\n" + "="*50)
        print(f"LOAD TEST RESULTS - {self.method} {self.proxy_url}")
        print("="*50)
        print(f"Total requests:       {total_requests}")
        print(f"Total time:           {total_time:.2f} seconds")
        print(f"Requests per second:  {requests_per_second:.2f}")
        print(f"Concurrency level:    {self.concurrency}")
        print(f"Success rate:         {success_rate:.1f}% (any valid HTTP response)")
        print("\nResponse time statistics:")
        print(f"  Min:                {min_time*1000:.2f} ms")
        print(f"  Max:                {max_time*1000:.2f} ms")
        print(f"  Average:            {avg_time*1000:.2f} ms")
        print(f"  Median:             {median_time*1000:.2f} ms")
        print(f"  95th percentile:    {p95_time*1000:.2f} ms")
        
        print("\nStatus code distribution:")
        for status_code, count in sorted(self.status_codes.items()):
            percentage = (count / total_requests) * 100
            status_text = status_code
            
            # Add descriptive text for common status codes
            if status_code == 200:
                status_text = f"{status_code} (OK)"
            elif status_code == 404:
                status_text = f"{status_code} (Not Found)"
            elif status_code == 500:
                status_text = f"{status_code} (Internal Server Error)"
            elif status_code == 502:
                status_text = f"{status_code} (Bad Gateway)"
            elif status_code == 504:
                status_text = f"{status_code} (Gateway Timeout)"
            
            print(f"  {status_text}: {count} ({percentage:.1f}%)")
        
        if self.errors:
            print(f"\nErrors: {len(self.errors)} ({len(self.errors)/total_requests*100:.1f}%)")
            # Print the first few unique errors
            unique_errors = set(self.errors[:10])
            for error in unique_errors:
                print(f"  - {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more")
        
        print("="*50)


def main():
    """Parse arguments and run the load test."""
    parser = argparse.ArgumentParser(description="Load Test for Proxy Server")
    parser.add_argument("--url", default="http://localhost:8080", 
                        help="Proxy server URL")
    parser.add_argument("--requests", type=int, default=1000, 
                        help="Number of requests to make")
    parser.add_argument("--concurrency", type=int, default=10, 
                        help="Number of concurrent requests")
    parser.add_argument("--duration", type=int, default=60, 
                        help="Test duration in seconds (for time-based tests)")
    parser.add_argument("--method", choices=["GET", "POST", "PUT", "DELETE"], 
                        default="GET", help="HTTP method to use")
    parser.add_argument("--time-based", action="store_true", 
                        help="Run a time-based test instead of a count-based test")
    
    args = parser.parse_args()
    
    # Create and run the load test
    load_test = LoadTest(
        proxy_url=args.url,
        num_requests=args.requests,
        concurrency=args.concurrency,
        test_duration=args.duration,
        method=args.method
    )
    
    try:
        if args.time_based:
            load_test.run_time_based_test()
        else:
            load_test.run_count_based_test()
            
        load_test.print_results()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        if load_test.response_times:
            load_test.end_time = time.time()
            load_test.print_results()


if __name__ == "__main__":
    main()
