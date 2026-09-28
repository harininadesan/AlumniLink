import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import current_user
from functools import wraps
from werkzeug.utils import secure_filename
from models.database import get_db_connection
from datetime import datetime
from profile_photos import remove_profile_photo, save_profile_photo
from student_conversions import (
    get_conversion_settings,
    is_conversion_eligible,
    valid_passing_out_year,
)

student_bp = Blueprint('student', __name__, url_prefix='/student')

UPLOAD_FOLDER_RESUMES = os.path.join('static', 'uploads', 'resumes')

os.makedirs(UPLOAD_FOLDER_RESUMES, exist_ok=True)

ALLOWED_RESUME_EXTENSIONS = {'pdf', 'doc', 'docx'}


def allowed_file(filename, allowed_extensions):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in allowed_extensions
    )


def student_required(f):
    """
    Restrict access to logged-in student users.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = str(session.get('role', '')).strip().lower()
        if current_user.is_authenticated:
            role = str(current_user.role).strip().lower()
            session['role'] = current_user.role

        if 'user_id' not in session or role != 'student':
            flash('Please log in as a Student to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


# --------------------------------------------------
# Helper: Fetch Student Profile
# --------------------------------------------------
def fetch_student_profile(user_id):
    """
    Fetch or create the student profile belonging to the logged-in user.
    """

    conn = get_db_connection()

    if conn is None:
        return {
            'full_name': session.get('full_name', 'Student User'),
            'email': '',
            'department': 'Information Technology',
            'admission_year': None,
            'graduation_year': 2026,
            'register_number': f"IT{user_id:04d}",
            'skills': '',
            'resume': None,
            'career_goal': '',
            'linkedin': '',
            'github': '',
            'bio': '',
            'profile_photo': None
        }

    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                u.full_name,
                u.email,
                u.profile_photo,
                s.student_id,
                s.department,
                s.admission_year,
                s.graduation_year,
                s.graduation_verified,
                cr.status AS conversion_status,
                s.register_number,
                s.skills,
                s.resume,
                s.career_goal,
                s.bio,
                s.linkedin,
                s.github
            FROM users u
            LEFT JOIN students s
                ON u.user_id = s.user_id
            LEFT JOIN student_conversion_requests cr
                ON cr.user_id = u.user_id
            WHERE u.user_id = %s
        """, (user_id,))

        profile = cursor.fetchone()

        if profile and profile.get('student_id') is None:

            reg_num = f"IT{user_id:04d}"

            cursor.execute("""
                INSERT INTO students
                (
                    user_id,
                    department,
                    admission_year,
                    graduation_year,
                    register_number,
                    skills,
                    resume,
                    career_goal
                )
                VALUES
                (
                    %s,
                    'Information Technology',
                    NULL,
                    2026,
                    %s,
                    '',
                    '',
                    ''
                )
            """, (user_id, reg_num))

            conn.commit()

            cursor.execute("""
                SELECT
                    u.full_name,
                    u.email,
                    u.profile_photo,
                    s.student_id,
                    s.department,
                    s.admission_year,
                    s.graduation_year,
                    s.graduation_verified,
                    cr.status AS conversion_status,
                    s.register_number,
                    s.skills,
                    s.resume,
                    s.career_goal,
                    s.bio,
                    s.linkedin,
                    s.github
                FROM users u
                JOIN students s
                    ON u.user_id = s.user_id
                LEFT JOIN student_conversion_requests cr
                    ON cr.user_id = u.user_id
                WHERE u.user_id = %s
            """, (user_id,))

            profile = cursor.fetchone()

        if profile:
            profile['linkedin'] = profile.get('linkedin') or ''
            profile['github'] = profile.get('github') or ''
            profile['bio'] = profile.get('bio') or ''
            profile['skills'] = profile.get('skills') or ''
            profile['career_goal'] = profile.get('career_goal') or ''
            if not profile.get('conversion_status'):
                settings = get_conversion_settings(cursor)
                if not is_conversion_eligible(profile.get('graduation_year')):
                    profile['conversion_status'] = 'not_eligible'
                elif (
                    settings['require_graduation_verification']
                    and not profile.get('graduation_verified')
                ):
                    profile['conversion_status'] = 'awaiting_verification'
                else:
                    profile['conversion_status'] = 'eligible'

        return profile

    except Exception as e:
        print(f"Error fetching student profile: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


# --------------------------------------------------
# Helper: Build Recent Activities
# --------------------------------------------------
def build_recent_activities(notifications):
    """
    Convert real database notifications into dashboard activity items.
    No fake activity data is generated.
    """

    activities = []

    for notification in notifications:

        title = notification.get('title') or 'Notification'
        message = notification.get('message') or ''
        created_at = notification.get('created_at')

        title_lower = title.lower()

        if 'mentorship' in title_lower:

            if 'accepted' in title_lower:
                icon = 'fa-circle-check'
                badge_class = 'bg-success'
                activity_type = 'request_accepted'

            elif 'request' in title_lower:
                icon = 'fa-paper-plane'
                badge_class = 'bg-primary'
                activity_type = 'request_sent'

            else:
                icon = 'fa-user-group'
                badge_class = 'bg-info'
                activity_type = 'mentorship'

        elif 'job' in title_lower:

            icon = 'fa-briefcase'
            badge_class = 'bg-info'
            activity_type = 'job_posted'

        elif 'profile' in title_lower:

            icon = 'fa-user-pen'
            badge_class = 'bg-warning'
            activity_type = 'profile_updated'

        else:

            icon = 'fa-bell'
            badge_class = 'bg-secondary'
            activity_type = 'notification'

        if created_at:

            if isinstance(created_at, datetime):
                activity_time = created_at.strftime(
                    '%d %b %Y, %I:%M %p'
                )
            else:
                activity_time = str(created_at)

        else:
            activity_time = ''

        activities.append({
            'type': activity_type,
            'title': title,
            'description': message,
            'time': activity_time,
            'icon': icon,
            'badge_class': badge_class
        })

    return activities


# --------------------------------------------------
# 1. Student Dashboard
# --------------------------------------------------
@student_bp.route('/dashboard', methods=['GET'])
@student_required
def dashboard():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    verified_alumni_count = 0
    mentorship_requests_count = 0
    job_opportunities_count = 0
    unread_notifications_count = 0

    alumni_list = []
    jobs = []
    requests_list = []
    notifications_list = []
    recent_activities = []

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            # ------------------------------------------
            # 1. Approved Alumni Count
            # ------------------------------------------
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM alumni
                WHERE verification_status = 'approved'
            """)

            res = cursor.fetchone()
            verified_alumni_count = res['total'] if res else 0

            # ------------------------------------------
            # 2. Student Mentorship Requests
            # ------------------------------------------
            if profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM mentorship_requests
                    WHERE student_id = %s
                """, (profile['student_id'],))

                res = cursor.fetchone()
                mentorship_requests_count = res['total'] if res else 0

            # ------------------------------------------
            # 3. Active Job Opportunities
            # ------------------------------------------
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM job_posts jp
                JOIN alumni a
                    ON jp.alumni_id = a.alumni_id
                WHERE jp.status = 'Active'
                AND a.verification_status = 'approved'
            """)

            res = cursor.fetchone()
            job_opportunities_count = res['total'] if res else 0

            # ------------------------------------------
            # 4. Unread Notifications
            # ------------------------------------------
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()
            unread_notifications_count = res['total'] if res else 0

            # ------------------------------------------
            # 5. Approved Alumni Sample
            # ------------------------------------------
            cursor.execute("""
                SELECT
                    a.alumni_id,
                    u.full_name,
                    u.email,
                    a.company,
                    a.designation,
                    a.location,
                    a.mentor_status,
                    a.graduation_year,
                    a.skills,
                    a.bio,
                    u.profile_photo
                FROM alumni a
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE a.verification_status = 'approved'
                ORDER BY a.alumni_id DESC
                LIMIT 4
            """)

            alumni_list = cursor.fetchall()

            # ------------------------------------------
            # 6. Recent Active Jobs
            # ------------------------------------------
            cursor.execute("""
                SELECT
                    jp.*,
                    u.full_name AS alumni_name
                FROM job_posts jp
                JOIN alumni a
                    ON jp.alumni_id = a.alumni_id
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE jp.status = 'Active'
                AND a.verification_status = 'approved'
                ORDER BY jp.created_at DESC
                LIMIT 3
            """)

            jobs = cursor.fetchall()

            # ------------------------------------------
            # 7. Recent Mentorship Requests
            # ------------------------------------------
            if profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT
                        mr.id AS request_id,
                        mr.message,
                        mr.status,
                        mr.created_at AS request_date,
                        u.full_name AS alumni_name,
                        a.company,
                        a.designation
                    FROM mentorship_requests mr
                    JOIN alumni a
                        ON mr.alumni_id = a.alumni_id
                    JOIN users u
                        ON a.user_id = u.user_id
                    WHERE mr.student_id = %s
                    ORDER BY mr.created_at DESC
                    LIMIT 3
                """, (profile['student_id'],))

                requests_list = cursor.fetchall()

            # ------------------------------------------
            # 8. Recent Notifications
            # ------------------------------------------
            cursor.execute("""
                SELECT *
                FROM notifications
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 5
            """, (user_id,))

            notifications_list = cursor.fetchall()

            # ------------------------------------------
            # 9. Build Real Activities
            # ------------------------------------------
            recent_activities = build_recent_activities(
                notifications_list
            )

        except Exception as e:

            print(f"Error querying dashboard metrics: {e}")

        finally:

            cursor.close()
            conn.close()

    # ------------------------------------------
    # AI Recommendations
    # ------------------------------------------
    ai_recommended_alumni = []
    suggested_skills = []

    if profile and profile.get('student_id'):

        try:

            from ai.skill_recommendation import (
                recommend_alumni_for_student,
                recommend_skills_for_student
            )

            ai_recommended_alumni = recommend_alumni_for_student(
                profile['student_id'],
                limit=4
            )

            suggested_skills = recommend_skills_for_student(
                profile.get('skills', '')
            )

        except Exception as e:

            print(f"AI recommendation error: {e}")

    if not alumni_list and ai_recommended_alumni:
        alumni_list = ai_recommended_alumni

    return render_template(
        'student_dashboard.html',
        profile=profile,
        verified_alumni_count=verified_alumni_count,
        mentorship_requests_count=mentorship_requests_count,
        job_opportunities_count=job_opportunities_count,
        unread_notifications_count=unread_notifications_count,
        recent_activities=recent_activities,
        alumni_list=alumni_list,
        ai_recommended_alumni=ai_recommended_alumni,
        suggested_skills=suggested_skills,
        jobs=jobs,
        requests=requests_list,
        notifications=notifications_list,
        active_page='dashboard'
    )


