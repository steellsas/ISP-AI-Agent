-- ============================================
-- Demo Service Plans
-- ============================================

-- Internet plans
INSERT INTO service_plans (plan_id, customer_id, service_type, plan_name, speed_mbps, price, status, activation_date, suspension_reason) VALUES
('PLAN001', 'CUST001', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-03-15', NULL),
('PLAN002', 'CUST002', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-04-20', NULL),
('PLAN003', 'CUST003', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-05-10', NULL),
('PLAN004', 'CUST004', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-06-05', NULL),
('PLAN005', 'CUST005', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-07-12', NULL),
('PLAN006', 'CUST006', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-08-18', NULL),
-- CUST007: Suspended due to payment!
('PLAN007', 'CUST007', 'internet', 'Internet 100 Mbps', 100, 15.99, 'suspended', '2023-09-22', 'Payment overdue 30+ days'),
('PLAN008', 'CUST008', 'internet', 'Internet 100 Mbps', 100, 15.99, 'active', '2023-10-30', NULL),
('PLAN009', 'CUST009', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active', '2023-11-14', NULL),
('PLAN010', 'CUST010', 'internet', 'Internet 300 Mbps', 300, 24.99, 'active', '2023-12-08', NULL);

-- TV plans (for TV scenario customers)
INSERT INTO service_plans (plan_id, customer_id, service_type, plan_name, speed_mbps, price, status, activation_date) VALUES
('PLAN_TV005', 'CUST005', 'tv', 'IP TV Standard', NULL, 8.99, 'active', '2023-07-12'),
('PLAN_TV010', 'CUST010', 'tv', 'IP TV Standard', NULL, 8.99, 'active', '2023-12-08');