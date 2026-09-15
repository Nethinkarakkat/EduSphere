# EduSphere Security Analysis & RLS Design

## Current Architecture Analysis

### Database Connection Method
- **Flask Backend**: Uses direct PostgreSQL connection via `psycopg2`
- **Connection User**: `postgres` (database owner)
- **Privileges**: 
  - `rolsuper`: False (not a superuser)
  - `rolbypassrls`: True (can bypass RLS)
  - Full grants on all tables (SELECT, INSERT, UPDATE, DELETE, TRIGGER, TRUNCATE, REFERENCES)

### Supabase Integration
- **Storage**: Uses Supabase Storage via Python SDK with service role key
- **Database Operations**: Uses direct PostgreSQL connection, NOT Supabase REST API
- **Authentication**: Flask session-based authentication, NOT Supabase Auth

### Security Implications

**Critical Finding**: The Flask backend connects with a privileged database user that can bypass RLS. This means:
- RLS policies will NOT affect Flask backend queries
- RLS only affects direct Supabase REST API calls
- The app doesn't use Supabase REST API for database operations

**Supabase Security Warnings**:
1. "Table publicly accessible" - Tables accessible via Supabase REST API to anyone with anon key
2. "Sensitive data publicly accessible" - Users table with password/email/phone columns accessible via API

## Vulnerability Details

### Affected Tables (All 10 tables)
- `users` - Contains password hashes, emails, phone numbers
- `exams` - Exam data
- `questions` - Exam questions and answers
- `question_bank` - Question repository
- `submissions` - Student exam submissions
- `submission_answers` - Student answers
- `activity_log` - User activity tracking
- `classrooms` - Classroom information
- `classroom_members` - Classroom memberships
- `exam_attempts` - Exam attempt tracking

### Attack Scenarios
1. **Anon Key Exposure**: If SUPABASE_KEY (anon key) is exposed, attacker can:
   - Read all users including password hashes
   - Read/modify exam data
   - Access student submissions
   - Modify questions

2. **Direct API Access**: Anyone with anon key can query Supabase REST API directly

## RLS Policy Design

### Principle: Block all Supabase REST API access

Since EduSphere doesn't use Supabase REST API for database operations, the safest approach is:

**Enable RLS on all tables with NO ALLOW policies for public/anon access**

This will:
- Block all Supabase REST API access (secure)
- Not affect Flask backend (bypasses RLS)
- Resolve Supabase security warnings
- Maintain all existing functionality

### Policy Strategy

#### 1. Users Table
```sql
-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Block all anon/public access
CREATE POLICY "Block anon access to users" 
ON users FOR ALL 
TO anon, authenticated 
USING (false) 
WITH CHECK (false);
```

#### 2. All Other Tables
Same approach - block all anon/public access while allowing Flask backend to bypass RLS.

### Alternative Approach (If Supabase API Access Needed)

If future development requires Supabase API access, we would need:
1. JWT-based authentication policies
2. Role-based access control
3. User-specific data filtering

However, since current architecture doesn't use Supabase API, the "block all" approach is safest.

## Implementation Plan

### Phase 1: Enable RLS on All Tables
```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_bank ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE submission_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE classrooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE classroom_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE exam_attempts ENABLE ROW LEVEL SECURITY;
```

### Phase 2: Create Blocking Policies
Create policies that block anon/authenticated access via Supabase API while allowing Flask backend (which bypasses RLS).

### Phase 3: Verification
- Test Flask backend functionality
- Verify Supabase Security Advisor
- Test direct API access is blocked

## Risk Assessment

### Low Risk
- Flask backend uses privileged connection that bypasses RLS
- No application code changes needed
- Existing functionality preserved

### Security Improvement
- Blocks unauthorized Supabase API access
- Protects sensitive data from API exposure
- Resolves Supabase security warnings

## Conclusion

The recommended approach is to enable RLS with blocking policies. This:
- Secures the database from unauthorized API access
- Maintains all existing Flask functionality
- Requires minimal changes
- Provides defense-in-depth security
