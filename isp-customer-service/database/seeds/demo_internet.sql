-- ============================================================================
-- "Neveikia internetas" demo slice — seed world (Phase 2.5, step 1)
--
-- Design docs: chatbot_core/docs/demo_plan_neveikia_internetas.md (S1-S5),
--              chatbot_core/docs/kliento_identifikacijos_dizainas.md §8.1
--              (approved locations + voice edge addresses).
--
-- ADDITIVE ONLY: CUST001-010 / SW001 / OUT001 from the original seeds are the
-- regression-suite world and are not modified here (one UPDATE adds the new
-- nullable switch_id link to OUT001 — no existing column changes).
--
-- Each customer carries a KNOWN telemetry state so diagnose_connection
-- returns a deterministic verdict. Telemetry lives in the NETWORK domain
-- (ports.observed_mac / crc_error_rate / dhcp_status, area_outages.switch_id);
-- in production the same signals come from network systems via the adapter.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- STREETS (reference base for hierarchical identification)
-- street_name without the 'g.' suffix (existing convention, STR001-003).
-- district: NULL = city proper; 'Šiaulių r.' = village in the district.
-- ----------------------------------------------------------------------------
INSERT INTO streets (street_id, city, street_name, street_type, district) VALUES
('STR101', 'Šiauliai',   'Dailės',                 'g.', NULL),          -- fuzzy pair with Dainų
('STR102', 'Šiauliai',   'Žemaitės',               'g.', NULL),          -- street named after a surname
('STR103', 'Šiauliai',   'S. Dariaus ir S. Girėno', 'g.', NULL),         -- long compound name with initials
('STR104', 'Ginkūnai',   'Žeimių',                 'g.', 'Šiaulių r.'),  -- street-level recovery target
('STR105', 'Bubiai',     'Aušros',                 'g.', 'Šiaulių r.'),  -- village-level disambiguation
('STR106', 'Vinkšnėnai', 'Sodo',                   'g.', 'Šiaulių r.');  -- house number with a letter (122F)

