#!/usr/bin/env python3
"""
Web Dashboard for Proxy Server

A Flask-based web interface for controlling the proxy server and running load tests.
"""

import os
import json
import time
import threading
import subprocess
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'proxy-dashboard-secret-key'
socketio = SocketIO(app)

# Global variables
proxy_process = None
proxy_running = False
test_results = []
current_config = {}

# Load default configuration
def load_config():
    config = {}
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key] = value
    return config

# Save configuration to .env file
def save_config(config):
    lines = []
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.strip().startswith('#') and '=' in line:
                key = line.split('=', 1)[0]
                if key in config:
                    lines.append(f"{key}={config[key]}\n")
                    del config[key]
                else:
                    lines.append(line)
            else:
                lines.append(line)
    
    # Add any new config items
    for key, value in config.items():
        lines.append(f"{key}={value}\n")
    
    with open('.env', 'w') as f:
        f.writelines(lines)

# Start the proxy server
def start_proxy_server():
    global proxy_process, proxy_running
    if not proxy_running:
        proxy_process = subprocess.Popen(['python', 'proxy_server.py'], 
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT,
                                         universal_newlines=True)
        proxy_running = True
        threading.Thread(target=read_proxy_output, daemon=True).start()

# Stop the proxy server
def stop_proxy_server():
    global proxy_process, proxy_running
    if proxy_running and proxy_process:
        proxy_process.terminate()
        proxy_process = None
        proxy_running = False

# Read proxy server output
def read_proxy_output():
    global proxy_process
    while proxy_running and proxy_process:
        output = proxy_process.stdout.readline()
        if output:
            socketio.emit('proxy_log', {'data': output.strip()})
        else:
            break

# Run a load test
def run_load_test(params):
    cmd = ['python', 'load_test.py']
    for key, value in params.items():
        if key == 'time_based' and value:
            cmd.append('--time-based')
        elif value:
            cmd.append(f'--{key}')
            cmd.append(str(value))
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    
    # Parse the results
    results = {
        'stdout': stdout.decode('utf-8'),
        'stderr': stderr.decode('utf-8'),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'params': params
    }
    
    # Extract key metrics from the output
    output = results['stdout']
    metrics = {}
    
    for line in output.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip()
            
            # Try to convert to numeric
            try:
                if '.' in value:
                    metrics[key] = float(value.split()[0])
                else:
                    metrics[key] = int(value.split()[0])
            except (ValueError, IndexError):
                metrics[key] = value
    
    results['metrics'] = metrics
    test_results.append(results)
    return results

# Generate charts for test results
def generate_charts():
    if not test_results:
        return None
    
    # Create a DataFrame from test results
    data = []
    for result in test_results:
        if 'metrics' in result:
            metrics = result['metrics']
            data.append({
                'timestamp': result['timestamp'],
                'requests_per_second': metrics.get('Requests per second', 0),
                'avg_response_time': metrics.get('Average', 0),
                'success_rate': metrics.get('Success rate', 100),
                'concurrency': metrics.get('Concurrency level', 0)
            })
    
    if not data:
        return None
        
    df = pd.DataFrame(data)
    
    # Generate charts
    charts = {}
    
    # Requests per second over time
    plt.figure(figsize=(10, 6))
    plt.plot(df['timestamp'], df['requests_per_second'], marker='o')
    plt.title('Requests per Second')
    plt.xlabel('Time')
    plt.ylabel('Requests/sec')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    charts['rps'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    # Average response time
    plt.figure(figsize=(10, 6))
    plt.plot(df['timestamp'], df['avg_response_time'], marker='o', color='green')
    plt.title('Average Response Time')
    plt.xlabel('Time')
    plt.ylabel('Response Time (ms)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    charts['response_time'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    return charts

# Routes
@app.route('/')
def index():
    global proxy_running
    return render_template('index.html', proxy_running=proxy_running)

@app.route('/config')
def config():
    global current_config
    current_config = load_config()
    return render_template('config.html', config=current_config)

@app.route('/save_config', methods=['POST'])
def save_config_route():
    config_data = request.form.to_dict()
    save_config(config_data)
    return redirect(url_for('config'))

@app.route('/load_test')
def load_test_page():
    return render_template('load_test.html', test_results=test_results)

@app.route('/api/start_proxy', methods=['POST'])
def api_start_proxy():
    start_proxy_server()
    return jsonify({'status': 'success', 'message': 'Proxy server started'})

@app.route('/api/stop_proxy', methods=['POST'])
def api_stop_proxy():
    stop_proxy_server()
    return jsonify({'status': 'success', 'message': 'Proxy server stopped'})

@app.route('/api/proxy_status')
def api_proxy_status():
    return jsonify({'running': proxy_running})

@app.route('/api/run_load_test', methods=['POST'])
def api_run_load_test():
    params = request.json
    results = run_load_test(params)
    charts = generate_charts()
    return jsonify({
        'status': 'success', 
        'results': results,
        'charts': charts
    })

@app.route('/api/test_results')
def api_test_results():
    return jsonify(test_results)

@app.route('/api/charts')
def api_charts():
    charts = generate_charts()
    return jsonify(charts or {})

# Socket.IO events
@socketio.on('connect')
def socket_connect():
    emit('status', {'data': 'Connected to server'})

@socketio.on('disconnect')
def socket_disconnect():
    pass

# Main entry point
if __name__ == '__main__':
    # Load initial configuration
    current_config = load_config()
    
    # Create directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    # Start the web server
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
