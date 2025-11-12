-- ============================================
-- Network Schema
-- Network Infrastructure and Diagnostics Database
-- ============================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================
-- SWITCHES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS switches (
    switch_id TEXT PRIMARY KEY,
    switch_name TEXT NOT NULL,
    location TEXT NOT NULL,
    ip_address TEXT,
    model TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'maintenance')),
    max_ports INTEGER DEFAULT 48,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX idx_switches_location ON switches(location);
CREATE INDEX idx_switches_status ON switches(status);

-- ============================================
-- PORTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS ports (
    port_id TEXT PRIMARY KEY,
    switch_id TEXT NOT NULL,
    port_number INTEGER NOT NULL,
    customer_id TEXT,
    equipment_mac TEXT,
    status TEXT DEFAULT 'down' CHECK(status IN ('up', 'down', 'admin_down', 'error')),
    speed_mbps INTEGER,
    duplex TEXT CHECK(duplex IN ('full', 'half', 'auto')),
    vlan_id INTEGER,
    last_status_change TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (switch_id) REFERENCES switches(switch_id) ON DELETE CASCADE,
    UNIQUE(switch_id, port_number)
);

CREATE INDEX idx_ports_switch ON ports(switch_id);
CREATE INDEX idx_ports_customer ON ports(customer_id);
CREATE INDEX idx_ports_mac ON ports(equipment_mac);
CREATE INDEX idx_ports_status ON ports(status);

-- ============================================
-- IP ASSIGNMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS ip_assignments (
    assignment_id TEXT PRIMARY KEY,
    customer_id TEXT,
    ip_address TEXT NOT NULL UNIQUE,
    mac_address TEXT,
    assignment_type TEXT CHECK(assignment_type IN ('static', 'dhcp', 'pppoe')),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lease_expires TIMESTAMP,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'reserved', 'blacklisted')),
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX idx_ip_customer ON ip_assignments(customer_id);
CREATE INDEX idx_ip_address ON ip_assignments(ip_address);
CREATE INDEX idx_ip_mac ON ip_assignments(mac_address);
CREATE INDEX idx_ip_status ON ip_assignments(status);

-- ============================================
-- BANDWIDTH LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS bandwidth_logs (
    log_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    download_mbps DECIMAL(10,2),
    upload_mbps DECIMAL(10,2),
    latency_ms INTEGER,
    packet_loss_percent DECIMAL(5,2),
    jitter_ms DECIMAL(8,2),
    measurement_type TEXT CHECK(measurement_type IN ('speedtest', 'continuous', 'diagnostic')),
    notes TEXT
);

CREATE INDEX idx_bandwidth_customer ON bandwidth_logs(customer_id);
CREATE INDEX idx_bandwidth_timestamp ON bandwidth_logs(timestamp);

-- ============================================
-- AREA OUTAGES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS area_outages (
    outage_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    street TEXT,
    area_description TEXT,
    outage_type TEXT NOT NULL CHECK(outage_type IN ('internet', 'tv', 'phone', 'all')),
    severity TEXT DEFAULT 'major' CHECK(severity IN ('minor', 'major', 'critical')),
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'resolved', 'investigating')),
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    estimated_resolution TIMESTAMP,
    affected_customers INTEGER,
    description TEXT NOT NULL,
    root_cause TEXT,
    resolution_notes TEXT
);

CREATE INDEX idx_outages_city ON area_outages(city);
CREATE INDEX idx_outages_street ON area_outages(street);
CREATE INDEX idx_outages_status ON area_outages(status);
CREATE INDEX idx_outages_type ON area_outages(outage_type);
CREATE INDEX idx_outages_reported ON area_outages(reported_at);

-- ============================================
-- SIGNAL QUALITY TABLE (for TV/Cable)
-- ============================================
CREATE TABLE IF NOT EXISTS signal_quality (
    quality_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signal_strength_dbm INTEGER,
    snr_db DECIMAL(5,2),
    ber DECIMAL(10,8),
    mer_db DECIMAL(5,2),
    status TEXT CHECK(status IN ('excellent', 'good', 'fair', 'poor', 'critical')),
    channel_issues TEXT,
    notes TEXT
);

