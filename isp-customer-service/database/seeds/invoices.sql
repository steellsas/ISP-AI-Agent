-- INVOICES (closing wave 2026-09-08): debt details for the inform templates.
-- CUST101 (S1, Tilžės g. 60-3) — the demo debt case: two unpaid months,
-- last payment received June 5. CUST007 — the base-seed suspended customer.
-- A couple of paid rows elsewhere so "paid" is the normal shape.

INSERT INTO invoices (invoice_id, customer_id, period, amount, status, paid_date) VALUES
-- CUST101: suspended for debt — 2 unpaid months, 49.98 EUR total
('INV101-06', 'CUST101', '2026-06', 24.99, 'paid',   '2026-06-05'),
('INV101-07', 'CUST101', '2026-07', 24.99, 'unpaid', NULL),
('INV101-08', 'CUST101', '2026-08', 24.99, 'unpaid', NULL),
-- CUST007: base-seed suspended customer — 1 unpaid month
('INV007-07', 'CUST007', '2026-07', 15.99, 'paid',   '2026-07-03'),
('INV007-08', 'CUST007', '2026-08', 15.99, 'unpaid', NULL),
-- Healthy examples: last month paid on time
('INV112-08', 'CUST112', '2026-08', 15.99, 'paid',   '2026-08-04'),
('INV104-08', 'CUST104', '2026-08', 24.99, 'paid',   '2026-08-02');
