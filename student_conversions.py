import logging
import os
from datetime import date, datetime

from models.database import get_db_connection


logger = logging.getLogger(__name__)
VALID_YEAR_MIN = 1990
VALID_YEAR_MAX = 2100
CONVERSION_LOCK_NAME = 'alumnilink_student_conversion_cron'


def valid_passing_out_year(value):
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if VALID_YEAR_MIN <= year <= VALID_YEAR_MAX else None


def is_conversion_eligible(value, current_year=None):
    year = valid_passing_out_year(value)
    return year is not None and year <= (current_year or date.today().year)


def get_conversion_settings(cursor):
    cursor.execute("""
        SELECT mode, require_graduation_verification
        FROM student_conversion_settings
        WHERE setting_id = 1
    """)
    settings = cursor.fetchone()
    if not settings:
        return {
            'mode': 'automatic',
            'require_graduation_verification': True,
        }
    settings['mode'] = settings.get('mode') or 'admin_approval'
    settings['require_graduation_verification'] = bool(
        settings.get('require_graduation_verification')
    )
    return settings


def set_conversion_request(cursor, student, status, reviewed_by=None):
    cursor.execute("""
        INSERT INTO student_conversion_requests
            (user_id, student_id, passing_out_year, status, reviewed_by, reviewed_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            student_id = VALUES(student_id),
            passing_out_year = VALUES(passing_out_year),
            status = VALUES(status),
            reviewed_by = VALUES(reviewed_by),
            reviewed_at = VALUES(reviewed_at)
    """, (
        student['user_id'],
        student['student_id'],
        valid_passing_out_year(student.get('graduation_year')),
        status,
        reviewed_by,
        datetime.now() if reviewed_by else None,
    ))


def convert_student(cursor, student_id, settings, method, admin_id=None):
    cursor.execute("""
        SELECT s.*, u.user_id, u.role, u.full_name
        FROM students s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.student_id = %s
        FOR UPDATE
    """, (student_id,))
    student = cursor.fetchone()
    if not student or str(student.get('role', '')).strip().lower() != 'student':
        raise ValueError('This account is not currently a student.')

    passing_out_year = valid_passing_out_year(student.get('graduation_year'))
    if not is_conversion_eligible(passing_out_year):
        raise ValueError('The student has not reached a valid passing-out year.')

    graduation_verified = bool(student.get('graduation_verified'))
    if settings.get('require_graduation_verification') and not graduation_verified:
        raise ValueError('Graduation verification is required before conversion.')

    cursor.execute('SELECT alumni_id FROM alumni WHERE user_id = %s FOR UPDATE', (student['user_id'],))
    alumni = cursor.fetchone()
    if alumni:
        cursor.execute("""
            UPDATE alumni
            SET skills = COALESCE(skills, %s),
                linkedin = COALESCE(linkedin, %s),
                admission_year = COALESCE(admission_year, %s),
                graduation_year = COALESCE(graduation_year, %s),
                department = COALESCE(department, %s),
                github = COALESCE(github, %s),
                bio = COALESCE(bio, %s)
            WHERE user_id = %s
        """, (
            student.get('skills'), student.get('linkedin'),
            student.get('admission_year'), passing_out_year,
            student.get('department') or 'Information Technology',
            student.get('github'), student.get('bio'), student['user_id'],
        ))
    else:
        cursor.execute("""
            INSERT INTO alumni
                (user_id, skills, linkedin, admission_year, graduation_year, department, github, bio,
                 verified, verification_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'pending')
        """, (
            student['user_id'], student.get('skills'), student.get('linkedin'),
            student.get('admission_year'), passing_out_year,
            student.get('department') or 'Information Technology',
            student.get('github'), student.get('bio'),
        ))

    cursor.execute("UPDATE users SET role = 'Alumni' WHERE user_id = %s", (student['user_id'],))
    set_conversion_request(cursor, student, 'converted', admin_id)
    cursor.execute("""
        INSERT INTO student_conversion_history
            (user_id, previous_role, new_role, conversion_method, admin_id, verification_status)
        VALUES (%s, %s, 'Alumni', %s, %s, %s)
    """, (
        student['user_id'], student['role'], method, admin_id,
        'verified' if graduation_verified else 'not_required',
    ))
    return student


