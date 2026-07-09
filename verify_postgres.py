import psycopg2
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

# Load environment variables
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

print("=" * 60)
print("SUPABASE POSTGRESQL VERIFICATION")
print("=" * 60)

try:
    # Connect to PostgreSQL
    print(f"\n1. Connecting to PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    print("   [OK] Connection established")
    
    # Get server info
    print("\n2. PostgreSQL Server Information:")
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"   Version: {version['version'][:50]}...")

    cursor.execute("SELECT current_database();")
    db = cursor.fetchone()
    print(f"   Database: {db['current_database']}")

    cursor.execute("SELECT current_schema();")
    schema = cursor.fetchone()
    print(f"   Schema: {schema['current_schema']}")
    
    # List all tables
    print("\n3. Tables in database:")
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    
    required_tables = [
        'users', 'exams', 'questions', 'question_bank', 
        'submissions', 'submission_answers', 'activity_log',
        'classrooms', 'classroom_members', 'exam_attempts'
    ]
    
    existing_tables = [row['table_name'] for row in tables]
    print(f"   Total tables found: {len(existing_tables)}")
    
    for table in existing_tables:
        status = "[OK]" if table in required_tables else "[  ]"
        print(f"   {status} {table}")
    
    # Verify required tables
    print("\n4. Required tables verification:")
    missing_tables = []
    for table in required_tables:
        if table in existing_tables:
            print(f"   [OK] {table} - EXISTS")
        else:
            print(f"   [FAIL] {table} - MISSING")
            missing_tables.append(table)
    
    # Verify users table structure
    print("\n5. Users table structure:")
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"   - {col[0]}: {col[1]}")
    
    # Verify default admin account
    print("\n6. Default admin account verification:")
    cursor.execute("""
        SELECT id, name, email, role, approved, profile_completed 
        FROM users 
        WHERE role = 'admin';
    """)
    admins = cursor.fetchall()
    
    if admins:
        for admin in admins:
            print(f"   [OK] Admin found:")
            print(f"     ID: {admin['id']}")
            print(f"     Name: {admin['name']}")
            print(f"     Email: {admin['email']}")
            print(f"     Role: {admin['role']}")
            print(f"     Approved: {admin['approved']}")
            print(f"     Profile Completed: {admin['profile_completed']}")
    else:
        print("   [FAIL] No admin account found!")
    
    # Count records in each table
    print("\n7. Record counts:")
    for table in existing_tables:
        try:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table};")
            count = cursor.fetchone()
            print(f"   {table}: {count['count']} records")
        except Exception as e:
            print(f"   {table}: Error counting - {e}")
    
    # Final summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    if missing_tables:
        print(f"[FAIL] {len(missing_tables)} required tables missing")
        print(f"  Missing: {', '.join(missing_tables)}")
    else:
        print("[OK] All required tables exist")
    
    if admins:
        print("[OK] Admin account exists")
    else:
        print("[FAIL] Admin account missing")
    
    if not missing_tables and admins:
        print("\n[SUCCESS] POSTGRESQL MIGRATION SUCCESSFUL")
    else:
        print("\n[FAIL] POSTGRESQL MIGRATION INCOMPLETE")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