# --------------------------------------------------
# 2. Search Alumni
# --------------------------------------------------
@student_bp.route('/search', methods=['GET'])
@student_required
def search_alumni():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    search_query = request.args.get('query', '').strip()
    search_type = request.args.get('type', 'all').strip().lower()

    filter_batch = request.args.get('filter_batch', '').strip()
    filter_company = request.args.get('filter_company', '').strip()
    filter_skills = request.args.get('filter_skills', '').strip()
    filter_location = request.args.get('filter_location', '').strip()

    alumni_list = []
    unread_notifications_count = 0
    requested_alumni_ids = {}

    filter_batches = []
    filter_companies = []
    filter_locations = []
    filter_skills_list = []

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            # ------------------------------------------
            # Filter: Graduation Years
            # ------------------------------------------
            cursor.execute("""
                SELECT DISTINCT graduation_year
                FROM alumni
                WHERE verification_status = 'approved'
                AND graduation_year IS NOT NULL
                ORDER BY graduation_year DESC
            """)

            filter_batches = [
                r['graduation_year']
                for r in cursor.fetchall()
            ]

            # ------------------------------------------
            # Filter: Companies
            # ------------------------------------------
            cursor.execute("""
                SELECT DISTINCT company
                FROM alumni
                WHERE verification_status = 'approved'
                AND company IS NOT NULL
                AND company != ''
                ORDER BY company ASC
            """)

            filter_companies = [
                r['company']
                for r in cursor.fetchall()
            ]

            # ------------------------------------------
            # Filter: Locations
            # ------------------------------------------
            cursor.execute("""
                SELECT DISTINCT location
                FROM alumni
                WHERE verification_status = 'approved'
                AND location IS NOT NULL
                AND location != ''
                ORDER BY location ASC
            """)

            filter_locations = [
                r['location']
                for r in cursor.fetchall()
            ]

            # ------------------------------------------
            # Filter: Skills
            # ------------------------------------------
            cursor.execute("""
                SELECT skills
                FROM alumni
                WHERE verification_status = 'approved'
                AND skills IS NOT NULL
                AND skills != ''
            """)

            all_skills = set()

            for row in cursor.fetchall():

                for skill in row['skills'].split(','):
                    skill = skill.strip()

                    if skill:
                        all_skills.add(skill)

            filter_skills_list = sorted(all_skills)

            # ------------------------------------------
            # Main Search Query
            # ------------------------------------------
            query = """
                SELECT
                    a.alumni_id,
                    u.full_name,
                    u.email,
                    u.profile_photo,
                    a.company,
                    a.designation,
                    a.experience,
                    a.skills,
                    a.location,
                    a.mentor_status,
                    a.verified,
                    a.graduation_year,
                    a.bio
                FROM alumni a
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE a.verification_status = 'approved'
            """

            params = []

            if search_query:

                if search_type == 'name':

                    query += """
                        AND u.full_name LIKE %s
                    """

                    params.append(
                        f"%{search_query}%"
                    )

                elif search_type == 'company':

                    query += """
                        AND a.company LIKE %s
                    """

                    params.append(
                        f"%{search_query}%"
                    )

                elif search_type == 'skills':

                    query += """
                        AND a.skills LIKE %s
                    """

                    params.append(
                        f"%{search_query}%"
                    )

                elif search_type == 'batch':

                    query += """
                        AND CAST(a.graduation_year AS CHAR) LIKE %s
                    """

                    params.append(
                        f"%{search_query}%"
                    )

                else:

                    query += """
                        AND (
                            u.full_name LIKE %s
                            OR a.company LIKE %s
                            OR a.skills LIKE %s
                            OR CAST(a.graduation_year AS CHAR) LIKE %s
                        )
                    """

                    params.extend([
                        f"%{search_query}%",
                        f"%{search_query}%",
                        f"%{search_query}%",
                        f"%{search_query}%"
                    ])

            if filter_batch:

                query += """
                    AND a.graduation_year = %s
                """

                params.append(filter_batch)

            if filter_company:

                query += """
                    AND a.company = %s
                """

                params.append(filter_company)

            if filter_skills:

                query += """
                    AND a.skills LIKE %s
                """

                params.append(
                    f"%{filter_skills}%"
                )

            if filter_location:

                query += """
                    AND a.location = %s
                """

                params.append(filter_location)

            query += """
                ORDER BY a.alumni_id DESC
            """

            cursor.execute(query, params)

            alumni_list = cursor.fetchall()

            # ------------------------------------------
            # AI Match Score
            # ------------------------------------------
            try:

                from ai.skill_recommendation import (
                    tokenize_skills,
                    calculate_jaccard_similarity
                )

                student_skills = tokenize_skills(
                    profile.get('skills', '')
                    if profile else ''
                )

                for alumni in alumni_list:

                    alumni_skills = tokenize_skills(
                        alumni.get('skills', '')
                    )

                    similarity = calculate_jaccard_similarity(
                        student_skills,
                        alumni_skills
                    )

                    if similarity > 0:
                        match_score = min(
                            98,
                            max(68, int(similarity * 100))
                        )
                    else:
                        match_score = 0

                    alumni['ai_match_score'] = match_score

            except Exception as e:

                print(f"AI match score error: {e}")

            # ------------------------------------------
            # Existing Mentorship Requests
            # ------------------------------------------
            if profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT alumni_id, status
                    FROM mentorship_requests
                    WHERE student_id = %s
                """, (profile['student_id'],))

                requested_alumni_ids = {
                    row['alumni_id']: row['status']
                    for row in cursor.fetchall()
                }

            # ------------------------------------------
            # Notification Count
            # ------------------------------------------
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        except Exception as e:

            print(f"Error searching alumni: {e}")

        finally:

            cursor.close()
            conn.close()

    # Add empty bio only for display if database value is NULL
    for alumni in alumni_list:

        if not alumni.get('bio'):

            alumni['bio'] = (
                f"Alumni member from the IT Class of "
                f"{alumni.get('graduation_year') or 'N/A'}."
            )

    return render_template(
        'search_alumni.html',
        profile=profile,
        alumni_list=alumni_list,
        search_query=search_query,
        search_type=search_type,
        filter_batch=filter_batch,
        filter_company=filter_company,
        filter_skills=filter_skills,
        filter_location=filter_location,
        filter_batches=filter_batches,
        filter_companies=filter_companies,
        filter_locations=filter_locations,
        filter_skills_list=filter_skills_list,
        requested_alumni_ids=requested_alumni_ids,
        unread_notifications_count=unread_notifications_count,
        active_page='search'
    )


# --------------------------------------------------
# 3. View Alumni Profile
# --------------------------------------------------
@student_bp.route('/alumni/<int:alumni_id>', methods=['GET'])
@student_required
def view_alumni_profile(alumni_id):

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    alumnus = None
    unread_notifications_count = 0
    request_status = None

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT
                    a.alumni_id,
                    u.full_name,
                    u.email,
                    u.profile_photo,
                    a.company,
                    a.designation,
                    a.experience,
                    a.skills,
                    a.linkedin,
                    a.location,
                    a.mentor_status,
                    a.github,
                    a.phone,
                    a.bio,
                    a.achievements,
                    a.share_email,
                    a.share_phone,
                    a.graduation_year
                FROM alumni a
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE a.alumni_id = %s
                AND a.verification_status = 'approved'
            """, (alumni_id,))

            alumnus = cursor.fetchone()

            if alumnus and profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT status
                    FROM mentorship_requests
                    WHERE student_id = %s
                    AND alumni_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (
                    profile['student_id'],
                    alumni_id
                ))

                status_row = cursor.fetchone()

                if status_row:
                    request_status = status_row['status']

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        except Exception as e:

            print(f"Error fetching alumni profile: {e}")

        finally:

            cursor.close()
            conn.close()

    if not alumnus:

        flash(
            'Alumni profile not found or not approved.',
            'danger'
        )

        return redirect(
            url_for('student.search_alumni')
        )

    return render_template(
        'alumni_profile.html',
        profile=profile,
        alumnus=alumnus,
        is_student_view=True,
        request_status=request_status,
        unread_notifications_count=unread_notifications_count,
        active_page='search'
    )