-- ----------------------------------------------------------------------------
-- CUSTOMERS (CUST101-111) — scenario states + identification edge cases
-- All carry an account_code (abonento kodas) — the fastest lookup path.
-- ----------------------------------------------------------------------------
INSERT INTO customers (customer_id, first_name, last_name, phone, email, account_code, status, notes) VALUES
-- S1 (B1): service suspended for debt — fast path, inform, no ticket
('CUST101', 'Tomas',     'Vaitkus',      '+37060020101', 'tomas.vaitkus@gmail.com',      'AB-10101', 'suspended', 'DEMO S1: skola - paslauga sustabdyta'),
-- S2 (B2): mass outage on Dainų g. (reuses active OUT001) — inform + ETA, no ticket
('CUST102', 'Rasa',      'Jankauskienė', '+37060020102', 'rasa.jankauskiene@gmail.com',  'AB-10102', 'active',    'DEMO S2: masinė avarija Dainų g.'),
-- S3 (B3): individual provider fault — switch unreachable, NO registered outage -> ticket
('CUST103', 'Egidijus',  'Norkus',       '+37060020103', 'egidijus.norkus@gmail.com',    'AB-10103', 'active',    'DEMO S3: switch nepasiekiamas, avarija neregistruota'),
-- S4 (B4/B5): port link DOWN, neighbours UP -> customer side, instruct (power/cable)
('CUST104', 'Vilma',     'Stankūnienė',  '+37060020104', 'vilma.stankuniene@gmail.com',  'AB-10104', 'active',    'DEMO S4: link DOWN, kaimynai UP - maitinimas/laidas'),
-- S5a (B6): customer replaced the router — foreign MAC observed on the port
('CUST105', 'Mantas',    'Urbonas',      '+37060020105', 'mantas.urbonas@gmail.com',     'AB-10105', 'active',    'DEMO S5a: naujas routeris - svetimas MAC'),
-- S5b (B6): factory reset — link UP, correct MAC, but no DHCP requests
('CUST106', 'Greta',     'Šimkutė',      '+37060020106', 'greta.simkute@gmail.com',      'AB-10106', 'active',    'DEMO S5b: factory reset - DHCP be užklausų'),
-- Identification pair: same house (Dainų g. 7, no flats), two contracts ->
-- surname disambiguation. NOTE: Dainų g. is inside the OUT001 outage area —
-- consistent world: if diagnosis runs, the whole street IS out.
('CUST107', 'Darius',    'Petraitis',    '+37060020107', 'darius.petraitis@gmail.com',   'AB-10107', 'active',    'DEMO ID: Dainų g. 7 pora (pavardės disambiguacija)'),
('CUST108', 'Saulius',   'Kazlauskas',   '+37060020108', 'saulius.kazlauskas@gmail.com', 'AB-10108', 'active',    'DEMO ID: Dainų g. 7 pora (pavardės disambiguacija)'),
-- Street-level recovery: "Šiauliai, Žeimių g." -> not in Šiauliai -> Šiaulių r., Ginkūnai
('CUST109', 'Aldona',    'Žukauskienė',  '+37060020109', 'aldona.zukauskiene@gmail.com', 'AB-10109', 'active',    'DEMO ID: Žeimių g. recovery (Ginkūnai)'),
-- Village-level disambiguation: "Šiaulių rajonas" alone -> which village?
('CUST110', 'Kęstutis',  'Balčiūnas',    '+37060020110', 'kestutis.balciunas@gmail.com', 'AB-10110', 'active',    'DEMO ID: Aušros g. 8 (Bubiai - kurio kaimo?)'),
-- House number with a letter: "šimtas dvidešimt du ef" (STT robustness)
('CUST111', 'Irena',     'Mockuvienė',   '+37060020111', 'irena.mockuviene@gmail.com',   'AB-10111', 'active',    'DEMO ID: Sodo g. 122F (namo nr. su raide)');

-- ----------------------------------------------------------------------------
-- ADDRESSES
-- ----------------------------------------------------------------------------
INSERT INTO addresses (address_id, customer_id, city, street, house_number, apartment_number, full_address, is_primary) VALUES
('ADDR101', 'CUST101', 'Šiauliai',   'Tilžės g.',                 '60',   '3',  'Šiauliai, Tilžės g. 60-3', TRUE),
('ADDR102', 'CUST102', 'Šiauliai',   'Dainų g.',                  '5',    '5',  'Šiauliai, Dainų g. 5-5', TRUE),    -- §7.2 example address; outage area
('ADDR103', 'CUST103', 'Šiauliai',   'Žemaitės g.',               '14',   '2',  'Šiauliai, Žemaitės g. 14-2', TRUE),
('ADDR104', 'CUST104', 'Šiauliai',   'S. Dariaus ir S. Girėno g.', '25',  '45', 'Šiauliai, S. Dariaus ir S. Girėno g. 25-45', TRUE),
('ADDR105', 'CUST105', 'Šiauliai',   'Tilžės g.',                 '60',   '7',  'Šiauliai, Tilžės g. 60-7', TRUE),
('ADDR106', 'CUST106', 'Šiauliai',   'Vilniaus g.',               '31',   '2',  'Šiauliai, Vilniaus g. 31-2', TRUE),
('ADDR107', 'CUST107', 'Šiauliai',   'Dainų g.',                  '7',    NULL, 'Šiauliai, Dainų g. 7', TRUE),      -- two contracts, no flats
('ADDR108', 'CUST108', 'Šiauliai',   'Dainų g.',                  '7',    NULL, 'Šiauliai, Dainų g. 7', TRUE),
('ADDR109', 'CUST109', 'Ginkūnai',   'Žeimių g.',                 '12',   '6',  'Šiaulių r., Ginkūnų k., Žeimių g. 12-6', TRUE),
('ADDR110', 'CUST110', 'Bubiai',     'Aušros g.',                 '8',    NULL, 'Šiaulių r., Bubių k., Aušros g. 8', TRUE),
('ADDR111', 'CUST111', 'Vinkšnėnai', 'Sodo g.',                   '122F', NULL, 'Šiaulių r., Vinkšnėnų k., Sodo g. 122F', TRUE);

