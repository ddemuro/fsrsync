/**
 * WebSocket Connection Handler for FSRsync Dashboard
 */

class WebSocketManager {
    constructor(url = null) {
        this.url = url || this.getWebSocketUrl();
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;
        this.messageQueue = [];
        this.messageHandlers = new Map();

        this.registerDefaultHandlers();
        this.connect();
    }

    getWebSocketUrl() {
        const saved = localStorage.getItem('wsUrl');
        if (saved) return saved;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        return `${protocol}//${host}/ws`;
    }

    connect() {
        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => this.handleOpen();
            this.ws.onmessage = (event) => this.handleMessage(event);
            this.ws.onerror = (error) => this.handleError(error);
            this.ws.onclose = () => this.handleClose();

        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }

    handleOpen() {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;

        // Update status indicator
        document.getElementById('status').style.color = '#10b981';

        // Flush message queue
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.send(message);
        }

        // Request initial stats
        this.send({
            type: 'request_stats',
            payload: {}
        });
    }

    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            console.log('WebSocket message:', message.type);

            const handler = this.messageHandlers.get(message.type);
            if (handler) {
                handler(message.payload);
            } else {
                console.warn('No handler for message type:', message.type);
            }

        } catch (error) {
            console.error('Error handling WebSocket message:', error);
        }
    }

    handleError(error) {
        console.error('WebSocket error:', error);
        document.getElementById('status').style.color = '#ef4444';
        dashboard.showNotification('WebSocket connection error', 'error');
    }

    handleClose() {
        console.log('WebSocket disconnected');
        document.getElementById('status').style.color = '#f59e0b';
        this.scheduleReconnect();
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => this.connect(), delay);
        } else {
            console.error('Max reconnection attempts reached');
            dashboard.showNotification('Failed to connect to server. Please refresh the page.', 'error');
        }
    }

    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            this.messageQueue.push(message);
        }
    }

    subscribe(type) {
        this.send({
            type: 'subscribe',
            payload: { type: type }
        });
    }

    unsubscribe(type) {
        this.send({
            type: 'unsubscribe',
            payload: { type: type }
        });
    }

    registerDefaultHandlers() {
        // Connected message
        this.on('connected', (payload) => {
            console.log('Connected to server:', payload.client_id);
        });

        // Stats update
        this.on('stats_update', (payload) => {
            dashboard.updateStats({
                connectedClients: payload.connected_clients,
                uptime: payload.server_uptime_seconds,
                activeTransfers: payload.active_transfers || 0,
                bandwidthUsage: payload.current_bandwidth || 0,
                activeConflicts: payload.active_conflicts || 0,
                peersOnline: payload.peers_online || 0,
                totalPeers: payload.total_peers || 0
            });

            // Update charts
            if (window.chartManager) {
                window.chartManager.updateData(payload);
            }
        });

        // Transfer progress
        this.on('transfer_progress', (payload) => {
            dashboard.addTransfer({
                id: payload.transfer_id,
                file: payload.file_path,
                peer: payload.peer,
                destination: payload.destination_path,
                progress: payload.progress_percent,
                bytesTransferred: payload.bytes_transferred,
                fileSize: payload.file_size,
                rate: payload.transfer_rate_bps,
                eta: payload.eta_seconds || 0,
                status: payload.status
            });
        });

        // Bandwidth update
        this.on('bandwidth_update', (payload) => {
            dashboard.stats.bandwidthUsage = payload.current_usage_bps;
            dashboard.stats.bandwidth = payload.per_peer_bandwidth || {};
            dashboard.renderStats();
        });

        // Peer status
        this.on('peer_status_update', (payload) => {
            dashboard.addPeer({
                hostname: payload.hostname,
                address: payload.address,
                port: payload.port,
                status: payload.status,
                lastSeen: payload.last_seen,
                latency: payload.latency_ms,
                bandwidth: payload.current_bandwidth,
                bandwidthLimit: payload.bandwidth_limit,
                successCount: payload.success_count,
                failureCount: payload.failure_count
            });
        });

        // Conflict detected
        this.on('conflict_detected', (payload) => {
            dashboard.addConflict({
                filePath: payload.file_path,
                localVersion: {
                    hostname: payload.local_hostname,
                    size: payload.local_size,
                    mtime: payload.local_mtime,
                    hash: payload.local_hash
                },
                remoteVersion: {
                    hostname: payload.remote_hostname,
                    size: payload.remote_size,
                    mtime: payload.remote_mtime,
                    hash: payload.remote_hash
                },
                resolved: false
            });
        });

        // Transfer completed
        this.on('transfer_completed', (payload) => {
            dashboard.updateTransfer(payload.transfer_id, {
                status: 'COMPLETED',
                progress: 100
            });
            dashboard.showNotification(`Transfer completed: ${payload.file_path}`, 'success');
        });

        // Error
        this.on('error', (payload) => {
            dashboard.showNotification(`Error: ${payload.error}`, 'error');
        });

        // Heartbeat
        this.on('heartbeat', () => {
            // Heartbeat received
        });
    }

    on(messageType, handler) {
        this.messageHandlers.set(messageType, handler);
    }

    off(messageType) {
        this.messageHandlers.delete(messageType);
    }
}

// Initialize WebSocket manager
window.ws = new WebSocketManager();

// Expose send method globally
window.sendMessage = (message) => {
    window.ws.send(message);
};
