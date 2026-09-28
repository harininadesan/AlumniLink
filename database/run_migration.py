"""
AlumniLink - Complete Database Migration Script (MySQL 5.x compatible)
Run this to bring the DB schema in sync with all route code.
Handles MySQL versions that do not support 'ADD COLUMN IF NOT EXISTS'.
"""
import mysql.connector
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

conn = mysql.connector.connect(
    host=Config.DB_HOST,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    database=Config.DB_NAME
)
cursor = conn.cursor(dictionary=True)


def column_exists(table, column):
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (Config.DB_NAME, table, column))
    return cursor.fetchone()['cnt'] > 0


def add_column(table, column_def):
    """column_def is the full column definition string e.g. 'col_name INT DEFAULT NULL' """
    col_name = column_def.strip().split()[0]
    if not column_exists(table, col_name):
        sql = f"ALTER TABLE {table} ADD COLUMN {column_def}"
        try:
            cursor.execute(sql)
            conn.commit()
            print(f"  ADDED: {table}.{col_name}")
        except Exception as e:
            print(f"  ERROR adding {table}.{col_name}: {e}")
    else:
        print(f"  EXISTS: {table}.{col_name}")


def run_sql(sql, label=""):
    try:
        cursor.execute(sql)
        conn.commit()
        print(f"  OK: {label or sql[:70]}")
    except Exception as e:
        print(f"  ERROR [{label or sql[:40]}]: {e}")


print("=== AlumniLink Migration Started ===\n")

# ── 0. users (password_hash column & title-case roles) ─────────────────────────
print("[ users ]")
add_column("users", "password_hash VARCHAR(255) DEFAULT NULL")
if column_exists("users", "password"):
    run_sql("ALTER TABLE users MODIFY COLUMN password VARCHAR(255) DEFAULT NULL", "Make password column nullable")
if column_exists("users", "password") and column_exists("users", "password_hash"):
    run_sql("UPDATE users SET password_hash = password WHERE password_hash IS NULL OR password_hash = ''",
            "Copy password column data to password_hash")
    run_sql("UPDATE users SET password = password_hash WHERE password IS NULL OR password = ''",
            "Copy password_hash data back to password column")

# Standardize existing role values in DB to Title Case ('Student', 'Alumni', 'Admin')
run_sql("UPDATE users SET role = 'Admin' WHERE LOWER(role) = 'admin'", "Standardize Admin role case")
run_sql("UPDATE users SET role = 'Student' WHERE LOWER(role) = 'student'", "Standardize Student role case")
run_sql("UPDATE users SET role = 'Alumni' WHERE LOWER(role) = 'alumni'", "Standardize Alumni role case")

# ── 1. job_posts ──────────────────────────────────────────────────────────────
print("\n[ job_posts ]")
add_column("job_posts", "job_type ENUM('Internship', 'Full-Time', 'Part-Time') NOT NULL DEFAULT 'Full-Time'")
add_column("job_posts", "work_mode ENUM('Remote', 'Hybrid', 'On-site') NOT NULL DEFAULT 'On-site'")
add_column("job_posts", "stipend_salary VARCHAR(100) DEFAULT NULL")
add_column("job_posts", "required_skills TEXT DEFAULT NULL")
add_column("job_posts", "eligibility TEXT DEFAULT NULL")
add_column("job_posts", "application_link VARCHAR(500) DEFAULT NULL")
add_column("job_posts", "status ENUM('Active', 'Closed') NOT NULL DEFAULT 'Active'")
add_column("job_posts", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
# Set existing rows to Active
run_sql("UPDATE job_posts SET status = 'Active' WHERE status IS NULL", "Set existing jobs Active")

# ── 2. mentorship_requests ───────────────────────────────────────────────────
print("\n[ mentorship_requests ]")
add_column("mentorship_requests", "request_date DATE DEFAULT NULL")
run_sql("UPDATE mentorship_requests SET request_date = DATE(created_at) WHERE request_date IS NULL",
        "Backfill request_date")
run_sql("ALTER TABLE mentorship_requests MODIFY COLUMN status ENUM('pending','accepted','approved','rejected','cancelled') DEFAULT 'pending'",
        "Extend status ENUM")

# ── 3. job_applications (create if missing) ──────────────────────────────────
print("\n[ job_applications ]")
run_sql("""CREATE TABLE IF NOT EXISTS job_applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    student_id INT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_application (job_id, student_id),
    FOREIGN KEY (job_id) REFERENCES job_posts (job_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students (student_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""", "CREATE job_applications")

# ── 4. alumni ────────────────────────────────────────────────────────────────
print("\n[ alumni ]")
add_column("alumni", "phone VARCHAR(50) DEFAULT NULL")
add_column("alumni", "github VARCHAR(255) DEFAULT NULL")
add_column("alumni", "bio TEXT DEFAULT NULL")
add_column("alumni", "achievements TEXT DEFAULT NULL")
add_column("alumni", "share_email BOOLEAN DEFAULT TRUE")
add_column("alumni", "share_phone BOOLEAN DEFAULT FALSE")
add_column("alumni", "graduation_year INT DEFAULT NULL")
# department column - might already exist from schema
add_column("alumni", "department VARCHAR(100) NOT NULL DEFAULT 'Information Technology'")

# Sync verification_status with verified flag
run_sql("UPDATE alumni SET verification_status = 'approved' WHERE verified = TRUE AND (verification_status IS NULL OR verification_status = 'pending')",
        "Sync verification_status=approved")
run_sql("UPDATE alumni SET verification_status = 'pending' WHERE verified = FALSE AND verification_status IS NULL",
        "Sync verification_status=pending")

# ── 5. students ──────────────────────────────────────────────────────────────
print("\n[ students ]")
add_column("students", "linkedin VARCHAR(255) DEFAULT NULL")
add_column("students", "github VARCHAR(255) DEFAULT NULL")
add_column("students", "bio TEXT DEFAULT NULL")

# ── Done ─────────────────────────────────────────────────────────────────────
cursor.close()
conn.close()
print("\n=== Migration Complete ===")
