-- ============================================
-- Demo Addresses - matching customer scenarios
-- ============================================

-- Street references
INSERT INTO streets (street_id, city, street_name, street_type) VALUES
('STR001', 'Šiauliai', 'Tilžės', 'g.'),
('STR002', 'Šiauliai', 'Dainų', 'g.'),
('STR003', 'Šiauliai', 'Vilniaus', 'g.');

-- Customer addresses
INSERT INTO addresses (address_id, customer_id, city, street, house_number, apartment_number, full_address, is_primary) VALUES
('ADDR001', 'CUST001', 'Šiauliai', 'Tilžės g.', '12', '5', 'Šiauliai, Tilžės g. 12-5', TRUE),
('ADDR002', 'CUST002', 'Šiauliai', 'Dainų g.', '5', '7', 'Šiauliai, Dainų g. 5-7', TRUE),      -- Outage area!
('ADDR003', 'CUST003', 'Šiauliai', 'Tilžės g.', '14', '3', 'Šiauliai, Tilžės g. 14-3', TRUE),
('ADDR004', 'CUST004', 'Šiauliai', 'Vilniaus g.', '25', '1', 'Šiauliai, Vilniaus g. 25-1', TRUE),
('ADDR005', 'CUST005', 'Šiauliai', 'Tilžės g.', '16', NULL, 'Šiauliai, Tilžės g. 16', TRUE),   -- House (TV)
('ADDR006', 'CUST006', 'Šiauliai', 'Vilniaus g.', '27', '5', 'Šiauliai, Vilniaus g. 27-5', TRUE),
('ADDR007', 'CUST007', 'Šiauliai', 'Dainų g.', '9', NULL, 'Šiauliai, Dainų g. 9', TRUE),
('ADDR008', 'CUST008', 'Šiauliai', 'Tilžės g.', '20', '8', 'Šiauliai, Tilžės g. 20-8', TRUE),
('ADDR009', 'CUST009', 'Šiauliai', 'Vilniaus g.', '29', NULL, 'Šiauliai, Vilniaus g. 29', TRUE),
('ADDR010', 'CUST010', 'Šiauliai', 'Tilžės g.', '22', NULL, 'Šiauliai, Tilžės g. 22', TRUE);