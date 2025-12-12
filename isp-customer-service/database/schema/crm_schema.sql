-- ============================================
-- CRM Schema
-- Customer Relationship Management Database
-- ============================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================
-- CUSTOMERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'cancelled')),
    notes TEXT
);

CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_status ON customers(status);

-- ============================================
-- ADDRESSES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS addresses (
    address_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    city TEXT NOT NULL,
    street TEXT NOT NULL,
    house_number TEXT NOT NULL,
    apartment_number TEXT,
    postal_code TEXT,
    full_address TEXT,
    is_primary BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX idx_addresses_customer ON addresses(customer_id);
CREATE INDEX idx_addresses_city ON addresses(city);
CREATE INDEX idx_addresses_street ON addresses(street);
CREATE INDEX idx_addresses_full ON addresses(city, street, house_number);

-- ============================================
-- SERVICE PLANS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS service_plans (
    plan_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    service_type TEXT NOT NULL CHECK(service_type IN ('internet', 'tv', 'phone', 'bundle')),
    plan_name TEXT NOT NULL,
    speed_mbps INTEGER,
    price DECIMAL(10,2) NOT NULL,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'cancelled')),
    activation_date DATE NOT NULL,
    suspension_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX idx_service_plans_customer ON service_plans(customer_id);
CREATE INDEX idx_service_plans_type ON service_plans(service_type);
CREATE INDEX idx_service_plans_status ON service_plans(status);

-- ============================================
-- CUSTOMER EQUIPMENT TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS customer_equipment (
    equipment_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    equipment_type TEXT NOT NULL CHECK(equipment_type IN ('router', 'modem', 'decoder', 'phone', 'ont')),
    model TEXT,
    serial_number TEXT,
    mac_address TEXT,
    installed_date DATE,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'faulty', 'returned')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX idx_equipment_customer ON customer_equipment(customer_id);
CREATE INDEX idx_equipment_mac ON customer_equipment(mac_address);
CREATE INDEX idx_equipment_type ON customer_equipment(equipment_type);
CREATE INDEX idx_equipment_serial ON customer_equipment(serial_number);

-- ============================================
-- TICKETS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    ticket_type TEXT NOT NULL CHECK(ticket_type IN ('network_issue', 'resolved', 'technician_visit', 'customer_not_found', 'no_service_area')),
    problem_type TEXT,
    priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'critical')),
    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'closed')),
    summary TEXT NOT NULL,
    details TEXT,
    resolution_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    assigned_to TEXT,
    troubleshooting_steps TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE INDEX idx_tickets_customer ON tickets(customer_id);
CREATE INDEX idx_tickets_type ON tickets(ticket_type);
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_priority ON tickets(priority);
CREATE INDEX idx_tickets_created ON tickets(created_at);

-- ============================================
-- CUSTOMER HISTORY TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS customer_history (
    history_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('ticket_created', 'ticket_resolved', 'payment', 'service_change', 'equipment_change', 'status_change')),
    event_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT,
    related_ticket_id TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (related_ticket_id) REFERENCES tickets(ticket_id) ON DELETE SET NULL
);

CREATE INDEX idx_history_customer ON customer_history(customer_id);
CREATE INDEX idx_history_event_type ON customer_history(event_type);
CREATE INDEX idx_history_date ON customer_history(event_date);

-- ============================================
-- CUSTOMER MEMORY TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS customer_memory (
    memory_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    memory_value TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    UNIQUE(customer_id, memory_key)
);

CREATE INDEX idx_memory_customer ON customer_memory(customer_id);
CREATE INDEX idx_memory_key ON customer_memory(memory_key);

-- ============================================
-- CONVERSATIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    customer_id TEXT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    messages TEXT NOT NULL,
    outcome TEXT,
    summary TEXT,
    ticket_id TEXT,
    duration_seconds INTEGER,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE SET NULL
);

CREATE INDEX idx_conversations_customer ON conversations(customer_id);
CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_timestamp ON conversations(timestamp);
CREATE INDEX idx_conversations_ticket ON conversations(ticket_id);

-- ============================================
-- STREETS REFERENCE TABLE (for fuzzy matching)
-- ============================================
CREATE TABLE IF NOT EXISTS streets (
    street_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    street_name TEXT NOT NULL,
    street_type TEXT,
    postal_code_prefix TEXT,
    UNIQUE(city, street_name)
);

CREATE INDEX idx_streets_city ON streets(city);
CREATE INDEX idx_streets_name ON streets(street_name);

-- ============================================
-- VIEWS
-- ============================================

-- View: Active customers with their primary address
CREATE VIEW IF NOT EXISTS active_customers_with_address AS
SELECT 
    c.customer_id,
    c.first_name,
    c.last_name,
    c.phone,
    c.email,
    a.city,
    a.street,
    a.house_number,
    a.apartment_number,
    a.full_address
FROM customers c
LEFT JOIN addresses a ON c.customer_id = a.customer_id AND a.is_primary = TRUE
WHERE c.status = 'active';

-- View: Customer service summary
CREATE VIEW IF NOT EXISTS customer_service_summary AS
SELECT 
    c.customer_id,
    c.first_name,
    c.last_name,
    COUNT(DISTINCT sp.plan_id) as active_services,
    COUNT(DISTINCT ce.equipment_id) as equipment_count,
    COUNT(DISTINCT t.ticket_id) as total_tickets,
    COUNT(DISTINCT CASE WHEN t.status = 'open' THEN t.ticket_id END) as open_tickets
FROM customers c
LEFT JOIN service_plans sp ON c.customer_id = sp.customer_id AND sp.status = 'active'
LEFT JOIN customer_equipment ce ON c.customer_id = ce.customer_id AND ce.status = 'active'
LEFT JOIN tickets t ON c.customer_id = t.customer_id
WHERE c.status = 'active'
GROUP BY c.customer_id;