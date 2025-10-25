/**
 * FSRsync Dashboard - Main Application Logic
 */

class Dashboard {
    constructor() {
        this.stats = {
            activeTransfers: 0,
            bandwidthUsage: 0,
            activeConflicts: 0,
            peersOnline: 0,
            totalPeers: 0,
            transferRate: 0,
            bandwidth: {}
        };

        this.transfers = new Map();
        this.peers = new Map();
        this.conflicts = new Map();
        this.metrics = {};

        this.initializeEventListeners();
        this.initializeCharts();
        this.loadSettings();
        this.startAutoRefresh();
    }

    initializeEventListeners() {
        // Tab navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => this.handleTabChange(e));
        });

        // Button actions
        document.getElementById('pause-all-btn')?.addEventListener('click', () => this.pauseAllTransfers());
        document.getElementById('resume-all-btn')?.addEventListener('click', () => this.resumeAllTransfers());
        document.getElementById('cancel-failed-btn')?.addEventListener('click', () => this.clearFailedTransfers());

        document.getElementById('resolve-all-btn')?.addEventListener('click', () => this.resolveAllConflicts());
        document.getElementById('apply-strategy-btn')?.addEventListener('click', () => this.applyResolutionStrategy());

        document.getElementById('set-global-limit-btn')?.addEventListener('click', () => this.setGlobalBandwidthLimit());
        document.getElementById('refresh-peers-btn')?.addEventListener('click', () => this.refreshPeerList());

        // Settings
        document.getElementById('dark-mode')?.addEventListener('change', (e) => this.toggleDarkMode(e));
        document.getElementById('auto-refresh')?.addEventListener('change', (e) => this.toggleAutoRefresh(e));
        document.getElementById('reconnect-btn')?.addEventListener('click', () => this.reconnectWebSocket());
        document.getElementById('export-logs-btn')?.addEventListener('click', () => this.exportLogs());
        document.getElementById('clear-data-btn')?.addEventListener('click', () => this.clearCache());

        // Modal close
        document.querySelectorAll('.close').forEach(closeBtn => {
            closeBtn.addEventListener('click', (e) => this.closeModal(e));
        });

        // Search and filter
        document.getElementById('peer-filter')?.addEventListener('input', (e) => this.filterPeers(e.target.value));
    }

    initializeCharts() {
        // Charts will be initialized by charts.js
        this.charts = {};
    }

    handleTabChange(event) {
        event.preventDefault();
        const tabName = event.target.dataset.tab;

        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });

        // Deactivate all nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        // Show selected tab
        document.getElementById(tabName)?.classList.add('active');
        event.target.classList.add('active');

        // Trigger chart redraw if needed
        if (this.charts[tabName]) {
            setTimeout(() => {
                Object.values(this.charts[tabName]).forEach(chart => {
                    if (chart && chart.resize) chart.resize();
                });
            }, 100);
        }
    }

    updateStats(newStats) {
        this.stats = { ...this.stats, ...newStats };
        this.renderStats();
    }

    renderStats() {
        // Update header stats
        document.getElementById('client-count').textContent = this.stats.connectedClients || 0;
        document.getElementById('uptime').textContent = this.formatDuration(this.stats.uptime || 0);

        // Update dashboard stats
        document.getElementById('active-transfers').textContent = this.stats.activeTransfers || 0;
        document.getElementById('transfer-rate').textContent = this.formatBytes(this.stats.transferRate) + '/s';

        document.getElementById('bandwidth-usage').textContent = this.formatBandwidth(this.stats.bandwidthUsage);
        document.getElementById('bandwidth-limit').textContent = this.stats.bandwidthLimit ?
            `/ ${this.formatBandwidth(this.stats.bandwidthLimit)}` : '/ ∞';

        document.getElementById('active-conflicts').textContent = this.stats.activeConflicts || 0;
        document.getElementById('peers-online').textContent = this.stats.peersOnline || 0;
        document.getElementById('total-peers').textContent = `/ ${this.stats.totalPeers || 0}`;
    }

    addTransfer(transfer) {
        this.transfers.set(transfer.id, transfer);
        this.renderTransfers();
    }

    updateTransfer(transferId, updates) {
        const transfer = this.transfers.get(transferId);
        if (transfer) {
            Object.assign(transfer, updates);
            this.renderTransfers();
        }
    }

    renderTransfers() {
        const container = document.getElementById('transfers-list');
        if (!container) return;

        container.innerHTML = '';

        this.transfers.forEach((transfer) => {
            const transferEl = document.createElement('div');
            transferEl.className = 'transfer-item';
            transferEl.innerHTML = `
                <div class="transfer-info">
                    <div class="transfer-file">${transfer.file}</div>
                    <div class="transfer-path">${transfer.peer} → ${transfer.destination}</div>
                    <div class="transfer-progress">
                        <div class="transfer-progress-bar" style="width: ${transfer.progress}%"></div>
                    </div>
                    <div class="transfer-stats">
                        <span>${transfer.progress}%</span>
                        <span>${this.formatBytes(transfer.bytesTransferred)} / ${this.formatBytes(transfer.fileSize)}</span>
                        <span>${this.formatBandwidth(transfer.rate)}</span>
                        <span>ETA: ${this.formatDuration(transfer.eta)}</span>
                    </div>
                </div>
                <div class="transfer-actions">
                    <button class="btn btn-secondary" onclick="dashboard.pauseTransfer('${transfer.id}')">⏸</button>
                    <button class="btn btn-danger" onclick="dashboard.cancelTransfer('${transfer.id}')">✕</button>
                </div>
            `;
            container.appendChild(transferEl);
        });

        if (this.transfers.size === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No active transfers</p>';
        }
    }

    addPeer(peer) {
        this.peers.set(peer.hostname, peer);
        this.renderPeers();
    }

    updatePeer(hostname, updates) {
        const peer = this.peers.get(hostname);
        if (peer) {
            Object.assign(peer, updates);
            this.renderPeers();
        }
    }

    renderPeers() {
        const container = document.getElementById('peers-list');
        if (!container) return;

        const filterText = document.getElementById('peer-filter')?.value.toLowerCase() || '';
        const filteredPeers = Array.from(this.peers.values()).filter(peer =>
            peer.hostname.toLowerCase().includes(filterText) ||
            peer.address.toLowerCase().includes(filterText)
        );

        container.innerHTML = '';

        filteredPeers.forEach((peer) => {
            const statusClass = peer.status === 'CONNECTED' || peer.status === 'SYNCING' ? 'online' : 'offline';
            const peerEl = document.createElement('div');
            peerEl.className = 'peer-card';
            peerEl.innerHTML = `
                <div class="peer-header">
                    <div>
                        <div class="peer-name">${peer.hostname}</div>
                        <div class="peer-path">${peer.address}:${peer.port}</div>
                    </div>
                    <span class="peer-status ${statusClass}">${peer.status}</span>
                </div>
                <div class="peer-details">
                    <div class="peer-detail">Last Sync: ${this.formatTime(peer.lastSeen)}</div>
                    <div class="peer-detail">Latency: ${peer.latency || '—'} ms</div>
                    <div class="peer-detail">Success Rate: ${((peer.successCount / (peer.successCount + peer.failureCount)) * 100).toFixed(1)}%</div>
                    <div class="peer-bandwidth">
                        <strong>Bandwidth:</strong> ${this.formatBandwidth(peer.bandwidth)} / ${this.formatBandwidth(peer.bandwidthLimit)}
                    </div>
                </div>
            `;
            container.appendChild(peerEl);
        });

        if (filteredPeers.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No peers found</p>';
        }
    }

    addConflict(conflict) {
        this.conflicts.set(conflict.filePath, conflict);
        this.renderConflicts();
        this.showNotification(`Conflict detected: ${conflict.filePath}`, 'warning');
    }

    resolveConflict(filePath, resolution) {
        const conflict = this.conflicts.get(filePath);
        if (conflict) {
            conflict.resolved = true;
            conflict.resolution = resolution;
            this.renderConflicts();
        }
    }

    renderConflicts() {
        const container = document.getElementById('conflicts-list');
        if (!container) return;

        const unresolved = Array.from(this.conflicts.values()).filter(c => !c.resolved);
        container.innerHTML = '';

        unresolved.forEach((conflict) => {
            const conflictEl = document.createElement('div');
            conflictEl.className = 'conflict-item';
            conflictEl.innerHTML = `
                <div class="conflict-file">${conflict.filePath}</div>
                <div class="conflict-versions">
                    <div class="conflict-version">
                        <strong>${conflict.localVersion.hostname}</strong>
                        <div>Size: ${this.formatBytes(conflict.localVersion.size)}</div>
                        <div>Modified: ${this.formatTime(conflict.localVersion.mtime)}</div>
                        <div>Hash: ${conflict.localVersion.hash.substring(0, 8)}...</div>
                    </div>
                    <div class="conflict-version">
                        <strong>${conflict.remoteVersion.hostname}</strong>
                        <div>Size: ${this.formatBytes(conflict.remoteVersion.size)}</div>
                        <div>Modified: ${this.formatTime(conflict.remoteVersion.mtime)}</div>
                        <div>Hash: ${conflict.remoteVersion.hash.substring(0, 8)}...</div>
                    </div>
                </div>
                <div class="conflict-actions">
                    <button class="btn btn-primary" onclick="dashboard.acceptVersion('${conflict.filePath}', 'local')">Keep Local</button>
                    <button class="btn btn-secondary" onclick="dashboard.acceptVersion('${conflict.filePath}', 'remote')">Keep Remote</button>
                    <button class="btn btn-warning" onclick="dashboard.openConflictModal('${conflict.filePath}')">Manual Review</button>
                </div>
            `;
            container.appendChild(conflictEl);
        });

        if (unresolved.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No unresolved conflicts</p>';
        }
    }

    updateMetrics(metrics) {
        this.metrics = metrics;
        this.renderMetrics();
    }

    renderMetrics() {
        if (!this.metrics || !this.metrics.summary) return;

        const summary = this.metrics.summary;
        const lifetime = summary.lifetime_stats || {};

        // Transfer stats
        const transferStats = document.getElementById('transfer-stats');
        if (transferStats) {
            transferStats.innerHTML = `
                <li>Total Transfers: <strong>${lifetime.transfers || 0}</strong></li>
                <li>Total Bytes: <strong>${this.formatBytes(lifetime.bytes_transferred || 0)}</strong></li>
                <li>Compression Savings: <strong>${this.formatBytes(lifetime.compression_savings || 0)}</strong></li>
                <li>Success Rate: <strong>${(100 - (lifetime.failures || 0) * 100 / Math.max(1, lifetime.transfers || 1)).toFixed(1)}%</strong></li>
            `;
        }

        // Reliability stats
        const reliabilityStats = document.getElementById('reliability-stats');
        if (reliabilityStats) {
            reliabilityStats.innerHTML = `
                <li>Conflicts Detected: <strong>${lifetime.conflicts || 0}</strong></li>
                <li>Conflicts Resolved: <strong>${lifetime.conflicts || 0}</strong></li>
                <li>Manual Conflicts: <strong>0</strong></li>
                <li>Retry Rate: <strong>${((lifetime.retries || 0) * 100 / Math.max(1, lifetime.transfers || 1)).toFixed(1)}%</strong></li>
            `;
        }

        // Performance stats
        const performanceStats = document.getElementById('performance-stats');
        if (performanceStats) {
            performanceStats.innerHTML = `
                <li>Avg Transfer Rate: <strong>${this.formatBandwidth(summary.average_transfer_rate_bps)}</strong></li>
                <li>Peak Bandwidth: <strong>${summary.peak_bandwidth_mbps?.toFixed(2)} Mbps</strong></li>
                <li>Avg Latency: <strong>0 ms</strong></li>
                <li>Queue Processing: <strong>0 ms</strong></li>
            `;
        }
    }

    // Action handlers
    pauseTransfer(transferId) {
        this.updateTransfer(transferId, { status: 'PAUSED' });
        window.ws?.send(JSON.stringify({
            type: 'pause_transfer',
            payload: { transfer_id: transferId }
        }));
    }

    resumeTransfer(transferId) {
        this.updateTransfer(transferId, { status: 'IN_PROGRESS' });
        window.ws?.send(JSON.stringify({
            type: 'resume_transfer',
            payload: { transfer_id: transferId }
        }));
    }

    cancelTransfer(transferId) {
        this.transfers.delete(transferId);
        this.renderTransfers();
        window.ws?.send(JSON.stringify({
            type: 'cancel_transfer',
            payload: { transfer_id: transferId }
        }));
    }

    pauseAllTransfers() {
        this.transfers.forEach((transfer, id) => {
            if (transfer.status !== 'COMPLETED') {
                this.pauseTransfer(id);
            }
        });
    }

    resumeAllTransfers() {
        this.transfers.forEach((transfer, id) => {
            if (transfer.status === 'PAUSED') {
                this.resumeTransfer(id);
            }
        });
    }

    clearFailedTransfers() {
        this.transfers.forEach((transfer, id) => {
            if (transfer.status === 'FAILED') {
                this.transfers.delete(id);
            }
        });
        this.renderTransfers();
    }

    acceptVersion(filePath, version) {
        const conflict = this.conflicts.get(filePath);
        if (conflict) {
            this.resolveConflict(filePath, version);
            window.ws?.send(JSON.stringify({
                type: 'resolve_conflict',
                payload: {
                    file_path: filePath,
                    resolution: version
                }
            }));
            this.showNotification(`Conflict resolved: ${filePath}`, 'success');
        }
    }

    applyResolutionStrategy() {
        const strategy = document.getElementById('resolution-strategy')?.value;
        if (strategy) {
            this.conflicts.forEach((conflict, filePath) => {
                if (!conflict.resolved) {
                    window.ws?.send(JSON.stringify({
                        type: 'resolve_conflict_with_strategy',
                        payload: {
                            file_path: filePath,
                            strategy: strategy
                        }
                    }));
                }
            });
            this.showNotification(`Applied strategy: ${strategy}`, 'success');
        }
    }

    resolveAllConflicts() {
        this.conflicts.forEach((conflict, filePath) => {
            if (!conflict.resolved) {
                this.resolveConflict(filePath, 'auto');
            }
        });
    }

    setGlobalBandwidthLimit() {
        const limit = parseInt(document.getElementById('global-limit')?.value);
        if (limit && limit > 0) {
            window.ws?.send(JSON.stringify({
                type: 'set_bandwidth_limit',
                payload: { limit_mbps: limit }
            }));
            this.showNotification(`Bandwidth limit set to ${limit} Mbps`, 'success');
        }
    }

    refreshPeerList() {
        window.ws?.send(JSON.stringify({ type: 'request_stats' }));
    }

    filterPeers(filterText) {
        this.renderPeers();
    }

    // Settings
    toggleDarkMode(event) {
        document.body.classList.toggle('dark-mode', event.target.checked);
        localStorage.setItem('darkMode', event.target.checked);
    }

    toggleAutoRefresh(event) {
        localStorage.setItem('autoRefresh', event.target.checked);
    }

    loadSettings() {
        const darkMode = localStorage.getItem('darkMode') === 'true';
        const autoRefresh = localStorage.getItem('autoRefresh') !== 'false';

        if (darkMode) {
            document.body.classList.add('dark-mode');
            document.getElementById('dark-mode').checked = true;
        }

        if (!autoRefresh) {
            document.getElementById('auto-refresh').checked = false;
        }
    }

    startAutoRefresh() {
        setInterval(() => {
            if (document.getElementById('auto-refresh')?.checked) {
                window.ws?.send(JSON.stringify({ type: 'request_stats' }));
            }
        }, 2000);

        // Update uptime
        setInterval(() => {
            this.stats.uptime = (this.stats.uptime || 0) + 1;
            document.getElementById('uptime').textContent = this.formatDuration(this.stats.uptime);
        }, 1000);
    }

    reconnectWebSocket() {
        const url = document.getElementById('ws-url')?.value;
        if (url) {
            localStorage.setItem('wsUrl', url);
            window.location.reload();
        }
    }

    exportLogs() {
        const logs = localStorage.getItem('logs') || 'No logs available';
        const element = document.createElement('a');
        element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(logs));
        element.setAttribute('download', `fsrsync-logs-${new Date().toISOString()}.txt`);
        element.style.display = 'none';
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
    }

    clearCache() {
        if (confirm('Clear all cached data?')) {
            localStorage.clear();
            location.reload();
        }
    }

    // Modal handlers
    openConflictModal(filePath) {
        const modal = document.getElementById('conflict-modal');
        const conflict = this.conflicts.get(filePath);
        if (modal && conflict) {
            document.getElementById('conflict-details-content').innerHTML = `
                <p><strong>File:</strong> ${conflict.filePath}</p>
                <p><strong>Local Version:</strong> ${this.formatBytes(conflict.localVersion.size)} (${this.formatTime(conflict.localVersion.mtime)})</p>
                <p><strong>Remote Version:</strong> ${this.formatBytes(conflict.remoteVersion.size)} (${this.formatTime(conflict.remoteVersion.mtime)})</p>
                <div style="margin-top: 1.5rem;">
                    <button class="btn btn-primary" onclick="dashboard.acceptVersion('${filePath}', 'local'); dashboard.closeModal()">Keep Local</button>
                    <button class="btn btn-secondary" onclick="dashboard.acceptVersion('${filePath}', 'remote'); dashboard.closeModal()">Keep Remote</button>
                </div>
            `;
            modal.classList.add('active');
        }
    }

    closeModal(event) {
        if (event && event.target.closest('.close')) {
            event.target.closest('.modal').classList.remove('active');
        }
    }

    // Notification
    showNotification(message, type = 'info') {
        const container = document.getElementById('notifications');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <span class="notification-close" onclick="this.parentElement.remove()">×</span>
            ${message}
        `;
        container.appendChild(notification);

        setTimeout(() => notification.remove(), 5000);
    }

    // Utility functions
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
    }

    formatBandwidth(bps) {
        if (!bps) return '0 Mbps';
        return (bps / (1024 * 1024)).toFixed(2) + ' Mbps';
    }

    formatTime(timestamp) {
        if (!timestamp) return 'Never';
        const date = new Date(timestamp * 1000);
        const now = new Date();
        const diff = now - date;

        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days}d ago`;
        if (hours > 0) return `${hours}h ago`;
        if (minutes > 0) return `${minutes}m ago`;
        return 'just now';
    }

    formatDuration(seconds) {
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
}

// Initialize dashboard
const dashboard = new Dashboard();
