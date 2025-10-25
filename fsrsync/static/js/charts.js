/**
 * FSRsync Dashboard - Charts Management
 * Handles all Chart.js initialization and updates
 */

class ChartManager {
    constructor() {
        this.charts = {};
        this.dataHistory = {
            timestamps: [],
            transferRate: [],
            bandwidth: [],
            peerStatus: {},
            conflicts: {}
        };
        this.maxDataPoints = 60; // 1 hour at 1-minute intervals

        this.initializeCharts();
    }

    initializeCharts() {
        // Transfer Rate Chart
        const transferRateCtx = document.getElementById('transferRateChart');
        if (transferRateCtx) {
            this.charts.transferRate = new Chart(transferRateCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Transfer Rate (MB/s)',
                        data: [],
                        borderColor: '#2563eb',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    }]
                },
                options: this.getLineChartOptions('Transfer Rate')
            });
        }

        // Bandwidth Chart
        const bandwidthCtx = document.getElementById('bandwidthChart');
        if (bandwidthCtx) {
            this.charts.bandwidth = new Chart(bandwidthCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Bandwidth Usage (Mbps)',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    }]
                },
                options: this.getLineChartOptions('Bandwidth Usage')
            });
        }

        // Peer Status Chart
        const peerStatusCtx = document.getElementById('peerStatusChart');
        if (peerStatusCtx) {
            this.charts.peerStatus = new Chart(peerStatusCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Online', 'Offline', 'Syncing'],
                    datasets: [{
                        data: [0, 0, 0],
                        backgroundColor: [
                            '#10b981',
                            '#ef4444',
                            '#f59e0b'
                        ],
                        borderColor: '#fff',
                        borderWidth: 2
                    }]
                },
                options: this.getDoughnutChartOptions('Peer Status')
            });
        }

        // Conflict Chart
        const conflictCtx = document.getElementById('conflictChart');
        if (conflictCtx) {
            this.charts.conflict = new Chart(conflictCtx, {
                type: 'bar',
                data: {
                    labels: ['Last-Write', 'Host-Priority', 'Size-Wins', 'Hash-Based', 'Manual'],
                    datasets: [{
                        label: 'Resolution Method',
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: [
                            '#2563eb',
                            '#3b82f6',
                            '#60a5fa',
                            '#93c5fd',
                            '#dbeafe'
                        ],
                        borderColor: '#fff',
                        borderWidth: 1
                    }]
                },
                options: this.getBarChartOptions('Conflict Resolutions')
            });
        }

        // Per-Peer Bandwidth Chart
        const perPeerCtx = document.getElementById('perPeerBandwidthChart');
        if (perPeerCtx) {
            this.charts.perPeerBandwidth = new Chart(perPeerCtx, {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Bandwidth Usage (Mbps)',
                        data: [],
                        backgroundColor: '#2563eb',
                        borderColor: '#1d4ed8',
                        borderWidth: 1
                    }]
                },
                options: this.getBarChartOptions('Per-Peer Bandwidth')
            });
        }

        // Success Rate Chart
        const successRateCtx = document.getElementById('successRateChart');
        if (successRateCtx) {
            this.charts.successRate = new Chart(successRateCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Success Rate (%)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    }]
                },
                options: this.getLineChartOptions('Success Rate')
            });
        }

        // Conflict Types Chart
        const conflictTypesCtx = document.getElementById('conflictTypesChart');
        if (conflictTypesCtx) {
            this.charts.conflictTypes = new Chart(conflictTypesCtx, {
                type: 'pie',
                data: {
                    labels: ['Concurrent Edit', 'Content Mismatch', 'Metadata Conflict'],
                    datasets: [{
                        data: [0, 0, 0],
                        backgroundColor: [
                            '#ef4444',
                            '#f97316',
                            '#f59e0b'
                        ],
                        borderColor: '#fff',
                        borderWidth: 2
                    }]
                },
                options: this.getPieChartOptions('Conflict Types')
            });
        }
    }

    updateData(stats) {
        const now = new Date().toLocaleTimeString();

        // Add timestamp
        this.dataHistory.timestamps.push(now);
        if (this.dataHistory.timestamps.length > this.maxDataPoints) {
            this.dataHistory.timestamps.shift();
        }

        // Update transfer rate
        const transferRateMbps = (stats.transfer_rate_bps || 0) / (1024 * 1024);
        this.dataHistory.transferRate.push(transferRateMbps);
        if (this.dataHistory.transferRate.length > this.maxDataPoints) {
            this.dataHistory.transferRate.shift();
        }

        // Update bandwidth
        const bandwidthMbps = (stats.current_bandwidth || 0) / (1024 * 1024);
        this.dataHistory.bandwidth.push(bandwidthMbps);
        if (this.dataHistory.bandwidth.length > this.maxDataPoints) {
            this.dataHistory.bandwidth.shift();
        }

        // Update charts
        this.updateTransferRateChart();
        this.updateBandwidthChart();
        this.updatePeerStatusChart(stats);
        this.updateConflictChart(stats);
        this.updatePerPeerBandwidthChart(stats);
        this.updateSuccessRateChart(stats);
    }

    updateTransferRateChart() {
        const chart = this.charts.transferRate;
        if (chart) {
            chart.data.labels = this.dataHistory.timestamps;
            chart.data.datasets[0].data = this.dataHistory.transferRate;
            chart.update('none');
        }
    }

    updateBandwidthChart() {
        const chart = this.charts.bandwidth;
        if (chart) {
            chart.data.labels = this.dataHistory.timestamps;
            chart.data.datasets[0].data = this.dataHistory.bandwidth;
            chart.update('none');
        }
    }

    updatePeerStatusChart(stats) {
        const chart = this.charts.peerStatus;
        if (chart && stats.peers) {
            const online = stats.peers.filter(p => p.status === 'CONNECTED').length;
            const offline = stats.peers.filter(p => p.status === 'OFFLINE').length;
            const syncing = stats.peers.filter(p => p.status === 'SYNCING').length;

            chart.data.datasets[0].data = [online, offline, syncing];
            chart.update('none');
        }
    }

    updateConflictChart(stats) {
        const chart = this.charts.conflict;
        if (chart && stats.conflict_resolutions) {
            const data = [
                stats.conflict_resolutions.LAST_WRITE_WINS || 0,
                stats.conflict_resolutions.HOST_PRIORITY || 0,
                stats.conflict_resolutions.SIZE_WINS || 0,
                stats.conflict_resolutions.HASH_BASED || 0,
                stats.conflict_resolutions.MANUAL || 0
            ];
            chart.data.datasets[0].data = data;
            chart.update('none');
        }
    }

    updatePerPeerBandwidthChart(stats) {
        const chart = this.charts.perPeerBandwidth;
        if (chart && stats.peers) {
            const peerNames = stats.peers.map(p => p.hostname).slice(0, 5);
            const bandwidths = stats.peers.map(p => (p.current_bandwidth || 0) / (1024 * 1024)).slice(0, 5);

            chart.data.labels = peerNames;
            chart.data.datasets[0].data = bandwidths;
            chart.update('none');
        }
    }

    updateSuccessRateChart(stats) {
        const chart = this.charts.successRate;
        if (chart) {
            const total = (stats.transfers_completed || 0) + (stats.transfers_failed || 0);
            const successRate = total > 0 ? ((stats.transfers_completed || 0) / total) * 100 : 100;

            chart.data.labels = this.dataHistory.timestamps;
            chart.data.datasets[0].data.push(successRate);
            if (chart.data.datasets[0].data.length > this.maxDataPoints) {
                chart.data.datasets[0].data.shift();
            }
            chart.update('none');
        }
    }

    // Chart configuration options
    getLineChartOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary'),
                        font: { size: 12 }
                    }
                },
                title: {
                    display: false
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)',
                        drawBorder: false
                    },
                    ticks: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary'),
                        font: { size: 11 }
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)',
                        drawBorder: false
                    },
                    ticks: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary'),
                        font: { size: 11 }
                    }
                }
            }
        };
    }

    getBarChartOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'x',
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary'),
                        font: { size: 12 }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary'),
                        font: { size: 11 }
                    }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary'),
                        font: { size: 11 }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        };
    }

    getDoughnutChartOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary'),
                        font: { size: 12 },
                        padding: 15
                    }
                }
            }
        };
    }

    getPieChartOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary'),
                        font: { size: 12 },
                        padding: 15
                    }
                }
            }
        };
    }
}

// Initialize chart manager
window.chartManager = new ChartManager();

// Subscribe to updates
if (window.ws) {
    window.ws.subscribe('stats');
    window.ws.subscribe('transfers');
    window.ws.subscribe('bandwidth');
}
