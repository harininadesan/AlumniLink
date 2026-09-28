import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from werkzeug.utils import secure_filename
from models.database import get_db_connection

# Define the alumni blueprint
alumni_bp = Blueprint('alumni', __name__, url_prefix='/alumni')

# Define target directories for static file uploads
UPLOAD_FOLDER_PHOTOS = os.path.join('static', 'uploads', 'profile_photos')
os.makedirs(UPLOAD_FOLDER_PHOTOS, exist_ok=True)

# Allowed file extensions helper
ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """
    Validates if the file suffix belongs to the allowed extensions set.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


def alumni_required(f):
    """
    Decorator to restrict access to logged-in Alumni users.
    Redirects unauthorized requests to the login screen.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = str(session.get('role', '')).strip().lower()
        if 'user_id' not in session or role != 'alumni':
            flash('Please log in as an Alumni to access the page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@alumni_bp.route('/dashboard', methods=['GET'])
@alumni_required
def dashboard():
    """
    Renders the Alumni Dashboard:
    - Fetches professional profile.
    - Lists student mentorship requests.
    - Displays job postings.
    - Loads notification logs.
    - Shows connection testimonials.
    """
    user_id = session['user_id']
    conn = None
    cursor = None
    
    dashboard_data = {
        'profile': None,
        'requests': [],
        'jobs': [],
        'feedback': [],
        'notifications': []
    }
    
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Database connection failed.', 'danger')
            return redirect(url_for('home'))
            
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch Alumni Profile Details
        cursor.execute("""
            SELECT u.full_name, u.email, u.profile_photo, a.alumni_id, 
                   a.company, a.designation, a.experience, a.skills, a.linkedin, a.location, a.mentor_status
            FROM users u
            LEFT JOIN alumni a ON u.user_id = a.user_id
            WHERE u.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
        
        # Guard clause: if alumni record doesn't exist, create a placeholder
        if profile and profile['alumni_id'] is None:
            cursor.execute("""
                INSERT INTO alumni (user_id, company, designation, experience, skills, linkedin, location, mentor_status)
                VALUES (%s, 'Tech Company', 'Software Engineer', '3+ Years', 'Python, SQL', 'https://linkedin.com', 'Remote', 1)
            """, (user_id,))
            conn.commit()
            
            # Re-fetch profile
            cursor.execute("""
                SELECT u.full_name, u.email, u.profile_photo, a.alumni_id, 
                       a.company, a.designation, a.experience, a.skills, a.linkedin, a.location, a.mentor_status
                FROM users u
                JOIN alumni a ON u.user_id = a.user_id
                WHERE u.user_id = %s
            """, (user_id,))
            profile = cursor.fetchone()
            
        dashboard_data['profile'] = profile
        alumni_id = profile['alumni_id'] if profile else None
        
        if alumni_id:
            # 2. Fetch Mentorship Requests (mr.id aliased as request_id for template compatibility)
            cursor.execute("""
                SELECT mr.id AS request_id, mr.message, mr.status, mr.request_date,
                       u.full_name AS student_name, u.email AS student_email,
                       s.department, s.graduation_year, s.skills, s.resume
                FROM mentorship_requests mr
                JOIN students s ON mr.student_id = s.student_id
                JOIN users u ON s.user_id = u.user_id
                WHERE mr.alumni_id = %s
                ORDER BY mr.request_date DESC
            """, (alumni_id,))
            dashboard_data['requests'] = cursor.fetchall()
            
            # 3. Fetch Job Posts created by this alumnus
            cursor.execute("""
                SELECT * FROM job_posts 
                WHERE alumni_id = %s 
                ORDER BY created_at DESC
            """, (alumni_id,))
            dashboard_data['jobs'] = cursor.fetchall()
            
            # 4. Fetch Feedback / Thank-you notes
            cursor.execute("""
                SELECT mr.message AS feedback_text, mr.request_date, u.full_name AS student_name
                FROM mentorship_requests mr
                JOIN students s ON mr.student_id = s.student_id
                JOIN users u ON s.user_id = u.user_id
                WHERE mr.alumni_id = %s AND mr.status = 'approved'
                ORDER BY mr.request_date DESC
            """, (alumni_id,))
            dashboard_data['feedback'] = cursor.fetchall()
            
        # 5. Fetch Notifications
        cursor.execute("""
            SELECT * FROM notifications 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        dashboard_data['notifications'] = cursor.fetchall()
        
    except Exception as e:
        flash(f"Error loading dashboard: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return render_template('alumni_dashboard.html', data=dashboard_data)


@alumni_bp.route('/profile', methods=['GET'])
@alumni_required
def view_profile():
    """
    Renders the Alumni Profile management page (alumni_profile.html).
    """
    user_id = session['user_id']
    conn = None
    cursor = None
    profile = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.full_name, u.email, u.profile_photo, a.alumni_id, 
                   a.company, a.designation, a.experience, a.skills, a.linkedin, a.location, a.mentor_status,
                   a.graduation_year, a.phone, a.github, a.bio, a.achievements, a.share_email, a.share_phone
            FROM users u
            JOIN alumni a ON u.user_id = a.user_id
            WHERE u.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
    except Exception as e:
        flash(f"Error loading profile: {e}", 'danger')
        return redirect(url_for('alumni.dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    if not profile:
        flash('Alumni profile details missing. Load dashboard first.', 'warning')
        return redirect(url_for('alumni.dashboard'))
        
    return render_template('alumni_profile.html', profile=profile)


@alumni_bp.route('/profile/edit', methods=['POST'])
@alumni_required
def edit_profile():
    """
    Updates the professional details profile in MySQL.
    Modifies both user data (full name) and alumni data.
    """
    full_name = request.form.get('full_name', '').strip()
    company = request.form.get('company', '').strip()
    designation = request.form.get('designation', '').strip()
    experience = request.form.get('experience', '').strip()
    skills = request.form.get('skills', '').strip()
    linkedin = request.form.get('linkedin', '').strip()
    location = request.form.get('location', '').strip()
    mentor_status = request.form.get('mentor_status', '0')
    
    # New fields
    graduation_year = request.form.get('graduation_year', '').strip()
    phone = request.form.get('phone', '').strip()
    github = request.form.get('github', '').strip()
    bio = request.form.get('bio', '').strip()
    achievements = request.form.get('achievements', '').strip()
    share_email = request.form.get('share_email', '0')
    share_phone = request.form.get('share_phone', '0')
    
    user_id = session['user_id']
    
    if not full_name or not company or not designation or not skills:
        flash('Full Name, Company, Designation, and Skills are required fields.', 'danger')
        return redirect(url_for('alumni.view_profile'))
        
    grad_year_val = int(graduation_year) if graduation_year.isdigit() else None
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Update parent users table name
        cursor.execute("UPDATE users SET full_name = %s WHERE user_id = %s", (full_name, user_id))
        
        # 2. Update professional details
        cursor.execute("""
            UPDATE alumni 
            SET company = %s, designation = %s, experience = %s, skills = %s, 
                linkedin = %s, location = %s, mentor_status = %s,
                graduation_year = %s, phone = %s, github = %s, bio = %s,
                achievements = %s, share_email = %s, share_phone = %s
            WHERE user_id = %s
        """, (company, designation, experience, skills, linkedin, location, int(mentor_status),
              grad_year_val, phone, github, bio, achievements, int(share_email), int(share_phone), user_id))
        
        conn.commit()
        session['full_name'] = full_name # sync header navbar display
        flash('Professional profile updated successfully!', 'success')
        
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Failed to update profile: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return redirect(url_for('alumni.view_profile'))


@alumni_bp.route('/profile/upload_photo', methods=['POST'])
@alumni_required
def upload_photo():
    """
    Handles secure file upload of the alumni profile image.
    """
    if 'profile_photo' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('alumni.view_profile'))
        
    file = request.files['profile_photo']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('alumni.view_profile'))
        
    if file and allowed_file(file.filename):
        filename = f"user_{session['user_id']}_" + secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER_PHOTOS, filename)
        
        conn = None
        cursor = None
        try:
            file.save(file_path)
            web_path = f"uploads/profile_photos/{filename}"
            
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET profile_photo = %s WHERE user_id = %s", (web_path, session['user_id']))
                conn.commit()
                flash('Profile photo updated successfully!', 'success')
            else:
                flash('Database unavailable.', 'danger')
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Failed to upload photo: {e}", 'danger')
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    else:
        flash('Allowed image types are png, jpg, jpeg, gif.', 'danger')
        
    return redirect(url_for('alumni.view_profile'))


@alumni_bp.route('/privacy/edit', methods=['POST'])
@alumni_required
def edit_privacy():
    """
    Toggles availability status.
    """
    mentor_status = request.form.get('mentor_status', '0')
    user_id = session['user_id']
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE alumni SET mentor_status = %s WHERE user_id = %s", (int(mentor_status), user_id))
        conn.commit()
        flash('Privacy settings updated successfully!', 'success')
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Failed to update privacy: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return redirect(url_for('alumni.dashboard'))


@alumni_bp.route('/requests/respond', methods=['POST'])
@alumni_required
def respond_request():
    """
    Accepts or rejects mentorship requests from students.
    Uses request `id` (which is aliased as request_id in queries).
    """
    request_id = request.form.get('request_id')
    action = request.form.get('action')
    
    if not request_id or action not in ['accept', 'reject']:
        flash('Invalid parameters.', 'danger')
        return redirect(url_for('alumni.dashboard'))
        
    status_mapping = {'accept': 'accepted', 'reject': 'rejected'}
    db_status = status_mapping[action]
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT mr.id, mr.student_id, s.user_id AS student_user_id, u.full_name AS alumni_name
            FROM mentorship_requests mr
            JOIN alumni a ON mr.alumni_id = a.alumni_id
            JOIN students s ON mr.student_id = s.student_id
            JOIN users u ON a.user_id = u.user_id
            WHERE mr.id = %s AND a.user_id = %s
        """, (request_id, session['user_id']))
        request_row = cursor.fetchone()
        
        if not request_row:
            flash('Request not found or access denied.', 'danger')
            return redirect(url_for('alumni.dashboard'))
            
        cursor.execute("UPDATE mentorship_requests SET status = %s WHERE id = %s", (db_status, request_id))
        
        student_user_id = request_row['student_user_id']
        alumni_name = request_row['alumni_name']
        notice_message = f"Your mentorship request to {alumni_name} has been {db_status}."
        
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, is_read)
            VALUES (%s, 'Mentorship Update', %s, 0)
        """, (student_user_id, notice_message))
        
        conn.commit()
        flash(f"Mentorship request {db_status} successfully!", 'success')
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Error responding: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return redirect(url_for('alumni.dashboard'))


@alumni_bp.route('/mentorship', methods=['GET'])
@alumni_required
def mentorship_page():
    """
    Dedicated mentorship requests management page for alumni.
    Shows all incoming requests with accept/reject actions.
    """
    user_id = session['user_id']
    requests_list = []
    profile = None
    stats = {'total': 0, 'pending': 0, 'accepted': 0, 'rejected': 0}

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get alumni profile
        cursor.execute("""
            SELECT u.full_name, u.email, u.profile_photo, a.alumni_id,
                   a.company, a.designation, a.verification_status
            FROM users u
            JOIN alumni a ON u.user_id = a.user_id
            WHERE u.user_id = %s
        """, (user_id,))
        profile = cursor.fetchone()

        if profile and profile['alumni_id']:
            alumni_id = profile['alumni_id']

            cursor.execute("""
                SELECT mr.id AS request_id, mr.message, mr.status, mr.request_date, mr.created_at,
                       u.full_name AS student_name, u.email AS student_email, u.profile_photo AS student_photo,
                       s.department, s.graduation_year, s.skills, s.register_number
                FROM mentorship_requests mr
                JOIN students s ON mr.student_id = s.student_id
                JOIN users u ON s.user_id = u.user_id
                WHERE mr.alumni_id = %s
                ORDER BY mr.created_at DESC
            """, (alumni_id,))
            requests_list = cursor.fetchall()

            # Stats
            for r in requests_list:
                stats['total'] += 1
                st = r.get('status', 'pending')
                if st == 'pending':
                    stats['pending'] += 1
                elif st in ('accepted', 'approved'):
                    stats['accepted'] += 1
                elif st == 'rejected':
                    stats['rejected'] += 1

    except Exception as e:
        flash(f"Error loading mentorship page: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('alumni_mentorship.html', profile=profile,
                           requests=requests_list, stats=stats)



# --------------------------------------------------
# Alumni Job Portal — Full CRUD
# --------------------------------------------------

def _get_alumni_id(user_id, cursor):
    """Helper: returns alumni_id for user_id, or None."""
    cursor.execute("SELECT alumni_id, verified FROM alumni WHERE user_id = %s", (user_id,))
    return cursor.fetchone()


@alumni_bp.route('/jobs', methods=['GET'])
@alumni_required
def manage_jobs():
    """
    Alumni job management dashboard — list all own posts with applicant counts.
    """
    user_id = session['user_id']
    jobs = []
    alumni_data = None
    total_applicants = 0

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.dashboard'))

        cursor.execute("""
            SELECT jp.*,
                   (SELECT COUNT(*) FROM job_applications ja WHERE ja.job_id = jp.job_id) AS applicant_count
            FROM job_posts jp
            WHERE jp.alumni_id = %s
            ORDER BY jp.created_at DESC
        """, (alumni_data['alumni_id'],))
        jobs = cursor.fetchall()

        total_applicants = sum(j['applicant_count'] for j in jobs)

    except Exception as e:
        flash(f"Error loading jobs: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    active_count = sum(1 for j in jobs if j.get('status') == 'Active')

    return render_template(
        'alumni_jobs.html',
        jobs=jobs,
        alumni_data=alumni_data,
        active_count=active_count,
        total_applicants=total_applicants,
        max_posts=10
    )


@alumni_bp.route('/jobs/create', methods=['GET'])
@alumni_required
def create_job_form():
    """
    Renders the create job form (GET).
    Only verified alumni allowed, max 10 active posts.
    """
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.dashboard'))

        if not alumni_data.get('verified'):
            flash('Only verified alumni can create job posts. Please wait for admin verification.', 'warning')
            return redirect(url_for('alumni.manage_jobs'))

        # Count active posts
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM job_posts WHERE alumni_id = %s AND status = 'Active'",
            (alumni_data['alumni_id'],)
        )
        active_cnt = cursor.fetchone()['cnt']
        if active_cnt >= 10:
            flash('You have reached the maximum limit of 10 active job posts.', 'warning')
            return redirect(url_for('alumni.manage_jobs'))

        # Pre-fill company from alumni profile
        cursor.execute("SELECT company FROM alumni WHERE alumni_id = %s", (alumni_data['alumni_id'],))
        profile_row = cursor.fetchone()
        prefill_company = profile_row['company'] if profile_row else ''

    except Exception as e:
        flash(f"Error: {e}", 'danger')
        return redirect(url_for('alumni.manage_jobs'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('create_job.html', prefill_company=prefill_company)


@alumni_bp.route('/jobs/create', methods=['POST'])
@alumni_required
def create_job():
    """
    Handles job post creation.
    """
    title           = request.form.get('title', '').strip()
    company         = request.form.get('company', '').strip()
    job_type        = request.form.get('job_type', 'Full-Time').strip()
    work_mode       = request.form.get('work_mode', 'On-site').strip()
    location        = request.form.get('location', '').strip()
    stipend_salary  = request.form.get('stipend_salary', '').strip()
    required_skills = request.form.get('required_skills', '').strip()
    eligibility     = request.form.get('eligibility', '').strip()
    description     = request.form.get('description', '').strip()
    application_link = request.form.get('application_link', '').strip()
    deadline        = request.form.get('deadline') or None

    if not title or not company or not description:
        flash('Title, Company, and Description are required.', 'danger')
        return redirect(url_for('alumni.create_job_form'))

    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.dashboard'))

        if not alumni_data.get('verified'):
            flash('Only verified alumni can post jobs.', 'warning')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM job_posts WHERE alumni_id = %s AND status = 'Active'",
            (alumni_data['alumni_id'],)
        )
        if cursor.fetchone()['cnt'] >= 10:
            flash('Maximum active post limit (10) reached.', 'warning')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("""
            INSERT INTO job_posts
                (alumni_id, title, company, job_type, work_mode, location,
                 stipend_salary, required_skills, eligibility, description,
                 application_link, deadline, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Active')
        """, (alumni_data['alumni_id'], title, company, job_type, work_mode, location,
               stipend_salary, required_skills, eligibility, description,
               application_link or None, deadline))
        conn.commit()
        flash(f"Job post '{title}' published successfully!", 'success')

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Failed to create post: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('alumni.manage_jobs'))


@alumni_bp.route('/jobs/edit/<int:job_id>', methods=['GET'])
@alumni_required
def edit_job_form(job_id):
    """
    Renders the edit form for an existing job post.
    Validates ownership before rendering.
    """
    user_id = session['user_id']
    job = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("""
            SELECT * FROM job_posts WHERE job_id = %s AND alumni_id = %s
        """, (job_id, alumni_data['alumni_id']))
        job = cursor.fetchone()

        if not job:
            flash('Job post not found or access denied.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

    except Exception as e:
        flash(f"Error: {e}", 'danger')
        return redirect(url_for('alumni.manage_jobs'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('edit_job.html', job=job)


@alumni_bp.route('/jobs/edit/<int:job_id>', methods=['POST'])
@alumni_required
def edit_job(job_id):
    """
    Handles saving edits to a job post.
    Validates ownership before updating.
    """
    title           = request.form.get('title', '').strip()
    company         = request.form.get('company', '').strip()
    job_type        = request.form.get('job_type', 'Full-Time').strip()
    work_mode       = request.form.get('work_mode', 'On-site').strip()
    location        = request.form.get('location', '').strip()
    stipend_salary  = request.form.get('stipend_salary', '').strip()
    required_skills = request.form.get('required_skills', '').strip()
    eligibility     = request.form.get('eligibility', '').strip()
    description     = request.form.get('description', '').strip()
    application_link = request.form.get('application_link', '').strip()
    deadline        = request.form.get('deadline') or None

    if not title or not company or not description:
        flash('Title, Company, and Description are required.', 'danger')
        return redirect(url_for('alumni.edit_job_form', job_id=job_id))

    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        # Ownership check
        cursor.execute(
            "SELECT job_id FROM job_posts WHERE job_id = %s AND alumni_id = %s",
            (job_id, alumni_data['alumni_id'])
        )
        if not cursor.fetchone():
            flash('Access denied — you do not own this post.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("""
            UPDATE job_posts
            SET title = %s, company = %s, job_type = %s, work_mode = %s, location = %s,
                stipend_salary = %s, required_skills = %s, eligibility = %s,
                description = %s, application_link = %s, deadline = %s
            WHERE job_id = %s
        """, (title, company, job_type, work_mode, location,
               stipend_salary, required_skills, eligibility,
               description, application_link or None, deadline, job_id))
        conn.commit()
        flash('Job post updated successfully!', 'success')

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Update failed: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('alumni.manage_jobs'))


@alumni_bp.route('/jobs/delete/<int:job_id>', methods=['POST'])
@alumni_required
def delete_job(job_id):
    """
    Permanently deletes a job post. Ownership validated.
    """
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute(
            "SELECT job_id FROM job_posts WHERE job_id = %s AND alumni_id = %s",
            (job_id, alumni_data['alumni_id'])
        )
        if not cursor.fetchone():
            flash('Access denied — you do not own this post.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("DELETE FROM job_posts WHERE job_id = %s", (job_id,))
        conn.commit()
        flash('Job post deleted successfully.', 'success')

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Delete failed: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('alumni.manage_jobs'))


@alumni_bp.route('/jobs/close/<int:job_id>', methods=['POST'])
@alumni_required
def close_job(job_id):
    """
    Marks a job post as Closed. Ownership validated.
    """
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute(
            "SELECT job_id FROM job_posts WHERE job_id = %s AND alumni_id = %s",
            (job_id, alumni_data['alumni_id'])
        )
        if not cursor.fetchone():
            flash('Access denied — you do not own this post.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("UPDATE job_posts SET status = 'Closed' WHERE job_id = %s", (job_id,))
        conn.commit()
        flash('Job post closed. Students can no longer apply.', 'info')

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error closing post: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('alumni.manage_jobs'))


@alumni_bp.route('/jobs/applicants/<int:job_id>', methods=['GET'])
@alumni_required
def view_applicants(job_id):
    """
    Shows the list of students who applied for a specific job.
    Validates ownership before displaying.
    """
    user_id = session['user_id']
    job = None
    applicants = []
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        alumni_data = _get_alumni_id(user_id, cursor)
        if not alumni_data:
            flash('Alumni profile not found.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("""
            SELECT * FROM job_posts WHERE job_id = %s AND alumni_id = %s
        """, (job_id, alumni_data['alumni_id']))
        job = cursor.fetchone()

        if not job:
            flash('Job post not found or access denied.', 'danger')
            return redirect(url_for('alumni.manage_jobs'))

        cursor.execute("""
            SELECT ja.applied_at, u.full_name, u.email, u.profile_photo,
                   s.department, s.graduation_year, s.register_number, s.skills, s.resume
            FROM job_applications ja
            JOIN students s ON ja.student_id = s.student_id
            JOIN users u ON s.user_id = u.user_id
            WHERE ja.job_id = %s
            ORDER BY ja.applied_at DESC
        """, (job_id,))
        applicants = cursor.fetchall()

    except Exception as e:
        flash(f"Error fetching applicants: {e}", 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('alumni_applicants.html', job=job, applicants=applicants)

# --------------------------------------------------
# 17. Private Chat with Accepted Student
# --------------------------------------------------
@alumni_bp.route('/chat/<int:mentorship_id>', methods=['GET'])
@alumni_required
def alumni_chat(mentorship_id):

    user_id = session['user_id']

    conn = get_db_connection()

    if not conn:
        flash('Database unavailable.', 'danger')
        return redirect(url_for('alumni.dashboard'))

    cursor = conn.cursor(dictionary=True)

    try:

        # ------------------------------------------
        # Verify alumni owns this accepted
        # mentorship connection
        # ------------------------------------------
        cursor.execute("""
            SELECT
                mr.id AS mentorship_id,
                mr.status,
                a.alumni_id,
                a.user_id AS alumni_user_id,
                s.student_id,
                s.user_id AS student_user_id,
                u.full_name AS student_name,
                u.email AS student_email,
                u.profile_photo AS student_photo,
                s.department,
                s.graduation_year,
                s.skills
            FROM mentorship_requests mr
            JOIN alumni a
                ON mr.alumni_id = a.alumni_id
            JOIN students s
                ON mr.student_id = s.student_id
            JOIN users u
                ON s.user_id = u.user_id
            WHERE mr.id = %s
            AND a.user_id = %s
            AND mr.status IN ('accepted', 'approved')
        """, (
            mentorship_id,
            user_id
        ))

        connection = cursor.fetchone()

        if not connection:

            flash(
                'Chat is available only for accepted mentorship connections.',
                'warning'
            )

            return redirect(
                url_for('alumni.mentorship_page')
            )

        # ------------------------------------------
        # Mark student messages as read
        # ------------------------------------------
        cursor.execute("""
            UPDATE chat_messages
            SET is_read = TRUE
            WHERE mentorship_id = %s
            AND receiver_user_id = %s
        """, (
            mentorship_id,
            user_id
        ))

        # ------------------------------------------
        # Fetch messages
        # ------------------------------------------
        cursor.execute("""
            SELECT
                cm.message_id,
                cm.sender_user_id,
                cm.receiver_user_id,
                cm.message,
                cm.is_read,
                cm.created_at,
                u.full_name AS sender_name
            FROM chat_messages cm
            JOIN users u
                ON cm.sender_user_id = u.user_id
            WHERE cm.mentorship_id = %s
            ORDER BY cm.created_at ASC, cm.message_id ASC
        """, (mentorship_id,))

        messages = cursor.fetchall()

        conn.commit()

        return render_template(
            'chat.html',
            connection=connection,
            messages=messages,
            current_user_id=user_id,
            user_role='alumni'
        )

    except Exception as e:

        conn.rollback()

        print(f"Alumni chat error: {e}")

        flash(
            'Unable to load chat.',
            'danger'
        )

        return redirect(
            url_for('alumni.mentorship_page')
        )

    finally:

        cursor.close()
        conn.close()


# --------------------------------------------------
# 18. Send Private Chat Message - Alumni
# --------------------------------------------------
@alumni_bp.route('/chat/<int:mentorship_id>/send', methods=['POST'])
@alumni_required
def alumni_send_chat_message(mentorship_id):

    user_id = session['user_id']

    message = request.form.get(
        'message',
        ''
    ).strip()

    if not message:

        flash(
            'Message cannot be empty.',
            'warning'
        )

        return redirect(
            url_for(
                'alumni.alumni_chat',
                mentorship_id=mentorship_id
            )
        )

    conn = get_db_connection()

    if not conn:

        flash(
            'Database unavailable.',
            'danger'
        )

        return redirect(
            url_for('alumni.mentorship_page')
        )

    cursor = conn.cursor(dictionary=True)

    try:

        # ------------------------------------------
        # Verify accepted mentorship belongs to
        # logged-in alumni
        # ------------------------------------------
        cursor.execute("""
            SELECT
                mr.id,
                s.user_id AS student_user_id
            FROM mentorship_requests mr
            JOIN alumni a
                ON mr.alumni_id = a.alumni_id
            JOIN students s
                ON mr.student_id = s.student_id
            WHERE mr.id = %s
            AND a.user_id = %s
            AND mr.status IN ('accepted', 'approved')
        """, (
            mentorship_id,
            user_id
        ))

        connection = cursor.fetchone()

        if not connection:

            flash(
                'You do not have permission to use this chat.',
                'danger'
            )

            return redirect(
                url_for('alumni.mentorship_page')
            )

        # ------------------------------------------
        # Insert message
        # ------------------------------------------
        cursor.execute("""
            INSERT INTO chat_messages
            (
                mentorship_id,
                sender_user_id,
                receiver_user_id,
                message
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
        """, (
            mentorship_id,
            user_id,
            connection['student_user_id'],
            message
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        print(f"Alumni send message error: {e}")

        flash(
            'Unable to send message.',
            'danger'
        )

    finally:

        cursor.close()
        conn.close()

    return redirect(
        url_for(
            'alumni.alumni_chat',
            mentorship_id=mentorship_id
        )
    )