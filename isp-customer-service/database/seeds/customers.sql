-- ============================================
-- Demo Customers - 10 customers for testing scenarios
-- ============================================

INSERT INTO customers (customer_id, first_name, last_name, phone, email, status, notes) VALUES
-- Scenario 1: Happy path - everything works, just needs router restart
('CUST001', 'Jonas', 'Jonaitis', '+37060012345', 'jonas.jonaitis@gmail.com', 'active', 'Happy path scenario'),

-- Scenario 2: Area outage - customer in affected area
('CUST002', 'Marija', 'Kazlauskienė', '+37060012346', 'marija.kazlauskiene@gmail.com', 'active', 'Outage scenario - Dainų g.'),

-- Scenario 3: Slow internet during peak hours
('CUST003', 'Petras', 'Petraitis', '+37060012347', 'petras.petraitis@gmail.com', 'active', 'Slow internet peak hours'),

-- Scenario 4: Port down - needs technician visit
('CUST004', 'Andrius', 'Andriuška', '+37060012348', 'andrius.andriuska@gmail.com', 'active', 'Port down - escalation scenario'),

-- Scenario 5: TV no signal
('CUST005', 'Ona', 'Onaitė', '+37060012349', 'ona.onaite@gmail.com', 'active', 'TV no signal scenario'),

-- Scenario 6: No IP assigned (expired DHCP)
('CUST006', 'Laima', 'Laimutė', '+37060012350', 'laima.laimute@gmail.com', 'active', 'No IP - DHCP expired'),

-- Scenario 7: Payment issue - suspended account
('CUST007', 'Tomas', 'Tomauskas', '+37060012351', 'tomas.tomauskas@gmail.com', 'suspended', 'Payment overdue - suspended'),

-- Scenario 8: Intermittent connection (packet loss)
('CUST008', 'Rūta', 'Rūtaitė', '+37060012352', 'ruta.rutaite@gmail.com', 'active', 'Intermittent - high packet loss'),

-- Scenario 9: All OK - control customer
('CUST009', 'Giedrius', 'Giedraitis', '+37060012353', 'giedrius.giedraitis@gmail.com', 'active', 'All OK - control'),

-- Scenario 10: All OK with TV
('CUST010', 'Vida', 'Vidaitė', '+37060012354', 'vida.vidaite@gmail.com', 'active', 'All OK with TV - control');