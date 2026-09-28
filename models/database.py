import mysql.connector
from mysql.connector import Error
from config import Config
from flask_login import UserMixin

def get_db_connection():
    """
    Establishes and returns a connection to the MySQL database 
    using parameters from config.py.
    
    Returns:
        mysql.connector.connection.MySQLConnection: Connection object if successful, None otherwise.
    """
    try:
        # Connect to MySQL database using settings from config.py
        connection = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        
        # Verify if the connection is active
        if connection.is_connected():
            return connection
            
    except Error as e:
        # Print a clear error message if connection fails
        print(f"Failed to connect to MySQL database: {e}")
        return None


class User(UserMixin):
    """
    User model for Flask-Login session management, matching the database schema.
    """
    def __init__(self, user_id, full_name, email, role, profile_photo=None):
        self.id = user_id
        self.full_name = full_name
        self.email = email
        self.role = role
        self.profile_photo = profile_photo

    @staticmethod
    def get(user_id):
        """
        Retrieve a user instance by their unique user_id.
        """
        conn = get_db_connection()
        if conn is None:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user_row = cursor.fetchone()
            if user_row:
                return User(
                    user_id=user_row['user_id'],
                    full_name=user_row['full_name'],
                    email=user_row['email'],
                    role=user_row['role'],
                    profile_photo=user_row.get('profile_photo')
                )
            return None
        except Error as e:
            print(f"Database error in User.get: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_by_email(email):
        """
        Retrieve a user instance by their email address.
        """
        conn = get_db_connection()
        if conn is None:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_row = cursor.fetchone()
            if user_row:
                return User(
                    user_id=user_row['user_id'],
                    full_name=user_row['full_name'],
                    email=user_row['email'],
                    role=user_row['role'],
                    profile_photo=user_row.get('profile_photo')
                )
            return None
        except Error as e:
            print(f"Database error in User.get_by_email: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
