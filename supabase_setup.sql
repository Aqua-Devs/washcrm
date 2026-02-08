-- PressureFlow CRM - Supabase Database Schema
-- Run this in Supabase SQL Editor to set up the database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'technician')),
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customers table
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    email TEXT,
    parking_situation TEXT CHECK (parking_situation IN ('oprit', 'straat', 'vergunning')),
    water_tap_location TEXT,
    water_pressure_lpm NUMERIC,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Services table (configurable by admin)
CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    price_per_unit NUMERIC NOT NULL DEFAULT 0,
    unit_type TEXT NOT NULL DEFAULT 'm2',
    heavy_multiplier NUMERIC NOT NULL DEFAULT 1.3,
    chemical_usage_rate NUMERIC DEFAULT 0,
    chemical_unit TEXT DEFAULT 'L',
    linked_inventory_id UUID,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Upsell items table
CREATE TABLE upsell_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    price NUMERIC NOT NULL DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Inventory table
CREATE TABLE inventory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_name TEXT NOT NULL,
    quantity_on_hand NUMERIC NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT 'L',
    threshold_warning NUMERIC DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Link services to inventory
ALTER TABLE services ADD CONSTRAINT fk_services_inventory
    FOREIGN KEY (linked_inventory_id) REFERENCES inventory(id) ON DELETE SET NULL;

-- Estimates / Quotes
CREATE TABLE estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'concept' CHECK (status IN ('concept', 'offerte', 'akkoord', 'voltooid', 'factuur', 'betaald')),
    subtotal NUMERIC NOT NULL DEFAULT 0,
    btw_percentage NUMERIC NOT NULL DEFAULT 21,
    total_incl_btw NUMERIC NOT NULL DEFAULT 0,
    signature_data TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Estimate line items (services)
CREATE TABLE estimate_lines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    estimate_id UUID NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    service_id UUID REFERENCES services(id),
    description TEXT NOT NULL,
    square_meters NUMERIC DEFAULT 0,
    pollution_level TEXT DEFAULT 'standaard' CHECK (pollution_level IN ('standaard', 'zwaar')),
    unit_price NUMERIC NOT NULL DEFAULT 0,
    multiplier NUMERIC NOT NULL DEFAULT 1.0,
    line_total NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Estimate upsell items
CREATE TABLE estimate_upsells (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    estimate_id UUID NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    upsell_item_id UUID REFERENCES upsell_items(id),
    description TEXT NOT NULL,
    price NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project photos
CREATE TABLE project_photos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    estimate_id UUID NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id),
    photo_type TEXT NOT NULL CHECK (photo_type IN ('voor', 'na', 'overig')),
    photo_data TEXT NOT NULL,
    caption TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Inventory log (track changes)
CREATE TABLE inventory_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inventory_id UUID NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
    estimate_id UUID REFERENCES estimates(id),
    change_amount NUMERIC NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Settings table (key-value for app settings)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default settings
INSERT INTO settings (key, value) VALUES
    ('company_name', 'MijnBedrijf'),
    ('company_email', ''),
    ('company_phone', ''),
    ('company_address', ''),
    ('company_kvk', ''),
    ('company_btw_id', ''),
    ('company_iban', ''),
    ('company_logo', ''),
    ('btw_percentage', '21'),
    ('estimate_prefix', 'OFF'),
    ('invoice_prefix', 'FAC'),
    ('estimate_counter', '1'),
    ('invoice_counter', '1');

-- Insert default services
INSERT INTO services (name, price_per_unit, unit_type, heavy_multiplier) VALUES
    ('Klinkers reinigen', 3.50, 'm2', 1.3),
    ('Dak reinigen', 5.00, 'm2', 1.3),
    ('Gevel reinigen', 4.00, 'm2', 1.3),
    ('Vlonder reinigen', 4.50, 'm2', 1.3),
    ('Terras reinigen', 3.50, 'm2', 1.3);

-- Insert default upsell items
INSERT INTO upsell_items (name, price) VALUES
    ('Prullenbak reinigen', 15.00),
    ('Tuinset reinigen', 40.00),
    ('Schutting reinigen (per stuk)', 25.00),
    ('Plantenbak reinigen', 10.00),
    ('Impregneren (per m²)', 2.50);

-- Insert default inventory
INSERT INTO inventory (item_name, quantity_on_hand, unit, threshold_warning) VALUES
    ('Bio-Degreaser', 20, 'L', 5),
    ('Anti-Mos Middel', 15, 'L', 3),
    ('Impregneer Vloeistof', 10, 'L', 2),
    ('Hogedruk Nozzles', 8, 'stuks', 2),
    ('Beschermtape', 5, 'rollen', 1);

-- Row Level Security (optional, enable if needed)
-- ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE estimates ENABLE ROW LEVEL SECURITY;

-- Create indexes for performance
CREATE INDEX idx_estimates_customer ON estimates(customer_id);
CREATE INDEX idx_estimates_status ON estimates(status);
CREATE INDEX idx_estimate_lines_estimate ON estimate_lines(estimate_id);
CREATE INDEX idx_project_photos_estimate ON project_photos(estimate_id);
CREATE INDEX idx_inventory_log_inventory ON inventory_log(inventory_id);
