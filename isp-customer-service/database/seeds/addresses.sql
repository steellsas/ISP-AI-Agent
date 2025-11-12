-- ============================================
-- Mock Address Data - Šiauliai city
-- Streets: Tilžės, Dainų, Lieporių, Vilniaus, Birutės, Gegužių
-- Mix of apartment buildings (30-45 apartments) and houses
-- ============================================

-- Insert street reference data for fuzzy matching
INSERT INTO streets (street_id, city, street_name, street_type) VALUES
('STR001', 'Šiauliai', 'Tilžės', 'g.'),
('STR002', 'Šiauliai', 'Dainų', 'g.'),
('STR003', 'Šiauliai', 'Lieporių', 'g.'),
('STR004', 'Šiauliai', 'Vilniaus', 'g.'),
('STR005', 'Šiauliai', 'Birutės', 'g.'),
('STR006', 'Šiauliai', 'Gegužių', 'g.');

-- Tilžės g. addresses (mix of apartments and houses)
INSERT INTO addresses (address_id, customer_id, city, street, house_number, apartment_number, full_address, is_primary) VALUES
('ADDR001', 'CUST001', 'Šiauliai', 'Tilžės g.', '12', '5', 'Šiauliai, Tilžės g. 12-5', TRUE),
('ADDR002', 'CUST002', 'Šiauliai', 'Tilžės g.', '12', '12', 'Šiauliai, Tilžės g. 12-12', TRUE),
('ADDR003', 'CUST003', 'Šiauliai', 'Tilžės g.', '12', '28', 'Šiauliai, Tilžės g. 12-28', TRUE),
('ADDR004', 'CUST004', 'Šiauliai', 'Tilžės g.', '14', '3', 'Šiauliai, Tilžės g. 14-3', TRUE),
('ADDR005', 'CUST005', 'Šiauliai', 'Tilžės g.', '14', '15', 'Šiauliai, Tilžės g. 14-15', TRUE),
('ADDR006', 'CUST006', 'Šiauliai', 'Tilžės g.', '16', NULL, 'Šiauliai, Tilžės g. 16', TRUE),
('ADDR007', 'CUST007', 'Šiauliai', 'Tilžės g.', '18', NULL, 'Šiauliai, Tilžės g. 18', TRUE),
('ADDR008', 'CUST008', 'Šiauliai', 'Tilžės g.', '20', '8', 'Šiauliai, Tilžės g. 20-8', TRUE),
('ADDR009', 'CUST009', 'Šiauliai', 'Tilžės g.', '20', '22', 'Šiauliai, Tilžės g. 20-22', TRUE),
('ADDR010', 'CUST010', 'Šiauliai', 'Tilžės g.', '22', NULL, 'Šiauliai, Tilžės g. 22', TRUE),

-- Dainų g. addresses
('ADDR011', 'CUST011', 'Šiauliai', 'Dainų g.', '5', '7', 'Šiauliai, Dainų g. 5-7', TRUE),
('ADDR012', 'CUST012', 'Šiauliai', 'Dainų g.', '5', '18', 'Šiauliai, Dainų g. 5-18', TRUE),
('ADDR013', 'CUST013', 'Šiauliai', 'Dainų g.', '5', '34', 'Šiauliai, Dainų g. 5-34', TRUE),
('ADDR014', 'CUST014', 'Šiauliai', 'Dainų g.', '7', '2', 'Šiauliai, Dainų g. 7-2', TRUE),
('ADDR015', 'CUST015', 'Šiauliai', 'Dainų g.', '7', '25', 'Šiauliai, Dainų g. 7-25', TRUE),
('ADDR016', 'CUST016', 'Šiauliai', 'Dainų g.', '9', NULL, 'Šiauliai, Dainų g. 9', TRUE),
('ADDR017', 'CUST017', 'Šiauliai', 'Dainų g.', '11', NULL, 'Šiauliai, Dainų g. 11', TRUE),
('ADDR018', 'CUST018', 'Šiauliai', 'Dainų g.', '13', '11', 'Šiauliai, Dainų g. 13-11', TRUE),
('ADDR019', 'CUST019', 'Šiauliai', 'Dainų g.', '13', '30', 'Šiauliai, Dainų g. 13-30', TRUE),
('ADDR020', 'CUST020', 'Šiauliai', 'Dainų g.', '15', NULL, 'Šiauliai, Dainų g. 15', TRUE),

