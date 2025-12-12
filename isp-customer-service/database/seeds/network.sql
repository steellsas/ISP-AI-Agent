-- ============================================
-- Demo Network - switches, ports, IPs, outages
-- ============================================

-- Switches
INSERT INTO switches (switch_id, switch_name, location, ip_address, model, status, max_ports) VALUES
('SW001', 'Šiauliai-Central-SW01', 'Šiauliai, Tilžės/Dainų rajonas', '10.10.1.1', 'Cisco Catalyst 2960-48TT', 'active', 48);

-- Ports - various statuses for scenarios
INSERT INTO ports (port_id, switch_id, port_number, customer_id, equipment_mac, status, speed_mbps, duplex, vlan_id, notes) VALUES
-- CUST001: Happy path - port UP
('PORT001', 'SW001', 1, 'CUST001', '00:1A:2B:3C:4D:01', 'up', 100, 'full', 10, 'Happy path'),

-- CUST002: Outage area - port UP (problem is area outage)
('PORT002', 'SW001', 2, 'CUST002', '00:1A:2B:3C:4D:02', 'up', 100, 'full', 10, 'Outage area'),

-- CUST003: Slow peak - port UP
('PORT003', 'SW001', 3, 'CUST003', '00:1A:2B:3C:4D:03', 'up', 100, 'full', 10, 'Peak hours slow'),

-- CUST004: Port DOWN - needs technician!
('PORT004', 'SW001', 4, 'CUST004', '00:1A:2B:3C:4D:04', 'down', NULL, NULL, 10, 'Port down - escalation'),

-- CUST005: TV customer - port UP
('PORT005', 'SW001', 5, 'CUST005', '00:1A:2B:3C:4D:05', 'up', 100, 'full', 10, 'TV customer'),

-- CUST006: No IP - port UP but IP expired
('PORT006', 'SW001', 6, 'CUST006', '00:1A:2B:3C:4D:06', 'up', 100, 'full', 10, 'No IP assigned'),

-- CUST007: Suspended - port UP
('PORT007', 'SW001', 7, 'CUST007', '00:1A:2B:3C:4D:07', 'up', 100, 'full', 10, 'Suspended account'),

-- CUST008: Intermittent - port UP but has issues
('PORT008', 'SW001', 8, 'CUST008', '00:1A:2B:3C:4D:08', 'up', 100, 'full', 10, 'Intermittent connection'),

-- CUST009: All OK
('PORT009', 'SW001', 9, 'CUST009', '00:1A:2B:3C:4D:09', 'up', 100, 'full', 10, 'All OK'),

-- CUST010: All OK with TV
('PORT010', 'SW001', 10, 'CUST010', '00:1A:2B:3C:4D:10', 'up', 100, 'full', 10, 'All OK with TV');

-- IP Assignments - various statuses
INSERT INTO ip_assignments (assignment_id, customer_id, ip_address, mac_address, assignment_type, status, notes) VALUES
('IP001', 'CUST001', '192.168.1.101', '00:1A:2B:3C:4D:01', 'dhcp', 'active', 'Happy path'),
('IP002', 'CUST002', '192.168.1.102', '00:1A:2B:3C:4D:02', 'dhcp', 'active', 'Outage area'),
('IP003', 'CUST003', '192.168.1.103', '00:1A:2B:3C:4D:03', 'dhcp', 'active', 'Peak hours'),
-- CUST004: NO IP - port is down
('IP005', 'CUST005', '192.168.1.105', '00:1A:2B:3C:4D:05', 'dhcp', 'active', 'TV customer'),
-- CUST006: IP EXPIRED!
('IP006', 'CUST006', '192.168.1.106', '00:1A:2B:3C:4D:06', 'dhcp', 'expired', 'DHCP expired - no IP'),
('IP007', 'CUST007', '192.168.1.107', '00:1A:2B:3C:4D:07', 'dhcp', 'active', 'Suspended'),
('IP008', 'CUST008', '192.168.1.108', '00:1A:2B:3C:4D:08', 'dhcp', 'active', 'Intermittent'),
('IP009', 'CUST009', '192.168.1.109', '00:1A:2B:3C:4D:09', 'dhcp', 'active', 'All OK'),
('IP010', 'CUST010', '192.168.1.110', '00:1A:2B:3C:4D:10', 'dhcp', 'active', 'All OK TV');

-- ACTIVE Area Outage - affects CUST002 (Dainų g.)
INSERT INTO area_outages (outage_id, city, street, outage_type, severity, status, reported_at, estimated_resolution, affected_customers, description) VALUES
('OUT001', 'Šiauliai', 'Dainų g.', 'internet', 'major', 'active', datetime('now', '-2 hours'), datetime('now', '+2 hours'), 15, 'Fiber cable damaged during construction. Technicians on site.');

-- Bandwidth logs for CUST008 - intermittent with packet loss
INSERT INTO bandwidth_logs (log_id, customer_id, timestamp, download_mbps, upload_mbps, latency_ms, packet_loss_percent, measurement_type, notes) VALUES
('BW001', 'CUST008', datetime('now', '-1 hour'), 45.5, 8.2, 85, 12.5, 'diagnostic', 'High packet loss detected'),
('BW002', 'CUST008', datetime('now', '-30 minutes'), 38.2, 7.1, 120, 18.3, 'diagnostic', 'Intermittent issue');

-- Ping test for CUST008 - shows packet loss
INSERT INTO ping_tests (test_id, customer_id, target_ip, timestamp, packets_sent, packets_received, packet_loss_percent, avg_latency_ms, test_result) VALUES
('PING001', 'CUST008', '8.8.8.8', datetime('now', '-15 minutes'), 10, 7, 30.0, 95.5, 'partial');