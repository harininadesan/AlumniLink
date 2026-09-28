import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Base configuration settings."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secure-fallback-key-alumnilink-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Database Settings
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_NAME = os.environ.get('DB_NAME', 'alumnilink_db')
    
    SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{os.environ.get('DB_PORT', '3306')}/{DB_NAME}?ssl_verify_cert=true"
)

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    ENV = 'development'

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    # In production, require environment variable to be set
    SECRET_KEY = os.environ.get('SECRET_KEY')

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