-- Lieporių g. addresses
('ADDR021', 'CUST021', 'Šiauliai', 'Lieporių g.', '8', '4', 'Šiauliai, Lieporių g. 8-4', TRUE),
('ADDR022', 'CUST022', 'Šiauliai', 'Lieporių g.', '8', '20', 'Šiauliai, Lieporių g. 8-20', TRUE),
('ADDR023', 'CUST023', 'Šiauliai', 'Lieporių g.', '8', '38', 'Šiauliai, Lieporių g. 8-38', TRUE),
('ADDR024', 'CUST024', 'Šiauliai', 'Lieporių g.', '10', '6', 'Šiauliai, Lieporių g. 10-6', TRUE),
('ADDR025', 'CUST025', 'Šiauliai', 'Lieporių g.', '10', '14', 'Šiauliai, Lieporių g. 10-14', TRUE),
('ADDR026', 'CUST026', 'Šiauliai', 'Lieporių g.', '12', NULL, 'Šiauliai, Lieporių g. 12', TRUE),
('ADDR027', 'CUST027', 'Šiauliai', 'Lieporių g.', '14', NULL, 'Šiauliai, Lieporių g. 14', TRUE),
('ADDR028', 'CUST028', 'Šiauliai', 'Lieporių g.', '16', '9', 'Šiauliai, Lieporių g. 16-9', TRUE),
('ADDR029', 'CUST029', 'Šiauliai', 'Lieporių g.', '16', '27', 'Šiauliai, Lieporių g. 16-27', TRUE),
('ADDR030', 'CUST030', 'Šiauliai', 'Lieporių g.', '18', NULL, 'Šiauliai, Lieporių g. 18', TRUE),

-- Vilniaus g. addresses
('ADDR031', 'CUST031', 'Šiauliai', 'Vilniaus g.', '25', '1', 'Šiauliai, Vilniaus g. 25-1', TRUE),
('ADDR032', 'CUST032', 'Šiauliai', 'Vilniaus g.', '25', '17', 'Šiauliai, Vilniaus g. 25-17', TRUE),
('ADDR033', 'CUST033', 'Šiauliai', 'Vilniaus g.', '25', '32', 'Šiauliai, Vilniaus g. 25-32', TRUE),
('ADDR034', 'CUST034', 'Šiauliai', 'Vilniaus g.', '27', '5', 'Šiauliai, Vilniaus g. 27-5', TRUE),
('ADDR035', 'CUST035', 'Šiauliai', 'Vilniaus g.', '27', '23', 'Šiauliai, Vilniaus g. 27-23', TRUE),
('ADDR036', 'CUST036', 'Šiauliai', 'Vilniaus g.', '29', NULL, 'Šiauliai, Vilniaus g. 29', TRUE),
('ADDR037', 'CUST037', 'Šiauliai', 'Vilniaus g.', '31', NULL, 'Šiauliai, Vilniaus g. 31', TRUE),
('ADDR038', 'CUST038', 'Šiauliai', 'Vilniaus g.', '33', '13', 'Šiauliai, Vilniaus g. 33-13', TRUE),
('ADDR039', 'CUST039', 'Šiauliai', 'Vilniaus g.', '33', '29', 'Šiauliai, Vilniaus g. 33-29', TRUE),
('ADDR040', 'CUST040', 'Šiauliai', 'Vilniaus g.', '35', NULL, 'Šiauliai, Vilniaus g. 35', TRUE),

-- Birutės g. addresses
('ADDR041', 'CUST041', 'Šiauliai', 'Birutės g.', '42', '8', 'Šiauliai, Birutės g. 42-8', TRUE),
('ADDR042', 'CUST042', 'Šiauliai', 'Birutės g.', '42', '19', 'Šiauliai, Birutės g. 42-19', TRUE),
('ADDR043', 'CUST043', 'Šiauliai', 'Birutės g.', '42', '36', 'Šiauliai, Birutės g. 42-36', TRUE),
('ADDR044', 'CUST044', 'Šiauliai', 'Birutės g.', '44', '4', 'Šiauliai, Birutės g. 44-4', TRUE),
('ADDR045', 'CUST045', 'Šiauliai', 'Birutės g.', '44', '21', 'Šiauliai, Birutės g. 44-21', TRUE),
('ADDR046', 'CUST046', 'Šiauliai', 'Birutės g.', '46', NULL, 'Šiauliai, Birutės g. 46', TRUE),
('ADDR047', 'CUST047', 'Šiauliai', 'Birutės g.', '48', NULL, 'Šiauliai, Birutės g. 48', TRUE),
('ADDR048', 'CUST048', 'Šiauliai', 'Birutės g.', '50', '10', 'Šiauliai, Birutės g. 50-10', TRUE),
('ADDR049', 'CUST049', 'Šiauliai', 'Birutės g.', '50', '26', 'Šiauliai, Birutės g. 50-26', TRUE),
('ADDR050', 'CUST050', 'Šiauliai', 'Birutės g.', '52', NULL, 'Šiauliai, Birutės g. 52', TRUE),

