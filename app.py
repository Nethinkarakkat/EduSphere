from flask import Flask, render_template, request, redirect, session, flash, make_response, jsonify, url_for
import sqlite3, os, csv, io, random, string
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF
import psycopg2
from psycopg2.extras import RealDictCursor

# Load .env file from the same directory as this script
env_path = os.path.join(os.path.dirname(__file__), '.env')
print(f"[STARTUP] Loading .env from: {env_path}")
print(f"[STARTUP] .env file exists: {os.path.exists(env_path)}")
load_dotenv(env_path)

# ── Startup Logging ──────────────────────────────────────────────────────────
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("[STARTUP] Loading environment variables...")
DATABASE_URL = os.environ.get("DATABASE_URL")
print(f"[STARTUP] DATABASE_URL value: {DATABASE_URL}")
if DATABASE_URL:
    print(f"[STARTUP] DATABASE_URL detected (PostgreSQL mode enabled)")
    print(f"[STARTUP] DATABASE_URL prefix: {DATABASE_URL[:40]}..." if len(DATABASE_URL) > 40 else f"[STARTUP] DATABASE_URL: {DATABASE_URL}")
else:
    print("[STARTUP] DATABASE_URL not detected (SQLite mode enabled)")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key")
app.permanent_session_lifetime = __import__("datetime").timedelta(minutes=30)

# Custom Jinja filter for datetime formatting (handles both string and datetime objects)
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    """Format datetime or string to specified format."""
    if value is None:
        return ''
    if isinstance(value, str):
        # If it's already a string, try to parse it first
        try:
            from datetime import datetime
            # Try common datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime(format)
                except ValueError:
                    continue
            # If parsing fails, return original string truncated
            return value[:16] if len(value) > 16 else value
        except Exception:
            return str(value)[:16] if len(str(value)) > 16 else str(value)
    # If it's a datetime object
    try:
        return value.strftime(format)
    except AttributeError:
        return str(value)[:16] if len(str(value)) > 16 else str(value)

app.jinja_env.filters['format_datetime'] = format_datetime

# Global avatar helper function
def get_avatar(user):
    """Get avatar URL for a user, or default avatar if no avatar exists."""
    if not user:
        return None
    
    profile_pic = None
    try:
        # Try profile_picture key first (database column - single source of truth)
        profile_pic = user["profile_picture"]
    except (KeyError, TypeError):
        try:
            # Fallback to profile_pic key (session key)
            profile_pic = user["profile_pic"]
        except (KeyError, TypeError):
            try:
                # Try get() method for profile_picture
                profile_pic = user.get("profile_picture")
            except (AttributeError, TypeError):
                try:
                    # Try get() method for profile_pic
                    profile_pic = user.get("profile_pic")
                except (AttributeError, TypeError):
                    profile_pic = None
    
    if profile_pic:
        # If it's a Supabase URL (starts with http), return it directly
        if isinstance(profile_pic, str) and profile_pic.startswith("http"):
            return profile_pic
        
        # If it's an old static/uploads path, fall back to default avatar
        # (these files don't exist on Render due to ephemeral filesystem)
        if isinstance(profile_pic, str) and profile_pic.startswith("/static/"):
            # Fall back to default avatar for old uploads
            pass
        # Check if local file exists (for development)
        elif isinstance(profile_pic, str):
            filepath = os.path.join('static', profile_pic)
            if os.path.exists(filepath):
                return url_for('static', filename=profile_pic)
    
    # Return default avatar using UI Avatars service (initials-based)
    name = user.get("name", "User")
    if isinstance(name, str) and name:
        # Generate initials-based avatar
        initials = "".join([n[0].upper() for n in name.split() if n][:2])
        return f"https://ui-avatars.com/api/?name={name}&background=4f46e5&color=fff&size=128&bold=true"
    
    return None

# Register get_avatar globally for all templates
app.jinja_env.globals['get_avatar'] = get_avatar

# File upload configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _add_pdf_footer(canvas, doc):
    """Add page number footer to every PDF page."""
    from reportlab.lib import colors as _colors
    from reportlab.lib.units import cm as _cm
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_colors.grey)
    page_num_text = f"Generated by EduSphere Examination System | Page {doc.page} | Generated on: {datetime.now().strftime('%d %b %Y %H:%M')}"
    canvas.drawCentredString(
        doc.pagesize[0] / 2,
        0.6 * _cm,
        page_num_text
    )
    canvas.restoreState()


def fmt_submitted(value):
    """Format datetime string as '15 Jun 2026 14:26'"""
    if not value:
        return "—"
    try:
        from datetime import datetime as _dt
        val = str(value).replace("T", " ")[:16]
        dt = _dt.strptime(val, "%Y-%m-%d %H:%M")
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return str(value)[:16] if value else "—"


def enforce_session_timeout():
    if "user_id" in session:
        session.permanent = True
        # Redirect to login if role/user_id somehow cleared
        if not session.get("role"):
            session.clear()
            return redirect("/")

# ── DB ─────────────────────────────────────────────────────────────────────
# Database configuration (already loaded above)
# DATABASE_URL is already set from environment variables

class DatabaseConnection:
    """Unified database connection wrapper for PostgreSQL and SQLite."""
    
    def __init__(self):
        self.is_postgres = DATABASE_URL is not None
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Establish database connection based on environment."""
        try:
            if self.is_postgres:
                print("[STARTUP] Connecting to PostgreSQL...")
                self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)
                print("[STARTUP] PostgreSQL connection established successfully")
            else:
                print("[STARTUP] Connecting to SQLite...")
                db_path = get_db_path()
                self.conn = sqlite3.connect(db_path, timeout=30)
                self.conn.row_factory = sqlite3.Row
                # Enable WAL mode for better concurrency
                self.conn.execute('PRAGMA journal_mode=WAL')
                print("[STARTUP] SQLite connection established successfully")
        except Exception as e:
            print(f"[STARTUP ERROR] Database connection failed: {e}")
            print(f"[STARTUP ERROR] Full exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def execute(self, query, params=None):
        """Execute a query with parameters. Handles parameter style differences."""
        if params is None:
            params = ()

        if self.is_postgres:
            # PostgreSQL uses %s placeholders
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor
        else:
            # SQLite uses ? placeholders - convert %s to ?
            sqlite_query = query.replace('%s', '?')
            cursor = self.conn.cursor()
            cursor.execute(sqlite_query, params)
            return cursor

    def last_insert_id(self):
        """Get the last inserted ID for the current connection."""
        if self.is_postgres:
            cursor = self.conn.cursor()
            cursor.execute("SELECT lastval()")
            return cursor.fetchone()['lastval']
        else:
            cursor = self.conn.cursor()
            cursor.execute("SELECT last_insert_rowid()")
            return cursor.fetchone()[0]
    
    def executemany(self, query, params):
        """Execute multiple queries with parameters."""
        if self.is_postgres:
            cursor = self.conn.cursor()
            cursor.executemany(query, params)
            return cursor
        else:
            # SQLite uses ? placeholders - convert %s to ?
            sqlite_query = query.replace('%s', '?')
            cursor = self.conn.cursor()
            cursor.executemany(sqlite_query, params)
            return cursor
    
    def commit(self):
        """Commit the transaction."""
        self.conn.commit()
    
    def rollback(self):
        """Rollback the transaction."""
        self.conn.rollback()
    
    def close(self):
        """Close the connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()

def get_db_path():
    """Get the database path and ensure the instance directory exists."""
    instance_path = os.path.join(os.path.dirname(__file__), 'instance')
    os.makedirs(instance_path, exist_ok=True)
    return os.path.join(instance_path, 'database.db')

def get_db():
    """Get a database connection (unified for PostgreSQL and SQLite)."""
    return DatabaseConnection()

