-- ==========================================================================
-- AlumniLink — Complete Migration Script (SAFE / NON-DESTRUCTIVE)
-- Run this to bring the database up to date with the current codebase.
-- ==========================================================================

-- Step 1: Extend job_posts table with all required columns
ALTER TABLE `job_posts`
    ADD COLUMN IF NOT EXISTS `job_type` ENUM('Internship', 'Full-Time', 'Part-Time') NOT NULL DEFAULT 'Full-Time' AFTER `company`,
    ADD COLUMN IF NOT EXISTS `work_mode` ENUM('Remote', 'Hybrid', 'On-site') NOT NULL DEFAULT 'On-site' AFTER `job_type`,
    ADD COLUMN IF NOT EXISTS `stipend_salary` VARCHAR(100) DEFAULT NULL AFTER `work_mode`,
    ADD COLUMN IF NOT EXISTS `required_skills` TEXT DEFAULT NULL AFTER `stipend_salary`,
    ADD COLUMN IF NOT EXISTS `eligibility` TEXT DEFAULT NULL AFTER `required_skills`,
    ADD COLUMN IF NOT EXISTS `application_link` VARCHAR(500) DEFAULT NULL AFTER `eligibility`,
    ADD COLUMN IF NOT EXISTS `status` ENUM('Active', 'Closed') NOT NULL DEFAULT 'Active' AFTER `application_link`,
    ADD COLUMN IF NOT EXISTS `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`;

-- Step 2: Set all existing job posts to Active status
UPDATE `job_posts` SET `status` = 'Active' WHERE `status` IS NULL;

-- Step 3: Extend mentorship_requests table
ALTER TABLE `mentorship_requests`
    ADD COLUMN IF NOT EXISTS `request_date` DATE DEFAULT NULL AFTER `status`,
    ADD COLUMN IF NOT EXISTS `approved` BOOLEAN DEFAULT FALSE AFTER `request_date`;

-- Update request_date from created_at for any existing rows
UPDATE `mentorship_requests` SET `request_date` = DATE(`created_at`) WHERE `request_date` IS NULL;

-- Step 4: Fix mentorship_requests status ENUM to include all needed values
ALTER TABLE `mentorship_requests`
    MODIFY COLUMN `status` ENUM('pending', 'accepted', 'approved', 'rejected', 'cancelled') DEFAULT 'pending';

-- Step 5: Create job_applications table if it doesn't exist
CREATE TABLE IF NOT EXISTS `job_applications` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `job_id` INT NOT NULL,
    `student_id` INT NOT NULL,
    `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `unique_application` (`job_id`, `student_id`),
    FOREIGN KEY (`job_id`) REFERENCES `job_posts` (`job_id`) ON DELETE CASCADE,
    FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Step 6: Make sure alumni table has verification_status column
ALTER TABLE `alumni`
    ADD COLUMN IF NOT EXISTS `verification_status` ENUM('pending', 'approved', 'rejected') DEFAULT 'pending' AFTER `verified`;

-- Sync verification_status with the verified boolean for existing rows
UPDATE `alumni` SET `verification_status` = 'approved' WHERE `verified` = TRUE AND (`verification_status` IS NULL OR `verification_status` = 'pending');
UPDATE `alumni` SET `verification_status` = 'pending' WHERE `verified` = FALSE AND `verification_status` IS NULL;

-- Step 7: Make sure alumni table has all profile fields
ALTER TABLE `alumni`
    ADD COLUMN IF NOT EXISTS `phone` VARCHAR(50) DEFAULT NULL AFTER `location`,
    ADD COLUMN IF NOT EXISTS `github` VARCHAR(255) DEFAULT NULL AFTER `linkedin`,
    ADD COLUMN IF NOT EXISTS `bio` TEXT DEFAULT NULL AFTER `github`,
    ADD COLUMN IF NOT EXISTS `achievements` TEXT DEFAULT NULL AFTER `bio`,
    ADD COLUMN IF NOT EXISTS `share_email` BOOLEAN DEFAULT TRUE AFTER `achievements`,
    ADD COLUMN IF NOT EXISTS `share_phone` BOOLEAN DEFAULT FALSE AFTER `share_email`,
    ADD COLUMN IF NOT EXISTS `graduation_year` INT DEFAULT NULL AFTER `department`,
    ADD COLUMN IF NOT EXISTS `department` VARCHAR(100) NOT NULL DEFAULT 'Information Technology';

-- Step 8: Make sure students table has all required fields
ALTER TABLE `students`
    ADD COLUMN IF NOT EXISTS `linkedin` VARCHAR(255) DEFAULT NULL AFTER `career_goal`,
    ADD COLUMN IF NOT EXISTS `github` VARCHAR(255) DEFAULT NULL AFTER `linkedin`,
    ADD COLUMN IF NOT EXISTS `bio` TEXT DEFAULT NULL AFTER `github`;

-- ==========================================================================
-- Verification
-- ==========================================================================
SELECT 'Migration complete' AS status;
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE();