# --------------------------------------------------
# 4. Mentorship Requests
# --------------------------------------------------
@student_bp.route('/requests', methods=['GET'])
@student_required
def view_requests():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    requests_list = []
    unread_notifications_count = 0

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            if profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT
                        mr.id AS request_id,
                        mr.message,
                        mr.status,
                        mr.created_at AS request_date,
                        u.full_name AS alumni_name,
                        u.email AS alumni_email,
                        u.profile_photo AS alumni_photo,
                        a.company,
                        a.designation
                    FROM mentorship_requests mr
                    JOIN alumni a
                        ON mr.alumni_id = a.alumni_id
                    JOIN users u
                        ON a.user_id = u.user_id
                    WHERE mr.student_id = %s
                    ORDER BY mr.created_at DESC
                """, (profile['student_id'],))

                requests_list = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        except Exception as e:

            print(f"Error fetching requests: {e}")

        finally:

            cursor.close()
            conn.close()

    return render_template(
        'student_requests.html',
        profile=profile,
        requests=requests_list,
        unread_notifications_count=unread_notifications_count,
        active_page='requests'
    )


# --------------------------------------------------
# 5. Job Opportunities
# --------------------------------------------------
@student_bp.route('/jobs', methods=['GET'])
@student_required
def view_jobs():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    jobs_list = []
    unread_notifications_count = 0
    applied_job_ids = set()

    search_query = request.args.get('q', '').strip()
    filter_type = request.args.get(
        'job_type',
        ''
    ).strip()

    filter_mode = request.args.get(
        'work_mode',
        ''
    ).strip()

    sort_by = request.args.get(
        'sort',
        'latest'
    ).strip()

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            query = """
                SELECT
                    jp.*,
                    u.full_name AS alumni_name,
                    u.email AS alumni_email,
                    a.company AS alumni_company,
                    a.designation AS alumni_designation,
                    a.verified AS alumni_verified
                FROM job_posts jp
                JOIN alumni a
                    ON jp.alumni_id = a.alumni_id
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE jp.status = 'Active'
                AND a.verification_status = 'approved'
            """

            params = []

            if search_query:

                query += """
                    AND (
                        jp.title LIKE %s
                        OR jp.company LIKE %s
                        OR jp.required_skills LIKE %s
                        OR jp.location LIKE %s
                    )
                """

                sq = f"%{search_query}%"

                params.extend([
                    sq,
                    sq,
                    sq,
                    sq
                ])

            if filter_type:

                query += """
                    AND jp.job_type = %s
                """

                params.append(filter_type)

            if filter_mode:

                query += """
                    AND jp.work_mode = %s
                """

                params.append(filter_mode)

            if sort_by == 'deadline':

                query += """
                    ORDER BY jp.deadline ASC
                """

            elif sort_by == 'company':

                query += """
                    ORDER BY jp.company ASC
                """

            else:

                query += """
                    ORDER BY jp.created_at DESC
                """

            cursor.execute(
                query,
                params
            )

            jobs_list = cursor.fetchall()

            # ------------------------------------------
            # Applied Jobs
            # ------------------------------------------
            if profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT job_id
                    FROM job_applications
                    WHERE student_id = %s
                """, (profile['student_id'],))

                applied_job_ids = {
                    row['job_id']
                    for row in cursor.fetchall()
                }

            # ------------------------------------------
            # Notification Count
            # ------------------------------------------
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        except Exception as e:

            print(f"Error fetching jobs: {e}")

        finally:

            cursor.close()
            conn.close()

    return render_template(
        'student_jobs.html',
        profile=profile,
        jobs=jobs_list,
        applied_job_ids=applied_job_ids,
        search_query=search_query,
        filter_type=filter_type,
        filter_mode=filter_mode,
        sort_by=sort_by,
        unread_notifications_count=unread_notifications_count,
        active_page='jobs'
    )