def _notify_admins(cursor, student, requires_verification):
    message = (
        f"{student['full_name']} reached passing-out year "
        f"{valid_passing_out_year(student.get('graduation_year'))}. "
    )
    if requires_verification:
        message += 'Verify graduation before approving conversion.'
    else:
        message += 'Review the student conversion request.'

    cursor.execute('SELECT user_id FROM admins')
    for admin in cursor.fetchall():
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, is_read)
            VALUES (%s, 'Student eligible for Alumni conversion', %s, 0)
        """, (admin['user_id'], message))


def run_scheduled_conversion_check():
    if os.environ.get('STUDENT_CONVERSION_SCHEDULE_ENABLED', '').lower() not in {'1', 'true', 'yes'}:
        logger.info('Student conversion schedule is disabled.')
        return {'status': 'disabled', 'processed': 0, 'converted': 0}

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError('Could not connect to the AlumniLink database.')

    cursor = None
    lock_acquired = False
    processed = 0
    converted = 0
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT GET_LOCK(%s, 0) AS lock_acquired', (CONVERSION_LOCK_NAME,))
        lock_acquired = bool((cursor.fetchone() or {}).get('lock_acquired'))
        if not lock_acquired:
            logger.info('Another student conversion check holds the database lock.')
            return {'status': 'already_running', 'processed': 0, 'converted': 0}

        settings = get_conversion_settings(cursor)
        cursor.execute("""
            SELECT s.*, u.user_id, u.full_name, u.role
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            WHERE LOWER(u.role) = 'student'
            FOR UPDATE
        """)
        students = cursor.fetchall()

        for student in students:
            year = valid_passing_out_year(student.get('graduation_year'))
            if year is None or year > date.today().year:
                cursor.execute("""
                    SELECT status, passing_out_year FROM student_conversion_requests
                    WHERE user_id = %s FOR UPDATE
                """, (student['user_id'],))
                request_row = cursor.fetchone()
                if request_row and request_row.get('status') not in {'converted', 'rejected'}:
                    set_conversion_request(cursor, student, 'not_eligible')
                continue

            processed += 1
            cursor.execute("""
                SELECT status, passing_out_year FROM student_conversion_requests
                WHERE user_id = %s FOR UPDATE
            """, (student['user_id'],))
            existing_request = cursor.fetchone()
            if (
                existing_request
                and existing_request.get('status') == 'rejected'
                and existing_request.get('passing_out_year') == year
                and settings['mode'] == 'admin_approval'
            ):
                continue

            needs_verification = (
                settings['require_graduation_verification']
                and not bool(student.get('graduation_verified'))
            )
            if needs_verification:
                status = 'awaiting_verification'
            elif settings['mode'] == 'admin_approval':
                status = 'pending_approval'
            else:
                status = 'eligible'

            changed = (
                not existing_request
                or existing_request.get('status') != status
                or existing_request.get('passing_out_year') != year
            )
            set_conversion_request(cursor, student, status)
            if changed and (
                needs_verification or settings['mode'] == 'admin_approval'
            ):
                _notify_admins(cursor, student, needs_verification)

            if settings['mode'] == 'automatic' and not needs_verification:
                convert_student(cursor, student['student_id'], settings, 'automatic')
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, is_read)
                    VALUES (%s, 'Alumni status updated',
                            'Your account is now an Alumni account. Your existing login remains unchanged.', 0)
                """, (student['user_id'],))
                converted += 1

        conn.commit()
        return {'status': 'complete', 'processed': processed, 'converted': converted}
    except Exception:
        conn.rollback()
        logger.exception('Scheduled student conversion check failed.')
        raise
    finally:
        if lock_acquired and cursor:
            try:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (CONVERSION_LOCK_NAME,))
            except Exception:
                logger.exception('Could not release student conversion advisory lock.')
        if cursor:
            cursor.close()
        conn.close()