-- NETWORK-SIDE FAULTS (demo set, Andrius 2026-09-11): the cable/line cases.
--   NT1 CUST305: link UP, correct MAC, HIGH CRC -> crc_errors (damaged/loose
--       cable; one reseat check with the caller, then a technician ticket).
--   NT2 CUST306 (+ neighbour CUST307 on the same ACTIVE switch, both ports
--       DOWN, no registered outage) -> node_fault_unregistered: e.g. the
--       stairwell cable damaged - several flats down at once; provider-side
--       ticket right away, no client actions.

INSERT INTO customers (customer_id, first_name, last_name, phone, email, account_code, status, notes) VALUES
('CUST305', 'Marius', 'Petrulis',  '+37060030305', 'marius.petrulis@gmail.com',  'AB-30305', 'active', 'DEMO NT1: CRC klaidos (pazeistas kabelis)'),
('CUST306', 'Lina',   'Urbonienė', '+37060030306', 'lina.urboniene@gmail.com',   'AB-30306', 'active', 'DEMO NT2: mazgo gedimas be avarijos'),
('CUST307', 'Petras', 'Urbonas',   '+37060030307', 'petras.urbonas@gmail.com',   'AB-30307', 'active', 'DEMO NT2: kaimynas (portas irgi down)');

INSERT INTO addresses (address_id, customer_id, city, street, house_number, apartment_number, full_address, is_primary) VALUES
('ADDR305', 'CUST305', 'Šiauliai', 'Tilžės g.',  '62', NULL, 'Šiauliai, Tilžės g. 62',    TRUE),
('ADDR306', 'CUST306', 'Šiauliai', 'Vilties g.', '17', '2',  'Šiauliai, Vilties g. 17-2', TRUE),
('ADDR307', 'CUST307', 'Šiauliai', 'Vilties g.', '17', '5',  'Šiauliai, Vilties g. 17-5', TRUE);

INSERT INTO service_plans (plan_id, customer_id, service_type, plan_name, speed_mbps, price, status, activation_date, suspension_reason) VALUES
('PLAN305', 'CUST305', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active', '2024-03-08', NULL),
('PLAN306', 'CUST306', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2024-04-11', NULL),
('PLAN307', 'CUST307', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2024-04-11', NULL);

INSERT INTO customer_equipment (equipment_id, customer_id, equipment_type, model, serial_number, mac_address, installed_date, status, notes) VALUES
('EQ305', 'CUST305', 'router', 'TP-Link Archer C6', 'TPL-C6-003305', '00:1A:2B:3C:4F:05', '2024-03-08', 'active', 'DEMO NT1'),
('EQ306', 'CUST306', 'router', 'TP-Link Archer C6', 'TPL-C6-003306', '00:1A:2B:3C:4F:06', '2024-04-11', 'active', 'DEMO NT2'),
('EQ307', 'CUST307', 'router', 'TP-Link Archer C6', 'TPL-C6-003307', '00:1A:2B:3C:4F:07', '2024-04-11', 'active', 'DEMO NT2');

-- NT2 lives on its own ACTIVE switch so the neighbour correlation is clean:
-- both ports down, zero up, no outage registered on this node.
INSERT INTO switches (switch_id, switch_name, location, ip_address, model, status, max_ports) VALUES
('SW305', 'Šiauliai-Vilties-SW05', 'Šiauliai, Vilties g. kvartalas', '10.10.5.1', 'Cisco Catalyst 2960-24TT', 'active', 24);

INSERT INTO ports (port_id, switch_id, port_number, customer_id, equipment_mac, status, speed_mbps, duplex, vlan_id, observed_mac, crc_error_rate, dhcp_status, notes) VALUES
('PORT305', 'SW101', 34, 'CUST305', '00:1A:2B:3C:4F:05', 'up',   300,  'full', 20, '00:1A:2B:3C:4F:05', 27.5, 'ok', 'DEMO NT1: aukstas CRC - pazeistas/atsilaisvines kabelis'),
('PORT306', 'SW305', 1,  'CUST306', '00:1A:2B:3C:4F:06', 'down', NULL, NULL,   50, NULL,                NULL, NULL, 'DEMO NT2: link DOWN, kaimynas irgi down, avarijos NERA'),
('PORT307', 'SW305', 2,  'CUST307', '00:1A:2B:3C:4F:07', 'down', NULL, NULL,   50, NULL,                NULL, NULL, 'DEMO NT2: kaimyno portas down');

INSERT INTO ip_assignments (assignment_id, customer_id, ip_address, mac_address, assignment_type, status, notes) VALUES
('IP305', 'CUST305', '192.168.3.105', '00:1A:2B:3C:4F:05', 'dhcp', 'active', 'DEMO NT1: lease galioja, bet linija klaidinga');
