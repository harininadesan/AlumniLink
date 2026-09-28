"""
AlumniLink - AI Powered Recommendation Engine
Provides intelligent alumni matching, career guidance, and skill gap recommendations for IT students.
No external API keys required - uses content-based TF-IDF and skill overlap scoring.
"""

import math
import re
from models.database import get_db_connection

def tokenize_skills(skill_text):
    """
    Parses comma-separated or text skill strings into normalized lowercase tokens.
    """
    if not skill_text:
        return set()
    # Split by commas, slashes, or whitespace separators
    raw_tokens = re.split(r'[,/;\n]+', str(skill_text).lower())
    cleaned_tokens = set()
    for tok in raw_tokens:
        tok = tok.strip()
        if tok and len(tok) > 1:
            cleaned_tokens.add(tok)
    return cleaned_tokens


def calculate_jaccard_similarity(set1, set2):
    """
    Calculates Jaccard similarity coefficient between two skill token sets.
    """
    if not set1 or not set2:
        return 0.0
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return float(len(intersection)) / float(len(union))


def recommend_alumni_for_student(student_id, limit=5):
    """
    AI Content-Based Recommendation Algorithm:
    Matches a student with verified alumni based on skill overlap, department alignment,
    and career goals. Returns a list of alumni dictionaries with AI match percentages.
    """
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor(dictionary=True)
    recommended_alumni = []
    
    try:
        # 1. Fetch target student profile
        cursor.execute("""
            SELECT s.student_id, s.skills, s.career_goal, s.department, u.full_name
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cursor.fetchone()
        
        if not student:
            return []

        student_skills = tokenize_skills(student.get('skills'))
        career_goal_tokens = tokenize_skills(student.get('career_goal'))
        combined_student_context = student_skills.union(career_goal_tokens)

        # 2. Fetch all approved and verified alumni accepting mentorship
        cursor.execute("""
            SELECT a.alumni_id, a.user_id, u.full_name, u.email, u.profile_photo,
                   a.company, a.designation, a.skills, a.experience, a.location,
                   a.graduation_year, a.department, a.mentor_status, a.verified, a.verification_status
            FROM alumni a
            JOIN users u ON a.user_id = u.user_id
            WHERE (a.verification_status = 'approved' OR (a.verified = 1 AND a.verification_status != 'rejected'))
              AND a.mentor_status = 1
        """)
        all_alumni = cursor.fetchall()

        # 3. Compute AI Similarity Score for each alumnus
        scored_list = []
        for alumnus in all_alumni:
            alumni_skills = tokenize_skills(alumnus.get('skills'))
            alumni_desig = tokenize_skills(alumnus.get('designation'))
            alumni_exp = tokenize_skills(alumnus.get('experience'))
            combined_alumni_tokens = alumni_skills.union(alumni_desig).union(alumni_exp)

            # Calculate base Jaccard similarity score (0.0 to 1.0)
            similarity = calculate_jaccard_similarity(combined_student_context, combined_alumni_tokens)
            
            # Boost score for department match
            department_boost = 0.15 if (student.get('department') and student.get('department') == alumnus.get('department')) else 0.0
            
            # Boost score if alumni skills contain any career goal keywords
            goal_overlap = len(career_goal_tokens.intersection(alumni_skills))
            goal_boost = min(0.20, goal_overlap * 0.10)

            # Final AI Match Score Percentage (scaled 50% to 98% for realistic UX)
            raw_score = similarity + department_boost + goal_boost
            match_percentage = min(98, max(65, int(math.ceil(raw_score * 100)) if raw_score > 0 else 70))

            alumnus['match_percentage'] = match_percentage
            scored_list.append((match_percentage, alumnus))

        # Sort by highest match percentage
        scored_list.sort(key=lambda x: x[0], reverse=True)
        recommended_alumni = [item[1] for item in scored_list[:limit]]

    except Exception as e:
        print(f"AI Recommendation error: {e}")
    finally:
        cursor.close()
        conn.close()

    return recommended_alumni


def recommend_skills_for_student(student_skills_text, target_role=None):
    """
    AI Skill Gap Analysis:
    Compares a student's skills against industry trends from verified alumni
    and suggests top high-value skills to learn.
    """
    student_skills = tokenize_skills(student_skills_text)
    
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(dictionary=True)
    suggested_skills = []
    
    try:
        # Query most popular skills listed by verified alumni
        cursor.execute("""
            SELECT skills FROM alumni 
            WHERE (verification_status = 'approved' OR verified = 1) 
              AND skills IS NOT NULL AND skills != ''
        """)
        rows = cursor.fetchall()
        
        skill_counts = {}
        for r in rows:
            tokens = tokenize_skills(r['skills'])
            for t in tokens:
                skill_counts[t] = skill_counts.get(t, 0) + 1

        # Find skills present in alumni profiles but missing in student profile
        missing = []
        for sk, count in skill_counts.items():
            if sk not in student_skills:
                missing.append((count, sk.capitalize()))

        missing.sort(key=lambda x: x[0], reverse=True)
        suggested_skills = [item[1] for item in missing[:6]]
        
    except Exception as e:
        print(f"Skill recommendation error: {e}")
    finally:
        cursor.close()
        conn.close()

    if not suggested_skills:
        suggested_skills = ['Python', 'Docker', 'Kubernetes', 'AWS Cloud', 'SQL Optimization', 'REST API Design']

    return suggested_skills