-- Gegužių g. addresses
('ADDR051', 'CUST051', 'Šiauliai', 'Gegužių g.', '3', '6', 'Šiauliai, Gegužių g. 3-6', TRUE),
('ADDR052', 'CUST052', 'Šiauliai', 'Gegužių g.', '3', '24', 'Šiauliai, Gegužių g. 3-24', TRUE),
('ADDR053', 'CUST053', 'Šiauliai', 'Gegužių g.', '3', '41', 'Šiauliai, Gegužių g. 3-41', TRUE),
('ADDR054', 'CUST054', 'Šiauliai', 'Gegužių g.', '5', '2', 'Šiauliai, Gegužių g. 5-2', TRUE),
('ADDR055', 'CUST055', 'Šiauliai', 'Gegužių g.', '5', '16', 'Šiauliai, Gegužių g. 5-16', TRUE),
('ADDR056', 'CUST056', 'Šiauliai', 'Gegužių g.', '7', NULL, 'Šiauliai, Gegužių g. 7', TRUE),
('ADDR057', 'CUST057', 'Šiauliai', 'Gegužių g.', '9', NULL, 'Šiauliai, Gegužių g. 9', TRUE),
('ADDR058', 'CUST058', 'Šiauliai', 'Gegužių g.', '11', '12', 'Šiauliai, Gegužių g. 11-12', TRUE),
('ADDR059', 'CUST059', 'Šiauliai', 'Gegužių g.', '11', '33', 'Šiauliai, Gegužių g. 11-33', TRUE),
('ADDR060', 'CUST060', 'Šiauliai', 'Gegužių g.', '13', NULL, 'Šiauliai, Gegužių g. 13', TRUE),