-- ----------------------------------------------------------------------------
-- SERVICE PLANS — internet for everyone; S1 suspended for debt
-- ----------------------------------------------------------------------------
INSERT INTO service_plans (plan_id, customer_id, service_type, plan_name, speed_mbps, price, status, activation_date, suspension_reason) VALUES
('PLAN101', 'CUST101', 'internet', 'Internet 300 Mbps', 300, 24.99, 'suspended', '2024-02-10', 'Neapmokėta sąskaita - 30+ d. skola'),
('PLAN102', 'CUST102', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-03-05', NULL),
('PLAN103', 'CUST103', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-04-12', NULL),
('PLAN104', 'CUST104', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active',    '2024-05-20', NULL),
('PLAN105', 'CUST105', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-06-15', NULL),
('PLAN106', 'CUST106', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-07-01', NULL),
('PLAN107', 'CUST107', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-08-09', NULL),
('PLAN108', 'CUST108', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active',    '2024-09-17', NULL),
('PLAN109', 'CUST109', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-10-23', NULL),
('PLAN110', 'CUST110', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-11-04', NULL),
('PLAN111', 'CUST111', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active',    '2024-12-11', NULL);

-- ----------------------------------------------------------------------------
-- EQUIPMENT — registered routers (CRM view of the world).
-- S5a's registered MAC is ...:05 — the port, however, OBSERVES a foreign MAC.
-- ----------------------------------------------------------------------------
INSERT INTO customer_equipment (equipment_id, customer_id, equipment_type, model, serial_number, mac_address, installed_date, status, notes) VALUES
('EQ201', 'CUST101', 'router', 'TP-Link Archer C6',  'TPL-C6-002101',  '00:1A:2B:3C:4E:01', '2024-02-10', 'active', 'DEMO S1'),
('EQ202', 'CUST102', 'router', 'TP-Link Archer C80', 'TPL-C80-002102', '00:1A:2B:3C:4E:02', '2024-03-05', 'active', 'DEMO S2'),
('EQ203', 'CUST103', 'router', 'MikroTik hAP ac2',   'MT-HAP2-002103', '00:1A:2B:3C:4E:03', '2024-04-12', 'active', 'DEMO S3'),
('EQ204', 'CUST104', 'router', 'TP-Link Archer AX10','TPL-AX10-002104','00:1A:2B:3C:4E:04', '2024-05-20', 'active', 'DEMO S4'),
('EQ205', 'CUST105', 'router', 'TP-Link Archer C6',  'TPL-C6-002105',  '00:1A:2B:3C:4E:05', '2024-06-15', 'active', 'DEMO S5a: registruotas SENAS routeris - klientas pasikeitė įrangą'),
('EQ206', 'CUST106', 'router', 'TP-Link Archer C80', 'TPL-C80-002106', '00:1A:2B:3C:4E:06', '2024-07-01', 'active', 'DEMO S5b'),
('EQ207', 'CUST107', 'router', 'TP-Link Archer C6',  'TPL-C6-002107',  '00:1A:2B:3C:4E:07', '2024-08-09', 'active', 'DEMO ID'),
('EQ208', 'CUST108', 'router', 'MikroTik hAP ac2',   'MT-HAP2-002108', '00:1A:2B:3C:4E:08', '2024-09-17', 'active', 'DEMO ID'),
('EQ209', 'CUST109', 'router', 'TP-Link Archer C6',  'TPL-C6-002109',  '00:1A:2B:3C:4E:09', '2024-10-23', 'active', 'DEMO ID'),
('EQ210', 'CUST110', 'router', 'TP-Link Archer C80', 'TPL-C80-002110', '00:1A:2B:3C:4E:10', '2024-11-04', 'active', 'DEMO ID'),
('EQ211', 'CUST111', 'router', 'TP-Link Archer AX10','TPL-AX10-002111','00:1A:2B:3C:4E:11', '2024-12-11', 'active', 'DEMO ID');

-- ----------------------------------------------------------------------------
-- SWITCHES
-- SW101: healthy node — most demo customers; S4's "neighbours UP" lives here.
-- SW102: UNREACHABLE node (S3) — only this customer's area, no outage row.
-- SW103: Šiaulių r. village node — Ginkūnai / Bubiai / Vinkšnėnai, all healthy.
-- (CUST102/S2 sits on the existing SW001 — the Dainų area switch tied to OUT001.)
-- ----------------------------------------------------------------------------
INSERT INTO switches (switch_id, switch_name, location, ip_address, model, status, max_ports) VALUES
('SW101', 'Šiauliai-South-SW02',   'Šiauliai, Tilžės/Vilniaus pietinis rajonas', '10.10.2.1', 'Cisco Catalyst 2960-48TT', 'active',   48),
('SW102', 'Šiauliai-Žemaitės-SW03','Šiauliai, Žemaitės rajonas',                 '10.10.3.1', 'Cisco Catalyst 2960-24TT', 'inactive', 24),
('SW103', 'Šiaulių-r-Ginkūnai-SW04','Šiaulių r., Ginkūnai/Bubiai/Vinkšnėnai',    '10.10.4.1', 'Cisco Catalyst 2960-24TT', 'active',   24);

-- Link the existing Dainų g. outage (OUT001) to its network node so the
-- verdict can correlate incident <-> switch (B2 vs B3 split). Additive: only
-- fills the new nullable column on the existing row.
UPDATE area_outages SET switch_id = 'SW001' WHERE outage_id = 'OUT001';

-- ----------------------------------------------------------------------------
-- PORTS — the per-scenario telemetry states (verdict signal source)
--
--   S1  PORT101: everything healthy (problem is billing, not network)
--   S2  PORT102: healthy port on SW001 (problem is the area outage)
--   S3  PORT103: switch SW102 unreachable -> port state stale/unknown
--   S4  PORT104: link DOWN, neighbours (ports 1,3,4,5,6 on SW101) UP -> local
--   S5a PORT105: link UP, observed_mac != registered (new router)
--   S5b PORT106: link UP, observed_mac correct, dhcp_status no_requests
-- ----------------------------------------------------------------------------
INSERT INTO ports (port_id, switch_id, port_number, customer_id, equipment_mac, status, speed_mbps, duplex, vlan_id, observed_mac, crc_error_rate, dhcp_status, notes) VALUES
('PORT101', 'SW101', 1,  'CUST101', '00:1A:2B:3C:4E:01', 'up',   300, 'full', 20, '00:1A:2B:3C:4E:01', 0.0,  'ok',          'DEMO S1: tinklas sveikas, blokas billing lygyje'),
('PORT102', 'SW001', 11, 'CUST102', '00:1A:2B:3C:4E:02', 'up',   100, 'full', 10, '00:1A:2B:3C:4E:02', 0.0,  'ok',          'DEMO S2: portas sveikas, gedimas - avarija (OUT001)'),
('PORT103', 'SW102', 1,  'CUST103', '00:1A:2B:3C:4E:03', 'down', NULL, NULL,  30, NULL,                NULL, NULL,          'DEMO S3: switch nepasiekiamas - busena pasenusi'),
('PORT104', 'SW101', 2,  'CUST104', '00:1A:2B:3C:4E:04', 'down', NULL, NULL,  20, NULL,                NULL, NULL,          'DEMO S4: link DOWN, kaimynai UP'),
('PORT105', 'SW101', 3,  'CUST105', '00:1A:2B:3C:4E:05', 'up',   100, 'full', 20, '00:E0:4C:AA:BB:05', 0.0,  'no_requests', 'DEMO S5a: matomas SVETIMAS MAC (naujas routeris)'),
('PORT106', 'SW101', 4,  'CUST106', '00:1A:2B:3C:4E:06', 'up',   100, 'full', 20, '00:1A:2B:3C:4E:06', 0.0,  'no_requests', 'DEMO S5b: MAC teisingas, DHCP uzklausu nera (factory reset)'),
('PORT107', 'SW101', 5,  'CUST107', '00:1A:2B:3C:4E:07', 'up',   100, 'full', 20, '00:1A:2B:3C:4E:07', 0.0,  'ok',          'DEMO ID: sveikas (S4 kaimynas)'),
('PORT108', 'SW101', 6,  'CUST108', '00:1A:2B:3C:4E:08', 'up',   300, 'full', 20, '00:1A:2B:3C:4E:08', 0.0,  'ok',          'DEMO ID: sveikas (S4 kaimynas)'),
('PORT109', 'SW103', 1,  'CUST109', '00:1A:2B:3C:4E:09', 'up',   100, 'full', 40, '00:1A:2B:3C:4E:09', 0.0,  'ok',          'DEMO ID: Ginkunai - sveikas'),
('PORT110', 'SW103', 2,  'CUST110', '00:1A:2B:3C:4E:10', 'up',   100, 'full', 40, '00:1A:2B:3C:4E:10', 0.0,  'ok',          'DEMO ID: Bubiai - sveikas'),
('PORT111', 'SW103', 3,  'CUST111', '00:1A:2B:3C:4E:11', 'up',   100, 'full', 40, '00:1A:2B:3C:4E:11', 0.0,  'ok',          'DEMO ID: Vinksnenai - sveikas');

-- ----------------------------------------------------------------------------
-- IP ASSIGNMENTS — coherent with port states
-- S3/S4: no row (link down / node unreachable -> no lease visible).
-- S5a: the OLD router's lease expired; the new (foreign-MAC) device has none.
-- S5b: lease expired after the factory reset (router no longer requests).
-- ----------------------------------------------------------------------------
INSERT INTO ip_assignments (assignment_id, customer_id, ip_address, mac_address, assignment_type, status, notes) VALUES
('IP101', 'CUST101', '192.168.2.101', '00:1A:2B:3C:4E:01', 'dhcp', 'active',  'DEMO S1'),
('IP102', 'CUST102', '192.168.2.102', '00:1A:2B:3C:4E:02', 'dhcp', 'active',  'DEMO S2'),
('IP105', 'CUST105', '192.168.2.105', '00:1A:2B:3C:4E:05', 'dhcp', 'expired', 'DEMO S5a: seno routerio lease'),
('IP106', 'CUST106', '192.168.2.106', '00:1A:2B:3C:4E:06', 'dhcp', 'expired', 'DEMO S5b: lease pasibaiges po factory reset'),
('IP107', 'CUST107', '192.168.2.107', '00:1A:2B:3C:4E:07', 'dhcp', 'active',  'DEMO ID'),
('IP108', 'CUST108', '192.168.2.108', '00:1A:2B:3C:4E:08', 'dhcp', 'active',  'DEMO ID'),
('IP109', 'CUST109', '192.168.2.109', '00:1A:2B:3C:4E:09', 'dhcp', 'active',  'DEMO ID'),
('IP110', 'CUST110', '192.168.2.110', '00:1A:2B:3C:4E:10', 'dhcp', 'active',  'DEMO ID'),
('IP111', 'CUST111', '192.168.2.111', '00:1A:2B:3C:4E:11', 'dhcp', 'active',  'DEMO ID');