CREATE INDEX idx_signal_customer ON signal_quality(customer_id);
CREATE INDEX idx_signal_timestamp ON signal_quality(timestamp);
CREATE INDEX idx_signal_status ON signal_quality(status);

-- ============================================
-- NETWORK EVENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS network_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK(event_type IN ('port_down', 'port_up', 'high_latency', 'packet_loss', 'bandwidth_exceeded', 'security_alert')),
    severity TEXT DEFAULT 'info' CHECK(severity IN ('info', 'warning', 'error', 'critical')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    switch_id TEXT,
    port_id TEXT,
    customer_id TEXT,
    description TEXT NOT NULL,
    details TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    FOREIGN KEY (switch_id) REFERENCES switches(switch_id) ON DELETE SET NULL,
    FOREIGN KEY (port_id) REFERENCES ports(port_id) ON DELETE SET NULL
);

CREATE INDEX idx_events_type ON network_events(event_type);
CREATE INDEX idx_events_severity ON network_events(severity);
CREATE INDEX idx_events_timestamp ON network_events(timestamp);
CREATE INDEX idx_events_customer ON network_events(customer_id);
CREATE INDEX idx_events_resolved ON network_events(resolved);

-- ============================================
-- PING TESTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS ping_tests (
    test_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    target_ip TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    packets_sent INTEGER DEFAULT 4,
    packets_received INTEGER,
    packet_loss_percent DECIMAL(5,2),
    min_latency_ms DECIMAL(8,2),
    avg_latency_ms DECIMAL(8,2),
    max_latency_ms DECIMAL(8,2),
    jitter_ms DECIMAL(8,2),
    test_result TEXT CHECK(test_result IN ('success', 'partial', 'failed', 'timeout'))
);

CREATE INDEX idx_ping_customer ON ping_tests(customer_id);
CREATE INDEX idx_ping_timestamp ON ping_tests(timestamp);

-- ============================================
-- TRACEROUTE LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS traceroute_logs (
    traceroute_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    destination TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hops_data TEXT,
    total_hops INTEGER,
    success BOOLEAN,
    notes TEXT
);

CREATE INDEX idx_traceroute_customer ON traceroute_logs(customer_id);
CREATE INDEX idx_traceroute_timestamp ON traceroute_logs(timestamp);

-- ============================================
-- VIEWS
-- ============================================

-- View: Port status summary by switch
CREATE VIEW IF NOT EXISTS port_status_summary AS
SELECT 
    s.switch_id,
    s.switch_name,
    s.location,
    COUNT(p.port_id) as total_ports,
    COUNT(CASE WHEN p.status = 'up' THEN 1 END) as ports_up,
    COUNT(CASE WHEN p.status = 'down' THEN 1 END) as ports_down,
    COUNT(CASE WHEN p.customer_id IS NOT NULL THEN 1 END) as ports_assigned
FROM switches s
LEFT JOIN ports p ON s.switch_id = p.switch_id
GROUP BY s.switch_id;

-- View: Active outages by area
CREATE VIEW IF NOT EXISTS active_outages_by_area AS
SELECT 
    city,
    street,
    outage_type,
    severity,
    COUNT(*) as outage_count,
    SUM(affected_customers) as total_affected,
    MIN(reported_at) as first_reported,
    MAX(estimated_resolution) as latest_eta
FROM area_outages
WHERE status = 'active'
GROUP BY city, street, outage_type;

-- View: Customer network health
CREATE VIEW IF NOT EXISTS customer_network_health AS
SELECT 
    bl.customer_id,
    AVG(bl.download_mbps) as avg_download_mbps,
    AVG(bl.upload_mbps) as avg_upload_mbps,
    AVG(bl.latency_ms) as avg_latency_ms,
    AVG(bl.packet_loss_percent) as avg_packet_loss,
    COUNT(DISTINCT DATE(bl.timestamp)) as measurement_days,
    MAX(bl.timestamp) as last_measurement
FROM bandwidth_logs bl
WHERE bl.timestamp >= datetime('now', '-30 days')
GROUP BY bl.customer_id;