def log_activity(user_id, action):
    try:
        conn = get_db()
        from datetime import datetime
        local_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("INSERT INTO activity_log(user_id,action,timestamp) VALUES(%s,%s,%s)", (user_id, action, local_timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"Activity log error: {e}")

def require_role(*roles):
    if session.get("role") not in roles:
        return redirect("/")
    # Enforce profile completion for student/faculty on every protected route
    g = check_profile_complete()
    if g: return g
    return None

def check_profile_complete():
    """Returns a redirect if the logged-in student/faculty hasn't completed
    their profile yet. Returns None if access should proceed normally.
    Admins are never blocked."""
    role = session.get("role")
    if role not in ("student", "faculty"):
        return None
    conn = get_db()
    user = conn.execute("SELECT profile_completed FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    conn.close()
    if user and not user["profile_completed"]:
        return redirect("/complete_profile")
    return None

def is_pass(score, total, pass_pct):
    if not total: return False
    return score >= (pass_pct / 100.0) * total

def gen_code(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

# ── Migrations ───────────────────────────────────────────────────────────────
def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    if DATABASE_URL:
        # PostgreSQL - need to create cursor first
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        """, (table_name,))
        return cursor.fetchone() is not None
    else:
        # SQLite - use ? placeholder
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return c.fetchone() is not None

def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    if DATABASE_URL:
        # PostgreSQL - need to create cursor first
        cursor = conn.cursor()
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cursor.fetchone() is not None
    else:
        # SQLite - use PRAGMA with proper string formatting
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in c.fetchall()]
        return column_name in columns

def migrate_db():
    """Run database migrations for both PostgreSQL and SQLite."""
    print("[STARTUP] migrate_db() called")
    if DATABASE_URL:
        print("[STARTUP] PostgreSQL migration mode")
        # PostgreSQL migration
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
    else:
        # SQLite migration
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()

    # Only run migrations if tables exist (fresh databases are handled by init_db)
    if not table_exists(conn, 'submissions'):
        conn.close()
        return

    # Helper function to add column if it doesn't exist
    def add_column_if_missing(table, column, definition):
        if not column_exists(conn, table, column):
            if DATABASE_URL:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            else:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            conn.commit()
    
    # Check if tab_switches column exists in submissions table
    add_column_if_missing('submissions', 'tab_switches', 'INTEGER DEFAULT 0')
    
    # Check if profile_picture column exists in users table
    add_column_if_missing('users', 'profile_picture', 'TEXT DEFAULT NULL')
    
    # Check if phone column exists in users table
    add_column_if_missing('users', 'phone', 'TEXT DEFAULT NULL')
    
    # Check if pass_mark column exists in exams table
    add_column_if_missing('exams', 'pass_mark', 'INTEGER DEFAULT 50')
    
    # Check if instructions column exists in exams table
    add_column_if_missing('exams', 'instructions', 'TEXT DEFAULT NULL')
    
    # Check if marks column exists in questions table
    add_column_if_missing('questions', 'marks', 'INTEGER DEFAULT 1')
    
    # Check if results_published column exists in submissions table
    add_column_if_missing('submissions', 'results_published', 'INTEGER DEFAULT 0')
    
    # Check if published_at column exists in submissions table
    add_column_if_missing('submissions', 'published_at', 'TIMESTAMP DEFAULT NULL')

    # Check if result_published column exists in submissions table (for submission-level publishing)
    if not column_exists(conn, 'submissions', 'result_published'):
        add_column_if_missing('submissions', 'result_published', 'INTEGER DEFAULT 0')
        # Migrate existing data: mark submissions from already-published exams as published
        cursor.execute("""
            UPDATE submissions
            SET result_published = 1,
                published_at = CURRENT_TIMESTAMP
            WHERE exam_id IN (
                SELECT id FROM exams WHERE published = 1
            )
        """)
        conn.commit()
    
    # Check if total_marks column exists in exams table
    add_column_if_missing('exams', 'total_marks', 'INTEGER DEFAULT 0')
    
    # Check if pass_marks_actual column exists in exams table
    add_column_if_missing('exams', 'pass_marks_actual', 'INTEGER DEFAULT 0')
    
    # Check if pass_percentage column exists in exams table
    add_column_if_missing('exams', 'pass_percentage', 'REAL DEFAULT 50.0')
    
    # Check if marks column exists in question_bank table
    add_column_if_missing('question_bank', 'marks', 'INTEGER DEFAULT 1')
    
    # Add new profile fields for unified profile redesign
    add_column_if_missing('users', 'date_of_birth', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'gender', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'last_profile_update', 'TIMESTAMP DEFAULT NULL')
    add_column_if_missing('users', 'faculty_id', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'designation', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'subject', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'admin_id', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'role_level', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'reg_number', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'program', 'TEXT DEFAULT NULL')
    add_column_if_missing('users', 'section', 'TEXT DEFAULT NULL')
    
    # Backfill submitted_at for old submissions where it was never set
    if DATABASE_URL:
        cursor.execute("SELECT id FROM submissions WHERE submitted_at IS NULL ORDER BY id ASC")
        null_rows = cursor.fetchall()
    else:
        cursor.execute("SELECT id FROM submissions WHERE submitted_at IS NULL ORDER BY id ASC")
        null_rows = cursor.fetchall()
    
    if null_rows:
        base_time = datetime(2026, 1, 1)
        for i, row in enumerate(null_rows):
            fallback_ts = (base_time + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("UPDATE submissions SET submitted_at=%s WHERE id=%s", (fallback_ts, row['id']))
        conn.commit()
    
    # Profile completion workflow
    if not column_exists(conn, 'users', 'profile_completed'):
        add_column_if_missing('users', 'profile_completed', 'INTEGER DEFAULT 0')
        cursor.execute("UPDATE users SET profile_completed=1 WHERE role='admin'")
        cursor.execute("UPDATE users SET profile_completed=1 WHERE role IN ('student','faculty') AND approved=1")
        conn.commit()

    # Archive system columns
    add_column_if_missing('classrooms', 'is_archived', 'INTEGER DEFAULT 0')
    add_column_if_missing('classrooms', 'archived_at', 'TIMESTAMP DEFAULT NULL')
    add_column_if_missing('classrooms', 'archived_by', 'INTEGER DEFAULT NULL')
    add_column_if_missing('exams', 'is_archived', 'INTEGER DEFAULT 0')
    add_column_if_missing('exams', 'archived_at', 'TIMESTAMP DEFAULT NULL')
    add_column_if_missing('exams', 'archived_by', 'INTEGER DEFAULT NULL')

    conn.close()

# ── Init DB ────────────────────────────────────────────────────────────────
def init_db():
    """Initialize database for both PostgreSQL and SQLite."""
    print("[STARTUP] init_db() called")
    if DATABASE_URL:
        print("[STARTUP] PostgreSQL mode detected, calling init_postgres_db()...")
        # PostgreSQL initialization
        init_postgres_db()
        print("[STARTUP] init_postgres_db() completed")
    else:
        print("[STARTUP] SQLite mode detected, calling init_sqlite_db()...")
        # SQLite initialization
        init_sqlite_db()
        print("[STARTUP] init_sqlite_db() completed")
    print("[STARTUP] init_db() completed")

def init_postgres_db():
    """Initialize PostgreSQL database with schema and default admin."""
    try:
        print("[STARTUP] init_postgres_db() called")
        print("[STARTUP] Connecting to PostgreSQL for initialization...")
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        print("[STARTUP] PostgreSQL connection established for initialization")
        cursor = conn.cursor()

        # Check if users table exists
        print("[STARTUP] Checking if users table exists...")
        if not table_exists(conn, 'users'):
            print("[STARTUP] Users table does not exist, creating schema...")

            # Create users table with all columns
            print("[STARTUP] Creating users table...")
            cursor.execute("""
                CREATE TABLE users(
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    email TEXT UNIQUE,
                    password TEXT,
                    role TEXT,
                    approved INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    profile_picture TEXT DEFAULT NULL,
                    phone TEXT DEFAULT NULL,
                    department TEXT DEFAULT '',
                    last_login TIMESTAMP,
                    date_of_birth TEXT DEFAULT NULL,
                    gender TEXT DEFAULT NULL,
                    last_profile_update TIMESTAMP DEFAULT NULL,
                    faculty_id TEXT DEFAULT NULL,
                    designation TEXT DEFAULT NULL,
                    subject TEXT DEFAULT NULL,
                    admin_id TEXT DEFAULT NULL,
                    role_level TEXT DEFAULT NULL,
                    reg_number TEXT DEFAULT NULL,
                    program TEXT DEFAULT NULL,
                    section TEXT DEFAULT NULL,
                    profile_completed INTEGER DEFAULT 0,
                    theme_preference TEXT DEFAULT 'light'
                )
            """)
            print("[STARTUP] Users table created successfully")

            # Create exams table
            print("[STARTUP] Creating exams table...")
            cursor.execute("""
                CREATE TABLE exams(
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    faculty_id INTEGER,
                    duration INTEGER,
                    exam_date TEXT,
                    subject TEXT DEFAULT '',
                    published INTEGER DEFAULT 0,
                    launched INTEGER DEFAULT 0,
                    classroom_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pass_mark INTEGER DEFAULT 50,
                    instructions TEXT DEFAULT NULL,
                    total_marks INTEGER DEFAULT 0,
                    pass_marks_actual INTEGER DEFAULT 0,
                    pass_percentage REAL DEFAULT 50.0,
                    is_archived INTEGER DEFAULT 0,
                    archived_at TIMESTAMP DEFAULT NULL,
                    archived_by INTEGER DEFAULT NULL
                )
            """)
            print("[STARTUP] Exams table created successfully")

            # Create questions table
            print("[STARTUP] Creating questions table...")
            cursor.execute("""
                CREATE TABLE questions(
                    id SERIAL PRIMARY KEY,
                    exam_id INTEGER,
                    question TEXT,
                    option1 TEXT,
                    option2 TEXT,
                    option3 TEXT,
                    option4 TEXT,
                    correct_answer TEXT,
                    difficulty TEXT DEFAULT 'medium',
                    marks INTEGER DEFAULT 1
                )
            """)
            print("[STARTUP] Questions table created successfully")

            # Create question_bank table
            print("[STARTUP] Creating question_bank table...")
            cursor.execute("""
                CREATE TABLE question_bank(
                    id SERIAL PRIMARY KEY,
                    question TEXT,
                    option1 TEXT,
                    option2 TEXT,
                    option3 TEXT,
                    option4 TEXT,
                    correct_answer TEXT,
                    category TEXT,
                    difficulty TEXT DEFAULT 'medium',
                    faculty_id INTEGER,
                    marks INTEGER DEFAULT 1
                )
            """)
            print("[STARTUP] Question_bank table created successfully")

            # Create submissions table
            print("[STARTUP] Creating submissions table...")
            cursor.execute("""
                CREATE TABLE submissions(
                    id SERIAL PRIMARY KEY,
                    student_id INTEGER,
                    exam_id INTEGER,
                    score INTEGER,
                    tab_switches INTEGER DEFAULT 0,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    results_published INTEGER DEFAULT 0,
                    result_published INTEGER DEFAULT 0,
                    published_at TIMESTAMP DEFAULT NULL
                )
            """)
            print("[STARTUP] Submissions table created successfully")

            # Create activity_log table
            print("[STARTUP] Creating activity_log table...")
            cursor.execute("""
                CREATE TABLE activity_log(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    action TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("[STARTUP] Activity_log table created successfully")

            # Create submission_answers table
            print("[STARTUP] Creating submission_answers table...")
            cursor.execute("""
                CREATE TABLE submission_answers(
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER,
                    question_id INTEGER,
                    student_answer TEXT DEFAULT ''
                )
            """)
            print("[STARTUP] Submission_answers table created successfully")

            # Create classrooms table
            print("[STARTUP] Creating classrooms table...")
            cursor.execute("""
                CREATE TABLE classrooms(
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    subject TEXT DEFAULT '',
                    code TEXT UNIQUE,
                    faculty_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_archived INTEGER DEFAULT 0,
                    archived_at TIMESTAMP DEFAULT NULL,
                    archived_by INTEGER DEFAULT NULL
                )
            """)
            print("[STARTUP] Classrooms table created successfully")

            # Create classroom_members table
            print("[STARTUP] Creating classroom_members table...")
            cursor.execute("""
                CREATE TABLE classroom_members(
                    id SERIAL PRIMARY KEY,
                    classroom_id INTEGER,
                    student_id INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(classroom_id, student_id)
                )
            """)
            print("[STARTUP] Classroom_members table created successfully")

            # Create exam_attempts table
            print("[STARTUP] Creating exam_attempts table...")
            cursor.execute("""
                CREATE TABLE exam_attempts(
                    id SERIAL PRIMARY KEY,
                    student_id INTEGER,
                    exam_id INTEGER,
                    current_question INTEGER DEFAULT 0,
                    remaining_time INTEGER DEFAULT 0,
                    answers TEXT DEFAULT '{}',
                    last_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(student_id, exam_id)
                )
            """)
            print("[STARTUP] Exam_attempts table created successfully")

            print("[STARTUP] All tables created successfully, committing...")
            conn.commit()
            print("[STARTUP] Tables committed successfully")

            # Create default admin account using environment variables or fallback
            print("[STARTUP] Creating default admin account...")
            default_admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@mail.com")
            default_admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")
            admin_password = generate_password_hash(default_admin_password)
            print(f"[STARTUP] Admin email: {default_admin_email}")
            cursor.execute(
                "INSERT INTO users(name, email, password, role, approved, profile_completed) VALUES(%s,%s,%s,%s,%s,%s)",
                ("Admin", default_admin_email, admin_password, "admin", 1, 1)
            )
            print("[STARTUP] Default admin account inserted")
            conn.commit()
            print("[STARTUP] Default admin account committed")
            print("[STARTUP] init_postgres_db() completed successfully")
        else:
            print("[STARTUP] Users table already exists, skipping schema creation")
    except Exception as e:
        print(f"[STARTUP ERROR] init_postgres_db() failed: {e}")
        print(f"[STARTUP ERROR] Full exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if 'conn' in locals():
            conn.close()

    # Clean up orphan records on startup
    cleanup_orphan_records()

    # Clean up duplicate submissions on startup
    cleanup_duplicate_submissions()

def init_sqlite_db():
    """Initialize SQLite database with schema and default admin."""
    db_path = get_db_path()
    
    # Check if database file exists
    db_exists = os.path.exists(db_path)
    
    # If database doesn't exist, create fresh database with schema and default admin
    if not db_exists:
        conn = sqlite3.connect(db_path, timeout=30)
        c = conn.cursor()
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        
        # Create users table with all columns
        c.execute("""
            CREATE TABLE users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password TEXT,
                role TEXT,
                approved INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                profile_picture TEXT DEFAULT NULL,
                phone TEXT DEFAULT NULL,
                department TEXT DEFAULT '',
                last_login DATETIME,
                date_of_birth TEXT DEFAULT NULL,
                gender TEXT DEFAULT NULL,
                last_profile_update DATETIME DEFAULT NULL,
                faculty_id TEXT DEFAULT NULL,
                designation TEXT DEFAULT NULL,
                subject TEXT DEFAULT NULL,
                admin_id TEXT DEFAULT NULL,
                role_level TEXT DEFAULT NULL,
                reg_number TEXT DEFAULT NULL,
                program TEXT DEFAULT NULL,
                section TEXT DEFAULT NULL,
                profile_completed INTEGER DEFAULT 0,
                theme_preference TEXT DEFAULT 'light'
            )
        """)
        
        # Create exams table
        c.execute("""
            CREATE TABLE exams(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                faculty_id INTEGER,
                duration INTEGER,
                exam_date TEXT,
                subject TEXT DEFAULT '',
                published INTEGER DEFAULT 0,
                launched INTEGER DEFAULT 0,
                classroom_id INTEGER DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create questions table
        c.execute("""
            CREATE TABLE questions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER,
                question TEXT,
                option1 TEXT,
                option2 TEXT,
                option3 TEXT,
                option4 TEXT,
                correct_answer TEXT,
                difficulty TEXT DEFAULT 'medium'
            )
        """)
        
        # Create question_bank table
        c.execute("""
            CREATE TABLE question_bank(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                option1 TEXT,
                option2 TEXT,
                option3 TEXT,
                option4 TEXT,
                correct_answer TEXT,
                category TEXT,
                difficulty TEXT DEFAULT 'medium',
                faculty_id INTEGER
            )
        """)
        
        # Create submissions table
        c.execute("""
            CREATE TABLE submissions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                exam_id INTEGER,
                score INTEGER,
                tab_switches INTEGER DEFAULT 0,
                submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create activity_log table
        c.execute("""
            CREATE TABLE activity_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create submission_answers table
        c.execute("""
            CREATE TABLE submission_answers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER,
                question_id INTEGER,
                student_answer TEXT DEFAULT ''
            )
        """)
        
        # Create classrooms table
        c.execute("""
            CREATE TABLE classrooms(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                subject TEXT DEFAULT '',
                code TEXT UNIQUE,
                faculty_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create classroom_members table
        c.execute("""
            CREATE TABLE classroom_members(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classroom_id INTEGER,
                student_id INTEGER,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(classroom_id, student_id)
            )
        """)
        
        # Create exam_attempts table
        c.execute("""
            CREATE TABLE exam_attempts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                exam_id INTEGER,
                current_question INTEGER DEFAULT 0,
                remaining_time INTEGER DEFAULT 0,
                answers TEXT DEFAULT '{}',
                last_saved DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, exam_id)
            )
        """)
        
        # Create default admin account using environment variables or fallback
        default_admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@mail.com")
        default_admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")
        admin_password = generate_password_hash(default_admin_password)
        c.execute(
            "INSERT INTO users(name, email, password, role, approved, profile_completed) VALUES(?,?,?,?,?,?)",
            ("Admin", default_admin_email, admin_password, "admin", 1, 1)
        )
        
        conn.commit()
        conn.close()
        return
    
    # If database exists, run migration logic
    conn = sqlite3.connect(db_path, timeout=30)
    c = conn.cursor()
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    # Check if email column has UNIQUE constraint, add it if missing
    c.execute("PRAGMA table_info(users)")
    columns = c.fetchall()
    email_col = next((col for col in columns if col[1] == "email"), None)
    if email_col and email_col[5] is None:  # No UNIQUE constraint
        # Create a new table with UNIQUE constraint on email
        c.execute("""
            CREATE TABLE IF NOT EXISTS users_new(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
                password TEXT, role TEXT, approved INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
        """)
        # Copy data from old table to new table
        c.execute("""
            INSERT INTO users_new (id, name, email, password, role, approved, created_at)
            SELECT id, name, email, password, role, approved, created_at FROM users
        """)
        # Drop old table and rename new table
        c.execute("DROP TABLE users")
        c.execute("ALTER TABLE users_new RENAME TO users")
        conn.commit()
    
    # Add missing columns if they don't exist
    c.execute("PRAGMA table_info(users)")
    columns = c.fetchall()
    column_names = [col[1] for col in columns]
    
    if "profile_picture" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN profile_picture TEXT DEFAULT NULL")
    if "phone" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT NULL")
    if "department" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT ''")
    if "last_login" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN last_login DATETIME")
    if "date_of_birth" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN date_of_birth TEXT DEFAULT NULL")
    if "gender" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN gender TEXT DEFAULT NULL")
    if "last_profile_update" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN last_profile_update DATETIME DEFAULT NULL")
    if "faculty_id" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN faculty_id TEXT DEFAULT NULL")
    if "designation" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN designation TEXT DEFAULT NULL")
    if "subject" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN subject TEXT DEFAULT NULL")
    if "admin_id" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN admin_id TEXT DEFAULT NULL")
    if "role_level" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN role_level TEXT DEFAULT NULL")
    if "reg_number" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN reg_number TEXT DEFAULT NULL")
    if "program" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN program TEXT DEFAULT NULL")
    if "section" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN section TEXT DEFAULT NULL")
    if "profile_completed" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN profile_completed INTEGER DEFAULT 0")
    if "theme_preference" not in column_names:
        c.execute("ALTER TABLE users ADD COLUMN theme_preference TEXT DEFAULT 'light'")
    
    # Set default theme to 'light' for all existing users with NULL or invalid theme values
    c.execute("UPDATE users SET theme_preference='light' WHERE theme_preference IS NULL OR theme_preference NOT IN ('light', 'dark')")
    conn.commit()
    
    conn.commit()
    c.execute("""CREATE TABLE IF NOT EXISTS exams(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, faculty_id INTEGER,
        duration INTEGER, exam_date TEXT, subject TEXT DEFAULT '',
        published INTEGER DEFAULT 0, launched INTEGER DEFAULT 0,
        classroom_id INTEGER DEFAULT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER, question TEXT,
        option1 TEXT, option2 TEXT, option3 TEXT, option4 TEXT,
        correct_answer TEXT, difficulty TEXT DEFAULT 'medium')""")
    c.execute("""CREATE TABLE IF NOT EXISTS question_bank(
        id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
        option1 TEXT, option2 TEXT, option3 TEXT, option4 TEXT,
        correct_answer TEXT, category TEXT, difficulty TEXT DEFAULT 'medium',
        faculty_id INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS submissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, exam_id INTEGER,
        score INTEGER, tab_switches INTEGER DEFAULT 0,
        submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS activity_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS submission_answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER, question_id INTEGER,
        student_answer TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS classrooms(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, subject TEXT DEFAULT '',
        code TEXT UNIQUE, faculty_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS classroom_members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classroom_id INTEGER, student_id INTEGER,
        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(classroom_id, student_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS exam_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER, exam_id INTEGER,
        current_question INTEGER DEFAULT 0,
        remaining_time INTEGER DEFAULT 0,
        answers TEXT DEFAULT '{}',
        last_saved DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, exam_id))""")
    # seed admin - check for existing admin by role, not by hardcoded email
    c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not c.fetchone():
        default_admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@mail.com")
        default_admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")
        pw = generate_password_hash(default_admin_password)
        c.execute("INSERT OR IGNORE INTO users(name,email,password,role,approved) VALUES(?,?,?,?,?)", ("Admin",default_admin_email,pw,"admin",1))
    conn.commit()
    conn.close()
    
    # Clean up orphan records on startup
    cleanup_orphan_records()
    
    # Clean up duplicate submissions on startup
    cleanup_duplicate_submissions()

def cleanup_orphan_records():
    """Remove orphan records from all tables to ensure data integrity."""
    conn = get_db()
    
    try:
        # Remove submission_answers where submission_id doesn't exist in submissions
        cursor = conn.execute("""
            DELETE FROM submission_answers
            WHERE submission_id NOT IN (SELECT id FROM submissions)
        """)
        orphan_answers = cursor.rowcount
        
        # Remove submission_answers where question_id doesn't exist in questions
        cursor = conn.execute("""
            DELETE FROM submission_answers
            WHERE question_id NOT IN (SELECT id FROM questions)
        """)
        orphan_answers += cursor.rowcount
        
        # Remove submissions where student_id doesn't exist in users
        cursor = conn.execute("""
            DELETE FROM submissions
            WHERE student_id NOT IN (SELECT id FROM users)
        """)
        orphan_submissions = cursor.rowcount
        
        # Remove submissions where exam_id doesn't exist in exams
        cursor = conn.execute("""
            DELETE FROM submissions
            WHERE exam_id NOT IN (SELECT id FROM exams)
        """)
        orphan_submissions += cursor.rowcount
        
        # Remove exam_attempts where student_id doesn't exist in users
        cursor = conn.execute("""
            DELETE FROM exam_attempts
            WHERE student_id NOT IN (SELECT id FROM users)
        """)
        orphan_attempts = cursor.rowcount
        
        # Remove exam_attempts where exam_id doesn't exist in exams
        cursor = conn.execute("""
            DELETE FROM exam_attempts
            WHERE exam_id NOT IN (SELECT id FROM exams)
        """)
        orphan_attempts += cursor.rowcount
        
        # Remove classroom_members where classroom_id doesn't exist in classrooms
        cursor = conn.execute("""
            DELETE FROM classroom_members
            WHERE classroom_id NOT IN (SELECT id FROM classrooms)
        """)
        orphan_members = cursor.rowcount
        
        # Remove classroom_members where student_id doesn't exist in users
        cursor = conn.execute("""
            DELETE FROM classroom_members
            WHERE student_id NOT IN (SELECT id FROM users)
        """)
        orphan_members += cursor.rowcount
        
        # Remove questions where exam_id doesn't exist in exams
        cursor = conn.execute("""
            DELETE FROM questions
            WHERE exam_id NOT IN (SELECT id FROM exams)
        """)
        orphan_questions = cursor.rowcount
        
        # Remove question_bank where faculty_id doesn't exist in users
        cursor = conn.execute("""
            DELETE FROM question_bank
            WHERE faculty_id NOT IN (SELECT id FROM users)
        """)
        orphan_bank = cursor.rowcount
        
        conn.commit()
        
        app.logger.info(f"Cleanup completed: {orphan_answers} orphan answers, {orphan_submissions} orphan submissions, {orphan_attempts} orphan attempts, {orphan_members} orphan members, {orphan_questions} orphan questions, {orphan_bank} orphan bank entries removed")
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Cleanup failed: {e}")
        raise
    finally:
        conn.close()

def cleanup_duplicate_submissions():
    """Remove duplicate submissions, keeping only the latest valid submission per (student_id, exam_id)."""
    conn = get_db()
    
    try:
        # Find duplicate submissions (same student_id, exam_id)
        cursor = conn.execute("""
            SELECT student_id, exam_id, COUNT(*) as submission_count
            FROM submissions
            GROUP BY student_id, exam_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()

        if not duplicates:
            app.logger.info("No duplicate submissions found")
            conn.close()
            return

        # For each duplicate pair, keep the latest submission and delete the rest
        for student_id, exam_id, submission_count in duplicates:
            # Get all submissions for this student/exam, ordered by submitted_at DESC (latest first)
            cursor = conn.execute("""
                SELECT id, submitted_at
                FROM submissions
                WHERE student_id = %s AND exam_id = %s
                ORDER BY submitted_at DESC
            """, (student_id, exam_id))
            submissions = cursor.fetchall()
            
            # Keep the first (latest) one, delete the rest
            keep_id = submissions[0][0]
            delete_ids = [sub[0] for sub in submissions[1:]]
            
            # Delete submission_answers for the duplicate submissions
            for sub_id in delete_ids:
                conn.execute("DELETE FROM submission_answers WHERE submission_id = %s", (sub_id,))
            
            # Delete the duplicate submissions
            for sub_id in delete_ids:
                conn.execute("DELETE FROM submissions WHERE id = %s", (sub_id,))
            
            app.logger.info(f"Removed {len(delete_ids)} duplicate submissions for student_id={student_id}, exam_id={exam_id}, keeping submission_id={keep_id}")
        
        conn.commit()
        conn.close()
        app.logger.info(f"Duplicate cleanup completed: processed {len(duplicates)} duplicate sets")
        
    except Exception as e:
        conn.rollback()
        conn.close()
        app.logger.error(f"Duplicate cleanup failed: {e}")
        raise

def validate_schema(conn):
    """Validate database schema and log missing items without crashing."""
    try:
        # Check required tables
        if DATABASE_URL:
            # PostgreSQL
            cursor = conn.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row['table_name'] for row in cursor.fetchall()]
        else:
            # SQLite - access underlying connection
            c = conn.conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in c.fetchall()]
        
        required_tables = ['users', 'exams', 'questions', 'submissions', 'classrooms', 'classroom_members', 'activity_log']
        for table in required_tables:
            if table not in tables:
                app.logger.warning(f"Schema validation: Required table '{table}' is missing")
        
        # Check required columns in exams table
        if DATABASE_URL:
            cursor = conn.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'exams'
            """)
            exam_columns = [row['column_name'] for row in cursor.fetchall()]
        else:
            c = conn.conn.cursor()
            c.execute("PRAGMA table_info(exams)")
            exam_columns = [row[1] for row in c.fetchall()]
        
        required_exam_columns = ['id', 'title', 'faculty_id', 'published', 'created_at']
        for col in required_exam_columns:
            if col not in exam_columns:
                app.logger.warning(f"Schema validation: exams table missing required column '{col}'")
        
        # Check required columns in submissions table
        if DATABASE_URL:
            cursor = conn.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'submissions'
            """)
            submission_columns = [row['column_name'] for row in cursor.fetchall()]
        else:
            c = conn.conn.cursor()
            c.execute("PRAGMA table_info(submissions)")
            submission_columns = [row[1] for row in c.fetchall()]
        
        required_submission_columns = ['id', 'student_id', 'exam_id', 'score']
        for col in required_submission_columns:
            if col not in submission_columns:
                app.logger.warning(f"Schema validation: submissions table missing required column '{col}'")
        
        # Check required columns in classrooms table
        if DATABASE_URL:
            cursor = conn.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'classrooms'
            """)
            classroom_columns = [row['column_name'] for row in cursor.fetchall()]
        else:
            c = conn.conn.cursor()
            c.execute("PRAGMA table_info(classrooms)")
            classroom_columns = [row[1] for row in c.fetchall()]
        required_classroom_columns = ['id', 'name', 'faculty_id']
        for col in required_classroom_columns:
            if col not in classroom_columns:
                app.logger.warning(f"Schema validation: classrooms table missing required column '{col}'")
        
        # Check required columns in classroom_members table
        if DATABASE_URL:
            cursor = conn.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'classroom_members'
            """)
            member_columns = [row['column_name'] for row in cursor.fetchall()]
        else:
            c = conn.conn.cursor()
            c.execute("PRAGMA table_info(classroom_members)")
            member_columns = [row[1] for row in c.fetchall()]
        required_member_columns = ['id', 'classroom_id', 'student_id']
        for col in required_member_columns:
            if col not in member_columns:
                app.logger.warning(f"Schema validation: classroom_members table missing required column '{col}'")
        
        app.logger.info("Schema validation completed")
    except Exception as e:
        app.logger.exception(f"Schema validation failed: {e}")

# ── Startup Sequence ──────────────────────────────────────────────────────────
print("[STARTUP] ===== Starting EduSphere Application =====")
print("[STARTUP] Initializing database...")
# Initialize database first (creates schema for fresh deployments)
init_db()
print("[STARTUP] Database initialization completed")
print("[STARTUP] Running migrations...")
# Then run migrations for existing databases
migrate_db()
print("[STARTUP] Migrations completed")
print("[STARTUP] ===== Startup Sequence Completed =====")

# Validate schema at startup
conn = get_db()
validate_schema(conn)
conn.close()

# ═══════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/")
def home(): return render_template("auth/login.html")

@app.route("/login", methods=["POST"])
def login():
    print(f"[LOGIN] Login attempt received")
    email = request.form["email"]; password = request.form["password"]; role = request.form["role"]
    print(f"[LOGIN] Email: {email}, Role: {role}")
    print(f"[LOGIN] Getting database connection...")
    conn = get_db()
    print(f"[LOGIN] Database connection established")
    print(f"[LOGIN] Executing user query...")
    user = conn.execute("SELECT * FROM users WHERE email=%s AND role=%s", (email,role)).fetchone()
    print(f"[LOGIN] User query completed, user found: {user is not None}")
    if not user:
        conn.close()
        return render_template("auth/login.html", error="Invalid email or role")
    print(f"[LOGIN] Checking password...")
    if not check_password_hash(user["password"], password):
        conn.close()
        return render_template("auth/login.html", error="Incorrect password")
    print(f"[LOGIN] Password verified")
    if user["approved"] == 0:
        conn.close()
        return render_template("auth/login.html", error="Account pending admin approval")
    print(f"[LOGIN] Setting session variables...")
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["name"]
    session["email"] = user["email"]
    if "phone" in user.keys() and user["phone"]:
        session["phone"] = user["phone"]
    if "profile_picture" in user.keys() and user["profile_picture"]:
        session["profile_pic"] = user["profile_picture"]
    # Load theme preference from database, default to 'light' if not set
    db_theme = user["theme_preference"] if ("theme_preference" in user.keys() and user["theme_preference"] in ("light","dark")) else None
    session["theme_preference"] = db_theme or "light"
    # Update last_login if column exists
    if "last_login" in user.keys():
        conn.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=%s", (user["id"],))
    print(f"[LOGIN] Logging activity...")
    log_activity(user["id"], "Logged in")
    browser_theme = request.cookies.get("es_theme")
    if browser_theme in ("light", "dark"):
        final_theme = browser_theme
        conn.execute("UPDATE users SET theme_preference=%s WHERE id=%s", (final_theme, user["id"]))
    else:
        final_theme = session["theme_preference"]
    conn.commit()
    conn.close()
    dest = "/complete_profile" if (role in ("student", "faculty") and "profile_completed" in user.keys() and not user["profile_completed"]) else {"admin":"/admin","faculty":"/faculty"}.get(role,"/student")
    resp = redirect(dest)
    resp.set_cookie("es_theme", final_theme, max_age=60*60*24*365, samesite="Lax", httponly=False)
    return resp

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        name=request.form["name"]; email=request.form["email"]
        password=request.form["password"]; confirm_password=request.form.get("confirm_password", "")
        role=request.form["role"]
        if password != confirm_password:
            return render_template("auth/signup.html", error="Passwords do not match.")
        password=generate_password_hash(password)
        if role == "admin":
            return render_template("auth/signup.html", error="Admin accounts cannot be created here.")
        approved = 1 if role == "student" else 0
        conn = get_db()
        try:
            conn.execute("INSERT INTO users(name,email,password,role,approved) VALUES(%s,%s,%s,%s,%s)", (name,email,password,role,approved))
            conn.commit()
            conn.close()
        except: 
            conn.close()
            return render_template("auth/signup.html", error="Email already registered")
        flash("Account created! Please log in.", "success")
        return redirect("/")
    return render_template("auth/signup.html")

@app.route("/logout")
def logout():
    if session.get("user_id"): log_activity(session["user_id"], "Logged out")
    session.clear()
    return redirect("/")

# ── Theme Toggle ───────────────────────────────────────────────────────────────
@app.route("/toggle_theme", methods=["POST"])
def toggle_theme():
    new_theme = request.json.get("theme", "light")
    if new_theme not in ["light", "dark"]:
        return jsonify({"success": False, "error": "Invalid theme"}), 400
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE users SET theme_preference=%s WHERE id=%s", (new_theme, session["user_id"]))
        conn.commit()
        session["theme_preference"] = new_theme
        conn.close()
    resp = jsonify({"success": True, "theme": new_theme})
    resp.set_cookie("es_theme", new_theme, max_age=60*60*24*365, samesite="Lax", httponly=False)
    return resp

# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVE CENTER — Faculty
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/faculty/archive")
def faculty_archive():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    fid = session["user_id"]
    archived_classrooms = conn.execute("""
        SELECT * FROM classrooms
        WHERE faculty_id=%s AND is_archived=1
        ORDER BY archived_at DESC
    """, (fid,)).fetchall()
    archived_exams = conn.execute("""
        SELECT e.*, c.name as classroom_name
        FROM exams e
        LEFT JOIN classrooms c ON c.id = e.classroom_id
        WHERE e.faculty_id=%s AND e.is_archived=1
        ORDER BY e.archived_at DESC
    """, (fid,)).fetchall()
    conn.close()
    return render_template("faculty/faculty_archive.html",
                           archived_classrooms=archived_classrooms,
                           archived_exams=archived_exams)


@app.route("/faculty/archive/restore_classroom/<int:cid>")
def restore_classroom(cid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id=%s AND faculty_id=%s AND is_archived=1",
        (cid, session["user_id"])
    ).fetchone()
    if not classroom:
        conn.close()
        flash("Archived classroom not found.", "danger")
        return redirect("/faculty/archive")
    # Restore classroom and its exams
    conn.execute("""UPDATE classrooms SET is_archived=0, archived_at=NULL, archived_by=NULL
                    WHERE id=%s AND faculty_id=%s""", (cid, session["user_id"]))
    conn.execute("""UPDATE exams SET is_archived=0, archived_at=NULL, archived_by=NULL
                    WHERE classroom_id=%s AND faculty_id=%s""", (cid, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Restored classroom: {classroom['name']}")
    flash(f"Classroom \"{classroom['name']}\" has been restored.", "success")
    return redirect("/faculty/archive")


@app.route("/faculty/archive/restore_exam/<int:eid>")
def restore_exam(eid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute(
        "SELECT * FROM exams WHERE id=%s AND faculty_id=%s AND is_archived=1",
        (eid, session["user_id"])
    ).fetchone()
    if not exam:
        conn.close()
        flash("Archived exam not found.", "danger")
        return redirect("/faculty/archive")
    conn.execute("""UPDATE exams SET is_archived=0, archived_at=NULL, archived_by=NULL
                    WHERE id=%s AND faculty_id=%s""", (eid, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Restored exam: {exam['title']}")
    flash(f"Exam \"{exam['title']}\" has been restored.", "success")
    return redirect("/faculty/archive")


@app.route("/faculty/archive/delete_classroom/<int:cid>")
def permanently_delete_classroom(cid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    classroom = conn.execute(
        "SELECT * FROM classrooms WHERE id=%s AND faculty_id=%s AND is_archived=1",
        (cid, session["user_id"])
    ).fetchone()
    if not classroom:
        conn.close()
        flash("Archived classroom not found.", "danger")
        return redirect("/faculty/archive")
    # Permanently delete classroom and related data
    exam_ids = [r[0] for r in conn.execute(
        "SELECT id FROM exams WHERE classroom_id=%s AND faculty_id=%s",
        (cid, session["user_id"])
    ).fetchall()]
    for eid in exam_ids:
        conn.execute("DELETE FROM submission_answers WHERE submission_id IN (SELECT id FROM submissions WHERE exam_id=%s)", (eid,))
        conn.execute("DELETE FROM submissions WHERE exam_id=%s", (eid,))
        conn.execute("DELETE FROM exam_attempts WHERE exam_id=%s", (eid,))
        conn.execute("DELETE FROM questions WHERE exam_id=%s", (eid,))
        conn.execute("DELETE FROM exams WHERE id=%s", (eid,))
    conn.execute("DELETE FROM classroom_members WHERE classroom_id=%s", (cid,))
    conn.execute("DELETE FROM classrooms WHERE id=%s AND faculty_id=%s", (cid, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Permanently deleted classroom: {classroom['name']}")
    flash(f"Classroom \"{classroom['name']}\" permanently deleted.", "success")
    return redirect("/faculty/archive")


@app.route("/faculty/archive/delete_exam/<int:eid>")
def permanently_delete_exam(eid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute(
        "SELECT * FROM exams WHERE id=%s AND faculty_id=%s AND is_archived=1",
        (eid, session["user_id"])
    ).fetchone()
    if not exam:
        conn.close()
        flash("Archived exam not found.", "danger")
        return redirect("/faculty/archive")
    conn.execute("DELETE FROM submission_answers WHERE submission_id IN (SELECT id FROM submissions WHERE exam_id=%s)", (eid,))
    conn.execute("DELETE FROM submissions WHERE exam_id=%s", (eid,))
    conn.execute("DELETE FROM exam_attempts WHERE exam_id=%s", (eid,))
    conn.execute("DELETE FROM questions WHERE exam_id=%s", (eid,))
    conn.execute("DELETE FROM exams WHERE id=%s AND faculty_id=%s", (eid, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Permanently deleted exam: {exam['title']}")
    flash(f"Exam \"{exam['title']}\" permanently deleted.", "success")
    return redirect("/faculty/archive")


@app.route("/complete_profile", methods=["GET","POST"])
def complete_profile():
    if "user_id" not in session or session.get("role") not in ("student","faculty"):
        return redirect("/")
    # If already complete, send to dashboard
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    if user and user["profile_completed"]:
        conn.close()
        return redirect("/faculty" if session["role"] == "faculty" else "/student")

    if request.method == "POST":
        name  = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        date_of_birth = request.form.get("date_of_birth","").strip()
        gender = request.form.get("gender","").strip()

        errors = []
        if not name:  errors.append("Full Name is required.")
        if not phone: errors.append("Phone Number is required.")

        if session["role"] == "student":
            reg_number = request.form.get("reg_number","").strip()
            program    = request.form.get("program","").strip()
            section    = request.form.get("section","").strip()
            if not reg_number: errors.append("Registration Number is required.")
            if not program:    errors.append("Program / Course is required.")
            if not section:    errors.append("Section / Batch is required.")
            if errors:
                conn.close()
                return render_template("auth/complete_profile.html", user=dict(user), errors=errors)
            conn.execute("""UPDATE users SET name=%s, phone=%s, date_of_birth=%s, gender=%s,
                            reg_number=%s, program=%s, section=%s, profile_completed=1,
                            last_profile_update=%s WHERE id=%s""",
                         (name, phone, date_of_birth, gender, reg_number, program, section,
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"]))
        else:  # faculty
            faculty_id_field = request.form.get("faculty_id","").strip()
            designation      = request.form.get("designation","").strip()
            subject          = request.form.get("subject","").strip()
            if not faculty_id_field: errors.append("Faculty ID is required.")
            if not designation:      errors.append("Designation is required.")
            if not subject:          errors.append("Subject is required.")
            if errors:
                conn.close()
                return render_template("auth/complete_profile.html", user=dict(user), errors=errors)
            conn.execute("""UPDATE users SET name=%s, phone=%s, date_of_birth=%s, gender=%s,
                            faculty_id=%s, designation=%s, subject=%s, profile_completed=1,
                            last_profile_update=%s WHERE id=%s""",
                         (name, phone, date_of_birth, gender, faculty_id_field, designation,
                          subject, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"]))

        conn.commit()
        conn.close()
        session["name"] = name
        log_activity(session["user_id"], "Completed profile setup")
        flash("Profile completed! Welcome to EduSphere.", "success")
        return redirect("/faculty" if session["role"] == "faculty" else "/student")

    conn.close()
    return render_template("auth/complete_profile.html", user=dict(user), errors=[])


@app.route("/admin")
def admin():
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    students = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='student'").fetchone()['count']
    faculty  = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='faculty'").fetchone()['count']
    active_faculty = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='faculty' AND approved=1").fetchone()['count']
    pending_faculty = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='faculty' AND approved=0").fetchone()['count']
    exams    = conn.execute("SELECT COUNT(*) as count FROM exams").fetchone()['count']
    total_classrooms = conn.execute("SELECT COUNT(*) as count FROM classrooms").fetchone()['count']
    active_exams = conn.execute("SELECT COUNT(*) as count FROM exams WHERE published=1 AND launched=1").fetchone()['count']
    pending  = conn.execute("SELECT * FROM users WHERE role='faculty' AND approved=0").fetchall()
    
    # Faculty list with stats
    faculty_list = conn.execute("""
        SELECT u.id, u.name, u.email, u.approved, u.created_at, u.profile_picture,
               COUNT(DISTINCT c.id) as classroom_count,
               COUNT(DISTINCT e.id) as exam_count,
               COUNT(DISTINCT cm.student_id) as student_count
        FROM users u
        LEFT JOIN classrooms c ON c.faculty_id = u.id
        LEFT JOIN exams e ON e.faculty_id = u.id
        LEFT JOIN classroom_members cm ON cm.classroom_id = c.id
        WHERE u.role='faculty'
        GROUP BY u.id, u.name, u.email, u.approved, u.created_at, u.profile_picture
        ORDER BY u.created_at DESC
    """).fetchall()
    
    # Classroom list with student count
    classroom_list = conn.execute("""
        SELECT c.id, c.name, c.subject, c.code, c.faculty_id, c.created_at,
               COUNT(cm.student_id) as student_count
        FROM classrooms c
        LEFT JOIN classroom_members cm ON cm.classroom_id = c.id
        GROUP BY c.id, c.name, c.subject, c.code, c.faculty_id, c.created_at
        ORDER BY c.created_at DESC
    """).fetchall()
    
    # quick statistics - submission-level publication stats (only valid records)
    try:
        # Total Submissions - count all valid submissions
        total_submissions = conn.execute("""
            SELECT COUNT(*) as count FROM submissions s
            JOIN users u ON u.id = s.student_id
            JOIN exams e ON e.id = s.exam_id
        """).fetchone()['count']
        
        # Pending Results - count unpublished submissions
        pending_results = conn.execute("""
            SELECT COUNT(*) as count FROM submissions s
            JOIN users u ON u.id = s.student_id
            JOIN exams e ON e.id = s.exam_id
            WHERE s.result_published=0
        """).fetchone()['count']
        
        # Published Results - count published submissions
        published_results = conn.execute("""
            SELECT COUNT(*) as count FROM submissions s
            JOIN users u ON u.id = s.student_id
            JOIN exams e ON e.id = s.exam_id
            WHERE s.result_published=1
        """).fetchone()['count']
        
        # Passed Students - count published results where percentage >= pass_percentage
        # First get exam total marks
        exam_totals = conn.execute("""
            SELECT exam_id, SUM(marks) as total_marks
            FROM questions
            GROUP BY exam_id
        """).fetchall()
        exam_total_map = {e["exam_id"]: e["total_marks"] for e in exam_totals}
        
        # Get published submissions with exam details
        published_submissions = conn.execute("""
            SELECT submissions.exam_id, submissions.score, exams.pass_percentage
            FROM submissions
            JOIN users u ON u.id = submissions.student_id
            JOIN exams ON exams.id = submissions.exam_id
            WHERE submissions.result_published=1
        """).fetchall()
        
        # Calculate passed count
        passed_students = 0
        for sub in published_submissions:
            exam_id = sub["exam_id"]
            score = sub["score"]
            pass_pct = sub["pass_percentage"] or 50
            total_marks = exam_total_map.get(exam_id, 100)
            pass_threshold = (pass_pct * total_marks) / 100
            if score >= pass_threshold:
                passed_students += 1
        
        # Pass Percentage - (Passed Students / Published Results) × 100
        pass_percentage = round((passed_students * 100.0 / published_results), 1) if published_results > 0 else 0
        
    except Exception as e:
        app.logger.exception("Quick statistics calculation failed")
        total_submissions = 0
        pending_results = 0
        published_results = 0
        passed_students = 0
        pass_percentage = 0
    # recent activity (last 8)
    activity = conn.execute("""
        SELECT activity_log.action, activity_log.timestamp, users.name, users.role
        FROM activity_log JOIN users ON users.id=activity_log.user_id
        ORDER BY activity_log.timestamp DESC LIMIT 8""").fetchall()
    conn.close()
    return render_template("admin/admin_dashboard.html",
        students=students, faculty=faculty, active_faculty=active_faculty, pending_faculty=pending_faculty,
        exams=exams, total_classrooms=total_classrooms, active_exams=active_exams,
        total_submissions=total_submissions, pending_results=pending_results, 
        passed_students=passed_students, pass_percentage=pass_percentage,
        pending=pending, faculty_list=faculty_list, classroom_list=classroom_list, activity=activity)

# ── Admin: Activity log full page ──────────────────────────────────────────
@app.route("/admin/activity")
def admin_activity():
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    search_query = request.args.get("search", "")
    role_filter = request.args.get("role", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    query = """SELECT activity_log.action, activity_log.timestamp, users.name, users.role, users.id as uid, users.email
               FROM activity_log JOIN users ON users.id=activity_log.user_id"""
    filters, params = [], []
    if search_query:
        filters.append("(users.name LIKE %s OR users.email LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if role_filter: filters.append("users.role=%s"); params.append(role_filter)
    if from_date: filters.append("DATE(activity_log.timestamp) >= %s"); params.append(from_date)
    if to_date: filters.append("DATE(activity_log.timestamp) <= %s"); params.append(to_date)
    if filters: query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY activity_log.timestamp DESC LIMIT 200"
    logs = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("admin/admin_activity.html", logs=logs,
                           search_query=search_query, sel_role=role_filter,
                           from_date=from_date, to_date=to_date)

@app.route("/admin/activity/export")
def admin_activity_export_csv():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported activity log to CSV")
    search_query = request.args.get("search", "")
    role_filter = request.args.get("role", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    query = """SELECT activity_log.action, activity_log.timestamp, users.name, users.role, users.id as uid, users.email
               FROM activity_log JOIN users ON users.id=activity_log.user_id"""
    filters, params = [], []
    if search_query:
        filters.append("(users.name LIKE %s OR users.email LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    if role_filter: filters.append("users.role=%s"); params.append(role_filter)
    if from_date: filters.append("DATE(activity_log.timestamp) >= %s"); params.append(from_date)
    if to_date: filters.append("DATE(activity_log.timestamp) <= %s"); params.append(to_date)
    if filters: query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY activity_log.timestamp DESC LIMIT 200"
    logs = conn.execute(query, params).fetchall()
    conn.close()
    
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["User","Role","Email","Action","Timestamp"])
    for r in logs:
        w.writerow([r["name"],r["role"],r["email"],r["action"],r["timestamp"]])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=activity_log.csv"
    return resp

@app.route("/admin/activity/export/pdf")
def admin_activity_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    g = require_role("admin")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported activity log to PDF")
        search_query = request.args.get("search", "")
        role_filter = request.args.get("role", "")
        from_date = request.args.get("from_date", "")
        to_date = request.args.get("to_date", "")
        query = """SELECT activity_log.action, activity_log.timestamp, users.name, users.role, users.id as uid, users.email
                   FROM activity_log JOIN users ON users.id=activity_log.user_id"""
        filters, params = [], []
        if search_query:
            filters.append("(users.name LIKE %s OR users.email LIKE %s)")
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        if role_filter: filters.append("users.role=%s"); params.append(role_filter)
        if from_date: filters.append("DATE(activity_log.timestamp) >= %s"); params.append(from_date)
        if to_date: filters.append("DATE(activity_log.timestamp) <= %s"); params.append(to_date)
        if filters: query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY activity_log.timestamp DESC LIMIT 200"
        logs = conn.execute(query, params).fetchall()
        conn.close()
        
        # Create PDF with shared configuration
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('ACTIVITY LOG REPORT', logo_path))
        
        # Applied filters
        if any([search_query, role_filter]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if search_query: elements.append(Paragraph(f"Search: {search_query}", styles['wrap']))
            if role_filter: elements.append(Paragraph(f"Role: {role_filter}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Records:", str(len(logs))),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["User", "Role", "Email", "Action", "Timestamp"]
        data = [headers]
        for r in logs:
            data.append([
                Paragraph(r["name"] or "—", styles['name']),
                Paragraph(r["role"] or "—", styles['wrap']),
                Paragraph(r["email"] or "—", styles['wrap']),
                Paragraph(r["action"] or "—", styles['wrap']),
                Paragraph(format_datetime(r["timestamp"]), styles['wrap'])
            ])
        
        # Get column widths and table style
        col_widths = get_column_widths('activity')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': False},   # User - no wrap
            {'align': 'CENTER', 'wrap': False}, # Role - no wrap
            {'align': 'LEFT', 'wrap': True},    # Email - wrap
            {'align': 'LEFT', 'wrap': True},    # Action - wrap
            {'align': 'CENTER', 'wrap': True},  # Timestamp - wrap for date/time
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="activity_log.pdf"'}
        )
    except Exception as e:
        import traceback
        app.logger.exception("PDF generation error (activity log)")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/admin/activity")

# ── Admin: Users page ──────────────────────────────────────────────────────
@app.route("/admin/users")
def admin_users():
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    q        = request.args.get("q","").strip()
    role_f   = request.args.get("role","")
    status_f = request.args.get("status","")
    sort     = request.args.get("sort","newest")
    query    = "SELECT * FROM users WHERE 1=1"
    params   = []
    if q:      query += " AND (name LIKE %s OR email LIKE %s)"; params += [f"%{q}%",f"%{q}%"]
    if role_f: query += " AND role=%s"; params.append(role_f)
    if status_f == "active":  query += " AND approved=1"
    if status_f == "pending": query += " AND approved=0"
    
    # Sorting options
    sort_map = {
        "newest": "created_at DESC",
        "oldest": "created_at ASC",
        "id_asc": "id ASC",
        "id_desc": "id DESC",
        "name_asc": "name ASC",
        "name_desc": "name DESC",
        "email_asc": "email ASC",
        "email_desc": "email DESC",
        "role_asc": "role ASC",
        "role_desc": "role DESC",
        "status_asc": "approved ASC",
        "status_desc": "approved DESC"
    }
    order_by = sort_map.get(sort, "created_at DESC")
    query += f" ORDER BY {order_by}"
    
    users = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("admin/admin_users.html", users=users, q=q, role_f=role_f, status_f=status_f, sort=sort)

@app.route("/admin/users/export")
def admin_users_export_csv():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported users to CSV")
    q        = request.args.get("q","").strip()
    role_f   = request.args.get("role","")
    status_f = request.args.get("status","")
    sort     = request.args.get("sort","newest")
    query    = "SELECT * FROM users WHERE 1=1"
    params   = []
    if q:      query += " AND (name LIKE %s OR email LIKE %s)"; params += [f"%{q}%",f"%{q}%"]
    if role_f: query += " AND role=%s"; params.append(role_f)
    if status_f == "active":  query += " AND approved=1"
    if status_f == "pending": query += " AND approved=0"
    query += " ORDER BY " + ("created_at ASC" if sort=="oldest" else "created_at DESC")
    users = conn.execute(query, params).fetchall()
    conn.close()
    
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["Name","Email","Role","Status","Created At"])
    for r in users:
        w.writerow([r["name"],r["email"],r["role"],"Active" if r["approved"] else "Pending",r["created_at"]])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=users.csv"
    return resp

@app.route("/admin/users/export/pdf")
def admin_users_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    import traceback
    g = require_role("admin")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported users to PDF")
        q        = request.args.get("q","").strip()
        role_f   = request.args.get("role","")
        status_f = request.args.get("status","")
        sort     = request.args.get("sort","newest")
        query    = "SELECT * FROM users WHERE 1=1"
        params   = []
        if q:      query += " AND (name LIKE %s OR email LIKE %s)"; params += [f"%{q}%",f"%{q}%"]
        if role_f: query += " AND role=%s"; params.append(role_f)
        if status_f == "active":  query += " AND approved=1"
        if status_f == "pending": query += " AND approved=0"
        query += " ORDER BY " + ("created_at ASC" if sort=="oldest" else "created_at DESC")
        users = conn.execute(query, params).fetchall()
        conn.close()
        
        # Create PDF with shared configuration
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('USERS REPORT', logo_path))
        
        # Applied filters
        if any([q, role_f, status_f]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if q: elements.append(Paragraph(f"Search: {q}", styles['wrap']))
            if role_f: elements.append(Paragraph(f"Role: {role_f}", styles['wrap']))
            if status_f: elements.append(Paragraph(f"Status: {status_f}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        active_count = sum(1 for r in users if r["approved"])
        summary_data = [
            ("Total Users:", str(len(users))),
            ("Active:", str(active_count)),
            ("Pending:", str(len(users) - active_count)),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Name", "Email", "Role", "Status", "Created At"]
        data = [headers]
        for r in users:
            data.append([
                Paragraph(r["name"] or "—", styles['name']),
                Paragraph(r["email"] or "—", styles['wrap']),
                Paragraph(r["role"] or "—", styles['wrap']),
                Paragraph("Active" if r["approved"] else "Pending", styles['wrap']),
                Paragraph(format_datetime(r["created_at"]), styles['wrap'])
            ])
        
        # Get column widths and table style
        col_widths = get_column_widths('users')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': False},   # Name - no wrap
            {'align': 'LEFT', 'wrap': True},    # Email - wrap
            {'align': 'CENTER', 'wrap': False}, # Role - no wrap
            {'align': 'CENTER', 'wrap': False}, # Status - no wrap
            {'align': 'CENTER', 'wrap': True},  # Created At - wrap for date/time
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="users.pdf"'}
        )
    except Exception as e:
        app.logger.exception("PDF export failed")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/admin/users")

@app.route("/approve/<id>")
def approve(id):
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    conn.execute("UPDATE users SET approved=1 WHERE id=%s", (id,)); conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Approved faculty id={id}")
    flash("Faculty approved.", "success"); return redirect("/admin")

@app.route("/add_user", methods=["GET","POST"])
def add_user():
    g = require_role("admin"); 
    if g: return g
    if request.method == "POST":
        name=request.form["name"]; email=request.form["email"]
        password=generate_password_hash(request.form["password"]); role=request.form["role"]
        conn = get_db()
        try:
            conn.execute("INSERT INTO users(name,email,password,role,approved) VALUES(%s,%s,%s,%s,1)", (name,email,password,role))
            conn.commit()
            conn.close()
            log_activity(session["user_id"], f"Added user {email}")
            flash("User created.", "success")
        except: 
            conn.close()
            flash("Email already registered.", "danger")
        return redirect("/admin/users")
    return render_template("admin/add_user.html")

@app.route("/view_user/<id>")
def view_user(id):
    g = require_role("admin")
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (id,)).fetchone()
    if not user:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/admin/users")
    
    # Get classroom associations
    classrooms = []
    exams_attempted = []
    activity_history = []
    
    if user["role"] == "student":
        classrooms = conn.execute("""
            SELECT classrooms.*, classroom_members.joined_at
            FROM classroom_members
            JOIN classrooms ON classrooms.id=classroom_members.classroom_id
            WHERE classroom_members.student_id=%s
            ORDER BY classrooms.name
        """, (id,)).fetchall()
        
        exams_attempted = conn.execute("""
            SELECT exams.*, submissions.score, submissions.submitted_at, submissions.result_published,
                   (SELECT SUM(q.marks) FROM questions q WHERE q.exam_id = exams.id) as total
            FROM submissions
            JOIN exams ON exams.id=submissions.exam_id
            WHERE submissions.student_id=%s
            ORDER BY submissions.submitted_at DESC
        """, (id,)).fetchall()
    
    elif user["role"] == "faculty":
        classrooms = conn.execute("""
            SELECT * FROM classrooms WHERE faculty_id=%s
            ORDER BY name
        """, (id,)).fetchall()
        
        exams_created = conn.execute("""
            SELECT * FROM exams WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0)
            ORDER BY created_at DESC
        """, (id,)).fetchall()
        
        exams_attempted = exams_created  # For faculty, show exams they created
    
    # Get activity history
    activity_history = conn.execute("""
        SELECT * FROM activity_log WHERE user_id=%s
        ORDER BY timestamp DESC LIMIT 50
    """, (id,)).fetchall()
    conn.close()
    
    if user:
        user = dict(user)
    return render_template("admin/view_user.html", user=user, classrooms=classrooms,
                           exams_attempted=exams_attempted, activity_history=activity_history)

@app.route("/edit_user/<id>", methods=["GET","POST"])
def edit_user(id):
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (id,)).fetchone()
    if not user:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/admin/users")
    
    is_own_profile = (id == session["user_id"])
    
    if request.method == "POST":
        if is_own_profile:
            # Admin can edit their own name and email
            conn.execute("UPDATE users SET name=%s,email=%s,role=%s WHERE id=%s", (request.form["name"],request.form["email"],request.form["role"],id))
        else:
            # Admin cannot edit name/email for other users, only role
            conn.execute("UPDATE users SET role=%s WHERE id=%s", (request.form["role"],id))
        conn.commit()
        conn.close()
        log_activity(session["user_id"], f"Updated user: {user['email']}")
        flash("User updated.", "success"); return redirect("/admin/users")
    
    conn.close()
    if user:
        user = dict(user)
    return render_template("admin/edit_user.html", user=user, is_own_profile=is_own_profile)

@app.route("/delete_user/<id>")
def delete_user(id):
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (id,)).fetchone()
    # Cascade delete associated records
    conn.execute("DELETE FROM submission_answers WHERE submission_id IN (SELECT id FROM submissions WHERE student_id=%s)", (id,))
    conn.execute("DELETE FROM submissions WHERE student_id=%s", (id,))
    conn.execute("DELETE FROM exam_attempts WHERE student_id=%s", (id,))
    conn.execute("DELETE FROM classroom_members WHERE student_id=%s", (id,))
    conn.execute("DELETE FROM activity_log WHERE user_id=%s", (id,))
    # If deleting a faculty, also delete their exams, questions, and classrooms
    if user["role"] == "faculty":
        conn.execute("DELETE FROM submission_answers WHERE submission_id IN (SELECT id FROM submissions WHERE exam_id IN (SELECT id FROM exams WHERE faculty_id=%s))", (id,))
        conn.execute("DELETE FROM submissions WHERE exam_id IN (SELECT id FROM exams WHERE faculty_id=%s)", (id,))
        conn.execute("DELETE FROM exam_attempts WHERE exam_id IN (SELECT id FROM exams WHERE faculty_id=%s)", (id,))
        conn.execute("DELETE FROM questions WHERE exam_id IN (SELECT id FROM exams WHERE faculty_id=%s)", (id,))
        conn.execute("DELETE FROM exam_attempts WHERE exam_id IN (SELECT id FROM exams WHERE faculty_id=%s)", (id,))
        conn.execute("DELETE FROM classroom_members WHERE classroom_id IN (SELECT id FROM classrooms WHERE faculty_id=%s)", (id,))
        conn.execute("DELETE FROM classrooms WHERE faculty_id=%s", (id,))
        conn.execute("DELETE FROM exams WHERE faculty_id=%s", (id,))
        conn.execute("DELETE FROM question_bank WHERE faculty_id=%s", (id,))
    conn.execute("DELETE FROM users WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Deleted user: {user['name']} ({user['email']})")
    flash("User deleted.", "success")
    return redirect("/admin/users")

# ── Admin: Reports ────────────────────────────────────────────────────────
@app.route("/reports")
def reports():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    sf = request.args.get("student","");  ef = request.args.get("exam","")
    ff = request.args.get("faculty","");  df = request.args.get("date_from","")
    dt = request.args.get("date_to","");  sq = request.args.get("search","").strip()

    query = """SELECT users.name, users.id as student_id,
               exams.title, exams.exam_date, exams.subject, exams.id as exam_id,
               faculty.name as faculty_name,
               submissions.score, submissions.submitted_at,
               COUNT(DISTINCT questions.id) AS total
               FROM submissions
               JOIN users    ON users.id=submissions.student_id
               JOIN exams    ON exams.id=submissions.exam_id
               JOIN users AS faculty ON faculty.id=exams.faculty_id
               JOIN questions ON questions.exam_id=exams.id"""
    filters, params = [], []
    if sf:  filters.append("users.id=%s");          params.append(sf)
    if ef:  filters.append("exams.id=%s");          params.append(ef)
    if ff:  filters.append("exams.faculty_id=%s");  params.append(ff)
    if df:  filters.append("exams.exam_date>=%s");  params.append(df)
    if dt:  filters.append("exams.exam_date<=%s");  params.append(dt)
    if sq:  filters.append("(users.name LIKE %s OR exams.title LIKE %s)"); params += [f"%{sq}%",f"%{sq}%"]
    if filters: query += " WHERE " + " AND ".join(filters)
    query += " GROUP BY users.id, users.name, exams.id, exams.title, exams.exam_date, exams.subject, faculty.name, submissions.id, submissions.score, submissions.submitted_at ORDER BY submissions.submitted_at DESC"
    data = conn.execute(query, params).fetchall()

    # Faculty performance
    faculty_stats = conn.execute("""
        SELECT faculty.id, faculty.name as faculty_name,
               COUNT(DISTINCT exams.id) as exam_count,
               COUNT(submissions.id) as attempt_count,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct
        FROM users AS faculty
        LEFT JOIN exams       ON exams.faculty_id=faculty.id
        LEFT JOIN submissions ON submissions.exam_id=exams.id
        WHERE faculty.role='faculty' GROUP BY faculty.id, faculty.name ORDER BY avg_pct DESC
    """).fetchall()

    # Top 5 students
    top_students = conn.execute("""
        SELECT users.id, users.name,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct,
               COUNT(submissions.id) as attempts
        FROM submissions JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        GROUP BY users.id, users.name ORDER BY avg_pct DESC LIMIT 5
    """).fetchall()

    # Bottom 5 students
    low_students = conn.execute("""
        SELECT users.id, users.name,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct,
               COUNT(submissions.id) as attempts
        FROM submissions JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        GROUP BY users.id, users.name ORDER BY avg_pct ASC LIMIT 5
    """).fetchall()

    students  = conn.execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall()
    all_exams = conn.execute("SELECT * FROM exams ORDER BY title").fetchall()
    all_fac   = conn.execute("SELECT * FROM users WHERE role='faculty' ORDER BY name").fetchall()
    conn.close()
    return render_template("admin/reports.html", data=data, students=students, exams=all_exams,
        faculty_list=all_fac, faculty_stats=faculty_stats,
        top_students=top_students, low_students=low_students,
        sel_student=sf, sel_exam=ef, sel_faculty=ff,
        date_from=df, date_to=dt, search=sq)

@app.route("/reports/export/csv")
def export_csv():
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported reports to CSV")
    sf = request.args.get("student", "")
    ef = request.args.get("exam", "")
    ff = request.args.get("faculty", "")
    df = request.args.get("date_from", "")
    dt = request.args.get("date_to", "")
    sq = request.args.get("search", "")
    
    query = """
        SELECT users.name as student, exams.title, exams.exam_date, exams.subject,
               faculty.name as faculty, submissions.score, COUNT(questions.id) as total, submissions.submitted_at, exams.pass_percentage
        FROM submissions JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        JOIN users AS faculty ON faculty.id=exams.faculty_id
        JOIN questions ON questions.exam_id=exams.id"""
    filters, params = [], []
    if sf:  filters.append("users.id=%s");          params.append(sf)
    if ef:  filters.append("exams.id=%s");          params.append(ef)
    if ff:  filters.append("exams.faculty_id=%s");  params.append(ff)
    if df:  filters.append("exams.exam_date>=%s");  params.append(df)
    if dt:  filters.append("exams.exam_date<=%s");  params.append(dt)
    if sq:  filters.append("(users.name LIKE %s OR exams.title LIKE %s)"); params += [f"%{sq}%",f"%{sq}%"]
    if filters: query += " WHERE " + " AND ".join(filters)
    query += " GROUP BY users.id, users.name, exams.id, exams.title, exams.exam_date, exams.subject, faculty.name, submissions.id, submissions.score, submissions.submitted_at, exams.pass_percentage ORDER BY submissions.submitted_at DESC"
    data = conn.execute(query, params).fetchall()
    conn.close()
    
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["Student","Exam","Date","Subject","Faculty","Score","Total","Percentage","Result"])
    for r in data:
        pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
        result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
        w.writerow([r["student"],r["title"],r["exam_date"],r["subject"],r["faculty"],
                    r["score"],r["total"],f"{pct}%",result])
    
    # Summary row
    total_count = len(data)
    pass_count = sum(1 for r in data if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
    fail_count = total_count - pass_count
    avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in data) / total_count if total_count else 0
    w.writerow([])
    w.writerow(["SUMMARY","","","","","","","",""])
    w.writerow(["Total Records", total_count, "", "", "", "", "", "", ""])
    w.writerow(["Passed", pass_count, "", "", "", "", "", "", ""])
    w.writerow(["Failed", fail_count, "", "", "", "", "", "", ""])
    w.writerow(["Average %", f"{avg_pct:.1f}%", "", "", "", "", "", "", ""])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"]="text/csv"
    resp.headers["Content-Disposition"]="attachment; filename=edusphere_report.csv"
    return resp

@app.route("/reports/export/pdf")
def export_pdf():
    from flask import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    import os
    import traceback
    g = require_role("admin")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported reports to PDF")
        sf = request.args.get("student", "")
        ef = request.args.get("exam", "")
        ff = request.args.get("faculty", "")
        df = request.args.get("date_from", "")
        dt = request.args.get("date_to", "")
        sq = request.args.get("search", "")
        
        query = """
            SELECT users.name as student, exams.title, exams.exam_date, exams.subject,
                   faculty.name as faculty, submissions.score, COUNT(questions.id) as total, submissions.submitted_at
            FROM submissions JOIN users ON users.id=submissions.student_id
            JOIN exams ON exams.id=submissions.exam_id
            JOIN users AS faculty ON faculty.id=exams.faculty_id
            JOIN questions ON questions.exam_id=exams.id"""
        filters, params = [], []
        if sf:  filters.append("users.id=%s");          params.append(sf)
        if ef:  filters.append("exams.id=%s");          params.append(ef)
        if ff:  filters.append("exams.faculty_id=%s");  params.append(ff)
        if df:  filters.append("exams.exam_date>=%s");  params.append(df)
        if dt:  filters.append("exams.exam_date<=%s");  params.append(dt)
        if sq:  filters.append("(users.name LIKE %s OR exams.title LIKE %s)"); params += [f"%{sq}%",f"%{sq}%"]
        if filters: query += " WHERE " + " AND ".join(filters)
        query += " GROUP BY users.id, users.name, exams.id, exams.title, exams.exam_date, exams.subject, faculty.name, submissions.id, submissions.score, submissions.submitted_at ORDER BY submissions.submitted_at DESC"
        data = conn.execute(query, params).fetchall()
        conn.close()
        
        # Calculate summary stats
        total_count = len(data)
        pass_count = sum(1 for r in data if r["total"] and r["score"] >= r["total"]/2)
        fail_count = total_count - pass_count
        avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in data) / total_count if total_count else 0
        
        # Create PDF with shared configuration
        from flask import Response
        from reportlab.platypus import Paragraph, Table
        from reportlab.lib import colors
        from pdf_utils import (
            create_pdf_document, get_pdf_styles, get_column_widths,
            get_table_style, format_datetime, create_header_table,
            create_summary_table, apply_column_alignment
        )
        import os
        
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('EXAM REPORT', logo_path))
        
        # Applied filters
        if any([sf, ef, ff, df, dt, sq]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if sf: elements.append(Paragraph(f"Student ID: {sf}", styles['wrap']))
            if ef: elements.append(Paragraph(f"Exam ID: {ef}", styles['wrap']))
            if ff: elements.append(Paragraph(f"Faculty ID: {ff}", styles['wrap']))
            if df: elements.append(Paragraph(f"Date From: {df}", styles['wrap']))
            if dt: elements.append(Paragraph(f"Date To: {dt}", styles['wrap']))
            if sq: elements.append(Paragraph(f"Search: {sq}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Records:", str(total_count)),
            ("Passed:", str(pass_count)),
            ("Failed:", str(fail_count)),
            ("Average %:", f"{avg_pct:.1f}%"),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Student", "Exam", "Date", "Subject", "Faculty", "Score", "Total", "%", "Result"]
        data_rows = [headers]
        for r in data:
            pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
            result = "Pass" if r["score"] >= r["total"]/2 else "Fail"
            result_style = styles['wrap'].clone()
            if result == "Pass":
                result_style.textColor = colors.HexColor('#16A34A')
                result_style.fontWeight = 600
            else:
                result_style.textColor = colors.HexColor('#DC2626')
                result_style.fontWeight = 600
            
            data_rows.append([
                Paragraph(r["student"] or "—", styles['name']),
                Paragraph(r["title"] or "—", styles['wrap']),
                Paragraph(format_datetime(r["exam_date"]), styles['wrap']),
                Paragraph(r["subject"] or "—", styles['wrap']),
                Paragraph(r["faculty"] or "—", styles['wrap']),
                Paragraph(str(r["score"]), styles['wrap']),
                Paragraph(str(r["total"]), styles['wrap']),
                Paragraph(f"{pct}%", styles['wrap']),
                Paragraph(result, result_style)
            ])
        
        # Get column widths and table style
        col_widths = get_column_widths('exam')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': False},   # Student - no wrap
            {'align': 'LEFT', 'wrap': True},    # Exam - wrap
            {'align': 'CENTER', 'wrap': True},  # Date - wrap for date/time
            {'align': 'LEFT', 'wrap': True},    # Subject - wrap
            {'align': 'LEFT', 'wrap': True},    # Faculty - wrap
            {'align': 'CENTER', 'wrap': False}, # Score - no wrap
            {'align': 'CENTER', 'wrap': False}, # Total - no wrap
            {'align': 'CENTER', 'wrap': False}, # % - no wrap
            {'align': 'CENTER', 'wrap': False}, # Result - no wrap
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data_rows, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="edusphere_report.pdf"'}
        )
    except Exception as e:
        app.logger.exception("PDF generation error (reports)")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/reports")

@app.route("/reports/export/faculty-csv")
def export_faculty_csv():
    g = require_role("admin"); 
    if g: return g
    conn = get_db()
    rows = conn.execute("""SELECT faculty.name, COUNT(DISTINCT exams.id) as exams, COUNT(submissions.id) as attempts
        FROM users AS faculty LEFT JOIN exams ON exams.faculty_id=faculty.id
        LEFT JOIN submissions ON submissions.exam_id=exams.id
        WHERE faculty.role='faculty' GROUP BY faculty.id, faculty.name""").fetchall()
    conn.close()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Faculty","Exams Conducted","Total Attempts"])
    for r in rows: w.writerow([r["name"],r["exams"],r["attempts"]])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"]="text/csv"
    resp.headers["Content-Disposition"]="attachment; filename=faculty_report.csv"
    return resp

# ═══════════════════════════════════════════════════════════════════════════
# CLASSROOMS
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/classrooms")
def classrooms():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    rooms = conn.execute("""
        SELECT classrooms.id, classrooms.name, classrooms.subject, classrooms.code, classrooms.faculty_id, classrooms.created_at, classrooms.is_archived,
               COUNT(classroom_members.id) as member_count
        FROM classrooms LEFT JOIN classroom_members ON classrooms.id=classroom_members.classroom_id
        WHERE classrooms.faculty_id=%s GROUP BY classrooms.id, classrooms.name, classrooms.subject, classrooms.code, classrooms.faculty_id, classrooms.created_at, classrooms.is_archived ORDER BY classrooms.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("faculty/classrooms.html", rooms=rooms)

@app.route("/classrooms/create", methods=["GET","POST"])
def create_classroom():
    g = require_role("faculty"); 
    if g: return g
    if request.method == "POST":
        name    = request.form["name"]
        subject = request.form.get("subject","")
        code    = gen_code()
        conn = get_db()
        # ensure unique code
        while conn.execute("SELECT id FROM classrooms WHERE code=%s", (code,)).fetchone():
            code = gen_code()
        conn.execute("INSERT INTO classrooms(name,subject,code,faculty_id) VALUES(%s,%s,%s,%s)", (name,subject,code,session["user_id"]))
        conn.commit()
        conn.close()
        log_activity(session["user_id"], f"Created classroom: {name}")
        flash(f"Classroom created! Code: {code}", "success")
        return redirect("/classrooms")
    return render_template("faculty/create_classroom.html")

@app.route("/classrooms/<int:cid>")
def classroom_detail(cid):
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    room = conn.execute("SELECT * FROM classrooms WHERE id=%s AND faculty_id=%s", (cid, session["user_id"])).fetchone()
    if not room:
        conn.close()
        return redirect("/classrooms")
    members = conn.execute("""
        SELECT users.*, classroom_members.joined_at FROM users
        JOIN classroom_members ON users.id=classroom_members.student_id
        WHERE classroom_members.classroom_id=%s ORDER BY users.name
    """, (cid,)).fetchall()
    exams = conn.execute("""
        SELECT exams.id, exams.title, exams.subject, exams.exam_date, exams.duration, exams.pass_percentage,
               exams.launched, exams.published, exams.classroom_id, exams.faculty_id, exams.created_at, exams.is_archived,
               COUNT(questions.id) as q_count
        FROM exams LEFT JOIN questions ON exams.id=questions.exam_id
        WHERE exams.classroom_id=%s AND exams.faculty_id=%s
        GROUP BY exams.id, exams.title, exams.subject, exams.exam_date, exams.duration, exams.pass_percentage,
               exams.launched, exams.published, exams.classroom_id, exams.faculty_id, exams.created_at, exams.is_archived
        ORDER BY exams.id DESC
    """, (cid, session["user_id"])).fetchall()
    # All other classrooms (for move exam dropdown)
    other_classrooms = conn.execute(
        "SELECT * FROM classrooms WHERE faculty_id=%s AND id!=%s ORDER BY name",
        (session["user_id"], cid)
    ).fetchall()
    # Exams not yet assigned to ANY classroom (can be added to this one)
    unassigned_exams = conn.execute("""
        SELECT exams.id, exams.title, exams.subject
        FROM exams
        WHERE exams.faculty_id=%s AND (exams.classroom_id IS NULL OR exams.classroom_id = 0)
        ORDER BY exams.title
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("student/classroom_detail.html", room=room, members=members,
                           exams=exams, other_classrooms=other_classrooms,
                           unassigned_exams=unassigned_exams)

@app.route("/classrooms/<int:cid>/remove/<int:sid>")
def remove_from_classroom(cid, sid):
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    conn.execute("DELETE FROM classroom_members WHERE classroom_id=%s AND student_id=%s", (cid,sid))
    conn.commit()
    conn.close()
    flash("Student removed from classroom.", "success")
    return redirect(f"/classrooms/{cid}")

@app.route("/classrooms/<int:cid>/delete")
def delete_classroom(cid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    classroom = conn.execute("SELECT * FROM classrooms WHERE id=%s AND faculty_id=%s", (cid, session["user_id"])).fetchone()
    if not classroom:
        conn.close()
        flash("Classroom not found.", "danger")
        return redirect("/classrooms")
    # Archive classroom and its exams instead of permanently deleting
    conn.execute("""UPDATE classrooms SET is_archived=1, archived_at=CURRENT_TIMESTAMP,
                    archived_by=%s WHERE id=%s AND faculty_id=%s""",
                 (session["user_id"], cid, session["user_id"]))
    conn.execute("""UPDATE exams SET is_archived=1, archived_at=CURRENT_TIMESTAMP,
                    archived_by=%s WHERE classroom_id=%s AND faculty_id=%s""",
                 (session["user_id"], cid, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Archived classroom: {classroom['name']}")
    flash(f"Classroom \"{classroom['name']}\" has been archived. You can restore it from the Archive Center.", "success")
    return redirect("/classrooms")

@app.route("/classrooms/<int:cid>/assign_exam", methods=["POST"])
def assign_exam_to_classroom(cid):
    g = require_role("faculty"); 
    if g: return g
    exam_id = request.form["exam_id"]
    conn = get_db()
    conn.execute("UPDATE exams SET classroom_id=%s WHERE id=%s AND faculty_id=%s", (cid, exam_id, session["user_id"]))
    conn.commit()
    conn.close()
    flash("Exam linked to classroom.", "success")
    return redirect(f"/classrooms/{cid}")

@app.route("/classrooms/<int:cid>/move_exam", methods=["POST"])
def move_exam_to_classroom(cid):
    g = require_role("faculty")
    if g: return g
    exam_id    = request.form["exam_id"]
    target_cid = request.form["target_classroom_id"]
    conn = get_db()
    # verify exam belongs to this faculty
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger")
        return redirect(f"/classrooms/{cid}")
    conn.execute("UPDATE exams SET classroom_id=%s WHERE id=%s", (target_cid, exam_id))
    conn.commit()
    conn.close()
    flash("Exam moved to new classroom.", "success")
    return redirect(f"/classrooms/{cid}")

@app.route("/classrooms/<int:cid>/copy_exam", methods=["POST"])
def copy_exam_to_classroom(cid):
    g = require_role("faculty")
    if g: return g
    exam_id    = request.form["exam_id"]
    target_cid = request.form["target_classroom_id"]
    conn = get_db()
    orig = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not orig:
        conn.close()
        flash("Exam not found.", "danger"); return redirect(f"/classrooms/{cid}")
    # Create new draft exam in target classroom — no submissions copied
    conn.execute("""INSERT INTO exams(title,faculty_id,duration,exam_date,subject,classroom_id,launched,published)
                    VALUES(%s,%s,%s,%s,%s,%s,0,0)""",
                 (f"Copy of {orig['title']}", session["user_id"], orig["duration"],
                  orig["exam_date"], orig["subject"], target_cid))
    conn.commit()
    new_id = conn.last_insert_id()
    # Copy questions only
    for q in conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall():
        conn.execute("""INSERT INTO questions(exam_id,question,option1,option2,option3,option4,correct_answer,difficulty)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (new_id, q["question"], q["option1"], q["option2"],
                      q["option3"], q["option4"], q["correct_answer"], q["difficulty"]))
    conn.commit()
    conn.close()
    flash("Exam copied to classroom as a new Draft. Submissions not copied.", "success")
    return redirect(f"/classrooms/{cid}")

@app.route("/classrooms/<int:cid>/edit", methods=["GET","POST"])
def edit_classroom(cid):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    room = conn.execute("SELECT * FROM classrooms WHERE id=%s AND faculty_id=%s", (cid, session["user_id"])).fetchone()
    if not room:
        conn.close()
        return redirect("/classrooms")
    if request.method == "POST":
        name    = request.form["name"]
        subject = request.form.get("subject", "")
        conn.execute("UPDATE classrooms SET name=%s, subject=%s WHERE id=%s", (name, subject, cid))
        conn.commit()
        conn.close()
        flash("Classroom updated.", "success")
        return redirect(f"/classrooms/{cid}")
    conn.close()
    return render_template("faculty/edit_classroom.html", room=room)

# ── Admin: Classrooms ───────────────────────────────────────────────────────
@app.route("/admin/classrooms")
def admin_classrooms():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    rooms = conn.execute("""
        SELECT c.id, c.name, c.subject, c.code, c.faculty_id, c.created_at, c.is_archived,
               u.name as faculty_name, COUNT(cm.id) as member_count
        FROM classrooms c
        LEFT JOIN users u ON u.id = c.faculty_id
        LEFT JOIN classroom_members cm ON cm.classroom_id = c.id
        WHERE (c.is_archived IS NULL OR c.is_archived=0)
        GROUP BY c.id, c.name, c.subject, c.code, c.faculty_id, c.created_at, c.is_archived, u.name
        ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin/admin_classrooms.html", rooms=rooms)

@app.route("/admin/classrooms/<int:cid>")
def admin_classroom_detail(cid):
    g = require_role("admin")
    if g: return g
    conn = get_db()
    room = conn.execute("SELECT * FROM classrooms WHERE id=%s", (cid,)).fetchone()
    if not room:
        conn.close()
        return redirect("/admin/classrooms")
    students = conn.execute("""
        SELECT u.id, u.name, u.email, u.reg_number, cm.joined_at
        FROM classroom_members cm
        JOIN users u ON u.id = cm.student_id
        WHERE cm.classroom_id = %s
        ORDER BY cm.joined_at DESC
    """, (cid,)).fetchall()
    exams = conn.execute("""
        SELECT e.id, e.title, e.subject, e.exam_date, e.duration, e.pass_percentage,
               e.launched, e.published, e.classroom_id, e.faculty_id, e.created_at, e.is_archived,
               COUNT(q.id) as question_count
        FROM exams e
        LEFT JOIN questions q ON q.exam_id = e.id
        WHERE e.classroom_id = %s
        GROUP BY e.id, e.title, e.subject, e.exam_date, e.duration, e.pass_percentage,
               e.launched, e.published, e.classroom_id, e.faculty_id, e.created_at, e.is_archived
        ORDER BY e.created_at DESC
    """, (cid,)).fetchall()
    conn.close()
    # Pass empty lists for variables expected by the template (for faculty features)
    # Explicitly pass theme to ensure data-theme is set correctly
    return render_template("student/classroom_detail.html", room=room, members=students, exams=exams,
                           other_classrooms=[], unassigned_exams=[])

# Admin cannot create/edit/delete classrooms - redirect with error
@app.route("/admin/classrooms/create", methods=["GET","POST"])
def admin_create_classroom():
    flash("Admins cannot create classrooms. Please ask a faculty member.", "danger")
    return redirect("/admin/classrooms")

@app.route("/admin/classrooms/<int:cid>/edit", methods=["GET","POST"])
def admin_edit_classroom(cid):
    flash("Admins cannot edit classrooms. Please ask a faculty member.", "danger")
    return redirect("/admin/classrooms")

@app.route("/admin/classrooms/<int:cid>/delete")
def admin_delete_classroom(cid):
    flash("Admins cannot delete classrooms. Please ask a faculty member.", "danger")
    return redirect("/admin/classrooms")

# ── Admin: Exams ───────────────────────────────────────────────────────────
@app.route("/admin/exams")
def admin_exams():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    status_f = request.args.get("status", "")
    sel_faculty = request.args.get("faculty", "")
    
    query = """
        SELECT e.id, e.title, e.subject, e.exam_date, e.duration, e.pass_percentage,
               e.launched, e.published, e.classroom_id, e.faculty_id, e.created_at, e.is_archived,
               u.name as faculty_name, c.name as classroom_name, COUNT(q.id) as question_count
        FROM exams e
        LEFT JOIN users u ON u.id = e.faculty_id
        LEFT JOIN classrooms c ON c.id = e.classroom_id
        LEFT JOIN questions q ON q.exam_id = e.id
        GROUP BY e.id, e.title, e.subject, e.exam_date, e.duration, e.pass_percentage,
               e.launched, e.published, e.classroom_id, e.faculty_id, e.created_at, e.is_archived,
               u.name, c.name
    """
    params = []
    if status_f == "draft":
        query += " HAVING e.published=0"
    elif status_f == "published":
        query += " HAVING e.published=1 AND e.launched=0"
    elif status_f == "completed":
        query += " HAVING e.launched=1"
    
    if sel_faculty:
        if "HAVING" in query:
            query += " AND e.faculty_id=%s"
        else:
            query += " HAVING e.faculty_id=%s"
        params.append(sel_faculty)
    
    query += " ORDER BY e.created_at DESC"
    exams = conn.execute(query, params).fetchall()
    faculty_list = conn.execute("SELECT id, name FROM users WHERE role='faculty' AND approved=1").fetchall()
    conn.close()
    
    return render_template("admin/admin_exams.html", exams=exams, status_f=status_f, sel_faculty=sel_faculty, faculty_list=faculty_list)

@app.route("/admin/exams/<int:eid>/delete")
def admin_delete_exam(eid):
    flash("Admins cannot delete exams. Please ask a faculty member.", "danger")
    return redirect("/admin/exams")

@app.route("/admin/exams/<int:eid>/move", methods=["GET","POST"])
def admin_move_exam(eid):
    flash("Admins cannot move exams. Please ask a faculty member.", "danger")
    return redirect("/admin/exams")

@app.route("/admin/question_bank")
def admin_question_bank():
    flash("Question Bank is for Faculty only.", "danger")
    return redirect("/admin")

# ── Admin: Reports ─────────────────────────────────────────────────────────
@app.route("/admin/reports")
def admin_reports():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    search = request.args.get("search", "").strip()
    sel_student = request.args.get("student", "")
    sel_exam = request.args.get("exam", "")
    sel_faculty = request.args.get("faculty", "")
    sel_classroom = request.args.get("classroom", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    
    # Get filter options
    students = conn.execute("SELECT id, name FROM users WHERE role='student'").fetchall()
    exams = conn.execute("SELECT id, title FROM exams").fetchall()
    faculty_list = conn.execute("SELECT id, name FROM users WHERE role='faculty' AND approved=1").fetchall()
    classrooms = conn.execute("SELECT id, name FROM classrooms").fetchall()
    
    # Build query for results
    query = """
        SELECT s.name, e.title, e.exam_date, u.name as faculty_name, c.name as classroom_name,
               sub.score, COUNT(q.id) as total
        FROM submissions sub
        JOIN users s ON s.id = sub.student_id
        JOIN exams e ON e.id = sub.exam_id
        JOIN users u ON u.id = e.faculty_id
        LEFT JOIN classrooms c ON c.id = e.classroom_id
        LEFT JOIN questions q ON q.exam_id = e.id
        WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND (s.name LIKE %s OR e.title LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if sel_student:
        query += " AND s.id=%s"
        params.append(sel_student)
    if sel_exam:
        query += " AND e.id=%s"
        params.append(sel_exam)
    if sel_faculty:
        query += " AND e.faculty_id=%s"
        params.append(sel_faculty)
    if sel_classroom:
        query += " AND e.classroom_id=%s"
        params.append(sel_classroom)
    if date_from:
        query += " AND sub.submitted_at >= %s"
        params.append(date_from)
    if date_to:
        query += " AND sub.submitted_at <= %s"
        params.append(date_to)
    
    query += " GROUP BY sub.id, s.name, e.title, e.exam_date, u.name, c.name, sub.score, sub.submitted_at ORDER BY sub.submitted_at DESC"
    data = conn.execute(query, params).fetchall()
    
    # Faculty stats
    faculty_stats = conn.execute("""
        SELECT u.id, u.name as faculty_name, COUNT(DISTINCT e.id) as exam_count,
               COUNT(sub.id) as attempt_count, 
               AVG(sub.score * 100.0 / (SELECT COUNT(*) FROM questions WHERE exam_id = sub.exam_id)) as avg_pct
        FROM users u
        JOIN exams e ON e.faculty_id = u.id
        LEFT JOIN submissions sub ON sub.exam_id = e.id
        WHERE u.role='faculty' AND u.approved=1
        GROUP BY u.id, u.name
    """).fetchall()
    
    # Classroom stats
    classroom_stats = conn.execute("""
        SELECT c.id, c.name as classroom_name, u.name as faculty_name, COUNT(DISTINCT cm.student_id) as student_count,
               AVG(sub.score * 100.0 / (SELECT COUNT(*) FROM questions WHERE exam_id = sub.exam_id)) as avg_pct
        FROM classrooms c
        LEFT JOIN users u ON u.id = c.faculty_id
        LEFT JOIN classroom_members cm ON cm.classroom_id = c.id
        LEFT JOIN exams e ON e.classroom_id = c.id
        LEFT JOIN submissions sub ON sub.exam_id = e.id
        GROUP BY c.id, c.name, u.name
    """).fetchall()
    conn.close()
    
    return render_template("admin/admin_reports.html", data=data, students=students, exams=exams,
                           faculty_list=faculty_list, classrooms=classrooms,
                           search=search, sel_student=sel_student, sel_exam=sel_exam,
                           sel_faculty=sel_faculty, sel_classroom=sel_classroom,
                           date_from=date_from, date_to=date_to,
                           faculty_stats=faculty_stats, classroom_stats=classroom_stats)

@app.route("/admin/reports/export/csv")
def admin_reports_export_csv():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    data = conn.execute("""
        SELECT s.name as student_name, e.title as exam_title, u.name as faculty_name,
               c.name as classroom_name, sub.score, COUNT(q.id) as total, sub.submitted_at
        FROM submissions sub
        JOIN users s ON s.id = sub.student_id
        JOIN exams e ON e.id = sub.exam_id
        JOIN users u ON u.id = e.faculty_id
        LEFT JOIN classrooms c ON c.id = e.classroom_id
        LEFT JOIN questions q ON q.exam_id = e.id
        GROUP BY sub.id, s.name, e.title, u.name, c.name, sub.score, sub.submitted_at
        ORDER BY sub.submitted_at DESC
    """).fetchall()
    conn.close()
    
    import io, csv
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Student","Exam","Faculty","Classroom","Score","Total","Percentage","Result","Date"])
    for r in data:
        pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
        w.writerow([r["student_name"], r["exam_title"], r["faculty_name"], r["classroom_name"],
                    r["score"], r["total"], f"{pct}%", "Pass" if r["score"]>=r["total"]/2 else "Fail",
                    r["submitted_at"].strftime('%Y-%m-%d') if r["submitted_at"] else ""])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=admin_reports.csv"
    return resp

# ── Admin: Profile ───────────────────────────────────────────────────────────
@app.route("/admin/profile", methods=["GET","POST"])
def admin_profile():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip()
        gender = request.form.get("gender", "").strip()
        admin_id_field = request.form.get("admin_id", "").strip()
        role_level = request.form.get("role_level", "").strip()
        current_password = request.form.get("current_password", "").strip()
        
        if not name or not email:
            conn.close()
            flash("Name and email are required.", "danger")
            return redirect("/admin/profile")
        
        if "@" not in email:
            conn.close()
            flash("Invalid email format.", "danger")
            return redirect("/admin/profile")
        
        # Get current user data to check if email is being changed
        current_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        current_email = current_user["email"] if current_user else ""
        
        # If email is being changed, require password verification
        if email != current_email:
            if not current_password:
                conn.close()
                flash("Current password is required to change email.", "danger")
                return redirect("/admin/profile")
            
            # Verify current password
            if not check_password_hash(current_user["password"], current_password):
                conn.close()
                flash("Incorrect password. Email not updated.", "danger")
                return redirect("/admin/profile")
        
        try:
            conn.execute("""
                UPDATE users SET name=%s, email=%s, phone=%s, date_of_birth=%s, gender=%s,
                admin_id=%s, role_level=%s, last_profile_update=%s
                WHERE id=%s
            """, (name, email, phone, date_of_birth, gender, admin_id_field, role_level,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"]))
            conn.commit()
        except Exception as db_err:
            conn.close()
            error_msg = str(db_err)
            if "UNIQUE" in error_msg.upper():
                flash("That email address is already in use by another account.", "danger")
            else:
                flash(f"Profile update failed: {error_msg}", "danger")
            return redirect("/admin/profile")
        
        # Refresh session from database
        updated_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if updated_user:
            session["name"] = updated_user["name"]
            session["email"] = updated_user["email"]
            if "phone" in updated_user.keys() and updated_user["phone"]:
                session["phone"] = updated_user["phone"]
        else:
            conn.close()
            flash("Profile update failed: user record not found.", "danger")
            return redirect("/admin/profile")
        
        conn.close()
        if email != current_email:
            flash("Email updated successfully. Please use the new email for future logins.", "success")
        else:
            flash("Profile updated successfully.", "success")
        return redirect("/admin/profile")
    
    conn.close()
    if user:
        user = dict(user)
        # Sync session with database profile picture
        if "profile_picture" in user and user["profile_picture"]:
            session["profile_pic"] = user["profile_picture"].replace("/static/", "", 1) if user["profile_picture"].startswith("/static/") else user["profile_picture"]
        else:
            session["profile_pic"] = ""
    return render_template("admin/admin_profile.html", user=user)

@app.route("/admin/profile/remove_picture", methods=["POST"])
def admin_remove_picture():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    
    if user and user["profile_picture"]:
        db_path = user["profile_picture"]
        
        # Delete from Supabase if it's a Supabase URL
        from supabase_storage import delete_profile_picture
        delete_profile_picture(db_path)
        
        # Also delete local file if it exists (for old uploads)
        if db_path.startswith("/static/"):
            rel_path = db_path.replace("/static/", "", 1)
            filepath = os.path.join('static', rel_path)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        conn.execute("UPDATE users SET profile_picture='' WHERE id=%s", (session["user_id"],))
        conn.commit()
        conn.close()
        session["profile_pic"] = ""
        log_activity(session["user_id"], "Deleted profile picture")
        flash("Profile picture removed.", "success")
    else:
        conn.close()
        flash("No profile picture to remove.", "warning")
    
    return redirect("/admin/profile")


# ── Admin: Upload Profile Picture (AJAX for cropping) ───────────────────────
@app.route("/admin/profile/upload_picture", methods=["POST"])
def admin_upload_picture():
    # Check authentication
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    if "profile_pic" not in request.files:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    file = request.files["profile_pic"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    # Validate file type
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return jsonify({"success": False, "error": "Invalid file type. Only JPG, JPEG, PNG allowed."}), 400
    
    # Validate file size (2MB max)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 2 * 1024 * 1024:
        return jsonify({"success": False, "error": "File size exceeds 2MB limit."}), 400
    
    try:
        # Upload to Supabase Storage
        from supabase_storage import upload_profile_picture, delete_profile_picture
        
        # Delete old profile picture if exists
        conn = get_db()
        old_pic = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if old_pic and old_pic["profile_picture"]:
            delete_profile_picture(old_pic["profile_picture"])
        
        # Upload new picture
        public_url = upload_profile_picture(file, session["user_id"])
        
        if not public_url:
            # Fallback to local storage if Supabase fails
            upload_folder = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"profile_admin_{session['user_id']}_{timestamp}.jpg"
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            public_url = f"/static/uploads/{filename}"
        
        # Update database
        conn.execute("UPDATE users SET profile_picture=%s WHERE id=%s", (public_url, session["user_id"]))
        conn.commit()
        conn.close()
        
        # Update session with the public URL
        if public_url.startswith("/static/"):
            session["profile_pic"] = public_url.replace("/static/", "", 1)
        else:
            session["profile_pic"] = public_url
        
        log_activity(session["user_id"], "Updated profile picture")
        
        return jsonify({"success": True, "message": "Profile picture updated successfully.", "image_url": public_url})
    except Exception as e:
        app.logger.exception("Admin profile upload error")
        return jsonify({"success": False, "error": str(e)}), 500

# ── Admin: Change Password ───────────────────────────────────────────────────
@app.route("/admin/change_password", methods=["GET","POST"])
def admin_change_password():
    g = require_role("admin")
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    
    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]
        
        if not check_password_hash(user["password"], current_password):
            conn.close()
            flash("Current password is incorrect.", "danger")
            return redirect("/admin/change_password")
        
        if new_password != confirm_password:
            conn.close()
            flash("New passwords do not match.", "danger")
            return redirect("/admin/change_password")
        
        if len(new_password) < 6:
            conn.close()
            flash("Password must be at least 6 characters long.", "danger")
            return redirect("/admin/change_password")
        
        conn.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new_password), session["user_id"]))
        conn.commit()
        conn.close()
        log_activity(session["user_id"], "Changed password")
        flash("Password changed successfully.", "success")
        return redirect("/admin/change_password")
    
    conn.close()
    return render_template("admin/admin_change_password.html")

# Student: join classroom
@app.route("/join_classroom", methods=["GET","POST"])
def join_classroom():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        
        if not code:
            flash("Please enter a classroom code.", "danger")
            return redirect("/join_classroom")
        
        try:
            conn = get_db()
            # Check for valid classroom code (including archived ones for proper error message)
            room = conn.execute("SELECT * FROM classrooms WHERE code=%s", (code,)).fetchone()
            if not room:
                conn.close()
                flash("❌ Invalid classroom code. Please check the code and try again.", "danger")
                return redirect("/join_classroom")
            
            # Check if classroom is archived
            if "is_archived" in room.keys() and room["is_archived"] == 1:
                conn.close()
                flash("⚠ This classroom is no longer accepting new students.", "danger")
                return redirect("/join_classroom")
            
            # Check if classroom is inactive (if there's an is_active column)
            if "is_active" in room.keys() and room["is_active"] == 0:
                conn.close()
                flash("⚠ This classroom is no longer accepting new students.", "danger")
                return redirect("/join_classroom")
            
            # Check already joined
            existing = conn.execute("SELECT id FROM classroom_members WHERE classroom_id=%s AND student_id=%s", (room["id"], session["user_id"])).fetchone()
            if existing:
                conn.close()
                flash("ℹ You have already joined this classroom.", "warning")
                return redirect("/student/classrooms")
            
            # All validations passed, join the classroom
            conn.execute("INSERT INTO classroom_members(classroom_id,student_id) VALUES(%s,%s)", (room["id"], session["user_id"]))
            conn.commit()
            conn.close()
            log_activity(session["user_id"], f"Joined classroom: {room['name']}")
            flash(f"✓ Joined classroom: {room['name']}!", "success")
            return redirect("/student/classrooms")
        except Exception as e:
            # Log the full error internally
            import logging
            logging.error(f"Error joining classroom: {str(e)}")
            # Show a friendly flash message
            flash("Something went wrong. Please try again.", "danger")
            return redirect("/join_classroom")
    return render_template("student/join_classroom.html")

# Student: My Classrooms
@app.route("/student/classrooms")
def student_classrooms():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    
    # Get student's classrooms with faculty name, student count, and exam count
    classrooms = conn.execute("""
        SELECT classrooms.id, classrooms.name, classrooms.subject, classrooms.code,
               users.name as faculty_name,
               (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
               (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
        FROM classrooms
        JOIN classroom_members ON classrooms.id = classroom_members.classroom_id
        JOIN users ON users.id = classrooms.faculty_id
        WHERE classroom_members.student_id = %s
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        ORDER BY classrooms.name
    """, (sid,)).fetchall()
    conn.close()
    
    return render_template("student/student_classrooms.html", classrooms=classrooms)

# Student: Profile
@app.route("/student/profile", methods=["GET","POST"])
def student_profile():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db()
    
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        reg_number = request.form.get("reg_number", "")
        phone = request.form.get("phone", "")
        date_of_birth = request.form.get("date_of_birth", "")
        gender = request.form.get("gender", "")
        program = request.form.get("program", "")
        section = request.form.get("section", "")
        current_password = request.form.get("current_password", "").strip()
        
        # Get current user data to check if email is being changed
        current_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        current_email = current_user["email"] if current_user else ""
        
        # If email is being changed, require password verification
        if email != current_email:
            if not current_password:
                conn.close()
                flash("Current password is required to change email.", "danger")
                return redirect("/student/profile")
            
            # Verify current password
            if not check_password_hash(current_user["password"], current_password):
                conn.close()
                flash("Incorrect password. Email not updated.", "danger")
                return redirect("/student/profile")
        
        try:
            conn.execute("""
                UPDATE users SET name=%s, email=%s, reg_number=%s, phone=%s,
                date_of_birth=%s, gender=%s, program=%s, section=%s, last_profile_update=%s
                WHERE id=%s
            """, (name, email, reg_number, phone, date_of_birth, gender, program, section,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"]))
            conn.commit()
        except Exception as db_err:
            conn.close()
            error_msg = str(db_err)
            if "UNIQUE" in error_msg.upper():
                flash("That email address is already in use by another account.", "danger")
            else:
                flash(f"Profile update failed: {error_msg}", "danger")
            return redirect("/student/profile")
        # Refresh session from database
        updated_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if updated_user:
            session["name"] = updated_user["name"]
            session["email"] = updated_user["email"]
            if "phone" in updated_user.keys() and updated_user["phone"]:
                session["phone"] = updated_user["phone"]
        else:
            conn.close()
            flash("Profile update failed: user record not found.", "danger")
            return redirect("/student/profile")
        
        conn.close()
        if email != current_email:
            flash("Email updated successfully. Please use the new email for future logins.", "success")
        else:
            flash("Profile updated successfully.", "success")
        return redirect("/student/profile")
    
    user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    conn.close()
    if user:
        user = dict(user)
        # Sync session with database profile picture
        if "profile_picture" in user and user["profile_picture"]:
            session["profile_pic"] = user["profile_picture"].replace("/static/", "", 1) if user["profile_picture"].startswith("/static/") else user["profile_picture"]
        else:
            session["profile_pic"] = ""
    return render_template("student/student_profile.html", user=user)

# Student: Change Password
@app.route("/student/change_password", methods=["GET","POST"])
def student_change_password():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db()
    
    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]
        
        user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        
        if not check_password_hash(user["password"], current_password):
            conn.close()
            flash("Current password is incorrect.", "danger")
            return redirect("/student/change_password")
        
        if new_password != confirm_password:
            conn.close()
            flash("New passwords do not match.", "danger")
            return redirect("/student/change_password")
        
        if len(new_password) < 6:
            conn.close()
            flash("Password must be at least 6 characters long.", "danger")
            return redirect("/student/change_password")
        
        conn.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new_password), session["user_id"]))
        conn.commit()
        conn.close()
        log_activity(session["user_id"], "Changed password")
        flash("Password changed successfully.", "success")
        return redirect("/student/change_password")
    
    conn.close()
    return render_template("student/student_change_password.html")

# Student: Upload Profile Picture (AJAX for cropping)
@app.route("/student/profile/upload_picture", methods=["POST"])
def student_upload_picture():
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    if "profile_pic" not in request.files:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    file = request.files["profile_pic"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    # Validate file type
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return jsonify({"success": False, "error": "Only JPG and PNG files are allowed"}), 400
    
    try:
        # Upload to Supabase Storage
        from supabase_storage import upload_profile_picture, delete_profile_picture
        
        # Delete old profile picture if exists
        conn = get_db()
        old_pic = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if old_pic and old_pic["profile_picture"]:
            delete_profile_picture(old_pic["profile_picture"])
        
        # Upload new picture
        public_url = upload_profile_picture(file, session["user_id"])
        
        if not public_url:
            # Fallback to local storage if Supabase fails
            filename = f"student_{session['user_id']}_{int(datetime.now().timestamp())}.jpg"
            filepath = os.path.join("static", "uploads", filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            public_url = f"/static/uploads/{filename}"
        
        # Update database (use profile_picture column for consistency)
        conn.execute("UPDATE users SET profile_picture=%s WHERE id=%s", (public_url, session["user_id"]))
        conn.commit()
        conn.close()
        
        # Update session with the public URL
        if public_url.startswith("/static/"):
            session["profile_pic"] = public_url.replace("/static/", "", 1)
        else:
            session["profile_pic"] = public_url
        
        log_activity(session["user_id"], "Updated profile picture")
        
        return jsonify({"success": True, "url": public_url})
        
    except Exception as e:
        app.logger.exception("Student profile upload error")
        return jsonify({"success": False, "error": str(e)}), 500

# Student: Remove Profile Picture
@app.route("/student/profile/remove_picture", methods=["POST"])
def student_remove_picture():
    if "user_id" not in session or session.get("role") != "student":
        return redirect("/")
    
    conn = get_db()
    user = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    
    if user and user["profile_picture"]:
        # Delete from Supabase if it's a Supabase URL
        from supabase_storage import delete_profile_picture
        delete_profile_picture(user["profile_picture"])
        
        # Also delete local file if it exists (for old uploads)
        db_path = user["profile_picture"]
        if db_path.startswith("/static/"):
            rel_path = db_path.replace("/static/", "", 1)
            filepath = os.path.join("static", rel_path)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        # Update database (use profile_picture column for consistency)
        conn.execute("UPDATE users SET profile_picture='' WHERE id=%s", (session["user_id"]))
        conn.commit()
        conn.close()
        session["profile_pic"] = ""
        log_activity(session["user_id"], "Deleted profile picture")
        flash("Profile picture deleted.", "success")
    else:
        conn.close()
    
    return redirect("/student/profile")

# ═══════════════════════════════════════════════════════════════════════════
# FACULTY
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/faculty")
def faculty():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db(); now = datetime.now().strftime("%Y-%m-%d")
    exams = conn.execute("""
        SELECT exams.id, exams.title, exams.exam_date, exams.duration,
               exams.launched, exams.published, exams.subject, exams.classroom_id,
               COUNT(questions.id) AS total_questions
        FROM exams LEFT JOIN questions ON exams.id=questions.exam_id
        WHERE exams.faculty_id=%s GROUP BY exams.id, exams.title, exams.exam_date, exams.duration,
               exams.launched, exams.published, exams.subject, exams.classroom_id ORDER BY exams.id DESC
    """, (session["user_id"],)).fetchall()
    exams_with_status = []
    for e in exams:
        if e["launched"] == 0:
            status = "draft"
        else:
            # Calculate submission-level stats (only valid records)
            total_submissions = conn.execute("""
                SELECT COUNT(*) as count FROM submissions s
                JOIN users u ON u.id = s.student_id
                WHERE s.exam_id=%s
            """, (e["id"],)).fetchone()['count']
            published_submissions = conn.execute("""
                SELECT COUNT(*) as count FROM submissions s
                JOIN users u ON u.id = s.student_id
                WHERE s.exam_id=%s AND s.result_published=1
            """, (e["id"],)).fetchone()['count']
            pending_submissions = total_submissions - published_submissions
            
            if total_submissions == 0:
                status = "active"
            elif pending_submissions == 0:
                status = "completed"
            else:
                status = "active"  # Has pending submissions
            
            # Convert to dict before adding fields (sqlite3.Row is immutable)
            e = dict(e)
            e["total_submissions"] = total_submissions
            e["published_submissions"] = published_submissions
            e["pending_submissions"] = pending_submissions
        
        exams_with_status.append({"exam": e, "status": status})
    
    # Pass classrooms for context with student counts
    my_classrooms = conn.execute(
        "SELECT * FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)
    ).fetchall()
    
    # Add student counts to classrooms (only valid records)
    classrooms_with_counts = []
    try:
        for c in my_classrooms:
            student_count = conn.execute("""
                SELECT COUNT(*) as count FROM classroom_members cm
                JOIN users u ON u.id = cm.student_id
                WHERE cm.classroom_id=%s
            """, (c["id"],)).fetchone()['count']
            exam_count = conn.execute(
                "SELECT COUNT(*) as count FROM exams WHERE classroom_id=%s AND faculty_id=%s", (c["id"], session["user_id"])
            ).fetchone()['count']
            classrooms_with_counts.append({
                "classroom": c,
                "student_count": student_count,
                "exam_count": exam_count
            })
    except sqlite3.OperationalError as e:
        app.logger.exception("Classroom counts query failed")
        classrooms_with_counts = []
    
    # Get recent activity logs
    try:
        recent_activities = conn.execute("""
            SELECT * FROM activity_log 
            WHERE user_id=%s 
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (session["user_id"],)).fetchall()
    except sqlite3.OperationalError:
        recent_activities = []
    
    # Calculate additional faculty insights
    try:
        total_students = sum(c["student_count"] for c in classrooms_with_counts)
    except:
        total_students = 0
    
    # Calculate average pass rate
    try:
        # First get exam total marks
        exam_totals = conn.execute("""
            SELECT exam_id, SUM(marks) as total_marks
            FROM questions
            GROUP BY exam_id
        """).fetchall()
        exam_total_map = {e["exam_id"]: e["total_marks"] for e in exam_totals}
        
        # Get submissions for published exams (only valid records)
        submissions_data = conn.execute("""
            SELECT submissions.exam_id, submissions.score, exams.pass_percentage
            FROM submissions
            JOIN users u ON u.id = submissions.student_id
            JOIN exams ON exams.id = submissions.exam_id
            WHERE exams.faculty_id=%s AND exams.published=1
        """, (session["user_id"],)).fetchall()
        
        # Calculate pass rate in Python
        passed_count = 0
        total_count = len(submissions_data)
        for sub in submissions_data:
            exam_id = sub["exam_id"]
            score = sub["score"]
            pass_pct = sub["pass_percentage"] or 50
            total_marks = exam_total_map.get(exam_id, 100)
            pass_threshold = (pass_pct * total_marks) / 100
            if score >= pass_threshold:
                passed_count += 1
        
        avg_pass_rate = round((passed_count * 100.0 / total_count), 1) if total_count > 0 else 0
    except Exception as e:
        app.logger.exception("Pass rate calculation failed")
        avg_pass_rate = 0
    
    # Upcoming exams (exams with exam_date >= today)
    try:
        upcoming_exams = len([e for e in exams if e["exam_date"] and e["exam_date"] >= now])
    except:
        upcoming_exams = 0
    
    # Recent result publications (exams published in last 7 days)
    try:
        recent_publications = conn.execute("""
            SELECT COUNT(*) as count FROM exams
            WHERE faculty_id=%s AND published=1 
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        """, (session["user_id"],)).fetchone()
        recent_publications_count = recent_publications["count"] if recent_publications else 0
    except Exception as e:
        app.logger.exception("Recent publications query failed")
        recent_publications_count = 0
    
    # Prepare exam chart data for Exam Results Overview
    exam_chart_data = []
    try:
        exam_totals = conn.execute("""
            SELECT exam_id, SUM(marks) as total_marks
            FROM questions
            GROUP BY exam_id
        """).fetchall()
        exam_total_map = {e["exam_id"]: e["total_marks"] for e in exam_totals}
        
        # Get published exams with pass rates
        published_exams = conn.execute("""
            SELECT exams.id, exams.title, exams.pass_percentage
            FROM exams
            WHERE exams.faculty_id=%s AND exams.published=1
        """, (session["user_id"],)).fetchall()
        
        for exam in published_exams:
            exam_id = exam["id"]
            total_marks = exam_total_map.get(exam_id, 100)
            pass_pct = exam["pass_percentage"] or 50
            
            # Get submissions for this exam (only valid records)
            submissions = conn.execute("""
                SELECT score FROM submissions s
                JOIN users u ON u.id = s.student_id
                WHERE s.exam_id=%s
            """, (exam_id,)).fetchall()
            
            if submissions:
                passed = sum(1 for s in submissions if s["score"] >= (pass_pct * total_marks / 100))
                pass_rate = round((passed * 100.0 / len(submissions)), 1)
                exam_chart_data.append({
                    "title": exam["title"][:20] + "..." if len(exam["title"]) > 20 else exam["title"],
                    "pass_rate": pass_rate
                })
    except Exception as e:
        app.logger.exception("Exam chart data calculation failed")
        exam_chart_data = []
    
    conn.close()
    return render_template("faculty/faculty_dashboard.html", 
                           exams=exams,
                           exams_with_status=exams_with_status, 
                           my_classrooms=my_classrooms,
                           classrooms_with_counts=classrooms_with_counts,
                           recent_activities=recent_activities,
                           total_students=total_students,
                           avg_pass_rate=avg_pass_rate,
                           upcoming_exams=upcoming_exams,
                           recent_publications=recent_publications_count,
                           exam_chart_data=exam_chart_data)

@app.route("/faculty/exams")
def faculty_exams():
    g = require_role("faculty")
    if g: return g
    conn = get_db(); now = datetime.now().strftime("%Y-%m-%d")
    exams = conn.execute("""
        SELECT exams.id, exams.title, exams.exam_date, exams.duration,
               exams.launched, exams.published, exams.subject, exams.classroom_id,
               COUNT(questions.id) AS total_questions
        FROM exams LEFT JOIN questions ON exams.id=questions.exam_id
        WHERE exams.faculty_id=%s GROUP BY exams.id ORDER BY exams.id DESC
    """, (session["user_id"],)).fetchall()
    exams_with_status = []
    for e in exams:
        if e["launched"] == 0:
            status = "draft"
        elif e["published"] == 1:
            status = "completed"
        else:
            status = "active"
        exams_with_status.append({"exam": e, "status": status})
    
    # Pass classrooms for context
    my_classrooms = conn.execute(
        "SELECT * FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)
    ).fetchall()
    conn.close()
    
    return render_template("faculty/faculty_exams.html", 
                           exams=exams,
                           exams_with_status=exams_with_status, 
                           my_classrooms=my_classrooms)

@app.route("/faculty/results")
def faculty_results():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    sel_subject = request.args.get("subject","")
    sel_classroom = request.args.get("classroom","")
    sel_exam = request.args.get("exam","")
    sel_date = request.args.get("date","")
    sel_date_from = request.args.get("date_from","")
    sel_date_to = request.args.get("date_to","")
    sel_result = request.args.get("result","")
    sel_sort = request.args.get("sort","")
    sel_search = request.args.get("search","").strip()
    
    query = """SELECT users.name as student_name, users.email as student_email,
               users.reg_number as student_reg_number,
               exams.title, exams.subject,
               exams.exam_date, submissions.score, submissions.submitted_at,
               exams.id as exam_id, exams.classroom_id, exams.pass_percentage,
               SUM(questions.marks) as total
               FROM submissions JOIN users ON users.id=submissions.student_id
               JOIN exams ON exams.id=submissions.exam_id
               JOIN questions ON questions.exam_id=exams.id
               WHERE exams.faculty_id=%s"""
    params = [session["user_id"]]
    
    if sel_subject: query += " AND exams.subject=%s"; params.append(sel_subject)
    if sel_classroom: query += " AND exams.classroom_id=%s"; params.append(sel_classroom)
    if sel_exam: query += " AND exams.id=%s"; params.append(sel_exam)
    if sel_date: query += " AND DATE(exams.exam_date)=%s"; params.append(sel_date)
    if sel_date_from: query += " AND exams.exam_date>=%s"; params.append(sel_date_from)
    if sel_date_to: query += " AND exams.exam_date<=%s"; params.append(sel_date_to)
    if sel_search:
        query += " AND (users.name LIKE %s OR users.reg_number LIKE %s OR users.email LIKE %s)"
        like_term = f"%{sel_search}%"
        params.extend([like_term, like_term, like_term])
    
    query += " GROUP BY users.id, users.name, users.email, users.reg_number, exams.id, exams.title, exams.subject, exams.exam_date, submissions.score, submissions.submitted_at, exams.classroom_id, exams.pass_percentage"
    
    # Pass/Fail filter must use HAVING clause after GROUP BY
    if sel_result:
        if sel_result == "pass":
            query += " HAVING submissions.score >= (SUM(questions.marks) * exams.pass_percentage / 100.0)"
        elif sel_result == "fail":
            query += " HAVING submissions.score < (SUM(questions.marks) * exams.pass_percentage / 100.0)"
    
    # Sorting
    if sel_sort == "score_desc":
        query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) DESC"
    elif sel_sort == "score_asc":
        query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) ASC"
    elif sel_sort == "date_desc":
        query += " ORDER BY submissions.submitted_at DESC"
    elif sel_sort == "date_asc":
        query += " ORDER BY submissions.submitted_at ASC"
    else:
        query += " ORDER BY exams.title, users.name"
    
    results  = conn.execute(query, params).fetchall()
    my_exams = conn.execute("SELECT id, title FROM exams WHERE faculty_id=%s ORDER BY title", (session["user_id"],)).fetchall()
    classrooms = conn.execute("SELECT id, name FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)).fetchall()
    subjects = conn.execute("SELECT DISTINCT subject FROM exams WHERE faculty_id=%s AND subject IS NOT NULL AND subject!='' ORDER BY subject", (session["user_id"],)).fetchall()
    subjects = [s["subject"] for s in subjects]
    conn.close()
    
    # Correct pass/fail using is_pass helper
    pass_count = sum(1 for r in results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
    fail_count = len(results) - pass_count
    
    return render_template("faculty/faculty_results.html", results=results, my_exams=my_exams,
                           classrooms=classrooms, subjects=subjects,
                           sel_subject=sel_subject, sel_classroom=sel_classroom,
                           sel_exam=sel_exam, sel_date=sel_date, sel_date_from=sel_date_from, sel_date_to=sel_date_to,
                           sel_result=sel_result, sel_sort=sel_sort, sel_search=sel_search,
                           pass_count=pass_count, fail_count=fail_count)

@app.route("/faculty/results/export")
def faculty_export_csv():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported faculty results to CSV")
    sel_subject = request.args.get("subject","")
    sel_classroom = request.args.get("classroom","")
    sel_exam = request.args.get("exam","")
    sel_date = request.args.get("date","")
    sel_date_from = request.args.get("date_from","")
    sel_date_to = request.args.get("date_to","")
    sel_result = request.args.get("result","")
    sel_sort = request.args.get("sort","")
    sel_search = request.args.get("search","").strip()
    
    query = """SELECT users.name as student_name, exams.title, exams.subject, exams.exam_date,
               submissions.score, submissions.submitted_at, exams.id as exam_id, exams.classroom_id,
               exams.pass_percentage, SUM(questions.marks) as total
               FROM submissions JOIN users ON users.id=submissions.student_id
               JOIN exams ON exams.id=submissions.exam_id
               JOIN questions ON questions.exam_id=exams.id
               WHERE exams.faculty_id=%s"""
    params = [session["user_id"]]
    
    if sel_subject: query += " AND exams.subject=%s"; params.append(sel_subject)
    if sel_classroom: query += " AND exams.classroom_id=%s"; params.append(sel_classroom)
    if sel_exam: query += " AND exams.id=%s"; params.append(sel_exam)
    if sel_date: query += " AND DATE(exams.exam_date)=%s"; params.append(sel_date)
    if sel_date_from: query += " AND exams.exam_date>=%s"; params.append(sel_date_from)
    if sel_date_to: query += " AND exams.exam_date<=%s"; params.append(sel_date_to)
    if sel_search:
        query += " AND (users.name LIKE %s OR users.reg_number LIKE %s OR users.email LIKE %s)"
        like_term = f"%{sel_search}%"
        params.extend([like_term, like_term, like_term])
    
    query += " GROUP BY users.id, users.name, exams.id, exams.title, exams.subject, exams.exam_date, submissions.score, submissions.submitted_at, exams.classroom_id, exams.pass_percentage"
    
    # Pass/Fail filter must use HAVING clause after GROUP BY
    if sel_result:
        if sel_result == "pass":
            query += " HAVING submissions.score >= (SUM(questions.marks) * exams.pass_percentage / 100.0)"
        elif sel_result == "fail":
            query += " HAVING submissions.score < (SUM(questions.marks) * exams.pass_percentage / 100.0)"
    
    # Sorting
    if sel_sort == "score_desc":
        query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) DESC"
    elif sel_sort == "score_asc":
        query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) ASC"
    elif sel_sort == "date_desc":
        query += " ORDER BY submissions.submitted_at DESC"
    elif sel_sort == "date_asc":
        query += " ORDER BY submissions.submitted_at ASC"
    else:
        query += " ORDER BY exams.title, users.name"
    
    results = conn.execute(query, params).fetchall()
    conn.close()
    
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["Student","Exam","Subject","Date","Score","Total","Percentage","Result","Submitted"])
    for r in results:
        pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
        result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
        w.writerow([r["student_name"],r["title"],r["subject"],r["exam_date"],
                    r["score"],r["total"],f"{pct}%",result,r["submitted_at"]])
    
    # Summary row
    total_count = len(results)
    pass_count = sum(1 for r in results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
    fail_count = total_count - pass_count
    avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in results) / total_count if total_count else 0
    w.writerow([])
    w.writerow(["SUMMARY","","","","","","","",""])
    w.writerow(["Total Records", total_count, "", "", "", "", "", "", ""])
    w.writerow(["Passed", pass_count, "", "", "", "", "", "", ""])
    w.writerow(["Failed", fail_count, "", "", "", "", "", "", ""])
    w.writerow(["Average %", f"{avg_pct:.1f}%", "", "", "", "", "", "", ""])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"]="text/csv"
    resp.headers["Content-Disposition"]="attachment; filename=my_results.csv"
    return resp

@app.route("/faculty/results/export/pdf")
def faculty_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from reportlab.lib import colors
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    g = require_role("faculty")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported faculty results to PDF")
        sel_subject = request.args.get("subject","")
        sel_classroom = request.args.get("classroom","")
        sel_exam = request.args.get("exam","")
        sel_date = request.args.get("date","")
        sel_date_from = request.args.get("date_from","")
        sel_date_to = request.args.get("date_to","")
        sel_result = request.args.get("result","")
        sel_sort = request.args.get("sort","")
        sel_search = request.args.get("search","").strip()
        
        query = """SELECT users.name as student_name, exams.title, exams.subject, exams.exam_date,
                   submissions.score, submissions.submitted_at, exams.id as exam_id, exams.classroom_id,
                   exams.pass_percentage, SUM(questions.marks) as total
                   FROM submissions JOIN users ON users.id=submissions.student_id
                   JOIN exams ON exams.id=submissions.exam_id
                   JOIN questions ON questions.exam_id=exams.id
                   WHERE exams.faculty_id=%s"""
        params = [session["user_id"]]
        
        if sel_subject: query += " AND exams.subject=%s"; params.append(sel_subject)
        if sel_classroom: query += " AND exams.classroom_id=%s"; params.append(sel_classroom)
        if sel_exam: query += " AND exams.id=%s"; params.append(sel_exam)
        if sel_date: query += " AND DATE(exams.exam_date)=%s"; params.append(sel_date)
        if sel_date_from: query += " AND exams.exam_date>=%s"; params.append(sel_date_from)
        if sel_date_to: query += " AND exams.exam_date<=%s"; params.append(sel_date_to)
        if sel_search:
            query += " AND (users.name LIKE %s OR users.reg_number LIKE %s OR users.email LIKE %s)"
            like_term = f"%{sel_search}%"
            params.extend([like_term, like_term, like_term])
        
        query += " GROUP BY users.id, exams.id"
        
        # Pass/Fail filter must use HAVING clause after GROUP BY
        if sel_result:
            if sel_result == "pass":
                query += " HAVING submissions.score >= (SUM(questions.marks) * exams.pass_percentage / 100.0)"
            elif sel_result == "fail":
                query += " HAVING submissions.score < (SUM(questions.marks) * exams.pass_percentage / 100.0)"
        
        # Sorting
        if sel_sort == "score_desc":
            query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) DESC"
        elif sel_sort == "score_asc":
            query += " ORDER BY (CAST(submissions.score AS FLOAT)/total) ASC"
        elif sel_sort == "date_desc":
            query += " ORDER BY submissions.submitted_at DESC"
        elif sel_sort == "date_asc":
            query += " ORDER BY submissions.submitted_at ASC"
        else:
            query += " ORDER BY exams.title, users.name"
        
        results = conn.execute(query, params).fetchall()
        conn.close()
        
        # Calculate summary stats
        total_count = len(results)
        pass_count = sum(1 for r in results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
        fail_count = total_count - pass_count
        avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in results) / total_count if total_count else 0
        
        # Create PDF with shared configuration
        from flask import Response
        from reportlab.platypus import Paragraph, Table
        from pdf_utils import (
            create_pdf_document, get_pdf_styles, get_column_widths,
            get_table_style, format_datetime, create_header_table,
            create_summary_table, apply_column_alignment
        )
        import os
        
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('FACULTY EXAM REPORT', logo_path))
        
        # Applied filters
        if any([sel_subject, sel_classroom, sel_exam, sel_date, sel_result]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if sel_subject: elements.append(Paragraph(f"Subject: {sel_subject}", styles['wrap']))
            if sel_classroom: elements.append(Paragraph(f"Classroom ID: {sel_classroom}", styles['wrap']))
            if sel_exam: elements.append(Paragraph(f"Exam ID: {sel_exam}", styles['wrap']))
            if sel_date: elements.append(Paragraph(f"Date: {sel_date}", styles['wrap']))
            if sel_result: elements.append(Paragraph(f"Result: {sel_result}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Records:", str(total_count)),
            ("Passed:", str(pass_count)),
            ("Failed:", str(fail_count)),
            ("Average %:", f"{avg_pct:.1f}%"),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Student", "Exam", "Subject", "Date", "Score", "Total", "%", "Result"]
        data = [headers]
        for r in results:
            pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
            result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
            
            data.append([
                Paragraph(r["student_name"] or "—", styles['name']),
                Paragraph(r["title"] or "—", styles['wrap']),
                Paragraph(r["subject"] or "—", styles['wrap']),
                Paragraph(format_datetime(r["exam_date"]), styles['wrap']),
                Paragraph(str(r["score"]), styles['wrap']),
                Paragraph(str(r["total"]), styles['wrap']),
                Paragraph(f"{pct}%", styles['wrap']),
                Paragraph(result, styles['wrap'])
            ])
        
        # Get column widths and table style
        col_widths = get_column_widths('faculty')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': False},   # Student - no wrap
            {'align': 'LEFT', 'wrap': True},    # Exam - wrap
            {'align': 'LEFT', 'wrap': True},    # Subject - wrap
            {'align': 'CENTER', 'wrap': True},  # Date - wrap for date/time
            {'align': 'CENTER', 'wrap': False}, # Score - no wrap
            {'align': 'CENTER', 'wrap': False}, # Total - no wrap
            {'align': 'CENTER', 'wrap': False}, # % - no wrap
            {'align': 'CENTER', 'wrap': False}, # Result - no wrap
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="faculty_results.pdf"'}
        )
    except Exception as e:
        import traceback
        app.logger.exception("PDF generation error (faculty results)")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/faculty/results")

@app.route("/faculty/student_analytics")
def student_analytics():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    fid = session["user_id"]
    
    # Get filter values
    sel_classroom = request.args.get("classroom", "")
    sel_exam = request.args.get("exam", "")
    sel_subject = request.args.get("subject", "")
    
    # Get filter options
    classrooms = conn.execute("SELECT id, name FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (fid,)).fetchall()
    exams = conn.execute("SELECT id, title FROM exams WHERE faculty_id=%s ORDER BY title", (fid,)).fetchall()
    subjects = conn.execute("SELECT DISTINCT subject FROM exams WHERE faculty_id=%s AND subject IS NOT NULL AND subject!='' ORDER BY subject", (fid,)).fetchall()
    subjects = [s["subject"] for s in subjects]
    
    # Build base query for student performance data
    query = """
        SELECT users.id as student_id, users.name as student_name,
               exams.id as exam_id, exams.title as exam_title, exams.subject,
               exams.classroom_id, classrooms.name as classroom_name,
               submissions.score, SUM(questions.marks) as total,
               exams.pass_percentage
        FROM submissions
        JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        LEFT JOIN classrooms ON classrooms.id=exams.classroom_id
        JOIN questions ON questions.exam_id=exams.id
        WHERE exams.faculty_id=%s
    """
    params = [fid]
    
    if sel_classroom:
        query += " AND exams.classroom_id=%s"
        params.append(sel_classroom)
    if sel_exam:
        query += " AND exams.id=%s"
        params.append(sel_exam)
    if sel_subject:
        query += " AND exams.subject=%s"
        params.append(sel_subject)
    
    query += " GROUP BY users.id, exams.id"
    
    results = conn.execute(query, params).fetchall()
    
    # Top Performers (highest average percentage)
    student_scores = {}
    for r in results:
        if r["total"] and r["total"] > 0:
            pct = (r["score"] / r["total"]) * 100
            if r["student_id"] not in student_scores:
                student_scores[r["student_id"]] = {"name": r["student_name"], "scores": [], "count": 0}
            student_scores[r["student_id"]]["scores"].append(pct)
            student_scores[r["student_id"]]["count"] += 1
    
    top_performers = []
    needs_improvement = []
    for sid, data in student_scores.items():
        avg_pct = sum(data["scores"]) / len(data["scores"])
        top_performers.append({"name": data["name"], "avg_pct": avg_pct, "attempts": data["count"]})
        needs_improvement.append({"name": data["name"], "avg_pct": avg_pct, "attempts": data["count"]})
    
    top_performers.sort(key=lambda x: x["avg_pct"], reverse=True)
    needs_improvement.sort(key=lambda x: x["avg_pct"])
    
    top_performers = top_performers[:5]
    needs_improvement = needs_improvement[:5]
    
    # Classroom Analytics
    classroom_stats = {}
    for r in results:
        cid = r["classroom_id"]
        cname = r["classroom_name"] or "Uncategorized"
        if cid not in classroom_stats:
            classroom_stats[cid] = {"name": cname, "scores": [], "total": 0, "pass": 0, "fail": 0}
        if r["total"] and r["total"] > 0:
            pct = r["score"] / r["total"]
            classroom_stats[cid]["scores"].append(pct)
            classroom_stats[cid]["total"] += 1
            if is_pass(r["score"], r["total"], r["pass_percentage"] or 50):
                classroom_stats[cid]["pass"] += 1
            else:
                classroom_stats[cid]["fail"] += 1
    
    classroom_analytics = []
    for cid, data in classroom_stats.items():
        if data["total"] > 0:
            avg_score = (sum(data["scores"]) / len(data["scores"])) * 100
            pass_pct = (data["pass"] / data["total"]) * 100
            fail_pct = (data["fail"] / data["total"]) * 100
            classroom_analytics.append({
                "name": data["name"],
                "avg_score": avg_score,
                "pass_pct": pass_pct,
                "fail_pct": fail_pct,
                "total_students": data["total"]
            })
    
    # Exam Analytics
    exam_stats = {}
    for r in results:
        eid = r["exam_id"]
        etitle = r["exam_title"]
        if eid not in exam_stats:
            exam_stats[eid] = {"title": etitle, "scores": [], "attempts": 0}
        if r["total"] and r["total"] > 0:
            pct = r["score"] / r["total"]
            exam_stats[eid]["scores"].append(pct)
            exam_stats[eid]["attempts"] += 1
    
    exam_analytics = []
    for eid, data in exam_stats.items():
        if data["attempts"] > 0:
            avg_marks = (sum(data["scores"]) / len(data["scores"])) * 100
            highest_marks = max(data["scores"]) * 100
            lowest_marks = min(data["scores"]) * 100
            exam_analytics.append({
                "title": data["title"],
                "attempts": data["attempts"],
                "avg_marks": avg_marks,
                "highest_marks": highest_marks,
                "lowest_marks": lowest_marks
            })
    
    conn.close()
    return render_template("faculty/faculty_analytics.html",
                           top_performers=top_performers,
                           needs_improvement=needs_improvement,
                           classroom_analytics=classroom_analytics,
                           exam_analytics=exam_analytics,
                           classrooms=classrooms,
                           exams=exams,
                           subjects=subjects,
                           sel_classroom=sel_classroom,
                           sel_exam=sel_exam,
                           sel_subject=sel_subject)

@app.route("/faculty/student_analytics/export")
def student_analytics_export_csv():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported student analytics to CSV")
    fid = session["user_id"]
    
    # Get filter values
    sel_classroom = request.args.get("classroom", "")
    sel_exam = request.args.get("exam", "")
    sel_subject = request.args.get("subject", "")
    
    # Build base query for student performance data
    query = """
        SELECT users.id as student_id, users.name as student_name,
               exams.id as exam_id, exams.title as exam_title, exams.subject,
               exams.classroom_id, classrooms.name as classroom_name,
               submissions.score, SUM(questions.marks) as total,
               exams.pass_percentage
        FROM submissions
        JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        LEFT JOIN classrooms ON classrooms.id=exams.classroom_id
        JOIN questions ON questions.exam_id=exams.id
        WHERE exams.faculty_id=%s
    """
    params = [fid]
    
    if sel_classroom:
        query += " AND exams.classroom_id=%s"
        params.append(sel_classroom)
    if sel_exam:
        query += " AND exams.id=%s"
        params.append(sel_exam)
    if sel_subject:
        query += " AND exams.subject=%s"
        params.append(sel_subject)
    
    query += " GROUP BY users.id, exams.id"
    
    results = conn.execute(query, params).fetchall()
    conn.close()
    
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["Student Name", "Exam Title", "Subject", "Classroom", "Score", "Total Marks", "Percentage", "Result"])
    
    for r in results:
        if r["total"] and r["total"] > 0:
            pct = round((r["score"] / r["total"]) * 100, 1)
            result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
            w.writerow([
                r["student_name"],
                r["exam_title"],
                r["subject"] or "—",
                r["classroom_name"] or "—",
                r["score"],
                r["total"],
                f"{pct}%",
                result
            ])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=student_analytics.csv"
    return resp

@app.route("/faculty/student_analytics/export/pdf")
def student_analytics_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from reportlab.lib import colors
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    import traceback
    
    g = require_role("faculty")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported student analytics to PDF")
        fid = session["user_id"]
        
        # Get filter values
        sel_classroom = request.args.get("classroom", "")
        sel_exam = request.args.get("exam", "")
        sel_subject = request.args.get("subject", "")
        
        # Build base query for student performance data
        query = """
            SELECT users.id as student_id, users.name as student_name,
                   exams.id as exam_id, exams.title as exam_title, exams.subject,
                   exams.classroom_id, classrooms.name as classroom_name,
                   submissions.score, SUM(questions.marks) as total,
                   exams.pass_percentage
            FROM submissions
            JOIN users ON users.id=submissions.student_id
            JOIN exams ON exams.id=submissions.exam_id
            LEFT JOIN classrooms ON classrooms.id=exams.classroom_id
            JOIN questions ON questions.exam_id=exams.id
            WHERE exams.faculty_id=%s
        """
        params = [fid]
        
        if sel_classroom:
            query += " AND exams.classroom_id=%s"
            params.append(sel_classroom)
        if sel_exam:
            query += " AND exams.id=%s"
            params.append(sel_exam)
        if sel_subject:
            query += " AND exams.subject=%s"
            params.append(sel_subject)
        
        query += " GROUP BY users.id, exams.id"
        
        results = conn.execute(query, params).fetchall()
        conn.close()
        
        # Create PDF with shared configuration
        from flask import Response
        from reportlab.platypus import Paragraph, Table
        from pdf_utils import (
            create_pdf_document, get_pdf_styles, get_column_widths,
            get_table_style, format_datetime, create_header_table,
            create_summary_table, apply_column_alignment
        )
        
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('STUDENT ANALYTICS REPORT', logo_path))
        
        # Applied filters
        if any([sel_classroom, sel_exam, sel_subject]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if sel_classroom: elements.append(Paragraph(f"Classroom ID: {sel_classroom}", styles['wrap']))
            if sel_exam: elements.append(Paragraph(f"Exam ID: {sel_exam}", styles['wrap']))
            if sel_subject: elements.append(Paragraph(f"Subject: {sel_subject}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Records:", str(len(results))),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Student Name", "Exam Title", "Subject", "Classroom", "Score", "Total", "%", "Result"]
        data = [headers]
        for r in results:
            if r["total"] and r["total"] > 0:
                pct = round((r["score"] / r["total"]) * 100, 1)
                result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
                data.append([
                    Paragraph(r["student_name"] or "—", styles['name']),
                    Paragraph(r["exam_title"] or "—", styles['wrap']),
                    Paragraph(r["subject"] or "—", styles['wrap']),
                    Paragraph(r["classroom_name"] or "—", styles['wrap']),
                    Paragraph(str(r["score"]), styles['wrap']),
                    Paragraph(str(r["total"]), styles['wrap']),
                    Paragraph(f"{pct}%", styles['wrap']),
                    Paragraph(result, styles['wrap'])
                ])
        
        # Get column widths and table style
        col_widths = get_column_widths('analytics')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': False},   # Student Name - no wrap
            {'align': 'LEFT', 'wrap': True},    # Exam Title - wrap
            {'align': 'LEFT', 'wrap': True},    # Subject - wrap
            {'align': 'LEFT', 'wrap': True},    # Classroom - wrap
            {'align': 'CENTER', 'wrap': False}, # Score - no wrap
            {'align': 'CENTER', 'wrap': False}, # Total - no wrap
            {'align': 'CENTER', 'wrap': False}, # % - no wrap
            {'align': 'CENTER', 'wrap': False}, # Result - no wrap
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="student_analytics.pdf"'}
        )
    except Exception as e:
        import traceback
        app.logger.exception("Student analytics PDF error")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/faculty/student_analytics")

@app.route("/preview_exam/<exam_id>")
def preview_exam(exam_id):
    g = require_role("admin", "faculty"); 
    if g: return g
    conn = get_db()
    if session["role"] == "admin":
        exam = conn.execute("SELECT * FROM exams WHERE id=%s", (exam_id,)).fetchone()
        if not exam:
            conn.close()
            return redirect("/admin/exams")
    else:
        exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id,session["user_id"])).fetchone()
        if not exam:
            conn.close()
            return redirect("/faculty")
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    exam_results = None
    if session["role"] == "admin":
        total_marks = sum(q["marks"] or 1 for q in questions)
        exam_results = conn.execute("""
            SELECT users.name as student_name, users.reg_number, submissions.score,
                   submissions.submitted_at, submissions.result_published
            FROM submissions
            JOIN users ON users.id = submissions.student_id
            WHERE submissions.exam_id = %s
            ORDER BY submissions.submitted_at DESC
        """, (exam_id,)).fetchall()
        exam_results = [dict(r, total=total_marks) for r in exam_results]
    conn.close()
    return render_template("faculty/preview_exam.html", exam=exam, questions=questions, exam_results=exam_results)

@app.route("/copy_exam/<exam_id>")
def copy_exam(exam_id):
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    orig = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not orig:
        conn.close()
        flash("Exam not found.", "danger"); return redirect("/faculty")
    conn.execute("INSERT INTO exams(title,faculty_id,duration,exam_date,subject,classroom_id) VALUES(%s,%s,%s,%s,%s,%s)", (f"Copy of {orig['title']}",session["user_id"],orig["duration"],orig["exam_date"],orig["subject"],orig["classroom_id"]))
    conn.commit()
    new_id = conn.last_insert_id()
    for q in conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall():
        conn.execute("INSERT INTO questions(exam_id,question,option1,option2,option3,option4,correct_answer,difficulty) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", (new_id,q["question"],q["option1"],q["option2"],q["option3"],q["option4"],q["correct_answer"],q["difficulty"]))
    conn.commit()
    conn.close()
    flash("Exam copied.", "success"); return redirect("/faculty")

@app.route("/create_exam", methods=["GET","POST"])
def create_exam():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    
    if request.method == "POST":
        action = request.form.get("action", "create")
        title=request.form["title"]; duration=request.form["duration"]
        exam_date=request.form["exam_date"]; subject=request.form.get("subject","")
        pass_percentage=request.form.get("pass_percentage", "50")
        instructions=request.form.get("instructions", "")
        method=request.form["method"]
        
        classroom_id = request.form.get("classroom_id","").strip()
        if not classroom_id:
            flash("Please select a classroom for this exam.", "warning")
            classrooms = conn.execute("""
                SELECT classrooms.*,
                       (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
                       users.name as faculty_name,
                       (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
                FROM classrooms
                LEFT JOIN users ON users.id = classrooms.faculty_id
                WHERE classrooms.faculty_id=%s
                ORDER BY classrooms.name
            """, (session["user_id"],)).fetchall()
            
            # Get statistics
            stats = {
                'total_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s", (session["user_id"],)).fetchone()['count'],
                'published_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=1", (session["user_id"],)).fetchone()['count'],
                'draft_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=0", (session["user_id"],)).fetchone()['count'],
                'classrooms': conn.execute("SELECT COUNT(*) as count FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0)", (session["user_id"],)).fetchone()['count']
            }
            conn.close()
            
            return render_template("faculty/create_exam.html", classrooms=classrooms, stats=stats)
        
        # Validate pass_percentage
        try:
            pass_pct = float(pass_percentage) if pass_percentage else 50.0
            if not (0 <= pass_pct <= 100):
                flash("Pass percentage must be between 0 and 100.", "danger")
                classrooms = conn.execute("""
                    SELECT classrooms.*,
                           (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
                           users.name as faculty_name,
                           (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
                    FROM classrooms
                    LEFT JOIN users ON users.id = classrooms.faculty_id
                    WHERE classrooms.faculty_id=%s
                    ORDER BY classrooms.name
                """, (session["user_id"],)).fetchall()
                
                # Get statistics
                stats = {
                    'total_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s", (session["user_id"],)).fetchone()['count'],
                    'published_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=1", (session["user_id"],)).fetchone()['count'],
                    'draft_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=0", (session["user_id"],)).fetchone()['count'],
                    'classrooms': conn.execute("SELECT COUNT(*) as count FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0)", (session["user_id"],)).fetchone()['count']
                }
                conn.close()
                
                return render_template("faculty/create_exam.html", classrooms=classrooms, stats=stats)
        except ValueError:
            flash("Invalid pass percentage value.", "danger")
            classrooms = conn.execute("""
                SELECT classrooms.*,
                       (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
                       users.name as faculty_name,
                       (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
                FROM classrooms
                LEFT JOIN users ON users.id = classrooms.faculty_id
                WHERE classrooms.faculty_id=%s
                ORDER BY classrooms.name
            """, (session["user_id"],)).fetchall()
            
            # Get statistics
            stats = {
                'total_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s", (session["user_id"],)).fetchone()['count'],
                'published_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=1", (session["user_id"],)).fetchone()['count'],
                'draft_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=0", (session["user_id"],)).fetchone()['count'],
                'classrooms': conn.execute("SELECT COUNT(*) as count FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0)", (session["user_id"],)).fetchone()['count']
            }
            conn.close()
            
            return render_template("faculty/create_exam.html", classrooms=classrooms, stats=stats)
        
        # Insert exam
        published = 1 if action == "create" else 0
        conn.execute("INSERT INTO exams(title,faculty_id,duration,exam_date,subject,classroom_id,total_marks,pass_mark,pass_percentage,instructions,published) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (title,session["user_id"],duration,exam_date,subject,classroom_id,0,50,pass_pct,instructions,published))
        conn.commit()
        exam_id = conn.last_insert_id()
        conn.close()
        log_activity(session["user_id"], f"Created exam: {title}")
        
        if action == "draft":
            flash("Exam saved as draft.", "success")
            return redirect(f"/edit_exam/{exam_id}")
        else:
            flash("Exam created.", "success")
            return redirect(f"/add_questions/{exam_id}" if method=="manual" else f"/select_questions/{exam_id}")
    
    # GET request
    classrooms = conn.execute("""
        SELECT classrooms.*,
               (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
               users.name as faculty_name,
               (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
        FROM classrooms
        LEFT JOIN users ON users.id = classrooms.faculty_id
        WHERE classrooms.faculty_id=%s
        ORDER BY classrooms.name
    """, (session["user_id"],)).fetchall()
    
    # Get statistics
    stats = {
        'total_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s", (session["user_id"],)).fetchone()['count'],
        'published_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=1", (session["user_id"],)).fetchone()['count'],
        'draft_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE faculty_id=%s AND published=0", (session["user_id"],)).fetchone()['count'],
        'classrooms': conn.execute("SELECT COUNT(*) as count FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0)", (session["user_id"],)).fetchone()['count']
    }
    conn.close()
    
    return render_template("faculty/create_exam.html", classrooms=classrooms, stats=stats)

@app.route("/edit_exam/<exam_id>", methods=["GET","POST"])
def edit_exam(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger")
        return redirect("/faculty")
    # Only check launched field - published is for result publication, not launch state
    if exam["launched"] == 1:
        conn.close()
        flash("Cannot edit a launched exam.", "warning")
        return redirect("/faculty")
    
    if request.method == "POST":
        title=request.form["title"]
        duration=request.form["duration"]
        exam_date=request.form["exam_date"]
        subject=request.form.get("subject","")
        pass_percentage=request.form.get("pass_percentage", "50")
        instructions=request.form.get("instructions", "")
        # Validate pass_percentage
        try:
            pass_pct = float(pass_percentage) if pass_percentage else 50.0
            if not (0 <= pass_pct <= 100):
                flash("Pass percentage must be between 0 and 100.", "danger")
                classrooms = conn.execute("SELECT * FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)).fetchall()
                conn.close()
                return render_template("faculty/edit_exam.html", exam=exam, classrooms=classrooms)
        except ValueError:
            flash("Invalid pass percentage value.", "danger")
            classrooms = conn.execute("SELECT * FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)).fetchall()
            conn.close()
            return render_template("faculty/edit_exam.html", exam=exam, classrooms=classrooms)
        conn.execute("UPDATE exams SET title=%s, duration=%s, exam_date=%s, subject=%s, pass_percentage=%s, instructions=%s WHERE id=%s", (title, duration, exam_date, subject, pass_pct, instructions, exam_id))
        conn.commit()
        conn.close()
        log_activity(session["user_id"], f"Edited exam: {title}")
        flash("Exam updated.", "success")
        return redirect("/faculty")
    
    classrooms = conn.execute("SELECT * FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("faculty/edit_exam.html", exam=exam, classrooms=classrooms)

@app.route("/add_questions/<exam_id>", methods=["GET","POST"])
def add_questions(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        return redirect("/faculty")
    # Only check launched field - published is for result publication, not launch state
    if exam["launched"] == 1:
        conn.close()
        flash("Cannot add questions to a launched exam.", "warning")
        return redirect(f"/view_questions/{exam_id}")
    if request.method == "POST":
        q    = request.form.get("question","").strip()
        o1   = request.form.get("o1","").strip()
        o2   = request.form.get("o2","").strip()
        o3   = request.form.get("o3","").strip()
        o4   = request.form.get("o4","").strip()
        # Get the selected correct option and use its value as the correct answer
        correct_option = request.form.get("correct_option")
        if correct_option == "o1":
            ans = o1
        elif correct_option == "o2":
            ans = o2
        elif correct_option == "o3":
            ans = o3
        elif correct_option == "o4":
            ans = o4
        else:
            flash("Please select the correct answer.", "danger")
            q_count = conn.execute("SELECT COUNT(*) as count FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['count']
            questions_list = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
            conn.close()
            return render_template("faculty/add_questions.html", exam_id=exam_id, exam=exam,
                                   q_count=q_count, questions_list=questions_list)
        diff = request.form.get("difficulty","medium").strip() or "medium"
        marks = request.form.get("marks", "1").strip() or "1"
        if not all([q, o1, o2, o3, o4, ans]):
            flash("All fields are required.", "danger")
        elif conn.execute("SELECT id FROM questions WHERE exam_id=%s AND question=%s", (exam_id, q)).fetchone():
            flash("Duplicate question — this question already exists in this exam.", "warning")
        else:
            conn.execute("""INSERT INTO questions
                (exam_id,question,option1,option2,option3,option4,correct_answer,difficulty,marks)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (exam_id, q, o1, o2, o3, o4, ans, diff, marks))
            conn.commit()
            # Recalculate total_marks
            total = conn.execute("SELECT SUM(marks) as total FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['total'] or 0
            conn.execute("UPDATE exams SET total_marks=%s WHERE id=%s", (total, exam_id))
            conn.commit()
            flash("Question added.", "success")
    q_count = conn.execute("SELECT COUNT(*) as count FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['count']
    questions_list = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    conn.close()
    return render_template("faculty/add_questions.html", exam_id=exam_id, exam=exam,
                           q_count=q_count, questions_list=questions_list)

@app.route("/select_questions/<exam_id>", methods=["GET","POST"])
def select_questions(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger"); return redirect("/faculty")
    if request.method == "POST":
        added = 0
        for qid in request.form.getlist("questions"):
            q = conn.execute("SELECT * FROM question_bank WHERE id=%s", (qid,)).fetchone()
            if not conn.execute("SELECT id FROM questions WHERE exam_id=%s AND question=%s", (exam_id,q["question"])).fetchone():
                marks = q.get("marks", 1) if q.get("marks") and q.get("marks") > 0 else 1
                conn.execute("INSERT INTO questions(exam_id,question,option1,option2,option3,option4,correct_answer,difficulty,marks) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (exam_id,q["question"],q["option1"],q["option2"],q["option3"],q["option4"],q["correct_answer"],q["difficulty"] if q["difficulty"] else "medium", marks))
                added += 1
        conn.commit()
        # Recalculate total_marks
        total = conn.execute("SELECT SUM(marks) as total FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['total'] or 0
        conn.execute("UPDATE exams SET total_marks=%s WHERE id=%s", (total, exam_id))
        conn.commit()
        conn.close()
        flash(f"{added} question(s) added.", "success")
        return redirect(f"/add_questions/{exam_id}")
    questions = conn.execute("SELECT * FROM question_bank WHERE faculty_id=%s", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("faculty/select_questions.html", questions=questions, exam_id=exam_id)

@app.route("/launch_exam/<exam_id>")
def launch_exam(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        return redirect("/faculty")
    if exam["published"] == 1:
        conn.close()
        flash("This exam is already completed.", "warning"); return redirect("/faculty")
    if exam["launched"] == 1:
        conn.close()
        flash("This exam is already launched.", "warning"); return redirect("/faculty")
    if not conn.execute("SELECT id FROM questions WHERE exam_id=%s", (exam_id,)).fetchone():
        conn.close()
        flash("Add at least one question before launching.", "warning")
        return redirect(f"/add_questions/{exam_id}")
    conn.execute("UPDATE exams SET launched=1 WHERE id=%s", (exam_id,)); conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Launched exam id={exam_id}")
    flash("Exam launched! Students can now attempt it.", "success")
    # Redirect to classroom detail if exam belongs to a classroom
    if exam["classroom_id"]:
        return redirect(f"/classrooms/{exam['classroom_id']}")
    return redirect("/faculty")

@app.route("/publish_result/<exam_id>")
def publish_result(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger"); return redirect("/faculty")
    if exam["published"] == 1:
        conn.close()
        flash("Results already published.", "warning"); return redirect("/faculty")
    conn.execute("UPDATE exams SET published=1 WHERE id=%s", (exam_id,))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Published results for exam: {exam['title']}")
    flash("Results published successfully.", "success")
    return redirect("/faculty")

@app.route("/delete_exam/<exam_id>")
def delete_exam(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger"); return redirect("/faculty")
    # Archive instead of permanently deleting
    conn.execute("""UPDATE exams SET is_archived=1, archived_at=CURRENT_TIMESTAMP,
                    archived_by=%s WHERE id=%s AND faculty_id=%s""",
                 (session["user_id"], exam_id, session["user_id"]))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Archived exam: {exam['title']}")
    flash(f"Exam \"{exam['title']}\" has been archived. You can restore it from the Archive Center.", "success")
    return redirect("/faculty")

@app.route("/view_questions/<exam_id>")
def view_questions(exam_id):
    g = require_role("admin", "faculty")
    if g: return g
    conn = get_db()
    if session["role"] == "faculty":
        exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
        if not exam:
            conn.close()
            flash("Exam not found.", "danger"); return redirect("/faculty")
    else:
        exam = conn.execute("SELECT * FROM exams WHERE id=%s", (exam_id,)).fetchone()
        if not exam:
            conn.close()
            flash("Exam not found.", "danger"); return redirect("/admin")
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    conn.close()
    return render_template("faculty/view_questions.html", questions=questions, exam_id=exam_id, exam=exam)

@app.route("/edit_questions/<exam_id>")
def edit_questions(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        return redirect("/faculty")
    # Only check launched field - published is for result publication, not launch state
    if exam["launched"] == 1:
        conn.close()
        flash("Cannot edit questions of a launched exam.", "warning")
        return redirect(f"/view_questions/{exam_id}")
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    conn.close()
    return render_template("faculty/edit_questions.html", questions=questions, exam_id=exam_id)

@app.route("/delete_question/<id>/<exam_id>")
def delete_question(id, exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger"); return redirect("/faculty")
    # Only check launched field - published is for result publication, not launch state
    if exam["launched"] == 1:
        conn.close()
        flash("Cannot delete questions from a launched exam.", "warning")
        return redirect(f"/view_questions/{exam_id}")
    conn.execute("DELETE FROM questions WHERE id=%s", (id,))
    conn.commit()
    # Recalculate total_marks
    total = conn.execute("SELECT SUM(marks) as total FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['total'] or 0
    conn.execute("UPDATE exams SET total_marks=%s WHERE id=%s", (total, exam_id))
    conn.commit()
    conn.close()
    return redirect(f"/view_questions/{exam_id}")

@app.route("/question_bank")
def question_bank():
    g = require_role("faculty"); 
    if g: return g
    conn = get_db(); q=request.args.get("q",""); cat=request.args.get("category","")
    query = "SELECT * FROM question_bank WHERE faculty_id=%s"; params=[session["user_id"]]
    if q: query+=" AND question LIKE %s"; params.append(f"%{q}%")
    if cat: query+=" AND category=%s"; params.append(cat)
    questions  = conn.execute(query, params).fetchall()
    categories = conn.execute("SELECT DISTINCT category FROM question_bank WHERE faculty_id=%s AND category!=''", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("faculty/question_bank.html", questions=questions, categories=categories, q=q, sel_cat=cat)

@app.route("/add_bank_question", methods=["GET","POST"])
def add_bank_question():
    g = require_role("faculty"); 
    if g: return g
    if request.method == "POST":
        conn = get_db()
        # Get the selected correct option and use its value as the correct answer
        correct_option = request.form.get("correct_option")
        if correct_option == "o1":
            correct_answer = request.form["o1"]
        elif correct_option == "o2":
            correct_answer = request.form["o2"]
        elif correct_option == "o3":
            correct_answer = request.form["o3"]
        elif correct_option == "o4":
            correct_answer = request.form["o4"]
        else:
            conn.close()
            flash("Please select the correct answer.", "danger")
            return render_template("faculty/add_bank_question.html")
        
        marks = request.form.get("marks", "1").strip() or "1"
        conn.execute("INSERT INTO question_bank(question,option1,option2,option3,option4,correct_answer,category,difficulty,faculty_id,marks) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (request.form["question"],request.form["o1"],request.form["o2"],request.form["o3"],
                      request.form["o4"],correct_answer,request.form.get("category",""),
                      request.form.get("difficulty","medium"),session["user_id"],marks))
        conn.commit()
        conn.close()
        flash("Question added.", "success"); return redirect("/question_bank")
    return render_template("faculty/add_bank_question.html")

@app.route("/edit_bank_question/<id>", methods=["GET","POST"])
def edit_bank_question(id):
    g = require_role("faculty"); 
    if g: return g
    conn = get_db()
    if request.method == "POST":
        # Get the selected correct option and use its value as the correct answer
        correct_option = request.form.get("correct_option")
        if correct_option == "o1":
            correct_answer = request.form["o1"]
        elif correct_option == "o2":
            correct_answer = request.form["o2"]
        elif correct_option == "o3":
            correct_answer = request.form["o3"]
        elif correct_option == "o4":
            correct_answer = request.form["o4"]
        else:
            flash("Please select the correct answer.", "danger")
            question = conn.execute("SELECT * FROM question_bank WHERE id=%s AND faculty_id=%s", (id, session["user_id"])).fetchone()
            conn.close()
            return render_template("faculty/edit_bank_question.html", question=question)
        
        marks = request.form.get("marks", "1").strip() or "1"
        conn.execute("UPDATE question_bank SET question=%s,option1=%s,option2=%s,option3=%s,option4=%s,correct_answer=%s,category=%s,difficulty=%s,marks=%s WHERE id=%s", (request.form["question"],request.form["o1"],request.form["o2"],request.form["o3"],
                      request.form["o4"],correct_answer,request.form.get("category",""),
                      request.form.get("difficulty","medium"),marks,id))
        conn.commit()
        conn.close()
        flash("Question updated.", "success"); return redirect("/question_bank")
    question = conn.execute("SELECT * FROM question_bank WHERE id=%s AND faculty_id=%s", (id, session["user_id"])).fetchone()
    if not question:
        conn.close()
        flash("Question not found.", "danger"); return redirect("/question_bank")
    conn.close()
    return render_template("faculty/edit_bank_question.html", question=question)

@app.route("/delete_bank_question/<id>")
def delete_bank_question(id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    q = conn.execute("SELECT * FROM question_bank WHERE id=%s AND faculty_id=%s", (id, session["user_id"])).fetchone()
    if not q:
        conn.close()
        flash("Question not found.", "danger"); return redirect("/question_bank")
    conn.execute("DELETE FROM question_bank WHERE id=%s", (id,)); conn.commit()
    conn.close()
    flash("Question deleted.", "success"); return redirect("/question_bank")

# ═══════════════════════════════════════════════════════════════════════════
# STUDENT
# ═══════════════════════════════════════════════════════════════════════════
@app.route("/student")
def student():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    g = check_profile_complete()
    if g: return g
    conn = get_db(); sid = session["user_id"]

    # Get student's classrooms with faculty name, student count, and exam count
    classrooms = conn.execute("""
        SELECT classrooms.id, classrooms.name, classrooms.subject, classrooms.code,
               users.name as faculty_name,
               (SELECT COUNT(*) FROM classroom_members WHERE classroom_id = classrooms.id) as student_count,
               (SELECT COUNT(*) FROM exams WHERE classroom_id = classrooms.id) as exam_count
        FROM classrooms
        JOIN classroom_members ON classrooms.id = classroom_members.classroom_id
        JOIN users ON users.id = classrooms.faculty_id
        WHERE classroom_members.student_id = %s
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        ORDER BY classrooms.name
    """, (sid,)).fetchall()

    # Get available exams (launched, not submitted)
    available_exams = conn.execute("""
        SELECT exams.*, classrooms.name as classroom_name
        FROM exams
        JOIN classrooms ON exams.classroom_id = classrooms.id
        JOIN classroom_members ON classrooms.id = classroom_members.classroom_id
        WHERE classroom_members.student_id = %s 
        AND exams.launched = 1
        AND (exams.is_archived IS NULL OR exams.is_archived=0)
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        AND NOT EXISTS (
            SELECT 1 FROM submissions 
            WHERE submissions.student_id = %s AND submissions.exam_id = exams.id
        )
        ORDER BY exams.exam_date ASC
    """, (sid, sid)).fetchall()

    # Get upcoming exams (available exams with future dates)
    today = datetime.now().strftime("%Y-%m-%d")
    upcoming_exams = [e for e in available_exams if e["exam_date"] >= today]

    # Get exams attempted count (only valid, non-archived records)
    exams_attempted = conn.execute("""
        SELECT COUNT(*) as count FROM submissions s
        JOIN exams e ON e.id = s.exam_id
        JOIN users u ON u.id = s.student_id
        WHERE s.student_id = %s
        AND (e.is_archived IS NULL OR e.is_archived=0)
    """, (sid,)).fetchone()['count']

    # Get average score as a PERCENTAGE (score / total_marks * 100) - only valid, non-archived records
    avg_score = 0
    published_subs = conn.execute("""
        SELECT s.score, s.exam_id
        FROM submissions s
        JOIN exams e ON e.id = s.exam_id
        WHERE s.student_id=%s AND s.result_published=1
        AND (e.is_archived IS NULL OR e.is_archived=0)
    """, (sid,)).fetchall()

    if published_subs:
        percentages = []
        for sub in published_subs:
            total_marks = conn.execute(
                "SELECT SUM(marks) as total FROM questions WHERE exam_id=%s", (sub["exam_id"],)
            ).fetchone()['total']
            if total_marks and total_marks > 0:
                percentages.append(round((sub["score"] / total_marks) * 100, 1))
        if percentages:
            avg_score = round(sum(percentages) / len(percentages), 1)

    # Get recent results (only published results, non-archived exams)
    recent_results = conn.execute("""
        SELECT submissions.score, submissions.submitted_at as date,
               submissions.result_published,
               exams.title as exam_title, exams.id as exam_id,
               classrooms.name as classroom_name
        FROM submissions
        JOIN exams ON submissions.exam_id = exams.id
        JOIN classrooms ON exams.classroom_id = classrooms.id
        WHERE submissions.student_id = %s AND submissions.result_published = 1
        AND (exams.is_archived IS NULL OR exams.is_archived=0)
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        ORDER BY submissions.submitted_at DESC
        LIMIT 5
    """, (sid,)).fetchall()

    # Calculate percentage for each result
    recent_results_with_pct = []
    for r in recent_results:
        total = conn.execute("SELECT SUM(marks) as total FROM questions WHERE exam_id=%s", (r["exam_id"],)).fetchone()['total']
        # Convert to dict before adding fields (sqlite3.Row is immutable)
        r_dict = dict(r)
        if total and total > 0:
            r_dict["percentage"] = round((r["score"] / total) * 100, 1)
        else:
            r_dict["percentage"] = 0
        recent_results_with_pct.append(r_dict)

    conn.close()
    return render_template("student/student_dashboard.html",
        available_exams=available_exams,
        upcoming_exams=upcoming_exams,
        exams_attempted=exams_attempted,
        avg_score=avg_score,
        classrooms=classrooms,
        recent_results=recent_results_with_pct)

# Student: Analytics
@app.route("/student/analytics")
def student_analytics_page():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    
    # Get student's published results for analytics
    results = conn.execute("""
        SELECT users.id as student_id, users.name as student_name,
               exams.id as exam_id, exams.title as exam_title, exams.subject,
               exams.classroom_id, classrooms.name as classroom_name,
               submissions.score, SUM(questions.marks) as total,
               exams.pass_percentage, submissions.submitted_at
        FROM submissions
        JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        LEFT JOIN classrooms ON classrooms.id=exams.classroom_id
        JOIN questions ON questions.exam_id=exams.id
        WHERE submissions.student_id=%s AND submissions.result_published=1
        GROUP BY users.id, users.name, exams.id, exams.title, exams.subject,
               exams.classroom_id, classrooms.name, submissions.score,
               exams.pass_percentage, submissions.submitted_at
        ORDER BY submissions.submitted_at DESC
    """, (sid,)).fetchall()
    
    # Calculate statistics — use percentage (score/total*100), not raw score
    total_exams = len(results)
    if total_exams > 0:
        percentages = [
            round((r["score"] / r["total"]) * 100, 1)
            for r in results if r["total"] and r["total"] > 0
        ]
        avg_score = round(sum(percentages) / len(percentages), 1) if percentages else 0
        pass_count = sum(1 for r in results if is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
        fail_count = total_exams - pass_count
        pass_rate = round((pass_count / total_exams) * 100, 1)
    else:
        avg_score = 0
        pass_count = 0
        fail_count = 0
        pass_rate = 0
    
    # Performance by subject
    subject_stats = {}
    for r in results:
        subject = r["subject"] or "General"
        if subject not in subject_stats:
            subject_stats[subject] = {"scores": [], "count": 0}
        if r["total"] and r["total"] > 0:
            pct = (r["score"] / r["total"]) * 100
            subject_stats[subject]["scores"].append(pct)
            subject_stats[subject]["count"] += 1
    
    subject_analytics = []
    for subject, data in subject_stats.items():
        if data["count"] > 0:
            avg_pct = sum(data["scores"]) / len(data["scores"])
            subject_analytics.append({
                "subject": subject,
                "avg_pct": avg_pct,
                "attempts": data["count"]
            })
    
    subject_analytics.sort(key=lambda x: x["avg_pct"], reverse=True)
    
    conn.close()
    return render_template("student/student_analytics.html",
                           total_exams=total_exams,
                           avg_score=avg_score,
                           pass_count=pass_count,
                           fail_count=fail_count,
                           pass_rate=pass_rate,
                           subject_analytics=subject_analytics,
                           results=results)

# Student: Available Exams
@app.route("/student/exams")
def student_exams():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    
    # Get available exams (launched, not submitted)
    available_exams = conn.execute("""
        SELECT exams.*, classrooms.name as classroom_name,
               users.name as faculty_name
        FROM exams
        JOIN classrooms ON exams.classroom_id = classrooms.id
        JOIN classroom_members ON classrooms.id = classroom_members.classroom_id
        JOIN users ON users.id = classrooms.faculty_id
        WHERE classroom_members.student_id = %s 
        AND exams.launched = 1
        AND (exams.is_archived IS NULL OR exams.is_archived=0)
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        AND NOT EXISTS (
            SELECT 1 FROM submissions 
            WHERE submissions.student_id = %s AND submissions.exam_id = exams.id
        )
        ORDER BY exams.exam_date ASC
    """, (sid, sid)).fetchall()
    
    # Get completed exams
    completed_exams = conn.execute("""
        SELECT exams.*, classrooms.name as classroom_name,
               users.name as faculty_name,
               submissions.score, submissions.submitted_at,
               submissions.result_published
        FROM submissions
        JOIN exams ON exams.id=submissions.exam_id
        JOIN classrooms ON exams.classroom_id = classrooms.id
        JOIN classroom_members ON classrooms.id = classroom_members.classroom_id
        JOIN users ON users.id = classrooms.faculty_id
        WHERE submissions.student_id = %s AND classroom_members.student_id = %s
        AND (classrooms.is_archived IS NULL OR classrooms.is_archived=0)
        AND (exams.is_archived IS NULL OR exams.is_archived=0)
        ORDER BY submissions.submitted_at DESC
    """, (sid, sid)).fetchall()
    
    conn.close()
    return render_template("student/student_exams.html",
                           available_exams=available_exams,
                           completed_exams=completed_exams)

@app.route("/student/classroom/<classroom_id>")
def student_classroom_detail(classroom_id):
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    
    # Check if student is member of this classroom
    membership = conn.execute("""
        SELECT * FROM classroom_members 
        WHERE classroom_id=%s AND student_id=%s
    """, (classroom_id, sid)).fetchone()
    
    if not membership:
        conn.close()
        flash("You are not a member of this classroom.", "danger")
        return redirect("/student/classrooms")
    
    # Get classroom details
    classroom = conn.execute("""
        SELECT classrooms.*, users.name as faculty_name, users.email as faculty_email
        FROM classrooms
        JOIN users ON users.id = classrooms.faculty_id
        WHERE classrooms.id = %s
    """, (classroom_id,)).fetchone()
    
    if not classroom:
        conn.close()
        flash("Classroom not found.", "danger")
        return redirect("/student/classrooms")
    
    # Get classroom exams with student's submission status
    exams = conn.execute("""
        SELECT exams.*, 
               COUNT(DISTINCT submissions.id) as submission_count,
               student_submissions.id as student_submission_id,
               student_submissions.score as student_score,
               student_submissions.result_published as student_result_published,
               student_submissions.submitted_at as student_submitted_at
        FROM exams
        LEFT JOIN submissions ON submissions.exam_id = exams.id
        LEFT JOIN (
            SELECT id, exam_id, student_id, score, result_published, submitted_at
            FROM submissions
            WHERE student_id = %s
        ) as student_submissions ON student_submissions.exam_id = exams.id
        WHERE exams.classroom_id = %s
        GROUP BY exams.id, student_submissions.id, student_submissions.score, 
                 student_submissions.result_published, student_submissions.submitted_at
        ORDER BY exams.exam_date DESC
    """, (sid, classroom_id)).fetchall()
    
    # Get student's submissions in this classroom
    submissions = conn.execute("""
        SELECT submissions.*, exams.title as exam_title, exams.exam_date
        FROM submissions
        JOIN exams ON exams.id = submissions.exam_id
        WHERE submissions.student_id = %s AND exams.classroom_id = %s
        ORDER BY submissions.submitted_at DESC
    """, (sid, classroom_id)).fetchall()
    
    # Get student count in classroom
    student_count = conn.execute("""
        SELECT COUNT(*) as count FROM classroom_members WHERE classroom_id = %s
    """, (classroom_id,)).fetchone()['count']
    
    conn.close()
    return render_template("student/student_classroom_detail.html",
                           classroom=classroom,
                           exams=exams,
                           submissions=submissions,
                           student_count=student_count)

@app.route("/exam_instructions/<exam_id>")
def exam_instructions(exam_id):
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND launched=1", (exam_id,)).fetchone()
    if not exam:
        conn.close()
        return redirect("/student")
    q_count = conn.execute("SELECT COUNT(*) as count FROM questions WHERE exam_id=%s", (exam_id,)).fetchone()['count']
    questions = conn.execute("SELECT marks FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    total_marks = sum(q["marks"] or 1 for q in questions)
    if conn.execute("SELECT id FROM submissions WHERE student_id=%s AND exam_id=%s", (session["user_id"],exam_id)).fetchone():
        conn.close()
        return redirect(f"/view_result/{exam_id}")
    conn.close()
    log_activity(session["user_id"], f"Started exam: {exam['title']}")
    return render_template("student/exam_instructions.html", exam=exam, q_count=q_count, total_marks=total_marks)

@app.route("/attempt/<exam_id>", methods=["GET","POST"])
def attempt_exam(exam_id):
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    
    # Check if student already submitted this exam
    existing_submission = conn.execute("SELECT * FROM submissions WHERE student_id=%s AND exam_id=%s", (sid,exam_id)).fetchone()
    if existing_submission:
        conn.close()
        # Check if result is published
        if existing_submission.get("result_published") == 1:
            flash("You have already completed this exam.", "info")
            return redirect(f"/view_result/{exam_id}")
        else:
            flash("You have already completed this exam. Result pending.", "info")
            return redirect("/student/exams")
    
    exam = conn.execute("SELECT * FROM exams WHERE id=%s", (exam_id,)).fetchone()
    if not exam or exam["launched"]!=1:
        conn.close()
        return redirect("/student")
    questions_raw = conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    
    # Check for in-progress attempt to restore
    saved_attempt = conn.execute("SELECT * FROM exam_attempts WHERE student_id=%s AND exam_id=%s", (sid,exam_id)).fetchone()
    saved_answers = {}
    current_question = 0
    remaining_time = 0
    
    if saved_attempt:
        import json
        try:
            saved_answers = json.loads(saved_attempt["answers"]) if saved_attempt["answers"] else {}
            current_question = saved_attempt["current_question"] or 0
            remaining_time = saved_attempt["remaining_time"] or 0
        except:
            saved_answers = {}
    
    if request.method == "POST":
        # Backend validation: ensure student_id and exam_id are valid before creating attempt
        if not exam or exam["id"] != int(exam_id):
            conn.close()
            flash("Invalid exam.", "danger")
            return redirect("/student/exams")
        
        score = sum(q["marks"] or 1 for q in questions_raw if request.form.get(str(q["id"]))==q["correct_answer"])
        tab_switches = 0
        try: tab_switches = max(0, int(request.form.get("tab_switches", 0)))
        except: pass
        conn.execute("INSERT INTO submissions(student_id,exam_id,score,tab_switches,result_published,submitted_at) VALUES(%s,%s,%s,%s,0,%s)", (sid, exam_id, score, tab_switches, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        sub_id = conn.execute("SELECT id FROM submissions WHERE student_id=%s AND exam_id=%s ORDER BY id DESC LIMIT 1", (sid,exam_id)).fetchone()["id"]
        for q in questions_raw:
            ans = request.form.get(str(q["id"]), "")
            conn.execute("INSERT INTO submission_answers(submission_id,question_id,student_answer) VALUES(%s,%s,%s)", (sub_id, q["id"], ans))
        conn.commit()
        
        # Clean up in-progress attempt after successful submission
        conn.execute("DELETE FROM exam_attempts WHERE student_id=%s AND exam_id=%s", (sid, exam_id))
        conn.commit()
        conn.close()
        
        if tab_switches > 0:
            log_activity(sid, f"Submitted exam id={exam_id} score={score} tab_switches={tab_switches}")
        else:
            log_activity(sid, f"Submitted exam id={exam_id} score={score}")
        return redirect(f"/view_result/{exam_id}")
    # Deterministic shuffle — same order every time for this student+exam combo
    seed = int(str(sid) + str(exam_id))
    rng  = random.Random(seed)
    questions = list(questions_raw)
    rng.shuffle(questions)
    shuffled = []
    for q in questions:
        opts = [q["option1"], q["option2"], q["option3"], q["option4"]]
        # Use question id as secondary seed so same question always has same option order
        opt_rng = random.Random(seed + q["id"])
        opt_rng.shuffle(opts)
        shuffled.append({"id":q["id"],"question":q["question"],"difficulty":q["difficulty"],
            "correct_answer":q["correct_answer"],
            "option1":opts[0],"option2":opts[1],"option3":opts[2],"option4":opts[3]})
    conn.close()
    return render_template("student/attempt_exam.html", questions=shuffled, exam=exam, 
                           saved_answers=saved_answers, current_question=current_question, 
                           remaining_time=remaining_time)

@app.route("/api/auto_save_exam", methods=["POST"])
def auto_save_exam():
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    exam_id = data.get("exam_id")
    current_question = data.get("current_question", 0)
    remaining_time = data.get("remaining_time", 0)
    answers = data.get("answers", {})
    
    if not exam_id:
        return jsonify({"success": False, "error": "Missing exam_id"}), 400
    
    conn = get_db()
    sid = session["user_id"]
    
    # Check if exam is still valid (not submitted)
    existing_submission = conn.execute("SELECT id FROM submissions WHERE student_id=%s AND exam_id=%s", (sid, exam_id)).fetchone()
    if existing_submission:
        conn.close()
        return jsonify({"success": False, "error": "Exam already submitted"}), 400
    
    # Upsert exam attempt record
    import json
    try:
        conn.execute("""
            INSERT INTO exam_attempts(student_id, exam_id, current_question, remaining_time, answers, last_saved)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(student_id, exam_id) DO UPDATE SET
                current_question = excluded.current_question,
                remaining_time = excluded.remaining_time,
                answers = excluded.answers,
                last_saved = excluded.last_saved
        """, (sid, exam_id, current_question, remaining_time, json.dumps(answers), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        conn.close()
        app.logger.error(f"Auto-save failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/view_result/<exam_id>")
def view_result(exam_id):
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    g = check_profile_complete()
    if g: return g
    conn = get_db(); sid = session["user_id"]
    result = conn.execute("SELECT * FROM submissions WHERE student_id=%s AND exam_id=%s", (sid,exam_id)).fetchone()
    if not result:
        conn.close()
        return redirect("/student")
    # Check if results are published
    if result["result_published"] == 0:
        conn.close()
        return render_template("errors/results_not_published.html", exam_id=exam_id)
    exam     = conn.execute("SELECT * FROM exams WHERE id=%s", (exam_id,)).fetchone()
    student  = conn.execute("SELECT * FROM users WHERE id=%s", (sid,)).fetchone()
    questions= conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    faculty  = conn.execute("SELECT * FROM users WHERE id=%s", (exam["faculty_id"],)).fetchone()
    classroom= conn.execute("SELECT * FROM classrooms WHERE id=%s", (exam["classroom_id"],)).fetchone()
    total    = sum(q["marks"] or 1 for q in questions)
    generated_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.close()
    log_activity(sid, f"Viewed result for exam: {exam['title']}")
    return render_template("student/results.html", score=result["score"], total=total,
        student=student, exam=exam, questions=questions, result=result,
        faculty=faculty, classroom=classroom, generated_date=generated_date)

@app.route("/publish_results/<exam_id>")
def publish_results(exam_id):
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=%s AND faculty_id=%s", (exam_id, session["user_id"])).fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger")
        return redirect("/faculty")
    
    # Check if there are pending submissions
    pending_count = conn.execute("SELECT COUNT(*) as count FROM submissions WHERE exam_id=%s AND result_published=0", (exam_id,)).fetchone()['count']
    
    if pending_count == 0:
        conn.close()
        flash("No pending results to publish.", "warning")
        return redirect("/faculty/results")
    
    # Update only pending submissions
    conn.execute("""
        UPDATE submissions 
        SET result_published = 1,
            published_at = CURRENT_TIMESTAMP
        WHERE exam_id = %s AND result_published = 0
    """, (exam_id,))
    
    # Keep exam-level published flag for backward compatibility
    conn.execute("UPDATE exams SET published=1 WHERE id=%s", (exam_id,))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], f"Published {pending_count} pending results for exam: {exam['title']}")
    flash(f"Results published successfully for {pending_count} submission(s).", "success")
    return redirect("/faculty/results")


@app.route("/view_validation/<exam_id>")
def view_validation(exam_id):
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    result = conn.execute("SELECT * FROM submissions WHERE student_id=%s AND exam_id=%s", (sid, exam_id)).fetchone()
    if not result:
        conn.close()
        return redirect("/student")
    exam     = conn.execute("SELECT * FROM exams WHERE id=%s", (exam_id,)).fetchone()
    student  = conn.execute("SELECT * FROM users WHERE id=%s", (sid,)).fetchone()
    questions= conn.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,)).fetchall()
    # Fetch student answers for this submission
    answers  = conn.execute("SELECT * FROM submission_answers WHERE submission_id=%s", (result["id"],)).fetchall()
    answer_map = {a["question_id"]: a["student_answer"] for a in answers}
    total    = len(questions)
    conn.close()
    return render_template("errors/validation.html",
        result=result, exam=exam, student=student,
        questions=questions, answer_map=answer_map, total=total)


# ═══════════════════════════════════════════════════════════════════════════
# FACULTY — ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/faculty/analytics")
def faculty_analytics():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    fid = session["user_id"]
    ef  = request.args.get("exam", "")
    cf  = request.args.get("classroom", "")
    sf  = request.args.get("subject", "")

    # Per-exam stats (with optional filters)
    eq = """
        SELECT exams.id, exams.title, exams.subject, exams.exam_date,
               classrooms.name as classroom_name,
               COUNT(DISTINCT submissions.id) as attempt_count,
               AVG(CAST(submissions.score AS FLOAT)) as avg_score,
               MAX(submissions.score) as max_score,
               MIN(submissions.score) as min_score,
               COUNT(DISTINCT questions.id) as total_q
        FROM exams
        LEFT JOIN submissions ON submissions.exam_id=exams.id
        LEFT JOIN questions   ON questions.exam_id=exams.id
        LEFT JOIN classrooms  ON classrooms.id=exams.classroom_id
        WHERE exams.faculty_id=%s"""
    ep = [fid]
    if ef: eq += " AND exams.id=%s";            ep.append(ef)
    if cf: eq += " AND exams.classroom_id=%s";  ep.append(cf)
    if sf: eq += " AND exams.subject=%s";       ep.append(sf)
    eq += " GROUP BY exams.id, exams.title, exams.subject, exams.exam_date, classrooms.name ORDER BY exams.exam_date DESC"
    exam_stats = conn.execute(eq, ep).fetchall()

    # Subject-wise stats
    subject_query = """
        SELECT exams.subject,
               COUNT(DISTINCT exams.id) as exam_count,
               COUNT(submissions.id) as total_attempts,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct
        FROM exams LEFT JOIN submissions ON submissions.exam_id=exams.id
        WHERE exams.faculty_id=%s AND exams.subject != ''"""
    subject_params = [fid]
    if ef: subject_query += " AND exams.id=%s"; subject_params.append(ef)
    if cf: subject_query += " AND exams.classroom_id=%s"; subject_params.append(cf)
    subject_query += " GROUP BY exams.subject ORDER BY avg_pct DESC"
    subject_stats = conn.execute(subject_query, subject_params).fetchall()

    # Classroom-wise stats
    classroom_query = """
        SELECT classrooms.id, classrooms.name as classroom_name,
               COUNT(DISTINCT exams.id) as exam_count,
               COUNT(submissions.id) as total_attempts,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct
        FROM classrooms
        LEFT JOIN exams       ON exams.classroom_id=classrooms.id
        LEFT JOIN submissions ON submissions.exam_id=exams.id
        WHERE classrooms.faculty_id=%s"""
    classroom_params = [fid]
    if ef: classroom_query += " AND exams.id=%s"; classroom_params.append(ef)
    if sf: classroom_query += " AND exams.subject=%s"; classroom_params.append(sf)
    classroom_query += " GROUP BY classrooms.id, classrooms.name ORDER BY classroom_name"
    classroom_stats = conn.execute(classroom_query, classroom_params).fetchall()

    # Top 5 performers
    top_query = """
        SELECT users.name,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct,
               COUNT(submissions.id) as attempts,
               MAX(submissions.score) as best_score
        FROM submissions
        JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        WHERE exams.faculty_id=%s"""
    top_params = [fid]
    if ef: top_query += " AND exams.id=%s"; top_params.append(ef)
    if cf: top_query += " AND exams.classroom_id=%s"; top_params.append(cf)
    if sf: top_query += " AND exams.subject=%s"; top_params.append(sf)
    top_query += " GROUP BY users.id, users.name ORDER BY avg_pct DESC LIMIT 5"
    top_students = conn.execute(top_query, top_params).fetchall()

    # Bottom 5 performers
    low_query = """
        SELECT users.name,
               AVG(CAST(submissions.score AS FLOAT)/NULLIF(
                   (SELECT COUNT(*) FROM questions WHERE exam_id=exams.id),0)*100) as avg_pct,
               COUNT(submissions.id) as attempts,
               MIN(submissions.score) as worst_score
        FROM submissions
        JOIN users ON users.id=submissions.student_id
        JOIN exams ON exams.id=submissions.exam_id
        WHERE exams.faculty_id=%s"""
    low_params = [fid]
    if ef: low_query += " AND exams.id=%s"; low_params.append(ef)
    if cf: low_query += " AND exams.classroom_id=%s"; low_params.append(cf)
    if sf: low_query += " AND exams.subject=%s"; low_params.append(sf)
    low_query += " GROUP BY users.id, users.name ORDER BY avg_pct ASC LIMIT 5"
    low_students = conn.execute(low_query, low_params).fetchall()

    # Filter dropdowns
    my_exams      = conn.execute("SELECT id,title FROM exams WHERE faculty_id=%s ORDER BY title", (fid,)).fetchall()
    my_classrooms = conn.execute("SELECT id,name FROM classrooms WHERE faculty_id=%s AND (is_archived IS NULL OR is_archived=0) ORDER BY name", (fid,)).fetchall()
    subjects      = conn.execute("SELECT DISTINCT subject FROM exams WHERE faculty_id=%s AND subject!='' ORDER BY subject", (fid,)).fetchall()

    conn.close()
    return render_template("faculty/faculty_analytics.html",
        exam_stats=exam_stats, subject_stats=subject_stats,
        classroom_stats=classroom_stats, top_students=top_students,
        low_students=low_students,
        my_exams=my_exams, my_classrooms=my_classrooms, subjects=subjects,
        sel_exam=ef, sel_classroom=cf, sel_subject=sf)


@app.route("/faculty/analytics/export")
def faculty_analytics_export():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    log_activity(session["user_id"], "Exported faculty analytics to CSV")
    fid = session["user_id"]
    ef  = request.args.get("exam", "")
    cf  = request.args.get("classroom", "")
    sf  = request.args.get("subject", "")
    
    query = """
        SELECT exams.title, exams.subject, exams.exam_date,
               COUNT(DISTINCT submissions.id) as attempts,
               AVG(CAST(submissions.score AS FLOAT)) as avg_score,
               MAX(submissions.score) as max_score,
               MIN(submissions.score) as min_score,
               COUNT(questions.id) as total_q
        FROM exams
        LEFT JOIN submissions ON submissions.exam_id=exams.id
        LEFT JOIN questions ON questions.exam_id=exams.id
        WHERE exams.faculty_id=%s"""
    params = [fid]
    if ef: query += " AND exams.id=%s"; params.append(ef)
    if cf: query += " AND exams.classroom_id=%s"; params.append(cf)
    if sf: query += " AND exams.subject=%s"; params.append(sf)
    query += " GROUP BY exams.id ORDER BY exams.exam_date DESC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Exam","Subject","Date","Attempts","Avg Score","Max","Min","Total Marks","Avg %"])
    for r in rows:
        avg_pct = round(r["avg_score"]/r["total_q"]*100,1) if r["total_q"] and r["avg_score"] else 0
        w.writerow([r["title"],r["subject"],r["exam_date"],r["attempts"],
                    round(r["avg_score"],1) if r["avg_score"] else 0,
                    r["max_score"],r["min_score"],r["total_q"],f"{avg_pct}%"])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=faculty_analytics.csv"
    return resp

@app.route("/faculty/analytics/export/pdf")
def faculty_analytics_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from reportlab.lib import colors
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    g = require_role("faculty")
    if g: return g
    try:
        conn = get_db()
        log_activity(session["user_id"], "Exported faculty analytics to PDF")
        fid = session["user_id"]
        ef  = request.args.get("exam", "")
        cf  = request.args.get("classroom", "")
        sf  = request.args.get("subject", "")
        query = """
            SELECT exams.title, exams.subject, exams.exam_date,
                   COUNT(DISTINCT submissions.id) as attempts,
                   AVG(CAST(submissions.score AS FLOAT)) as avg_score,
                   MAX(submissions.score) as max_score,
                   MIN(submissions.score) as min_score,
                   COUNT(questions.id) as total_q
            FROM exams
            LEFT JOIN submissions ON submissions.exam_id=exams.id
            LEFT JOIN questions ON questions.exam_id=exams.id
            WHERE exams.faculty_id=%s"""
        params = [fid]
        if ef: query += " AND exams.id=%s"; params.append(ef)
        if cf: query += " AND exams.classroom_id=%s"; params.append(cf)
        if sf: query += " AND exams.subject=%s"; params.append(sf)
        query += " GROUP BY exams.id ORDER BY exams.exam_date DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        total_attempts = sum(r["attempts"] or 0 for r in rows)

        # Create PDF with shared configuration
        from flask import Response
        from reportlab.platypus import Paragraph, Table
        from pdf_utils import (
            create_pdf_document, get_pdf_styles, get_column_widths,
            get_table_style, format_datetime, create_header_table,
            create_summary_table, apply_column_alignment
        )
        
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('FACULTY ANALYTICS REPORT', logo_path))
        
        # Applied filters
        if any([ef, cf, sf]):
            elements.append(Paragraph("<b>Applied Filters:</b>", styles['wrap']))
            if ef: elements.append(Paragraph(f"Exam ID: {ef}", styles['wrap']))
            if cf: elements.append(Paragraph(f"Classroom ID: {cf}", styles['wrap']))
            if sf: elements.append(Paragraph(f"Subject: {sf}", styles['wrap']))
            elements.append(Paragraph("<br/>", styles['wrap']))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Exams:", str(len(rows))),
            ("Total Attempts:", str(total_attempts)),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Exam", "Subject", "Date", "Attempts", "Avg Score", "Max", "Min", "Avg %"]
        data = [headers]
        for r in rows:
            try:
                total_q   = r["total_q"] or 1
                avg_score = r["avg_score"] or 0
                avg_pct   = round(avg_score / total_q * 100, 1) if total_q and avg_score else 0
                data.append([
                    Paragraph(r["title"] or "—", styles['wrap']),
                    Paragraph(r["subject"] or "—", styles['wrap']),
                    Paragraph(format_datetime(r["exam_date"]), styles['wrap']),
                    Paragraph(str(r["attempts"] or 0), styles['wrap']),
                    Paragraph(str(round(avg_score,1) if avg_score else 0), styles['wrap']),
                    Paragraph(str(r["max_score"] or 0), styles['wrap']),
                    Paragraph(str(r["min_score"] or 0), styles['wrap']),
                    Paragraph(f"{avg_pct}%", styles['wrap']),
                ])
            except Exception as re: app.logger.error(f"Analytics PDF row: {re}"); continue
        if len(data) == 1: data.append(["—","—","—","—","—","—","—","—"])
        
        # Get column widths and table style
        col_widths = get_column_widths('analytics')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': True},    # Exam - wrap
            {'align': 'LEFT', 'wrap': True},    # Subject - wrap
            {'align': 'CENTER', 'wrap': True},  # Date - wrap for date/time
            {'align': 'CENTER', 'wrap': False}, # Attempts - no wrap
            {'align': 'CENTER', 'wrap': False}, # Avg Score - no wrap
            {'align': 'CENTER', 'wrap': False}, # Max - no wrap
            {'align': 'CENTER', 'wrap': False}, # Min - no wrap
            {'align': 'CENTER', 'wrap': False}, # Avg % - no wrap
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(response.getvalue(), mimetype="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="faculty_analytics.pdf"'})
    except Exception as e:
        import traceback
        app.logger.exception("Analytics PDF error")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/faculty/analytics")



# ═══════════════════════════════════════════════════════════════════════════
# STUDENT — RESULT HISTORY + DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/student/results")
def student_results():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    results = conn.execute("""
        SELECT exams.title, exams.subject, exams.exam_date, exams.faculty_id,
               submissions.score, submissions.submitted_at, exams.id as exam_id,
               submissions.result_published, exams.pass_percentage,
               SUM(questions.marks) as total,
               faculty.name as faculty_name
        FROM submissions
        JOIN exams ON exams.id=submissions.exam_id
        JOIN questions ON questions.exam_id=exams.id
        JOIN users as faculty ON faculty.id=exams.faculty_id
        WHERE submissions.student_id=%s
        GROUP BY exams.id, exams.title, exams.subject, exams.exam_date, exams.faculty_id,
               submissions.score, submissions.submitted_at, submissions.result_published,
               exams.pass_percentage, faculty.name ORDER BY submissions.submitted_at DESC
    """, (sid,)).fetchall()
    student = conn.execute("SELECT * FROM users WHERE id=%s", (sid,)).fetchone()
    conn.close()
    pass_count_val = sum(1 for r in results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50) and r["result_published"] == 1)
    fail_count_val = sum(1 for r in results if r["total"] and not is_pass(r["score"], r["total"], r["pass_percentage"] or 50) and r["result_published"] == 1)
    return render_template("student/student_results.html", results=results, student=student,
                           pass_count_val=pass_count_val, fail_count_val=fail_count_val)


@app.route("/student/results/export")
def student_results_export():
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    conn = get_db(); sid = session["user_id"]
    log_activity(sid, "Exported student results to CSV")
    results = conn.execute("""
        SELECT exams.title, exams.subject, exams.exam_date,
               submissions.score, submissions.submitted_at, exams.id as exam_id,
               submissions.result_published, exams.pass_percentage,
               SUM(questions.marks) as total,
               faculty.name as faculty_name
        FROM submissions
        JOIN exams ON exams.id=submissions.exam_id
        JOIN questions ON questions.exam_id=exams.id
        JOIN users as faculty ON faculty.id=exams.faculty_id
        WHERE submissions.student_id=%s
        GROUP BY exams.id, exams.title, exams.subject, exams.exam_date,
               submissions.score, submissions.submitted_at, submissions.result_published,
               exams.pass_percentage, faculty.name ORDER BY submissions.submitted_at DESC
    """, (sid,)).fetchall()
    student = conn.execute("SELECT * FROM users WHERE id=%s", (sid,)).fetchone()
    conn.close()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow(["Student","Exam","Subject","Faculty","Date","Score","Total","Percentage","Result","Submitted At"])
    for r in results:
        pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
        result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
        w.writerow([student["name"],r["title"],r["subject"],r["faculty_name"],r["exam_date"],
                    r["score"],r["total"],f"{pct}%",result,r["submitted_at"]])
    
    # Summary row
    total_count = len(results)
    pass_count = sum(1 for r in results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50) and r["result_published"] == 1)
    fail_count = sum(1 for r in results if r["total"] and not is_pass(r["score"], r["total"], r["pass_percentage"] or 50) and r["result_published"] == 1)
    avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in results if r["result_published"] == 1) / pass_count if pass_count > 0 else 0
    w.writerow([])
    w.writerow(["SUMMARY","","","","","","","","",""])
    w.writerow(["Total Records", total_count, "", "", "", "", "", "", "", ""])
    w.writerow(["Passed", pass_count, "", "", "", "", "", "", "", ""])
    w.writerow(["Failed", fail_count, "", "", "", "", "", "", "", ""])
    w.writerow(["Average %", f"{avg_pct:.1f}%", "", "", "", "", "", "", "", ""])
    
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = f"attachment; filename={student['name']}_results.csv"
    return resp

@app.route("/student/results/export/pdf")
def student_export_pdf():
    from flask import Response
    from reportlab.platypus import Paragraph, Table
    from reportlab.lib import colors
    from pdf_utils import (
        create_pdf_document, get_pdf_styles, get_column_widths,
        get_table_style, format_datetime, create_header_table,
        create_summary_table, apply_column_alignment
    )
    import os
    if "user_id" not in session or session.get("role") != "student": return redirect("/")
    try:
        conn = get_db(); sid = session["user_id"]
        log_activity(sid, "Exported student results to PDF")
        results = conn.execute("""
            SELECT exams.title, exams.subject, exams.exam_date,
                   submissions.score, submissions.submitted_at, exams.id as exam_id,
                   submissions.result_published, exams.pass_percentage,
                   SUM(questions.marks) as total,
                   faculty.name as faculty_name
            FROM submissions
            JOIN exams ON exams.id=submissions.exam_id
            JOIN questions ON questions.exam_id=exams.id
            JOIN users as faculty ON faculty.id=exams.faculty_id
            WHERE submissions.student_id=%s
            GROUP BY exams.id ORDER BY submissions.submitted_at DESC
        """, (sid,)).fetchall()
        student = conn.execute("SELECT * FROM users WHERE id=%s", (sid,)).fetchone()
        conn.close()

        # Calculate summary stats
        total_count = len(results)
        published_results = [r for r in results if r["result_published"] == 1]
        pending_count = total_count - len(published_results)
        pass_count = sum(1 for r in published_results if r["total"] and is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
        fail_count = sum(1 for r in published_results if r["total"] and not is_pass(r["score"], r["total"], r["pass_percentage"] or 50))
        avg_pct = sum(round(r["score"]/r["total"]*100,1) if r["total"] else 0 for r in published_results) / len(published_results) if published_results else 0
        
        # Create PDF with shared configuration
        from flask import Response
        from reportlab.platypus import Paragraph, Table
        from pdf_utils import (
            create_pdf_document, get_pdf_styles, get_column_widths,
            get_table_style, format_datetime, create_header_table,
            create_summary_table, apply_column_alignment
        )
        
        response = io.BytesIO()
        doc = create_pdf_document(response)
        styles = get_pdf_styles()
        elements = []
        
        # Header
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        elements.append(create_header_table('STUDENT RESULT HISTORY REPORT', logo_path))
        
        # Summary section
        elements.append(Paragraph("SUMMARY", styles['summary_heading']))
        summary_data = [
            ("Total Exams:", str(total_count)),
            ("Published Results:", str(len(published_results))),
            ("Passed:", str(pass_count)),
            ("Failed:", str(fail_count)),
            ("Pending:", str(pending_count)),
            ("Average %:", f"{avg_pct:.1f}%"),
        ]
        elements.append(create_summary_table(summary_data))
        elements.append(Paragraph("<br/><br/>", styles['wrap']))
        
        # Data table
        headers = ["Exam", "Subject", "Faculty", "Date", "Score", "Total", "%", "Result"]
        data = [headers]
        for r in results:
            pct = round(r["score"]/r["total"]*100,1) if r["total"] else 0
            result = "Pass" if is_pass(r["score"], r["total"], r["pass_percentage"] or 50) else "Fail"
            data.append([
                Paragraph(r["title"] or "—", styles['wrap']),
                Paragraph(r["subject"] or "—", styles['wrap']),
                Paragraph(r["faculty_name"] or "—", styles['wrap']),
                Paragraph(format_datetime(r["exam_date"]), styles['wrap']),
                Paragraph(str(r["score"]), styles['wrap']),
                Paragraph(str(r["total"]), styles['wrap']),
                Paragraph(f"{pct}%", styles['wrap']),
                Paragraph(result, styles['wrap'])
            ])
        
        # Get column widths and table style
        col_widths = get_column_widths('student')
        table_style = get_table_style(len(headers))
        
        # Apply column-specific alignment and word wrap
        column_configs = [
            {'align': 'LEFT', 'wrap': True},    # Exam - wrap
            {'align': 'LEFT', 'wrap': True},    # Subject - wrap
            {'align': 'LEFT', 'wrap': True},    # Faculty - wrap
            {'align': 'CENTER', 'wrap': True},  # Date - wrap for date/time
            {'align': 'CENTER', 'wrap': False}, # Score - no wrap
            {'align': 'CENTER', 'wrap': False}, # Total - no wrap
            {'align': 'CENTER', 'wrap': False}, # % - no wrap
            {'align': 'CENTER', 'wrap': False}, # Result - no wrap
        ]
        table_style = apply_column_alignment(table_style, column_configs)
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(table_style)
        elements.append(table)
        
        # Footer
        elements.append(Paragraph("<br/><br/><br/>", styles['wrap']))
        elements.append(Paragraph("Generated by EduSphere Examination System", styles['footer']))
        elements.append(Paragraph("This report is electronically generated and does not require a signature.", styles['footer']))
        
        doc.build(elements)
        response.seek(0)
        return Response(
            response.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{student["name"]}_marksheet.pdf"'}
        )
    except Exception as e:
        import traceback
        app.logger.exception("PDF generation error (student results)")
        flash("Unable to generate PDF. Please try again.", "danger")
        return redirect("/student/results")


@app.route("/faculty/integrity")
def faculty_integrity():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    fid = session["user_id"]
    ef = request.args.get("exam", "")
    query = """
        SELECT users.name as student_name, exams.title as exam_title,
               exams.id as exam_id, submissions.tab_switches,
               submissions.score, submissions.submitted_at,
               COUNT(questions.id) as total
        FROM submissions
        JOIN users    ON users.id    = submissions.student_id
        JOIN exams    ON exams.id    = submissions.exam_id
        JOIN questions ON questions.exam_id = exams.id
        WHERE exams.faculty_id=%s AND submissions.tab_switches > 0"""
    params = [fid]
    if ef:
        query += " AND exams.id=%s"; params.append(ef)
    query += " GROUP BY submissions.id, users.name, exams.title, exams.id, submissions.tab_switches, submissions.score, submissions.submitted_at ORDER BY submissions.tab_switches DESC"
    flags = conn.execute(query, params).fetchall()
    my_exams = conn.execute("SELECT id, title FROM exams WHERE faculty_id=%s ORDER BY title", (fid,)).fetchall()
    conn.close()
    return render_template("faculty/faculty_integrity.html", flags=flags,
                           my_exams=my_exams, sel_exam=ef)


@app.route("/faculty/profile", methods=["GET","POST"])
def faculty_profile():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip()
        gender = request.form.get("gender", "").strip()
        faculty_id_field = request.form.get("faculty_id", "").strip()
        designation = request.form.get("designation", "").strip()
        subject = request.form.get("subject", "").strip()
        current_password = request.form.get("current_password", "").strip()
        
        if not name or not email:
            conn.close()
            flash("Name and email are required.", "danger")
            return redirect("/faculty/profile")

        if "@" not in email:
            conn.close()
            flash("Invalid email format.", "danger")
            return redirect("/faculty/profile")
        
        # Get current user data to check if email is being changed
        current_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        current_email = current_user["email"] if current_user else ""
        
        # If email is being changed, require password verification
        if email != current_email:
            if not current_password:
                conn.close()
                flash("Current password is required to change email.", "danger")
                return redirect("/faculty/profile")

            # Verify current password
            if not check_password_hash(current_user["password"], current_password):
                conn.close()
                flash("Incorrect password. Email not updated.", "danger")
                return redirect("/faculty/profile")
        
        try:
            conn.execute("""
                UPDATE users SET name=%s, email=%s, phone=%s, date_of_birth=%s, gender=%s,
                faculty_id=%s, designation=%s, subject=%s, last_profile_update=%s
                WHERE id=%s
            """, (name, email, phone, date_of_birth, gender, faculty_id_field, designation,
                  subject, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"]))
            conn.commit()
        except Exception as db_err:
            conn.close()
            error_msg = str(db_err)
            if "UNIQUE" in error_msg.upper():
                flash("That email address is already in use by another account.", "danger")
            else:
                flash(f"Profile update failed: {error_msg}", "danger")
            return redirect("/faculty/profile")
        # Refresh session from database
        updated_user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if updated_user:
            session["name"] = updated_user["name"]
            session["email"] = updated_user["email"]
            if "phone" in updated_user.keys() and updated_user["phone"]:
                session["phone"] = updated_user["phone"]
        else:
            conn.close()
            flash("Profile update failed: user record not found.", "danger")
            return redirect("/faculty/profile")

        conn.close()
        if email != current_email:
            flash("Email updated successfully. Please use the new email for future logins.", "success")
        else:
            flash("Profile updated successfully.", "success")
        return redirect("/faculty/profile")
    
    user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    if user:
        user = dict(user)
        # Sync session with database profile picture
        if "profile_picture" in user and user["profile_picture"]:
            session["profile_pic"] = user["profile_picture"].replace("/static/", "", 1) if user["profile_picture"].startswith("/static/") else user["profile_picture"]
        else:
            session["profile_pic"] = ""
    conn.close()
    return render_template("faculty/faculty_profile.html", user=user)


@app.route("/faculty/profile/upload_picture", methods=["POST"])
def faculty_upload_picture():
    # Check authentication
    if session.get("role") != "faculty":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    if "profile_pic" not in request.files:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    file = request.files["profile_pic"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    # Validate file type
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return jsonify({"success": False, "error": "Invalid file type. Only JPG, JPEG, PNG allowed."}), 400
    
    # Validate file size (2MB max)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 2 * 1024 * 1024:
        return jsonify({"success": False, "error": "File size exceeds 2MB limit."}), 400
    
    try:
        # Upload to Supabase Storage
        from supabase_storage import upload_profile_picture, delete_profile_picture
        
        # Delete old profile picture if exists
        conn = get_db()
        old_pic = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        if old_pic and old_pic["profile_picture"]:
            delete_profile_picture(old_pic["profile_picture"])
        
        # Upload new picture
        public_url = upload_profile_picture(file, session["user_id"])
        
        if not public_url:
            # Fallback to local storage if Supabase fails
            upload_folder = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"profile_faculty_{session['user_id']}_{timestamp}.jpg"
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            public_url = f"/static/uploads/{filename}"
        
        # Update database (use profile_picture column for consistency)
        conn.execute("UPDATE users SET profile_picture=%s WHERE id=%s", (public_url, session["user_id"]))
        conn.commit()
        conn.close()
        
        # Update session with the public URL
        if public_url.startswith("/static/"):
            session["profile_pic"] = public_url.replace("/static/", "", 1)
        else:
            session["profile_pic"] = public_url
        
        log_activity(session["user_id"], "Updated profile picture")

        return jsonify({"success": True, "message": "Profile picture updated successfully.", "image_url": public_url})
    except Exception as e:
        app.logger.exception("Faculty profile upload error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/faculty/profile/remove_picture", methods=["POST"])
def faculty_remove_picture():
    g = require_role("faculty")
    if g: return g
    conn = get_db()
    user = conn.execute("SELECT profile_picture FROM users WHERE id=%s", (session["user_id"],)).fetchone()
    
    if user and user["profile_picture"]:
        # Delete from Supabase if it's a Supabase URL
        from supabase_storage import delete_profile_picture
        delete_profile_picture(user["profile_picture"])
        
        # Also delete local file if it exists (for old uploads)
        db_path = user["profile_picture"]
        if db_path.startswith("/static/"):
            rel_path = db_path.replace("/static/", "", 1)
            filepath = os.path.join('static', rel_path)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        # Update database (use profile_picture column for consistency)
        conn.execute("UPDATE users SET profile_picture='' WHERE id=%s", (session["user_id"]))
        conn.commit()
        conn.close()
        session["profile_pic"] = ""
        flash("Profile picture removed.", "success")
    else:
        conn.close()
        flash("No profile picture to remove.", "warning")

    return redirect("/faculty/profile")


@app.route("/faculty/change_password", methods=["GET","POST"])
def faculty_change_password():
    g = require_role("faculty")
    if g: return g
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        
        if not check_password_hash(user["password"], current_password):
            flash("Current password is incorrect.", "danger")
            return redirect("/faculty/change_password")
        
        if new_password != confirm_password:
            flash("Passwords do not match.", "warning")
            return redirect("/faculty/change_password")
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return redirect("/faculty/change_password")
        
        conn.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new_password), session["user_id"]))
        conn.commit()
        conn.close()
        flash("Password updated successfully.", "success")
        return redirect("/faculty/profile")
    
    return render_template("faculty/faculty_change_password.html")


if __name__ == "__main__":
    app.run(debug=True)
