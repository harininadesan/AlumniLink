from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from flask_bcrypt import Bcrypt
from models.database import get_db_connection, User
from student_conversions import valid_passing_out_year
import re

# Create the authentication blueprint
auth_bp = Blueprint('auth', __name__)

# Initialize Bcrypt locally for password hashing operations
bcrypt = Bcrypt()


# Helper for basic email validation
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles Student and Alumni registration.
    Admin registration is intentionally disabled.
    """

    if current_user.is_authenticated:
        return redirect_role_dashboard(current_user.role)

    if request.method == 'POST':

        # Retrieve common registration fields
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', '').strip().lower()

        # Validate required fields
        if not full_name or not email or not password or not confirm_password or not role:
            flash('All registration fields are required.', 'danger')
            return render_template('register.html')

        # Validate email
        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        # Validate password length
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')

        # Confirm password
        if password != confirm_password:
            flash('Passwords do not match. Please verify.', 'danger')
            return render_template('register.html')

        # Only Student and Alumni can register publicly
        if role not in ['student', 'alumni']:
            flash('Invalid user role selected.', 'danger')
            return render_template('register.html')

        # Role-specific fields
        graduation_year = None
        admission_year = None
        register_number = None
        company = None
        designation = None
        location = None

        if role == 'student':

            graduation_year = request.form.get(
                'graduation_year', ''
            ).strip()

            admission_year_text = request.form.get(
                'admission_year', ''
            ).strip()

            register_number = request.form.get(
                'register_number', ''
            ).strip()

            if not graduation_year or not register_number:
                flash(
                    'Graduation year and registration number are required for students.',
                    'danger'
                )
                return render_template('register.html')

            graduation_year = valid_passing_out_year(graduation_year)
            if graduation_year is None:
                flash(
                    'Passing-out year must be between 1990 and 2100.',
                    'danger'
                )
                return render_template('register.html')

            if admission_year_text:
                admission_year = valid_passing_out_year(admission_year_text)
                if admission_year is None or admission_year > graduation_year:
                    flash('Admission year must be valid and no later than the passing-out year.', 'danger')
                    return render_template('register.html')

        elif role == 'alumni':

            company = request.form.get(
                'company', ''
            ).strip()

            designation = request.form.get(
                'designation', ''
            ).strip()

            location = request.form.get(
                'location', ''
            ).strip()

        conn = None
        cursor = None

        try:

            # Connect to database
            conn = get_db_connection()

            if conn is None:
                flash(
                    'Database connection error. Please try again later.',
                    'danger'
                )
                return render_template('register.html')

            cursor = conn.cursor(dictionary=True)

            # Check whether email already exists
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            existing_user = cursor.fetchone()

            if existing_user:
                flash(
                    'This email address is already registered. Please login.',
                    'warning'
                )
                return render_template('register.html')

            # Check duplicate student register number
            if role == 'student':

                cursor.execute(
                    "SELECT * FROM students WHERE register_number = %s",
                    (register_number,)
                )

                if cursor.fetchone():
                    flash(
                        'This registration number is already registered.',
                        'danger'
                    )
                    return render_template('register.html')

            # Hash password using Flask-Bcrypt
            hashed_password = bcrypt.generate_password_hash(
                password
            ).decode('utf-8')

            # Convert form role to database role
            if role == 'student':
                db_role = 'Student'
            else:
                db_role = 'Alumni'

            # Insert user
            query = """
                INSERT INTO users
                (full_name, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
            """

            cursor.execute(
                query,
                (
                    full_name,
                    email,
                    hashed_password,
                    db_role
                )
            )

            user_id = cursor.lastrowid

            # Create Student profile
            if role == 'student':

                cursor.execute(
                    """
                    INSERT INTO students
                    (user_id, department, admission_year, graduation_year, register_number)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        'Information Technology',
                        admission_year,
                        graduation_year,
                        register_number
                    )
                )

            # Create Alumni profile
            elif role == 'alumni':

                cursor.execute(
                    """
                    INSERT INTO alumni
                    (
                        user_id,
                        company,
                        designation,
                        location,
                        mentor_status,
                        verified,
                        verification_status,
                        department
                    )
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        company or None,
                        designation or None,
                        location or None,
                        1,
                        0,
                        'pending',
                        'Information Technology'
                    )
                )

            # Save transaction
            conn.commit()

            flash(
                'Registration successful! Please login below.',
                'success'
            )

            return redirect(url_for('auth.login'))

        except Exception as e:

            if conn:
                conn.rollback()

            flash(
                f'Database error during registration: {e}',
                'danger'
            )

            return render_template('register.html')

        finally:

            if cursor:
                cursor.close()

            if conn:
                conn.close()

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles login for Student, Alumni and Admin.

    Uses the actual users.password_hash column.
    """

    if current_user.is_authenticated:
        return redirect_role_dashboard(current_user.role)

    if request.method == 'POST':

        # Get login fields
        email = request.form.get(
            'email',
            ''
        ).strip().lower()

        password = request.form.get(
            'password',
            ''
        )

        remember_me = True if request.form.get(
            'remember_me'
        ) else False

        # Validate fields
        if not email or not password:

            flash(
                'Please enter both email and password.',
                'danger'
            )

            return render_template('login.html')

        # Find user by email
        user_obj = User.get_by_email(email)

        if not user_obj:

            flash(
                'Invalid email or password.',
                'danger'
            )

            return render_template('login.html')

        conn = None
        cursor = None

        try:

            # Connect to database
            conn = get_db_connection()

            if conn is None:

                flash(
                    'Database connection error. Please try again later.',
                    'danger'
                )

                return render_template('login.html')

            cursor = conn.cursor(dictionary=True)

            # IMPORTANT:
            # The database uses password_hash.
            # Do not query a non-existing password column.
            cursor.execute(
                """
                SELECT password_hash
                FROM users
                WHERE user_id = %s
                """,
                (user_obj.id,)
            )

            hashed_pass_row = cursor.fetchone()

            stored_hash = None

            if hashed_pass_row:
                stored_hash = hashed_pass_row.get(
                    'password_hash'
                )

            # Check password
            if not stored_hash:

                flash(
                    'Invalid email or password.',
                    'danger'
                )

                return render_template('login.html')

            if not bcrypt.check_password_hash(
                stored_hash,
                password
            ):

                flash(
                    'Invalid email or password.',
                    'danger'
                )

                return render_template('login.html')

            # Alumni verification information
            if str(user_obj.role).strip().lower() == 'alumni':

                cursor.execute(
                    """
                    SELECT verified, verification_status
                    FROM alumni
                    WHERE user_id = %s
                    """,
                    (user_obj.id,)
                )

                alumni_row = cursor.fetchone()

                if alumni_row:

                    verified = alumni_row.get('verified')
                    verification_status = str(
                        alumni_row.get(
                            'verification_status'
                        ) or ''
                    ).strip().lower()

                    if not verified or verification_status == 'pending':

                        flash(
                            'Your alumni account is pending admin verification. '
                            'Some dashboard features may be restricted until approved.',
                            'info'
                        )

            # Login using Flask-Login
            login_user(
                user_obj,
                remember=remember_me
            )

            # Store compatibility session values
            session['user_id'] = user_obj.id
            session['role'] = user_obj.role
            session['full_name'] = user_obj.full_name

            flash(
                f'Welcome back, {user_obj.full_name}!',
                'success'
            )

            # Redirect based on role
            return redirect_role_dashboard(
                user_obj.role
            )

        except Exception as e:

            flash(
                f'Database error during login verification: {e}',
                'danger'
            )

            return render_template('login.html')

        finally:

            if cursor:
                cursor.close()

            if conn:
                conn.close()

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """
    Logs out the current user.
    """

    logout_user()

    session.clear()

    flash(
        'You have been logged out successfully.',
        'info'
    )

    return redirect(url_for('home'))


def redirect_role_dashboard(role):
    """
    Redirect users according to their database role.

    Supports:
    Student
    Alumni
    Admin
    """

    normalized_role = str(
        role
    ).strip().lower()

    if normalized_role == 'student':

        return redirect(
            url_for('student.dashboard')
        )

    elif normalized_role == 'alumni':

        return redirect(
            url_for('alumni.dashboard')
        )

    elif normalized_role == 'admin':

        return redirect(
            url_for('admin.dashboard')
        )

    else:

        flash(
            'Unknown user role. Contact IT support.',
            'danger'
        )

        return redirect(
            url_for('home')
        )