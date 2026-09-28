-- ==========================================================================
-- AlumniLink — Job Portal Module Migration
-- Run this on your existing database to add the Job Portal feature.
-- This is NON-DESTRUCTIVE: it does NOT drop existing tables.
-- ==========================================================================

-- Step 1: Extend the existing job_posts table with new columns
-- (Only runs if the column doesn't already exist)

ALTER TABLE `job_posts`
    ADD COLUMN IF NOT EXISTS `job_type` ENUM('Internship', 'Full-Time', 'Part-Time') NOT NULL DEFAULT 'Full-Time' AFTER `company`,
    ADD COLUMN IF NOT EXISTS `work_mode` ENUM('Remote', 'Hybrid', 'On-site') NOT NULL DEFAULT 'On-site' AFTER `job_type`,
    ADD COLUMN IF NOT EXISTS `stipend_salary` VARCHAR(100) DEFAULT NULL AFTER `work_mode`,
    ADD COLUMN IF NOT EXISTS `required_skills` TEXT DEFAULT NULL AFTER `stipend_salary`,
    ADD COLUMN IF NOT EXISTS `eligibility` TEXT DEFAULT NULL AFTER `required_skills`,
    ADD COLUMN IF NOT EXISTS `application_link` VARCHAR(500) DEFAULT NULL AFTER `eligibility`,
    ADD COLUMN IF NOT EXISTS `status` ENUM('Active', 'Closed') NOT NULL DEFAULT 'Active' AFTER `application_link`,
    ADD COLUMN IF NOT EXISTS `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`;

-- Step 2: Add the mentorship_requests columns that code expects (request_date alias)
-- The existing schema uses `created_at` but routes reference `request_date` — add alias column
ALTER TABLE `mentorship_requests`
    ADD COLUMN IF NOT EXISTS `request_date` DATE DEFAULT NULL AFTER `status`,
    ADD COLUMN IF NOT EXISTS `approved` BOOLEAN DEFAULT FALSE AFTER `request_date`;

-- Set request_date from created_at for existing rows
UPDATE `mentorship_requests` SET `request_date` = DATE(`created_at`) WHERE `request_date` IS NULL;

-- Ensure status column matches what routes use ('approved' / 'rejected' / 'pending')
-- The original schema uses 'accepted' — we add 'approved' as an alias value by altering the ENUM
ALTER TABLE `mentorship_requests`
    MODIFY COLUMN `status` ENUM('pending', 'approved', 'accepted', 'rejected', 'cancelled') DEFAULT 'pending';

-- Step 3: Create the job_applications table (if not exists)
CREATE TABLE IF NOT EXISTS `job_applications` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `job_id` INT NOT NULL,
    `student_id` INT NOT NULL,
    `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `unique_application` (`job_id`, `student_id`),
    FOREIGN KEY (`job_id`) REFERENCES `job_posts` (`job_id`) ON DELETE CASCADE,
    FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================================================
-- Verification Queries — Run to confirm migration success
-- ==========================================================================
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'job_posts';
-- SELECT COUNT(*) FROM job_applications;
-- SHOW CREATE TABLE job_applications;
