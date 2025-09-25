-- User Setup Script for Meat Shrink Tracking App
-- Run this AFTER creating users in Supabase Authentication → Users

-- Step 1: Create auth users first in Supabase Auth UI with these emails:
-- manager@store1.com
-- associate@store1.com  
-- lead@store1.com
-- auditor@company.com
-- admin@company.com

-- Step 2: Replace the UUIDs below with the actual user IDs from Auth → Users page
-- Step 3: Run this script in SQL Editor

INSERT INTO app_users (id, email, role, store_id, is_active) VALUES
-- Replace these UUIDs with real ones from Auth Users page
('REPLACE-WITH-REAL-UUID-1', 'manager@store1.com', 'manager', 1, true),
('REPLACE-WITH-REAL-UUID-2', 'associate@store1.com', 'associate', 1, true),
('REPLACE-WITH-REAL-UUID-3', 'lead@store1.com', 'lead', 1, true),
('REPLACE-WITH-REAL-UUID-4', 'auditor@company.com', 'auditor', 1, true),
('REPLACE-WITH-REAL-UUID-5', 'admin@company.com', 'admin', 1, true);

-- Step 4: Verify users were created correctly
SELECT u.email, au.role, au.store_id, au.is_active 
FROM auth.users u 
JOIN app_users au ON u.id = au.id;