# --------------------------------------------------
# 6. Job Detail
# --------------------------------------------------
@student_bp.route('/jobs/<int:job_id>', methods=['GET'])
@student_required
def job_detail(job_id):

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    job = None
    already_applied = False
    unread_notifications_count = 0

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT
                    jp.*,
                    u.full_name AS alumni_name,
                    u.email AS alumni_email,
                    u.profile_photo AS alumni_photo,
                    a.company AS alumni_company,
                    a.designation AS alumni_designation,
                    a.alumni_id
                FROM job_posts jp
                JOIN alumni a
                    ON jp.alumni_id = a.alumni_id
                JOIN users u
                    ON a.user_id = u.user_id
                WHERE jp.job_id = %s
                AND jp.status = 'Active'
                AND a.verification_status = 'approved'
            """, (job_id,))

            job = cursor.fetchone()

            if job and profile and profile.get('student_id'):

                cursor.execute("""
                    SELECT id
                    FROM job_applications
                    WHERE job_id = %s
                    AND student_id = %s
                """, (
                    job_id,
                    profile['student_id']
                ))

                already_applied = (
                    cursor.fetchone() is not None
                )

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        except Exception as e:

            print(f"Error fetching job detail: {e}")

        finally:

            cursor.close()
            conn.close()

    if not job:

        flash(
            'Job post not found or no longer available.',
            'warning'
        )

        return redirect(
            url_for('student.view_jobs')
        )

    return render_template(
        'job_details.html',
        profile=profile,
        job=job,
        already_applied=already_applied,
        unread_notifications_count=unread_notifications_count,
        active_page='jobs'
    )


# --------------------------------------------------
# 7. Notifications
# --------------------------------------------------
@student_bp.route('/notifications', methods=['GET'])
@student_required
def view_notifications():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    notifications_list = []
    unread_notifications_count = 0

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            # Count unread before marking them read
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

            cursor.execute("""
                SELECT *
                FROM notifications
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))

            notifications_list = cursor.fetchall()

            # Mark notifications as read
            cursor.execute("""
                UPDATE notifications
                SET is_read = 1
                WHERE user_id = %s
            """, (user_id,))

            conn.commit()

        except Exception as e:

            print(f"Error fetching notifications: {e}")

        finally:

            cursor.close()
            conn.close()

    return render_template(
        'student_notifications.html',
        profile=profile,
        notifications=notifications_list,
        unread_notifications_count=0,
        active_page='notifications'
    )


