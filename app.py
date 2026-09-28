import os
import logging
import shutil
from urllib.parse import urlsplit
from flask import Flask, render_template, send_from_directory, url_for
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from config import config_by_name
from models.database import User
from werkzeug.exceptions import NotFound

# Load environment variables
load_dotenv()

# Initialize extensions
login_manager = LoginManager()
bcrypt = Bcrypt()

def create_app(config_name=None):
    """
    Application factory pattern to create and configure the Flask app.
    """
    app = Flask(__name__)
    
    # Determine configuration type (defaults to development)
    if not config_name:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    photo_storage_path = os.environ.get('PROFILE_PHOTO_STORAGE_PATH') or None
    is_render = os.environ.get('RENDER', '').lower() in {'1', 'true', 'yes'}
    if photo_storage_path:
        photo_storage_path = os.path.abspath(photo_storage_path)
        if is_render:
            render_disk_path = os.path.abspath(
                os.environ.get('RENDER_DISK_MOUNT_PATH', '/var/data')
            )
            try:
                is_persistent_path = (
                    os.path.ismount(render_disk_path)
                    and os.path.commonpath((photo_storage_path, render_disk_path)) == render_disk_path
                )
            except ValueError:
                is_persistent_path = False
            if not is_persistent_path:
                photo_storage_path = None
    elif not is_render:
        photo_storage_path = os.path.join(app.instance_path, 'profile_photos')

    app.config['PROFILE_PHOTO_STORAGE_PATH'] = photo_storage_path
    if photo_storage_path:
        os.makedirs(photo_storage_path, exist_ok=True)
        legacy_photo_path = os.path.join(
            app.static_folder, 'uploads', 'profile_photos'
        )
        if os.path.isdir(legacy_photo_path):
            for entry in os.scandir(legacy_photo_path):
                if not entry.is_file(follow_symlinks=False):
                    continue
                extension = os.path.splitext(entry.name)[1].lower()
                if extension not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                    continue
                destination = os.path.join(photo_storage_path, entry.name)
                if os.path.exists(destination):
                    continue
                try:
                    shutil.copy2(entry.path, destination)
                except OSError:
                    logging.getLogger(__name__).warning(
                        'Could not copy legacy profile photo %s to persistent storage.',
                        entry.name,
                        exc_info=True,
                    )

    def profile_photo_url(photo_reference):
        if not photo_reference:
            return url_for('static', filename='profile-avatar.svg')

        reference = str(photo_reference).strip()
        parsed_reference = urlsplit(reference)
        if parsed_reference.scheme in {'http', 'https'}:
            return reference

        filename = os.path.basename(parsed_reference.path.replace('\\', '/'))
        if not filename:
            return url_for('static', filename='profile-avatar.svg')
        return url_for('profile_photo_media', filename=filename)

    app.add_template_global(profile_photo_url, name='profile_photo_url')
    
    # Initialize extensions with the app context
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    
    bcrypt.init_app(app)
    
    # Register Blueprints
    from routes.auth import auth_bp
    from routes.student import student_bp
    from routes.alumni import alumni_bp
    from routes.admin import admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(alumni_bp)
    app.register_blueprint(admin_bp)
    
    # Root Route - Renders the professional homepage
    @app.route('/')
    def home():
        return render_template('home.html')

    @app.route('/media/profile_photos/<path:filename>')
    def profile_photo_media(filename):
        photo_directories = [app.config.get('PROFILE_PHOTO_STORAGE_PATH')]
        photo_directories.append(
            os.path.join(app.static_folder, 'uploads', 'profile_photos')
        )

        for directory in photo_directories:
            if not directory:
                continue
            try:
                return send_from_directory(directory, filename)
            except NotFound:
                continue

        return send_from_directory(app.static_folder, 'profile-avatar.svg')
        
    return app

# Initialize the global app object
app = create_app()

@app.before_request
def sync_session_with_current_user():
    """
    Ensures that if Flask-Login has an active current_user session,
    the matching custom session parameters are populated.
    This prevents redirect loops due to mismatch between Flask-Login and session state.
    """
    from flask import session
    from flask_login import current_user
    if current_user.is_authenticated:
        if 'user_id' not in session:
            session['user_id'] = current_user.id
        if 'role' not in session:
            session['role'] = current_user.role
        if 'full_name' not in session:
            session['full_name'] = current_user.full_name

@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login user loader callback to reload the user object from the session.
    """
    return User.get(user_id)

if __name__ == '__main__':
    # Retrieve port and host settings or run with defaults
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    app.run(host=host, port=port, debug=app.config.get('DEBUG', True))