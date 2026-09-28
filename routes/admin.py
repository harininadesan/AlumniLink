from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from models.database import get_db_connection

# Define the admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """
    Decorator to restrict access only to logged-in Admin users.
    Redirects unauthenticated requests to the login screen.
    Safely normalizes role case checking.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = str(session.get('role', '')).strip().lower()
        if 'user_id' not in session or role != 'admin':
            flash('Please log in as an Administrator to access the panel.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """
    Renders the Administrator Dashboard:
    - Queries real MySQL statistics (students, alumni, pending/approved/rejected, jobs, mentorship requests).
    - Lists alumni awaiting account verification.
    - Provides recent activity feeds for students, alumni, jobs, and mentorship requests.
    """
    conn = None
    cursor = None
    
    stats = {
        'students': 0,
        'alumni': 0,
        'pending_alumni': 0,
        'approved_alumni': 0,
        'rejected_alumni': 0,
        'jobs': 0,
        'requests': 0,
        'pending_requests': 0
    }
    
    lists = {
        'pending_alumni': [],
        'students': [],
        'alumni': [],
        'jobs': [],
        'requests': [],
        'recent_students': [],
        'recent_alumni': [],
        'recent_jobs': [],
        'recent_requests': []
    }
    
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Database connection failed.', 'danger')
            return redirect(url_for('home'))
            
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch aggregate statistics counts from MySQL
        cursor.execute("SELECT COUNT(*) AS count FROM students")
        stats['students'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) AS count FROM alumni")
        stats['alumni'] = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) AS count FROM alumni 
            WHERE verification_status = 'pending' 
               OR (verified = FALSE AND (verification_status IS NULL OR verification_status = 'pending'))
        """)
        stats['pending_alumni'] = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) AS count FROM alumni 
            WHERE verification_status = 'approved' 
               OR (verified = TRUE AND (verification_status IS NULL OR verification_status = 'approved'))
        """)
        stats['approved_alumni'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM alumni WHERE verification_status = 'rejected'")
        stats['rejected_alumni'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) AS count FROM job_posts")
        stats['jobs'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM mentorship_requests")
        stats['requests'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM mentorship_requests WHERE status = 'pending'")
        stats['pending_requests'] = cursor.fetchone()['count']
        
        # 2. Fetch pending alumni verification profiles
        cursor.execute("""
            SELECT a.alumni_id, u.full_name, u.email, u.profile_photo, a.company, a.designation,
                   a.location, a.graduation_year, a.skills, a.verification_status, a.verified, u.created_at
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.verification_status = 'pending' 
               OR (a.verified = FALSE AND (a.verification_status IS NULL OR a.verification_status = 'pending'))
            ORDER BY u.created_at DESC
        """)
        lists['pending_alumni'] = cursor.fetchall()
        
        # 3. Fetch all students for management catalog
        cursor.execute("""
            SELECT s.student_id, u.full_name, u.email, u.profile_photo, s.department, 
                   s.graduation_year, s.register_number, u.created_at
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY u.full_name ASC
        """)
        lists['students'] = cursor.fetchall()
        
        # 4. Fetch all alumni for management catalog
        cursor.execute("""
            SELECT a.alumni_id, u.full_name, u.email, u.profile_photo, a.company, a.designation,
                   a.location, a.graduation_year, a.skills, a.verified, a.verification_status, a.mentor_status
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            ORDER BY u.full_name ASC
        """)
        lists['alumni'] = cursor.fetchall()
        
        # 5. Fetch all job posts for moderation
        cursor.execute("""
            SELECT jp.job_id, jp.title, jp.company, jp.job_type, jp.work_mode, jp.location, jp.status, jp.created_at, u.full_name AS alumni_name
            FROM job_posts jp
            JOIN alumni a ON jp.alumni_id = a.alumni_id
            JOIN users u ON a.user_id = u.user_id
            ORDER BY jp.created_at DESC
        """)
        lists['jobs'] = cursor.fetchall()

        # 6. Fetch mentorship requests for monitoring reports
        cursor.execute("""
            SELECT mr.id AS request_id, mr.status, mr.created_at AS request_date, mr.message,
                   u_student.full_name AS student_name, u_student.email AS student_email,
                   u_alumni.full_name AS alumni_name, u_alumni.email AS alumni_email
            FROM mentorship_requests mr
            JOIN students s ON mr.student_id = s.student_id
            JOIN users u_student ON s.user_id = u_student.user_id
            JOIN alumni a ON mr.alumni_id = a.alumni_id
            JOIN users u_alumni ON a.user_id = u_alumni.user_id
            ORDER BY mr.created_at DESC
        """)
        lists['requests'] = cursor.fetchall()

        # 7. Fetch Recent Activity feeds (latest 5 per category)
        cursor.execute("""
            SELECT s.student_id, u.full_name, u.email, u.profile_photo, s.department, s.graduation_year, u.created_at
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY u.created_at DESC LIMIT 5
        """)
        lists['recent_students'] = cursor.fetchall()

        cursor.execute("""
            SELECT a.alumni_id, u.full_name, u.email, u.profile_photo, a.company, a.designation, a.verification_status, a.verified, u.created_at
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            ORDER BY u.created_at DESC LIMIT 5
        """)
        lists['recent_alumni'] = cursor.fetchall()

        cursor.execute("""
            SELECT jp.job_id, jp.title, jp.company, jp.job_type, jp.created_at, u.full_name AS alumni_name
            FROM job_posts jp
            JOIN alumni a ON jp.alumni_id = a.alumni_id
            JOIN users u ON a.user_id = u.user_id
            ORDER BY jp.created_at DESC LIMIT 5
        """)
        lists['recent_jobs'] = cursor.fetchall()

        cursor.execute("""
            SELECT mr.id AS request_id, mr.status, mr.created_at AS request_date,
                   u_student.full_name AS student_name, u_alumni.full_name AS alumni_name
            FROM mentorship_requests mr
            JOIN students s ON mr.student_id = s.student_id
            JOIN users u_student ON s.user_id = u_student.user_id
            JOIN alumni a ON mr.alumni_id = a.alumni_id
            JOIN users u_alumni ON a.user_id = u_alumni.user_id
            ORDER BY mr.created_at DESC LIMIT 5
        """)
        lists['recent_requests'] = cursor.fetchall()
        
    except Exception as e:
        flash(f"Error loading admin statistics: {e}", 'danger')
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('admin_dashboard.html', stats=stats, lists=lists)


@admin_bp.route('/students', methods=['GET'], endpoint='students')
@admin_bp.route('/students', methods=['GET'], endpoint='manage_students')
@admin_required
def manage_students():
    """
    Renders manage_students.html.
    Fetches and filters students based on search query matching name, email, department, or registry ID.
    """
    search = request.args.get('search', '').strip()
    conn = None
    cursor = None
    students_list = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if search:
            query = """
                SELECT s.student_id, s.user_id, u.full_name, u.email, u.profile_photo, u.created_at,
                       s.department, s.graduation_year, s.register_number, s.skills, s.resume, s.career_goal, s.bio
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                WHERE u.full_name LIKE %s OR u.email LIKE %s OR s.register_number LIKE %s OR s.department LIKE %s
                ORDER BY u.full_name ASC
            """
            sp = f"%{search}%"
            cursor.execute(query, (sp, sp, sp, sp))
        else:
            query = """
                SELECT s.student_id, s.user_id, u.full_name, u.email, u.profile_photo, u.created_at,
                       s.department, s.graduation_year, s.register_number, s.skills, s.resume, s.career_goal, s.bio
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                ORDER BY u.full_name ASC
            """
            cursor.execute(query)
        students_list = cursor.fetchall()
        
    except Exception as e:
        flash(f"Error retrieving student catalog: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('manage_students.html', students=students_list, search=search)


@admin_bp.route('/student/<int:student_id>', methods=['GET'])
@admin_required
def view_student_profile(student_id):
    """
    Renders admin_student_profile.html.
    Displays complete student profile for admin inspection.
    """
    conn = None
    cursor = None
    student = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.*, u.full_name, u.email, u.profile_photo, u.created_at AS user_created_at
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()
        if not student:
            flash("Student profile not found.", "danger")
            return redirect(url_for('admin.manage_students'))
    except Exception as e:
        flash(f"Error loading student profile: {e}", "danger")
        return redirect(url_for('admin.manage_students'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('admin_student_profile.html', student=student)


@admin_bp.route('/alumni', methods=['GET'], endpoint='alumni')
@admin_bp.route('/alumni', methods=['GET'], endpoint='manage_alumni')
@admin_required
def manage_alumni():
    """
    Renders manage_alumni.html.
    Fetches and filters alumni based on search query and verification_status filter.
    """
    search = request.args.get('search', '').strip()
    filter_status = request.args.get('status', '').strip()  # pending / approved / rejected
    conn = None
    cursor = None
    alumni_list = []
    stats = {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0}
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS cnt FROM alumni")
        stats['total'] = cursor.fetchone()['cnt']
        
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM alumni 
            WHERE verification_status = 'pending' 
               OR (verified = FALSE AND (verification_status IS NULL OR verification_status = 'pending'))
        """)
        stats['pending'] = cursor.fetchone()['cnt']
        
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM alumni 
            WHERE verification_status = 'approved' 
               OR (verified = TRUE AND (verification_status IS NULL OR verification_status = 'approved'))
        """)
        stats['approved'] = cursor.fetchone()['cnt']
        
        cursor.execute("SELECT COUNT(*) AS cnt FROM alumni WHERE verification_status = 'rejected'")
        stats['rejected'] = cursor.fetchone()['cnt']

        query = """
            SELECT a.alumni_id, a.user_id, u.full_name, u.email, u.profile_photo, u.created_at,
                   a.company, a.designation, a.location, a.verified, a.verification_status,
                   a.graduation_year, a.department, a.skills, a.mentor_status, a.phone
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            WHERE 1=1
        """
        params = []

        if search:
            query += " AND (u.full_name LIKE %s OR u.email LIKE %s OR a.company LIKE %s OR a.designation LIKE %s OR a.skills LIKE %s)"
            sp = f"%{search}%"
            params.extend([sp, sp, sp, sp, sp])

        if filter_status == 'pending':
            query += " AND (a.verification_status = 'pending' OR (a.verified = FALSE AND (a.verification_status IS NULL OR a.verification_status = 'pending')))"
        elif filter_status == 'approved':
            query += " AND (a.verification_status = 'approved' OR (a.verified = TRUE AND (a.verification_status IS NULL OR a.verification_status = 'approved')))"
        elif filter_status == 'rejected':
            query += " AND a.verification_status = 'rejected'"

        query += " ORDER BY u.full_name ASC"
        cursor.execute(query, params)
        alumni_list = cursor.fetchall()
        
    except Exception as e:
        flash(f"Error retrieving alumni catalog: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('manage_alumni.html', alumni=alumni_list, search=search, filter_status=filter_status, stats=stats)


@admin_bp.route('/alumni/<int:alumni_id>', methods=['GET'])
@admin_required
def view_alumni_profile(alumni_id):
    """
    Renders admin_alumni_profile.html.
    Provides complete alumni profile information required for verification inspection.
    """
    conn = None
    cursor = None
    alumnus = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.*, u.full_name, u.email, u.profile_photo, u.created_at AS user_created_at
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.alumni_id = %s
        """, (alumni_id,))
        alumnus = cursor.fetchone()
        if not alumnus:
            flash("Alumni profile not found.", "danger")
            return redirect(url_for('admin.manage_alumni'))
    except Exception as e:
        flash(f"Error loading alumni profile: {e}", "danger")
        return redirect(url_for('admin.manage_alumni'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('admin_alumni_profile.html', alumnus=alumnus)


@admin_bp.route('/alumni/verify', methods=['POST'])
@admin_required
def verify_alumni():
    """
    Approves or rejects an alumni profile verification request.
    Updates verification_status and verified fields.
    """
    alumni_id = request.form.get('alumni_id')
    action = request.form.get('action')  # 'approve' or 'reject'
    
    if not alumni_id or action not in ['approve', 'reject']:
        flash('Invalid verification action parameters.', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT a.alumni_id, a.user_id, u.full_name FROM alumni a JOIN users u ON a.user_id = u.user_id WHERE a.alumni_id = %s", (alumni_id,))
        row = cursor.fetchone()
        
        if not row:
            flash('Alumni account not found.', 'danger')
            return redirect(url_for('admin.dashboard'))
            
        user_id = row['user_id']
        name = row['full_name']
        
        if action == 'approve':
            cursor.execute("""
                UPDATE alumni SET verified = TRUE, verification_status = 'approved'
                WHERE alumni_id = %s
            """, (alumni_id,))
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message)
                VALUES (%s, 'Account Verified',
                    'Congratulations! Your alumni account has been verified by the IT department admin. You can now post jobs and mentor students.')
            """, (user_id,))
            conn.commit()
            flash(f'Alumni account for {name} has been APPROVED successfully!', 'success')
            
        elif action == 'reject':
            cursor.execute("""
                UPDATE alumni SET verified = FALSE, verification_status = 'rejected'
                WHERE alumni_id = %s
            """, (alumni_id,))
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message)
                VALUES (%s, 'Verification Status Update',
                    'Your alumni account verification request was reviewed and set to rejected status. Please contact the IT department for more details.')
            """, (user_id,))
            conn.commit()
            flash(f'Alumni verification for {name} was REJECTED.', 'info')
            
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Database error during verification: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    referrer = request.referrer
    if referrer and 'alumni' in referrer and 'dashboard' not in referrer:
        return redirect(url_for('admin.manage_alumni'))
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/student/delete', methods=['POST'])
@admin_required
def delete_student():
    """
    Permanently deletes a student user account from the database.
    """
    student_id = request.form.get('student_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT user_id FROM students WHERE student_id = %s", (student_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("DELETE FROM users WHERE user_id = %s", (row['user_id'],))
            conn.commit()
            flash('Student account deleted successfully.', 'success')
        else:
            flash('Student record not found.', 'danger')
            
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Failed to delete student: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    referrer = request.referrer
    if referrer and 'students' in referrer:
        return redirect(url_for('admin.manage_students'))
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/alumni/delete', methods=['POST'])
@admin_required
def delete_alumni():
    """
    Permanently deletes an alumni user account from the database.
    """
    alumni_id = request.form.get('alumni_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT user_id FROM alumni WHERE alumni_id = %s", (alumni_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("DELETE FROM users WHERE user_id = %s", (row['user_id'],))
            conn.commit()
            flash('Alumni account deleted successfully.', 'success')
        else:
            flash('Alumni record not found.', 'danger')
            
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Failed to delete alumni: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    referrer = request.referrer
    if referrer and 'alumni' in referrer and 'dashboard' not in referrer:
        return redirect(url_for('admin.manage_alumni'))
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/jobs', methods=['GET'], endpoint='jobs')
@admin_bp.route('/jobs', methods=['GET'], endpoint='manage_jobs')
@admin_required
def manage_jobs():
    """
    Admin job moderation catalog — view, search, remove, or close any job post.
    """
    search = request.args.get('search', '').strip()
    filter_status = request.args.get('status', '').strip()
    conn = None
    cursor = None
    jobs_list = []
    stats = {'total': 0, 'active': 0, 'closed': 0}

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT jp.job_id, jp.title, jp.company, jp.job_type, jp.work_mode,
                   jp.location, jp.stipend_salary, jp.deadline, jp.status, jp.description,
                   jp.required_skills, jp.eligibility, jp.application_link,
                   jp.created_at, u.full_name AS alumni_name, u.email AS alumni_email,
                   a.alumni_id,
                   (SELECT COUNT(*) FROM job_applications ja WHERE ja.job_id = jp.job_id) AS applicant_count
            FROM job_posts jp
            JOIN alumni a ON jp.alumni_id = a.alumni_id
            JOIN users u ON a.user_id = u.user_id
            WHERE 1=1
        """
        params = []

        if search:
            query += """ AND (jp.title LIKE %s OR jp.company LIKE %s
                           OR u.full_name LIKE %s OR jp.location LIKE %s)"""
            sq = f"%{search}%"
            params.extend([sq, sq, sq, sq])

        if filter_status:
            query += " AND jp.status = %s"
            params.append(filter_status)

        query += " ORDER BY jp.created_at DESC"
        cursor.execute(query, params)
        jobs_list = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS cnt FROM job_posts")
        stats['total'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) AS cnt FROM job_posts WHERE status = 'Active'")
        stats['active'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) AS cnt FROM job_posts WHERE status = 'Closed'")
        stats['closed'] = cursor.fetchone()['cnt']

    except Exception as e:
        flash(f"Error loading jobs: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template(
        'admin_jobs.html',
        jobs=jobs_list,
        stats=stats,
        search=search,
        filter_status=filter_status
    )


@admin_bp.route('/job/<int:job_id>', methods=['GET'])
@admin_required
def view_job_detail(job_id):
    """
    Returns JSON details for a specific job post for admin inspection modal.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT jp.*, u.full_name AS alumni_name, u.email AS alumni_email, a.company AS alumni_company, a.designation AS alumni_designation
            FROM job_posts jp
            JOIN alumni a ON jp.alumni_id = a.alumni_id
            JOIN users u ON a.user_id = u.user_id
            WHERE jp.job_id = %s
        """, (job_id,))
        job = cursor.fetchone()
        if not job:
            return jsonify({'error': 'Job post not found'}), 404
        return jsonify(job)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@admin_bp.route('/job/delete', methods=['POST'])
@admin_required
def delete_job():
    """
    Moderates and deletes a published job opening.
    """
    job_id = request.form.get('job_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_posts WHERE job_id = %s", (job_id,))
        conn.commit()
        flash('Job post deleted successfully.', 'success')
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Failed to remove job posting: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    referrer = request.referrer
    if referrer and 'jobs' in referrer:
        return redirect(url_for('admin.manage_jobs'))
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/jobs/close', methods=['POST'])
@admin_required
def admin_close_job():
    """
    Admin action to close a job post.
    """
    job_id = request.form.get('job_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE job_posts SET status = 'Closed' WHERE job_id = %s", (job_id,))
        conn.commit()
        flash('Job post closed successfully.', 'info')
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Error: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.manage_jobs'))


@admin_bp.route('/mentorship', methods=['GET'], endpoint='mentorship')
@admin_bp.route('/mentorship', methods=['GET'], endpoint='manage_mentorship')
@admin_required
def manage_mentorship():
    """
    Admin Mentorship Requests Catalog.
    Lists all mentorship requests initiated by students to alumni.
    """
    search = request.args.get('search', '').strip()
    filter_status = request.args.get('status', '').strip()
    conn = None
    cursor = None
    requests_list = []
    stats = {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0}

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS cnt FROM mentorship_requests")
        stats['total'] = cursor.fetchone()['cnt']
        
        cursor.execute("SELECT COUNT(*) AS cnt FROM mentorship_requests WHERE status = 'pending'")
        stats['pending'] = cursor.fetchone()['cnt']
        
        cursor.execute("SELECT COUNT(*) AS cnt FROM mentorship_requests WHERE status IN ('approved', 'accepted')")
        stats['approved'] = cursor.fetchone()['cnt']
        
        cursor.execute("SELECT COUNT(*) AS cnt FROM mentorship_requests WHERE status = 'rejected'")
        stats['rejected'] = cursor.fetchone()['cnt']

        query = """
            SELECT mr.id AS request_id, mr.student_id, mr.alumni_id, mr.message, mr.status,
                   mr.created_at, mr.updated_at,
                   u_student.full_name AS student_name, u_student.email AS student_email,
                   u_student.profile_photo AS student_photo, s.department AS student_dept,
                   u_alumni.full_name AS alumni_name, u_alumni.email AS alumni_email,
                   u_alumni.profile_photo AS alumni_photo, a.company AS alumni_company,
                   a.designation AS alumni_designation
            FROM mentorship_requests mr
            JOIN students s ON mr.student_id = s.student_id
            JOIN users u_student ON s.user_id = u_student.user_id
            JOIN alumni a ON mr.alumni_id = a.alumni_id
            JOIN users u_alumni ON a.user_id = u_alumni.user_id
            WHERE 1=1
        """
        params = []

        if search:
            query += " AND (u_student.full_name LIKE %s OR u_alumni.full_name LIKE %s OR mr.message LIKE %s)"
            sq = f"%{search}%"
            params.extend([sq, sq, sq])

        if filter_status == 'approved':
            query += " AND mr.status IN ('approved', 'accepted')"
        elif filter_status:
            query += " AND mr.status = %s"
            params.append(filter_status)

        query += " ORDER BY mr.created_at DESC"
        cursor.execute(query, params)
        requests_list = cursor.fetchall()

    except Exception as e:
        flash(f"Error loading mentorship requests: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template(
        'admin_mentorship.html',
        requests=requests_list,
        stats=stats,
        search=search,
        filter_status=filter_status
    )


@admin_bp.route('/notifications', methods=['GET'], endpoint='notifications')
@admin_bp.route('/notifications', methods=['GET'], endpoint='manage_notifications')
@admin_required
def manage_notifications():
    """
    Renders admin_notifications.html.
    Displays dynamic administrative alerts and recent notification log history.
    """
    conn = None
    cursor = None
    pending_alumni_alerts = []
    mentorship_alerts = []
    job_alerts = []
    sent_broadcasts = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Unverified alumni alerts
        cursor.execute("""
            SELECT a.alumni_id, u.full_name, u.email, u.created_at, a.company, a.designation
            FROM alumni a 
            JOIN users u ON a.user_id = u.user_id
            WHERE a.verification_status = 'pending' 
               OR (a.verified = FALSE AND (a.verification_status IS NULL OR a.verification_status = 'pending'))
            ORDER BY u.created_at DESC
        """)
        pending_alumni_alerts = cursor.fetchall()

        # 2. Recent mentorship request alerts
        cursor.execute("""
            SELECT mr.id, mr.created_at, mr.status, u_stu.full_name AS student_name, u_alm.full_name AS alumni_name
            FROM mentorship_requests mr
            JOIN students s ON mr.student_id = s.student_id
            JOIN users u_stu ON s.user_id = u_stu.user_id
            JOIN alumni a ON mr.alumni_id = a.alumni_id
            JOIN users u_alm ON a.user_id = u_alm.user_id
            ORDER BY mr.created_at DESC LIMIT 10
        """)
        mentorship_alerts = cursor.fetchall()

        # 3. Recent job post alerts
        cursor.execute("""
            SELECT jp.job_id, jp.title, jp.company, jp.created_at, u.full_name AS alumni_name
            FROM job_posts jp
            JOIN alumni a ON jp.alumni_id = a.alumni_id
            JOIN users u ON a.user_id = u.user_id
            ORDER BY jp.created_at DESC LIMIT 10
        """)
        job_alerts = cursor.fetchall()

        # 4. Broadcast notification log
        cursor.execute("""
            SELECT n.*, u.full_name AS recipient_name, u.role AS recipient_role
            FROM notifications n
            JOIN users u ON n.user_id = u.user_id
            ORDER BY n.created_at DESC LIMIT 30
        """)
        sent_broadcasts = cursor.fetchall()

    except Exception as e:
        flash(f"Error loading admin notifications: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template(
        'admin_notifications.html',
        pending_alumni_alerts=pending_alumni_alerts,
        mentorship_alerts=mentorship_alerts,
        job_alerts=job_alerts,
        sent_broadcasts=sent_broadcasts
    )


@admin_bp.route('/notifications/broadcast', methods=['POST'])
@admin_required
def broadcast_notification():
    """
    Sends a system broadcast alert notification to specific segments.
    """
    title = request.form.get('title', '').strip()
    message = request.form.get('message', '').strip()
    target = request.form.get('target', 'all')
    
    if not title or not message:
        flash('Notification Title and Message cannot be blank.', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if target == 'students':
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message)
                SELECT user_id, %s, %s FROM users WHERE role = 'student'
            """, (title, message))
        elif target == 'alumni':
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message)
                SELECT user_id, %s, %s FROM users WHERE role = 'alumni'
            """, (title, message))
        else:
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message)
                SELECT user_id, %s, %s FROM users
            """, (title, message))
            
        conn.commit()
        flash('Notification broadcasted successfully!', 'success')
        
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Notification broadcast failed: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    referrer = request.referrer
    if referrer and 'notifications' in referrer:
        return redirect(url_for('admin.manage_notifications'))
    return redirect(url_for('admin.dashboard'))
