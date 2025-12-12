-- ============================================
-- Demo Equipment - Routers and TV Decoders
-- ============================================

-- Routers
INSERT INTO customer_equipment (equipment_id, customer_id, equipment_type, model, serial_number, mac_address, installed_date, status, notes) VALUES
('EQ001', 'CUST001', 'router', 'TP-Link Archer C6', 'TPL-C6-001234', '00:1A:2B:3C:4D:01', '2023-03-15', 'active', 'Happy path'),
('EQ002', 'CUST002', 'router', 'TP-Link Archer C80', 'TPL-C80-001235', '00:1A:2B:3C:4D:02', '2023-04-20', 'active', 'Outage area'),
('EQ003', 'CUST003', 'router', 'TP-Link Archer AX10', 'TPL-AX10-001236', '00:1A:2B:3C:4D:03', '2023-05-10', 'active', 'Peak hours'),
('EQ004', 'CUST004', 'router', 'MikroTik hAP ac2', 'MT-HAP2-001001', '00:1A:2B:3C:4D:04', '2023-06-05', 'active', 'Port down scenario'),
('EQ005', 'CUST005', 'router', 'TP-Link Archer C6', 'TPL-C6-001237', '00:1A:2B:3C:4D:05', '2023-07-12', 'active', 'TV customer'),
('EQ006', 'CUST006', 'router', 'MikroTik RB750Gr3', 'MT-RB750-001002', '00:1A:2B:3C:4D:06', '2023-08-18', 'active', 'No IP'),
('EQ007', 'CUST007', 'router', 'TP-Link Archer C80', 'TPL-C80-001238', '00:1A:2B:3C:4D:07', '2023-09-22', 'active', 'Suspended'),
('EQ008', 'CUST008', 'router', 'Unknown', NULL, '00:1A:2B:3C:4D:08', '2023-10-30', 'active', 'Intermittent - own router'),
('EQ009', 'CUST009', 'router', 'TP-Link Archer AX10', 'TPL-AX10-001239', '00:1A:2B:3C:4D:09', '2023-11-14', 'active', 'All OK'),
('EQ010', 'CUST010', 'router', 'MikroTik hAP ac2', 'MT-HAP2-001003', '00:1A:2B:3C:4D:10', '2023-12-08', 'active', 'All OK TV');

-- TV Decoders (only for TV customers)
INSERT INTO customer_equipment (equipment_id, customer_id, equipment_type, model, serial_number, mac_address, installed_date, status) VALUES
('EQ105', 'CUST005', 'decoder', 'MAG 322', 'MAG322-00105', '00:5A:6B:7C:8D:05', '2023-07-12', 'active'),
('EQ110', 'CUST010', 'decoder', 'MAG 410', 'MAG410-00110', '00:5A:6B:7C:8D:10', '2023-12-08', 'active');