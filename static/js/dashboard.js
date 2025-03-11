document.addEventListener('DOMContentLoaded', function() {
    const statusBadge = document.getElementById('status-badge');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const logOutput = document.getElementById('log-output');
    const hostInfo = document.getElementById('host-info');
    const portInfo = document.getElementById('port-info');
    const threadsInfo = document.getElementById('threads-info');
    const redisInfo = document.getElementById('redis-info');
    
    // Connect to Socket.IO
    const socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to server');
        // Add a test message to the log output to verify it's working
        logOutput.innerHTML += "Connected to server\n";
        logOutput.scrollTop = logOutput.scrollHeight;
    });
    
    socket.on('connect_error', function(error) {
        console.error('Connection error:', error);
        logOutput.innerHTML += "Socket.IO connection error\n";
        logOutput.scrollTop = logOutput.scrollHeight;
    });
    
    socket.on('proxy_log', function(data) {
        console.log('Received log:', data); // Debug log
        
        if (!data || !data.data) {
            console.error('Invalid log data received');
            return;
        }
        
        const log = data.data;
        // Add a timestamp to each log entry
        const timestamp = new Date().toLocaleTimeString();
        const formattedLog = `[${timestamp}] ${log}`;
        
        // Append to log output with proper formatting
        logOutput.innerHTML += formattedLog + '\n';
        
        // Auto-scroll to bottom
        logOutput.scrollTop = logOutput.scrollHeight;
        
        // Limit the number of log lines to prevent performance issues
        const maxLines = 1000;
        const lines = logOutput.innerHTML.split('\n');
        if (lines.length > maxLines) {
            logOutput.innerHTML = lines.slice(lines.length - maxLines).join('\n');
        }
    });
    
    // Check proxy status
    function checkProxyStatus() {
        fetch('/api/proxy_status')
            .then(response => response.json())
            .then(data => {
                if (data.running) {
                    statusBadge.textContent = 'Running';
                    statusBadge.className = 'badge bg-success';
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                    
                    // If proxy is running, fetch logs
                    fetchProxyLogs();
                } else {
                    statusBadge.textContent = 'Stopped';
                    statusBadge.className = 'badge bg-danger';
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                }
            })
            .catch(error => {
                console.error('Error checking proxy status:', error);
                statusBadge.textContent = 'Unknown';
                statusBadge.className = 'badge bg-warning';
            });
    }
    
    // Fetch proxy logs from API
    function fetchProxyLogs() {
        fetch('/api/proxy_logs')
            .then(response => response.json())
            .then(data => {
                if (data.logs && data.logs.length > 0) {
                    // Clear existing logs
                    logOutput.innerHTML = '';
                    
                    // Add each log with timestamp
                    data.logs.forEach(log => {
                        const timestamp = new Date().toLocaleTimeString();
                        logOutput.innerHTML += `[${timestamp}] ${log}\n`;
                    });
                    
                    // Auto-scroll to bottom
                    logOutput.scrollTop = logOutput.scrollHeight;
                }
            })
            .catch(error => {
                console.error('Error fetching proxy logs:', error);
            });
    }
    
    // Load server information
    function loadServerInfo() {
        fetch('/config')
            .then(response => response.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                
                // Extract config values from the form
                const configForm = doc.querySelector('form');
                if (configForm) {
                    const hostInput = configForm.querySelector('[name="HOST"]');
                    const portInput = configForm.querySelector('[name="PORT"]');
                    const threadsInput = configForm.querySelector('[name="THREAD_POOL_SIZE"]');
                    const redisHostInput = configForm.querySelector('[name="REDIS_HOST"]');
                    const redisPortInput = configForm.querySelector('[name="REDIS_PORT"]');
                    
                    if (hostInput) hostInfo.textContent = hostInput.value;
                    if (portInput) portInfo.textContent = portInput.value;
                    if (threadsInput) threadsInfo.textContent = threadsInput.value;
                    
                    if (redisHostInput && redisPortInput) {
                        redisInfo.textContent = `${redisHostInput.value}:${redisPortInput.value}`;
                    }
                }
            })
            .catch(error => {
                console.error('Error loading server info:', error);
            });
    }
    
    // Start proxy server
    startBtn.addEventListener('click', function() {
        fetch('/api/start_proxy', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            console.log('Proxy started:', data);
            checkProxyStatus();
        })
        .catch(error => {
            console.error('Error starting proxy:', error);
        });
    });
    
    // Stop proxy server
    stopBtn.addEventListener('click', function() {
        fetch('/api/stop_proxy', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            console.log('Proxy stopped:', data);
            checkProxyStatus();
        })
        .catch(error => {
            console.error('Error stopping proxy:', error);
        });
    });
    
    // Initial checks
    checkProxyStatus();
    loadServerInfo();
    
    // Periodic status check and log updates
    setInterval(checkProxyStatus, 5000);
});
