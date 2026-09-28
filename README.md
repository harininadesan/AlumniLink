## Persistent Profile Photos on Render

Profile photos are stored outside the application source tree and served through
the Flask media endpoint. For Render, attach a persistent disk to the web service
with mount path `/var/data`, then set this environment variable:

```text
PROFILE_PHOTO_STORAGE_PATH=/var/data/profile_photos
```

The application refuses photo uploads on Render when this setting is missing or
the configured directory is not under the mounted disk, so uploads are not
silently written to an ephemeral filesystem. If using a different disk mount,
set `RENDER_DISK_MOUNT_PATH` to its mount path as well. Keep the service at a
single instance when using a Render disk; use shared object storage if the
service needs multiple instances. Local development stores photos in Flask's
`instance/profile_photos` directory.

## Student-to-Alumni Conversion

The existing `students.graduation_year` is used as the passing-out year;
`admission_year` is optional. Existing account, credential, photo, and student
records are retained. Conversion creates or fills the matching Alumni profile,
updates the existing user's role, and records the conversion in one transaction.

Before deploying, run the existing idempotent migration against the configured
database:

```text
python database/run_migration.py
```

Do not run `database/schema.sql` against an existing production database; it
recreates tables. The migration adds optional student year/verification fields
and the conversion settings, request, and history tables without dropping data.

### Render Scheduling

Create a Render **Cron Job** using the same repository and database environment
variables as the web service (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
Set its build command to the normal requirements installation and its command to:

```text
python database/check_student_conversions.py
```

Schedule it daily, for example `15 0 * * *` (00:15 UTC), and set
`STUDENT_CONVERSION_SCHEDULE_ENABLED=true` on the Cron Job. New installations
default to **Automatic** mode with graduation verification required; admins
can change either setting in **Student
Conversions**. Automatic mode converts eligible users only when all configured
verification requirements pass. The advisory DB lock prevents overlapping
checks; conversion history is unique per user to prevent duplicate conversion.

Automatic conversion is not active until this Cron Job is deployed, has database
connectivity, and has completed a successful run. It is deliberately not run in
the web worker, so Gunicorn restarts or multiple workers cannot create duplicate
scheduler loops.

### Local Testing

After migrating a development database, set an eligible student's passing-out
year to the current year or earlier. To test automatic mode, enable
`STUDENT_CONVERSION_SCHEDULE_ENABLED=true`, set the conversion mode to Automatic
in the Admin Panel, and run `python database/check_student_conversions.py`.
For admin approval, select Admin approval, run the same command, then approve or
reject the resulting row in Student Conversions. To require verification, enable
that setting, mark the student's graduation verified in the Admin Panel, then
run the check again or approve the pending request. The Student Profile page's
**Promote to Alumni** action provides the separate manual admin path and asks for
confirmation.
