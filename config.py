"""
Configuration management for EduSphere application.
Loads configuration from environment variables using python-dotenv.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration class."""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'
    FLASK_DEBUG = os.environ.get('FLASK_DEBUG', '1') == '1'
    
    # Application Configuration
    APP_NAME = os.environ.get('APP_NAME') or 'EduSphere'
    APP_URL = os.environ.get('APP_URL') or 'http://localhost:5000'
    
    # Database Configuration
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///instance/database.db'
    
    # Session Configuration
    SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT') or 3600)  # 1 hour default
    
    # Upload Configuration
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH') or 16 * 1024 * 1024)  # 16MB
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'static/uploads/profiles'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Email Configuration (for future use)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration."""
        # Create instance folder if it doesn't exist
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)
        
        # Create upload folder if it doesn't exist
        upload_path = os.path.join(app.root_path, Config.UPLOAD_FOLDER)
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_ENV = 'development'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_ENV = 'production'
    
    # Override for production - ensure SECRET_KEY is set
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Warn if SECRET_KEY is not set in production
        if not os.environ.get('SECRET_KEY'):
            raise ValueError(
                'SECRET_KEY must be set in production environment. '
                'Set the SECRET_KEY environment variable.'
            )


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DATABASE_URL = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """
    Get configuration class based on environment.
    
    Args:
        config_name: Configuration name (development, production, testing)
                    If None, uses FLASK_ENV environment variable
    
    Returns:
        Configuration class
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    return config.get(config_name, config['default'])