# --------------------------------------------------
# 8. Student Profile
# --------------------------------------------------
@student_bp.route('/profile', methods=['GET'])
@student_required
def view_profile():

    user_id = session['user_id']
    profile = fetch_student_profile(user_id)

    unread_notifications_count = 0

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE user_id = %s
                AND is_read = 0
            """, (user_id,))

            res = cursor.fetchone()

            unread_notifications_count = (
                res['total'] if res else 0
            )

        finally:

            cursor.close()
            conn.close()

    return render_template(
        'student_profile.html',
        profile=profile,
        unread_notifications_count=unread_notifications_count,
        active_page='profile'
    )


# --------------------------------------------------
# 9. Edit Student Profile
# --------------------------------------------------
@student_bp.route('/profile/edit', methods=['POST'])
@student_required
def edit_profile():

    user_id = session['user_id']

    full_name = request.form.get(
        'full_name',
        ''
    ).strip()

    department = request.form.get(
        'department',
        ''
    ).strip()

    graduation_year = request.form.get(
        'graduation_year',
        ''
    ).strip()

    admission_year_text = request.form.get(
        'admission_year',
        ''
    ).strip()

    skills = request.form.get(
        'skills',
        ''
    ).strip()

    career_goal = request.form.get(
        'career_goal',
        ''
    ).strip()

    bio = request.form.get(
        'bio',
        ''
    ).strip()

    linkedin = request.form.get(
        'linkedin',
        ''
    ).strip()

    github = request.form.get(
        'github',
        ''
    ).strip()

    graduation_year = valid_passing_out_year(graduation_year)
    admission_year = None
    if admission_year_text:
        admission_year = valid_passing_out_year(admission_year_text)

    if not full_name or not department or graduation_year is None:

        flash(
            'Full Name, Department, and Graduation Year are required.',
            'danger'
        )

        return redirect(
            url_for('student.view_profile')
        )

    if admission_year_text and (
        admission_year is None or admission_year > graduation_year
    ):
        flash('Admission year must be valid and no later than the passing-out year.', 'danger')
        return redirect(url_for('student.view_profile'))

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor()

        try:

            cursor.execute("""
                UPDATE users
                SET full_name = %s
                WHERE user_id = %s
            """, (
                full_name,
                user_id
            ))

            cursor.execute("""
                UPDATE students
                SET
                    department = %s,
                    admission_year = %s,
                    graduation_year = %s,
                    skills = %s,
                    career_goal = %s,
                    bio = %s,
                    linkedin = %s,
                    github = %s
                WHERE user_id = %s
            """, (
                department,
                admission_year,
                graduation_year,
                skills,
                career_goal,
                bio,
                linkedin,
                github,
                user_id
            ))

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    title,
                    message,
                    is_read
                )
                VALUES
                (
                    %s,
                    'Profile Updated',
                    'You successfully updated your profile details.',
                    0
                )
            """, (user_id,))

            conn.commit()

            session['full_name'] = full_name

            flash(
                'Your profile details have been updated successfully!',
                'success'
            )

        except Exception as e:

            conn.rollback()

            flash(
                f"Error updating profile: {e}",
                'danger'
            )

        finally:

            cursor.close()
            conn.close()

    else:

        session['full_name'] = full_name

        flash(
            'Database unavailable.',
            'danger'
        )

    return redirect(
        url_for('student.view_profile')
    )


