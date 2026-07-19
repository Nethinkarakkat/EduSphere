"""
Migration script to add marks column to question_bank table.
Run this script once to update the database schema.
"""

import sys
import os

# Add the parent directory to the path to import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_db

def migrate():
    """Add marks column to question_bank table and set default value."""
    conn = get_db()
    
    try:
        # Check if marks column already exists (SQLite syntax)
        result = conn.execute("PRAGMA table_info(question_bank)").fetchall()
        column_exists = any(col[1] == 'marks' for col in result)
        
        if column_exists:
            print("Marks column already exists in question_bank table.")
        else:
            # Add marks column with default value 1
            conn.execute("ALTER TABLE question_bank ADD COLUMN marks INTEGER DEFAULT 1")
            conn.commit()
            print("Added marks column to question_bank table with default value 1.")
        
        # Update any existing NULL marks to 1
        conn.execute("UPDATE question_bank SET marks = 1 WHERE marks IS NULL OR marks = 0")
        conn.commit()
        print("Updated existing questions with default marks=1.")
        
        print("Migration completed successfully.")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
