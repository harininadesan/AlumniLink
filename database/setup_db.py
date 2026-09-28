import os
import sys
import mysql.connector
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

# Ensure we can import from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_NAME = os.getenv('DB_NAME', 'alumnilink_db')

def setup_database():
    print(f"Connecting to MySQL server at {DB_HOST}...")
    try:
        # Connect to MySQL Server (without specifying DB name first)
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        
        # Create database if it doesn't exist
        print(f"Creating database {DB_NAME} if not exists...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        cursor.close()
        conn.close()
        
        # Connect to the specific database
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        
        # Read and run schema.sql
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        print(f"Reading schema file from {schema_path}...")
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
            
        # Execute commands by splitting with ';'
        # Remove comments first
        sql_commands = []
        current_command = []
        for line in sql_script.split('\n'):
            stripped = line.strip()
            if not stripped or stripped.startswith('--') or stripped.startswith('#'):
                continue
            current_command.append(line)
            if stripped.endswith(';'):
                sql_commands.append('\n'.join(current_command))
                current_command = []
                
        print(f"Executing {len(sql_commands)} SQL commands to initialize tables...")
        for cmd in sql_commands:
            if cmd.strip():
                cursor.execute(cmd)
        conn.commit()
        print("Database schema successfully applied.")
        
        # Seeding initial users
        print("Seeding default accounts...")
        bcrypt = Bcrypt()
        
        # Check if users already exist
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            print("Users already exist. Skipping seed.")
            return
            
        # 1. Seed Admin
        admin_pass = bcrypt.generate_password_hash('admin123').decode('utf-8')
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
            ('System Administrator', 'admin@alumnilink.edu', admin_pass, 'admin')
        )
        admin_user_id = cursor.lastrowid
        cursor.execute("INSERT INTO admins (user_id) VALUES (%s)", (admin_user_id,))
        
        # 2. Seed Student
        student_pass = bcrypt.generate_password_hash('student123').decode('utf-8')
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
            ('John Student', 'student@alumnilink.edu', student_pass, 'student')
        )
        student_user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO students (user_id, department, graduation_year, register_number, bio) VALUES (%s, %s, %s, %s, %s)",
            (student_user_id, 'Information Technology', 2026, 'IT2026001', 'Information Technology student passionate about software development, web applications, and databases.')
        )
        
        # 3. Seed Alumni (Verified)
        alumni_pass = bcrypt.generate_password_hash('alumni123').decode('utf-8')
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
            ('Jane Alumni', 'alumni@alumnilink.edu', alumni_pass, 'alumni')
        )
        alumni_user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO alumni (user_id, company, designation, experience, skills, linkedin, location, mentor_status, verified, verification_status, department, graduation_year, phone, github, bio, achievements, share_email, share_phone) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (alumni_user_id, 'Google', 'Software Engineer', 'Worked on cloud infrastructure', 'Python, Flask, MySQL, JavaScript', 'https://linkedin.com/in/janealumni', 'Mountain View, CA', 1, 1, 'approved', 'Information Technology', 2018, '+1-555-0199', 'https://github.com/janealumni', 'Senior software engineer at Google with a passion for helping students transition into tech. Experienced in Python, Flask, and distributed systems.', 'Google Peer Bonus Award (2024), 3x Hackathon Winner', 1, 1)
        )
        
        conn.commit()
        print("Seeding completed successfully.")
        print("\nTest Credentials:")
        print("  Admin   : admin@alumnilink.edu  / admin123")
        print("  Student : student@alumnilink.edu / student123")
        print("  Alumni  : alumni@alumnilink.edu  / alumni123")
        
    except mysql.connector.Error as err:
        print(f"MySQL Error: {err}")
    except Exception as e:
        print(f"Error during setup: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    setup_database()