# --------------------------------------------------
# 10. Request Mentorship
# --------------------------------------------------
@student_bp.route('/request_mentorship', methods=['POST'])
@student_required
def request_mentorship():

    alumni_id = request.form.get(
        'alumni_id'
    )

    message = request.form.get(
        'message',
        ''
    ).strip()

    user_id = session['user_id']

    if not alumni_id:

        flash(
            'Target alumni mentor not specified.',
            'danger'
        )

        return redirect(
            url_for('student.search_alumni')
        )

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            # ------------------------------------------
            # Student ID
            # ------------------------------------------
            cursor.execute("""
                SELECT student_id
                FROM students
                WHERE user_id = %s
            """, (user_id,))

            student = cursor.fetchone()

            if not student:

                flash(
                    'Student profile not found.',
                    'danger'
                )

                return redirect(
                    url_for('student.search_alumni')
                )

            student_id = student['student_id']

            # ------------------------------------------
            # Verify alumni is approved and available
            # ------------------------------------------
            cursor.execute("""
                SELECT
                    user_id,
                    mentor_status
                FROM alumni
                WHERE alumni_id = %s
                AND verification_status = 'approved'
            """, (alumni_id,))

            alumni_row = cursor.fetchone()

            if not alumni_row:

                flash(
                    'This alumni is not approved or is no longer available.',
                    'warning'
                )

                return redirect(
                    url_for('student.search_alumni')
                )

            # ------------------------------------------
            # Check mentor availability
            # ------------------------------------------
            if alumni_row.get('mentor_status') in (
                0,
                '0',
                False
            ):

                flash(
                    'This alumni is currently not accepting mentorship requests.',
                    'warning'
                )

                return redirect(
                    url_for(
                        'student.view_alumni_profile',
                        alumni_id=alumni_id
                    )
                )

            # ------------------------------------------
            # Duplicate request check
            # ------------------------------------------
            cursor.execute("""
                SELECT id
                FROM mentorship_requests
                WHERE student_id = %s
                AND alumni_id = %s
                AND status IN ('pending', 'approved')
            """, (
                student_id,
                alumni_id
            ))

            if cursor.fetchone():

                flash(
                    'You already have a pending or active mentorship request to this alumni.',
                    'warning'
                )

                return redirect(
                    url_for('student.view_requests')
                )

            # ------------------------------------------
            # Insert request
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO mentorship_requests
                (
                    student_id,
                    alumni_id,
                    message,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    'pending'
                )
            """, (
                student_id,
                alumni_id,
                message
            ))

            # ------------------------------------------
            # Notify Alumni
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    title,
                    message,
                    is_read
                )
                VALUES
                (
                    %s,
                    'New Mentorship Request',
                    'A student has submitted a new mentorship request to connect with you.',
                    0
                )
            """, (alumni_row['user_id'],))

            # ------------------------------------------
            # Notify Student
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    title,
                    message,
                    is_read
                )
                VALUES
                (
                    %s,
                    'Mentorship Request Sent',
                    'Your request has been delivered to the alumni mentor.',
                    0
                )
            """, (user_id,))

            conn.commit()

            flash(
                'Mentorship request submitted successfully!',
                'success'
            )

        except Exception as e:

            conn.rollback()

            flash(
                f"Error submitting mentorship request: {e}",
                'danger'
            )

        finally:

            cursor.close()
            conn.close()

    else:

        flash(
            'Database unavailable.',
            'danger'
        )

    return redirect(
        url_for('student.view_requests')
    )


# --------------------------------------------------
# 11. Cancel Mentorship Request
# --------------------------------------------------
@student_bp.route('/requests/cancel', methods=['POST'])
@student_required
def cancel_mentorship_request():

    request_id = request.form.get(
        'request_id'
    )

    user_id = session['user_id']

    if not request_id:

        flash(
            'Invalid request.',
            'danger'
        )

        return redirect(
            url_for('student.view_requests')
        )

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT mr.id
                FROM mentorship_requests mr
                JOIN students s
                    ON mr.student_id = s.student_id
                WHERE mr.id = %s
                AND s.user_id = %s
                AND mr.status = 'pending'
            """, (
                request_id,
                user_id
            ))

            row = cursor.fetchone()

            if not row:

                flash(
                    'Request not found or cannot be cancelled.',
                    'warning'
                )

                return redirect(
                    url_for('student.view_requests')
                )

            cursor.execute("""
                UPDATE mentorship_requests
                SET status = 'cancelled'
                WHERE id = %s
            """, (request_id,))

            conn.commit()

            flash(
                'Mentorship request cancelled successfully.',
                'info'
            )

        except Exception as e:

            conn.rollback()

            flash(
                f"Error cancelling request: {e}",
                'danger'
            )

        finally:

            cursor.close()
            conn.close()

    else:

        flash(
            'Database unavailable.',
            'danger'
        )

    return redirect(
        url_for('student.view_requests')
    )


