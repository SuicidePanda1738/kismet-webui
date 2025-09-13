import os
import logging
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "kismet-web-interface-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///kismet.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import models first, then create tables
    import models
    db.create_all()
    
    # Import routes after database is initialized
    import routes

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with JSON response for API endpoints"""
    if request.path.startswith('/convert-to-kml') or request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    # Return a simple text response for other 404s
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with JSON response for API endpoints"""
    if request.path.startswith('/convert-to-kml') or request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    # Return a simple text response for other 500s
    return "Internal server error", 500

if __name__ == '__main__':
    # Run the Flask development server when executed directly
    app.run(host='0.0.0.0', port=5000, debug=True)
