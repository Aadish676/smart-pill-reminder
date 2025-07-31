#!/usr/bin/env python3
"""
Database migration script to fix the missing reset_token_expiry column
"""

import sqlite3
import sys
import os

def migrate_database():
    """Add missing columns to the database"""
    
    # Database file path
    db_path = 'pillpal.db'
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if reset_token_expiry column exists
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'reset_token_expiry' not in columns:
            print("Adding reset_token_expiry column to user table...")
            cursor.execute("ALTER TABLE user ADD COLUMN reset_token_expiry DATETIME")
            print("Successfully added reset_token_expiry column")
        else:
            print("reset_token_expiry column already exists")
        
        # Check for other potentially missing columns
        required_columns = {
            'reset_token': 'VARCHAR(255)',
            'created_at': 'DATETIME',
            'last_login': 'DATETIME', 
            'is_active': 'BOOLEAN DEFAULT 1'
        }
        
        for column_name, column_type in required_columns.items():
            if column_name not in columns:
                print(f"Adding {column_name} column to user table...")
                cursor.execute(f"ALTER TABLE user ADD COLUMN {column_name} {column_type}")
                print(f"Successfully added {column_name} column")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("Database migration completed successfully")
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        return False

if __name__ == "__main__":
    print("Starting database migration...")
    if migrate_database():
        print("Migration completed successfully")
        sys.exit(0)
    else:
        print("Migration failed")
        sys.exit(1)