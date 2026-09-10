-- SIMILAR STREETS (NLU wave, 2026-09-10): fuzzy-ambiguous street pairs for
-- the LETTERS-round voice tests. Each pair shares a prefix with a base
-- street, so the registry genuinely has several close candidates:
--   Tilžės  ~ Tilvyčio  (prefix TIL)
--   Dainų   ~ Dainavos  (+ Dailės from the demo slice - a D-triple)
--   Vilniaus ~ Vilties  (prefix VIL)
-- One healthy customer on each, so identification completes normally.

INSERT INTO streets (street_id, city, street_name, street_type, district) VALUES
('STR301', 'Šiauliai', 'Tilvyčio', 'g.', NULL),
('STR302', 'Šiauliai', 'Dainavos', 'g.', NULL),
('STR303', 'Šiauliai', 'Vilties',  'g.', NULL);

INSERT INTO customers (customer_id, first_name, last_name, phone, email, account_code, status, notes) VALUES
('CUST301', 'Rasa',  'Kairienė',   '+37060030301', 'rasa.kairiene@gmail.com',   'AB-30301', 'active', 'DEMO PR: panašios gatvės (Tilvyčio)'),
('CUST302', 'Jonas', 'Dainauskas', '+37060030302', 'jonas.dainauskas@gmail.com','AB-30302', 'active', 'DEMO PR: panašios gatvės (Dainavos)'),
('CUST303', 'Eglė',  'Vilkienė',   '+37060030303', 'egle.vilkiene@gmail.com',   'AB-30303', 'active', 'DEMO PR: panašios gatvės (Vilties)');

INSERT INTO addresses (address_id, customer_id, city, street, house_number, apartment_number, full_address, is_primary) VALUES
('ADDR301', 'CUST301', 'Šiauliai', 'Tilvyčio g.', '8',  NULL, 'Šiauliai, Tilvyčio g. 8',  TRUE),
('ADDR302', 'CUST302', 'Šiauliai', 'Dainavos g.', '4',  NULL, 'Šiauliai, Dainavos g. 4',  TRUE),
('ADDR303', 'CUST303', 'Šiauliai', 'Vilties g.',  '15', NULL, 'Šiauliai, Vilties g. 15',  TRUE);

INSERT INTO service_plans (plan_id, customer_id, service_type, plan_name, speed_mbps, price, status, activation_date, suspension_reason) VALUES
('PLAN301', 'CUST301', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2024-05-10', NULL),
('PLAN302', 'CUST302', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2024-06-12', NULL),
('PLAN303', 'CUST303', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active', '2024-07-15', NULL);

INSERT INTO customer_equipment (equipment_id, customer_id, equipment_type, model, serial_number, mac_address, installed_date, status, notes) VALUES
('EQ301', 'CUST301', 'router', 'TP-Link Archer C6', 'TPL-C6-003301', '00:1A:2B:3C:4F:01', '2024-05-10', 'active', 'DEMO PR'),
('EQ302', 'CUST302', 'router', 'TP-Link Archer C6', 'TPL-C6-003302', '00:1A:2B:3C:4F:02', '2024-06-12', 'active', 'DEMO PR'),
('EQ303', 'CUST303', 'router', 'TP-Link Archer C6', 'TPL-C6-003303', '00:1A:2B:3C:4F:03', '2024-07-15', 'active', 'DEMO PR');

INSERT INTO ports (port_id, switch_id, port_number, customer_id, equipment_mac, status, speed_mbps, duplex, vlan_id, observed_mac, crc_error_rate, dhcp_status, notes) VALUES
('PORT301', 'SW101', 31, 'CUST301', '00:1A:2B:3C:4F:01', 'up', 100, 'full', 20, '00:1A:2B:3C:4F:01', 0.0, 'ok', 'DEMO PR: sveika linija'),
('PORT302', 'SW101', 32, 'CUST302', '00:1A:2B:3C:4F:02', 'up', 100, 'full', 20, '00:1A:2B:3C:4F:02', 0.0, 'ok', 'DEMO PR: sveika linija'),
('PORT303', 'SW101', 33, 'CUST303', '00:1A:2B:3C:4F:03', 'up', 300, 'full', 20, '00:1A:2B:3C:4F:03', 0.0, 'ok', 'DEMO PR: sveika linija');

INSERT INTO ip_assignments (assignment_id, customer_id, ip_address, mac_address, assignment_type, status, notes) VALUES
('IP301', 'CUST301', '192.168.3.101', '00:1A:2B:3C:4F:01', 'dhcp', 'active', 'DEMO PR'),
('IP302', 'CUST302', '192.168.3.102', '00:1A:2B:3C:4F:02', 'dhcp', 'active', 'DEMO PR'),
('IP303', 'CUST303', '192.168.3.103', '00:1A:2B:3C:4F:03', 'dhcp', 'active', 'DEMO PR');
