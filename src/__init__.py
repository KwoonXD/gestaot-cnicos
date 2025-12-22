import os
import secrets
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv
from .models import db, User

def create_app():
    load_dotenv()

    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # Config
    session_secret = os.environ.get("SESSION_SECRET")
    if not session_secret:
        session_secret = secrets.token_hex(32)
    app.secret_key = session_secret

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Init Extensions
    db.init_app(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    # Register Blueprints
    from .routes.auth_routes import auth_bp
    from .routes.operacional_routes import operacional_bp
    from .routes.financeiro_routes import financeiro_bp
    from .routes.api_routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(operacional_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app
