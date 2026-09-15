-- ============================================================================
-- EduSphere Security Migration: Enable RLS and Block Unauthorized API Access
-- ============================================================================
-- This migration enables Row Level Security (RLS) on all tables and creates
-- policies to block unauthorized access via Supabase REST API.
--
-- IMPORTANT: The Flask backend uses a privileged PostgreSQL connection that
-- bypasses RLS, so these policies will NOT affect existing application functionality.
-- They only protect against unauthorized Supabase REST API access.
--
-- Security Improvements:
-- - Blocks anonymous/public access to all tables via Supabase API
-- - Protects sensitive data (passwords, emails, phone numbers) from API exposure
-- - Resolves Supabase Security Advisor warnings
-- ============================================================================

-- ============================================================================
-- Phase 1: Enable RLS on All Tables
-- ============================================================================

-- Enable RLS on users table (contains sensitive data: password, email, phone)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Enable RLS on exams table
ALTER TABLE exams ENABLE ROW LEVEL SECURITY;

-- Enable RLS on questions table (contains exam answers)
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;

-- Enable RLS on question_bank table
ALTER TABLE question_bank ENABLE ROW LEVEL SECURITY;

-- Enable RLS on submissions table (student exam data)
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;

-- Enable RLS on submission_answers table (student answers)
ALTER TABLE submission_answers ENABLE ROW LEVEL SECURITY;

-- Enable RLS on activity_log table (audit trail)
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;

-- Enable RLS on classrooms table
ALTER TABLE classrooms ENABLE ROW LEVEL SECURITY;

-- Enable RLS on classroom_members table
ALTER TABLE classroom_members ENABLE ROW LEVEL SECURITY;

-- Enable RLS on exam_attempts table
ALTER TABLE exam_attempts ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Phase 2: Create Blocking Policies for Supabase API Access
-- ============================================================================

-- Users Table - Block all anon/authenticated API access
-- Flask backend bypasses RLS, so this only blocks Supabase REST API
CREATE POLICY "Block anon access to users" 
ON users FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Exams Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to exams" 
ON exams FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Questions Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to questions" 
ON questions FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Question Bank Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to question_bank" 
ON question_bank FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Submissions Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to submissions" 
ON submissions FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Submission Answers Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to submission_answers" 
ON submission_answers FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Activity Log Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to activity_log" 
ON activity_log FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Classrooms Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to classrooms" 
ON classrooms FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Classroom Members Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to classroom_members" 
ON classroom_members FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- Exam Attempts Table - Block all anon/authenticated API access
CREATE POLICY "Block anon access to exam_attempts" 
ON exam_attempts FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);

-- ============================================================================
-- Phase 3: Verification Queries
-- ============================================================================

-- Verify RLS is enabled on all tables
SELECT 
    schemaname,
    tablename,
    rowsecurity as rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- Verify policies were created
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;

-- ============================================================================
-- Rollback Instructions (if needed)
-- ============================================================================
-- To rollback these changes, run:
--
-- DROP POLICY IF EXISTS "Block anon access to users" ON users;
-- DROP POLICY IF EXISTS "Block anon access to exams" ON exams;
-- DROP POLICY IF EXISTS "Block anon access to questions" ON questions;
-- DROP POLICY IF EXISTS "Block anon access to question_bank" ON question_bank;
-- DROP POLICY IF EXISTS "Block anon access to submissions" ON submissions;
-- DROP POLICY IF EXISTS "Block anon access to submission_answers" ON submission_answers;
-- DROP POLICY IF EXISTS "Block anon access to activity_log" ON activity_log;
-- DROP POLICY IF EXISTS "Block anon access to classrooms" ON classrooms;
-- DROP POLICY IF EXISTS "Block anon access to classroom_members" ON classroom_members;
-- DROP POLICY IF EXISTS "Block anon access to exam_attempts" ON exam_attempts;
--
-- ALTER TABLE users DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE exams DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE questions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE question_bank DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE submissions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE submission_answers DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE activity_log DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE classrooms DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE classroom_members DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE exam_attempts DISABLE ROW LEVEL SECURITY;
-- ============================================================================