-- More addresses across all streets
('ADDR061', 'CUST061', 'Šiauliai', 'Tilžės g.', '24', '11', 'Šiauliai, Tilžės g. 24-11', TRUE),
('ADDR062', 'CUST062', 'Šiauliai', 'Tilžės g.', '26', NULL, 'Šiauliai, Tilžės g. 26', TRUE),
('ADDR063', 'CUST063', 'Šiauliai', 'Dainų g.', '17', '9', 'Šiauliai, Dainų g. 17-9', TRUE),
('ADDR064', 'CUST064', 'Šiauliai', 'Dainų g.', '19', NULL, 'Šiauliai, Dainų g. 19', TRUE),
('ADDR065', 'CUST065', 'Šiauliai', 'Lieporių g.', '20', '14', 'Šiauliai, Lieporių g. 20-14', TRUE),
('ADDR066', 'CUST066', 'Šiauliai', 'Lieporių g.', '22', NULL, 'Šiauliai, Lieporių g. 22', TRUE),
('ADDR067', 'CUST067', 'Šiauliai', 'Vilniaus g.', '37', '7', 'Šiauliai, Vilniaus g. 37-7', TRUE),
('ADDR068', 'CUST068', 'Šiauliai', 'Vilniaus g.', '39', NULL, 'Šiauliai, Vilniaus g. 39', TRUE),
('ADDR069', 'CUST069', 'Šiauliai', 'Birutės g.', '54', '15', 'Šiauliai, Birutės g. 54-15', TRUE),
('ADDR070', 'CUST070', 'Šiauliai', 'Birutės g.', '56', NULL, 'Šiauliai, Birutės g. 56', TRUE),
('ADDR071', 'CUST071', 'Šiauliai', 'Gegužių g.', '15', '19', 'Šiauliai, Gegužių g. 15-19', TRUE),
('ADDR072', 'CUST072', 'Šiauliai', 'Gegužių g.', '17', NULL, 'Šiauliai, Gegužių g. 17', TRUE),
('ADDR073', 'CUST073', 'Šiauliai', 'Tilžės g.', '28', '5', 'Šiauliai, Tilžės g. 28-5', TRUE),
('ADDR074', 'CUST074', 'Šiauliai', 'Tilžės g.', '30', NULL, 'Šiauliai, Tilžės g. 30', TRUE),
('ADDR075', 'CUST075', 'Šiauliai', 'Dainų g.', '21', '13', 'Šiauliai, Dainų g. 21-13', TRUE),
('ADDR076', 'CUST076', 'Šiauliai', 'Dainų g.', '23', NULL, 'Šiauliai, Dainų g. 23', TRUE),
('ADDR077', 'CUST077', 'Šiauliai', 'Lieporių g.', '24', '8', 'Šiauliai, Lieporių g. 24-8', TRUE),
('ADDR078', 'CUST078', 'Šiauliai', 'Lieporių g.', '26', NULL, 'Šiauliai, Lieporių g. 26', TRUE),
('ADDR079', 'CUST079', 'Šiauliai', 'Vilniaus g.', '41', '11', 'Šiauliai, Vilniaus g. 41-11', TRUE),
('ADDR080', 'CUST080', 'Šiauliai', 'Vilniaus g.', '43', NULL, 'Šiauliai, Vilniaus g. 43', TRUE),
('ADDR081', 'CUST081', 'Šiauliai', 'Birutės g.', '58', '17', 'Šiauliai, Birutės g. 58-17', TRUE),
('ADDR082', 'CUST082', 'Šiauliai', 'Birutės g.', '60', NULL, 'Šiauliai, Birutės g. 60', TRUE),
('ADDR083', 'CUST083', 'Šiauliai', 'Gegužių g.', '19', '22', 'Šiauliai, Gegužių g. 19-22', TRUE),
('ADDR084', 'CUST084', 'Šiauliai', 'Gegužių g.', '21', NULL, 'Šiauliai, Gegužių g. 21', TRUE),
('ADDR085', 'CUST085', 'Šiauliai', 'Tilžės g.', '32', '9', 'Šiauliai, Tilžės g. 32-9', TRUE),
('ADDR086', 'CUST086', 'Šiauliai', 'Tilžės g.', '34', NULL, 'Šiauliai, Tilžės g. 34', TRUE),
('ADDR087', 'CUST087', 'Šiauliai', 'Dainų g.', '25', '16', 'Šiauliai, Dainų g. 25-16', TRUE),
('ADDR088', 'CUST088', 'Šiauliai', 'Dainų g.', '27', NULL, 'Šiauliai, Dainų g. 27', TRUE),
('ADDR089', 'CUST089', 'Šiauliai', 'Lieporių g.', '28', '10', 'Šiauliai, Lieporių g. 28-10', TRUE),
('ADDR090', 'CUST090', 'Šiauliai', 'Lieporių g.', '30', NULL, 'Šiauliai, Lieporių g. 30', TRUE),
('ADDR091', 'CUST091', 'Šiauliai', 'Vilniaus g.', '45', '14', 'Šiauliai, Vilniaus g. 45-14', TRUE),
('ADDR092', 'CUST092', 'Šiauliai', 'Vilniaus g.', '47', NULL, 'Šiauliai, Vilniaus g. 47', TRUE),
('ADDR093', 'CUST093', 'Šiauliai', 'Birutės g.', '62', '20', 'Šiauliai, Birutės g. 62-20', TRUE),
('ADDR094', 'CUST094', 'Šiauliai', 'Birutės g.', '64', NULL, 'Šiauliai, Birutės g. 64', TRUE),
('ADDR095', 'CUST095', 'Šiauliai', 'Gegužių g.', '23', '25', 'Šiauliai, Gegužių g. 23-25', TRUE),
('ADDR096', 'CUST096', 'Šiauliai', 'Gegužių g.', '25', NULL, 'Šiauliai, Gegužių g. 25', TRUE),
('ADDR097', 'CUST097', 'Šiauliai', 'Tilžės g.', '36', '18', 'Šiauliai, Tilžės g. 36-18', TRUE),
('ADDR098', 'CUST098', 'Šiauliai', 'Dainų g.', '29', '12', 'Šiauliai, Dainų g. 29-12', TRUE),
('ADDR099', 'CUST099', 'Šiauliai', 'Lieporių g.', '32', '6', 'Šiauliai, Lieporių g. 32-6', TRUE),
('ADDR100', 'CUST100', 'Šiauliai', 'Vilniaus g.', '49', NULL, 'Šiauliai, Vilniaus g. 49', TRUE);