-- =========================================================================
-- AlumniLink – AI Powered Privacy First Alumni Networking Platform Database Schema
-- DBMS: MySQL
-- =========================================================================

-- Disable foreign key checks temporarily to drop tables in correct order if they exist
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `notifications`;
DROP TABLE IF EXISTS `certificates`;
DROP TABLE IF EXISTS `user_skills`;
DROP TABLE IF EXISTS `skills`;
DROP TABLE IF EXISTS `job_posts`;
DROP TABLE IF EXISTS `mentorship_requests`;
DROP TABLE IF EXISTS `admins`;
DROP TABLE IF EXISTS `alumni`;
DROP TABLE IF EXISTS `students`;
DROP TABLE IF EXISTS `users`;
SET FOREIGN_KEY_CHECKS = 1;

-- 1. USERS TABLE
-- Stores credentials and core details for all users regardless of their specific role.
CREATE TABLE `users` (
    `user_id` INT AUTO_INCREMENT PRIMARY KEY,
    `full_name` VARCHAR(150) NOT NULL,
    `email` VARCHAR(100) UNIQUE NOT NULL,
    `password` VARCHAR(255) NOT NULL,
    `role` ENUM('student', 'alumni', 'admin') NOT NULL,
    `profile_photo` VARCHAR(255) DEFAULT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. STUDENTS TABLE
-- Holds academic and career profiling details unique to IT students.
CREATE TABLE `students` (
    `student_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `department` VARCHAR(100) NOT NULL DEFAULT 'Information Technology',
    `admission_year` INT DEFAULT NULL,
    `graduation_year` INT NOT NULL,
    `graduation_verified` BOOLEAN NOT NULL DEFAULT FALSE,
    `register_number` VARCHAR(50) UNIQUE NOT NULL,
    `skills` TEXT DEFAULT NULL, -- Comma-separated list for simplified search
    `resume` VARCHAR(255) DEFAULT NULL,
    `career_goal` VARCHAR(255) DEFAULT NULL,
    `bio` TEXT DEFAULT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. ALUMNI TABLE
-- Stores professional background, current employment, and mentoring availability for verified alumni.
CREATE TABLE `alumni` (
    `alumni_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `company` VARCHAR(150) DEFAULT NULL,
    `designation` VARCHAR(100) DEFAULT NULL,
    `experience` TEXT DEFAULT NULL, -- Detailed career experience history
    `skills` TEXT DEFAULT NULL, -- Comma-separated professional skills
    `linkedin` VARCHAR(255) DEFAULT NULL,
    `location` VARCHAR(150) DEFAULT NULL,
    `mentor_status` BOOLEAN DEFAULT TRUE, -- TRUE: active/accepting mentees, FALSE: busy/not accepting
    `verified` BOOLEAN DEFAULT FALSE, -- FALSE: pending admin verification, TRUE: verified
    `verification_status` ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    `department` VARCHAR(100) NOT NULL DEFAULT 'Information Technology',
    `admission_year` INT DEFAULT NULL,
    `graduation_year` INT DEFAULT NULL,
    `phone` VARCHAR(50) DEFAULT NULL,
    `github` VARCHAR(255) DEFAULT NULL,
    `bio` TEXT DEFAULT NULL,
    `achievements` TEXT DEFAULT NULL,
    `share_email` BOOLEAN DEFAULT TRUE,
    `share_phone` BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. ADMINS TABLE
-- Connects users assigned with internal moderation/verification privileges.
CREATE TABLE `admins` (
    `admin_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. STUDENT CONVERSION POLICY AND AUDIT
CREATE TABLE `student_conversion_settings` (
    `setting_id` TINYINT UNSIGNED PRIMARY KEY,
    `mode` ENUM('automatic', 'admin_approval') NOT NULL DEFAULT 'automatic',
    `require_graduation_verification` BOOLEAN NOT NULL DEFAULT TRUE,
    `updated_by` INT DEFAULT NULL,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `student_conversion_requests` (
    `conversion_request_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE,
    `student_id` INT NOT NULL,
    `passing_out_year` INT DEFAULT NULL,
    `status` ENUM('not_eligible', 'eligible', 'awaiting_verification', 'pending_approval', 'rejected', 'converted') NOT NULL,
    `reviewed_by` INT DEFAULT NULL,
    `reviewed_at` TIMESTAMP NULL DEFAULT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE,
    FOREIGN KEY (`reviewed_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
    INDEX `idx_conversion_status_year` (`status`, `passing_out_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `student_conversion_history` (
    `conversion_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL UNIQUE,
    `previous_role` VARCHAR(30) NOT NULL,
    `new_role` VARCHAR(30) NOT NULL,
    `converted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `conversion_method` ENUM('automatic', 'admin_approved', 'manual_admin') NOT NULL,
    `admin_id` INT DEFAULT NULL,
    `verification_status` ENUM('verified', 'not_required') NOT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`admin_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. MENTORSHIP REQUESTS TABLE
-- Manages requests initiated by students to seek professional mentorship or feedback from alumni.
CREATE TABLE `mentorship_requests` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `student_id` INT NOT NULL,
    `alumni_id` INT NOT NULL,
    `message` TEXT DEFAULT NULL,
    `status` ENUM('pending', 'accepted', 'rejected', 'cancelled') DEFAULT 'pending',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE,
    FOREIGN KEY (`alumni_id`) REFERENCES `alumni` (`alumni_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. JOB POSTS TABLE
-- Internal job referrals, mock roles, or placement vacancies posted by verified alumni.
CREATE TABLE `job_posts` (
    `job_id` INT AUTO_INCREMENT PRIMARY KEY,
    `alumni_id` INT NOT NULL,
    `title` VARCHAR(150) NOT NULL,
    `company` VARCHAR(150) NOT NULL,
    `description` TEXT NOT NULL,
    `location` VARCHAR(150) DEFAULT NULL,
    `deadline` DATE DEFAULT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`alumni_id`) REFERENCES `alumni` (`alumni_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. SKILLS TABLE
-- Master dictionary of IT skills and domain specializations used by the AI-powered recommendation system.
CREATE TABLE `skills` (
    `skill_id` INT AUTO_INCREMENT PRIMARY KEY,
    `skill_name` VARCHAR(100) UNIQUE NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. USER SKILLS TABLE
-- Mapping table to enable clean many-to-many associations between users (students/alumni) and skill sets.
CREATE TABLE `user_skills` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `skill_id` INT NOT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
    FOREIGN KEY (`skill_id`) REFERENCES `skills` (`skill_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. CERTIFICATES TABLE
-- Academic or professional verification certificates uploaded by students or alumni.
CREATE TABLE `certificates` (
    `certificate_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `certificate_name` VARCHAR(150) NOT NULL,
    `file_path` VARCHAR(255) NOT NULL,
    `upload_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. NOTIFICATIONS TABLE
-- Real-time notification logs to alert users about connections, request statuses, or new jobs.
CREATE TABLE `notifications` (
    `notification_id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `title` VARCHAR(150) NOT NULL,
    `message` TEXT NOT NULL,
    `is_read` BOOLEAN DEFAULT FALSE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