# --------------------------------------------------
# 12. Search Alumni Alias
# --------------------------------------------------
@student_bp.route('/search-alumni', methods=['GET'])
@student_required
def search_alumni_redirect():

    return redirect(
        url_for('student.search_alumni')
    )


# --------------------------------------------------
# 13. Mentorship Alias
# --------------------------------------------------
@student_bp.route('/mentorship', methods=['GET'])
@student_required
def mentorship_page():

    return redirect(
        url_for('student.view_requests')
    )


# --------------------------------------------------
# 14. Apply for Job
# --------------------------------------------------
@student_bp.route('/jobs/apply/<int:job_id>', methods=['POST'])
@student_required
def apply_job(job_id):

    user_id = session['user_id']

    conn = get_db_connection()

    if conn:

        cursor = conn.cursor(dictionary=True)

        try:

            # ------------------------------------------
            # Fetch active job from approved alumni
            # ------------------------------------------
            cursor.execute("""
                SELECT
                    jp.job_id,
                    jp.title,
                    jp.company,
                    jp.status,
                    a.user_id AS alumni_user_id
                FROM job_posts jp
                JOIN alumni a
                    ON jp.alumni_id = a.alumni_id
                WHERE jp.job_id = %s
                AND a.verification_status = 'approved'
            """, (job_id,))

            job = cursor.fetchone()

            if not job:

                flash(
                    'Job post not found or unavailable.',
                    'danger'
                )

                return redirect(
                    url_for('student.view_jobs')
                )

            if job['status'] != 'Active':

                flash(
                    'This job post is closed and no longer accepting applications.',
                    'warning'
                )

                return redirect(
                    url_for(
                        'student.job_detail',
                        job_id=job_id
                    )
                )

            # ------------------------------------------
            # Student record
            # ------------------------------------------
            cursor.execute("""
                SELECT student_id
                FROM students
                WHERE user_id = %s
            """, (user_id,))

            student_row = cursor.fetchone()

            if not student_row:

                flash(
                    'Student profile not found. Complete your profile first.',
                    'danger'
                )

                return redirect(
                    url_for('student.view_jobs')
                )

            student_id = student_row['student_id']

            # ------------------------------------------
            # Duplicate application
            # ------------------------------------------
            cursor.execute("""
                SELECT id
                FROM job_applications
                WHERE job_id = %s
                AND student_id = %s
            """, (
                job_id,
                student_id
            ))

            if cursor.fetchone():

                flash(
                    'You have already applied for this position!',
                    'warning'
                )

                return redirect(
                    url_for(
                        'student.job_detail',
                        job_id=job_id
                    )
                )

            # ------------------------------------------
            # Insert application
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO job_applications
                (
                    job_id,
                    student_id
                )
                VALUES
                (
                    %s,
                    %s
                )
            """, (
                job_id,
                student_id
            ))

            # ------------------------------------------
            # Notify Student
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    title,
                    message,
                    is_read
                )
                VALUES
                (
                    %s,
                    'Job Application Submitted',
                    %s,
                    0
                )
            """, (
                user_id,
                f"Your application for '{job['title']}' at "
                f"{job['company']} has been submitted successfully."
            ))

            # ------------------------------------------
            # Notify Alumni
            # ------------------------------------------
            cursor.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    title,
                    message,
                    is_read
                )
                VALUES
                (
                    %s,
                    'New Job Applicant',
                    %s,
                    0
                )
            """, (
                job['alumni_user_id'],
                f"A student has applied for your posting: "
                f"'{job['title']}' at {job['company']}."
            ))

            conn.commit()

            flash(
                f"Application submitted successfully for "
                f"'{job['title']}'!",
                'success'
            )

        except Exception as e:

            conn.rollback()

            if 'Duplicate entry' in str(e):

                flash(
                    'You have already applied for this position!',
                    'warning'
                )

            else:

                flash(
                    f"Application error: {e}",
                    'danger'
                )

        finally:

            cursor.close()
            conn.close()

    else:

        flash(
            'Database unavailable. Please try again later.',
            'danger'
        )

    return redirect(
        url_for(
            'student.job_detail',
            job_id=job_id
        )
    )


# --------------------------------------------------
# 15. Upload Profile Photo
# --------------------------------------------------
@student_bp.route('/profile/upload_photo', methods=['POST'])
@student_required
def upload_photo():

    if 'profile_photo' not in request.files:

        flash(
            'No file uploaded.',
            'danger'
        )

        return redirect(
            url_for('student.view_profile')
        )

    file = request.files['profile_photo']

    if file.filename == '':

        flash(
            'No file selected.',
            'danger'
        )

        return redirect(
            url_for('student.view_profile')
        )

    conn = None
    cursor = None
    new_reference = None
    committed = False
    storage_path = current_app.config.get('PROFILE_PHOTO_STORAGE_PATH')

    try:
        new_reference, _ = save_profile_photo(
            file,
            session['user_id'],
            storage_path
        )
        conn = get_db_connection()
        if conn is None:
            raise RuntimeError('Database unavailable.')

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT profile_photo FROM users WHERE user_id = %s FOR UPDATE',
            (session['user_id'],)
        )
        user = cursor.fetchone()
        if not user:
            raise RuntimeError('Student account not found.')

        cursor.execute("""
            UPDATE users
            SET profile_photo = %s
            WHERE user_id = %s
        """, (new_reference, session['user_id']))
        conn.commit()
        committed = True

        remove_profile_photo(
            user.get('profile_photo'),
            storage_path,
            os.path.join(current_app.static_folder, 'uploads', 'profile_photos')
        )
        flash('Profile photo updated successfully!', 'success')
    except Exception as error:
        if conn:
            conn.rollback()
        if new_reference and not committed:
            remove_profile_photo(
                new_reference,
                storage_path,
                os.path.join(current_app.static_folder, 'uploads', 'profile_photos')
            )
        flash(f'Failed to upload photo: {error}', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(
        url_for('student.view_profile')
    )


# --------------------------------------------------
# 16. Upload Resume
# --------------------------------------------------
@student_bp.route('/profile/upload_resume', methods=['POST'])
@student_required
def upload_resume():

    if 'resume' not in request.files:

        flash(
            'No file uploaded.',
            'danger'
        )

        return redirect(
            url_for('student.view_profile')
        )

    file = request.files['resume']

    if file.filename == '':

        flash(
            'No file selected.',
            'danger'
        )

        return redirect(
            url_for('student.view_profile')
        )

    if file and allowed_file(
        file.filename,
        ALLOWED_RESUME_EXTENSIONS
    ):

        filename = (
            f"student_{session['user_id']}_"
            + secure_filename(file.filename)
        )

        file_path = os.path.join(
            UPLOAD_FOLDER_RESUMES,
            filename
        )

        conn = None
        cursor = None

        try:

            file.save(file_path)

            web_path = (
                f"uploads/resumes/{filename}"
            )

            conn = get_db_connection()

            if conn:

                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE students
                    SET resume = %s
                    WHERE user_id = %s
                """, (
                    web_path,
                    session['user_id']
                ))

                conn.commit()

                flash(
                    'Resume updated successfully!',
                    'success'
                )

            else:

                flash(
                    'Database unavailable.',
                    'danger'
                )

        except Exception as e:

            if conn:
                conn.rollback()

            flash(
                f"Failed to upload resume: {e}",
                'danger'
            )

        finally:

            if cursor:
                cursor.close()

            if conn:
                conn.close()

    else:

        flash(
            'Allowed resume types are pdf, doc, docx.',
            'danger'
        )

    return redirect(
        url_for('student.view_profile')
    )

