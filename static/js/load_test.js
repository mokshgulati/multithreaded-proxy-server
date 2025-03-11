document.addEventListener('DOMContentLoaded', function() {
    const testForm = document.getElementById('load-test-form');
    const testStatus = document.getElementById('test-status');
    const testProgress = document.getElementById('test-progress');
    const testResults = document.getElementById('test-results');
    const resultsTable = document.getElementById('results-table');
    const rawOutput = document.getElementById('raw-output');
    const rpsChart = document.getElementById('rps-chart');
    const responseTimeChart = document.getElementById('response-time-chart');
    const noRpsData = document.getElementById('no-rps-data');
    const noRtData = document.getElementById('no-rt-data');
    const historyTable = document.getElementById('history-table');
    
    // Load test history
    function loadTestHistory() {
        fetch('/api/test_results')
            .then(response => response.json())
            .then(data => {
                if (data.length > 0) {
                    historyTable.innerHTML = '';
                    
                    // Sort by timestamp, newest first
                    data.sort((a, b) => {
                        return new Date(b.timestamp) - new Date(a.timestamp);
                    });
                    
                    // Show only the last 10 tests
                    const recentTests = data.slice(0, 10);
                    
                    recentTests.forEach(test => {
                        const metrics = test.metrics || {};
                        const row = document.createElement('tr');
                        
                        row.innerHTML = `
                            <td>${test.timestamp}</td>
                            <td>${test.params.requests || '-'}</td>
                            <td>${test.params.concurrency || '-'}</td>
                            <td>${metrics['Requests per second'] ? metrics['Requests per second'].toFixed(2) : '-'}</td>
                            <td>${metrics['Average'] ? metrics['Average'].toFixed(2) : '-'}</td>
                        `;
                        
                        historyTable.appendChild(row);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading test history:', error);
            });
    }
    
    // Load charts
    function loadCharts() {
        fetch('/api/charts')
            .then(response => response.json())
            .then(data => {
                if (data.rps) {
                    rpsChart.src = 'data:image/png;base64,' + data.rps;
                    rpsChart.classList.remove('d-none');
                    noRpsData.classList.add('d-none');
                } else {
                    rpsChart.classList.add('d-none');
                    noRpsData.classList.remove('d-none');
                }
                
                if (data.response_time) {
                    responseTimeChart.src = 'data:image/png;base64,' + data.response_time;
                    responseTimeChart.classList.remove('d-none');
                    noRtData.classList.add('d-none');
                } else {
                    responseTimeChart.classList.add('d-none');
                    noRtData.classList.remove('d-none');
                }
            })
            .catch(error => {
                console.error('Error loading charts:', error);
            });
    }
    
    // Run a load test
    testForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(testForm);
        const params = {};
        
        for (const [key, value] of formData.entries()) {
            if (key === 'time_based') {
                params[key] = true;
            } else if (value) {
                params[key] = value;
            }
        }
        
        // Construct the full URL
        if (params.url && params.path) {
            if (!params.path.startsWith('/')) {
                params.path = '/' + params.path;
            }
            params.url = params.url + params.path;
            delete params.path;
        }
        
        // Update UI
        testStatus.textContent = 'Running test...';
        testStatus.className = 'alert alert-info';
        testProgress.style.display = 'block';
        rawOutput.textContent = 'Test in progress...';
        
        // Send request
        fetch('/api/run_load_test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        })
        .then(response => response.json())
        .then(data => {
            // Update UI
            testStatus.textContent = 'Test completed successfully';
            testStatus.className = 'alert alert-success';
            testProgress.style.display = 'none';
            testResults.classList.remove('d-none');
            
            // Display raw output
            rawOutput.textContent = data.results.stdout || 'No output';
            
            // Update results table
            resultsTable.innerHTML = '';
            const metrics = data.results.metrics || {};
            
            for (const [key, value] of Object.entries(metrics)) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><strong>${key}</strong></td>
                    <td>${value}</td>
                `;
                resultsTable.appendChild(row);
            }
            
            // Update charts
            if (data.charts) {
                if (data.charts.rps) {
                    rpsChart.src = 'data:image/png;base64,' + data.charts.rps;
                    rpsChart.classList.remove('d-none');
                    noRpsData.classList.add('d-none');
                }
                
                if (data.charts.response_time) {
                    responseTimeChart.src = 'data:image/png;base64,' + data.charts.response_time;
                    responseTimeChart.classList.remove('d-none');
                    noRtData.classList.add('d-none');
                }
            }
            
            // Reload test history
            loadTestHistory();
        })
        .catch(error => {
            console.error('Error running test:', error);
            testStatus.textContent = 'Error running test: ' + error.message;
            testStatus.className = 'alert alert-danger';
            testProgress.style.display = 'none';
        });
    });
    
    // Initial load
    loadTestHistory();
    loadCharts();
});