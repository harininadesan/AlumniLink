import os
from flask import Flask, render_template
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from config import config_by_name
from models.database import User

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