# --------------------------------------------------
# 17. Private Chat with Accepted Alumni
# --------------------------------------------------
@student_bp.route('/chat/<int:mentorship_id>', methods=['GET'])
@student_required
def student_chat(mentorship_id):

    user_id = session['user_id']

    conn = get_db_connection()

    if not conn:
        flash('Database unavailable.', 'danger')
        return redirect(url_for('student.view_requests'))

    cursor = conn.cursor(dictionary=True)

    try:

        # ------------------------------------------
        # Verify student owns this mentorship
        # and mentorship has been accepted
        # ------------------------------------------
        cursor.execute("""
            SELECT
                mr.id AS mentorship_id,
                mr.status,
                s.student_id,
                s.user_id AS student_user_id,
                a.alumni_id,
                a.user_id AS alumni_user_id,
                u.full_name AS alumni_name,
                u.email AS alumni_email,
                u.profile_photo AS alumni_photo,
                a.company,
                a.designation
            FROM mentorship_requests mr
            JOIN students s
                ON mr.student_id = s.student_id
            JOIN alumni a
                ON mr.alumni_id = a.alumni_id
            JOIN users u
                ON a.user_id = u.user_id
            WHERE mr.id = %s
            AND s.user_id = %s
            AND mr.status IN ('accepted', 'approved')
            AND a.verification_status = 'approved'
        """, (
            mentorship_id,
            user_id
        ))

        connection = cursor.fetchone()

        if not connection:

            flash(
                'Chat is available only after the mentorship request has been accepted.',
                'warning'
            )

            return redirect(
                url_for('student.view_requests')
            )

        # ------------------------------------------
        # Mark messages sent by alumni as read
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
        # Fetch chat messages
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
            user_role='student'
        )

    except Exception as e:

        conn.rollback()

        print(f"Student chat error: {e}")

        flash(
            'Unable to load chat.',
            'danger'
        )

        return redirect(
            url_for('student.view_requests')
        )

    finally:

        cursor.close()
        conn.close()


# --------------------------------------------------
# 18. Send Private Chat Message - Student
# --------------------------------------------------
@student_bp.route('/chat/<int:mentorship_id>/send', methods=['POST'])
@student_required
def student_send_chat_message(mentorship_id):

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
                'student.student_chat',
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
            url_for('student.view_requests')
        )

    cursor = conn.cursor(dictionary=True)

    try:

        # ------------------------------------------
        # Verify accepted mentorship belongs to
        # logged-in student
        # ------------------------------------------
        cursor.execute("""
            SELECT
                mr.id,
                a.user_id AS alumni_user_id
            FROM mentorship_requests mr
            JOIN students s
                ON mr.student_id = s.student_id
            JOIN alumni a
                ON mr.alumni_id = a.alumni_id
            WHERE mr.id = %s
            AND s.user_id = %s
            AND mr.status IN ('accepted', 'approved')
            AND a.verification_status = 'approved'
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
                url_for('student.view_requests')
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
            connection['alumni_user_id'],
            message
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        print(f"Student send message error: {e}")

        flash(
            'Unable to send message.',
            'danger'
        )

    finally:

        cursor.close()
        conn.close()

    return redirect(
        url_for(
            'student.student_chat',
            mentorship_id=mentorship_id
        )
    )