import os
import secrets
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_executor import Executor
from dotenv import load_dotenv
from .models import db, User

# CRÍTICO: Inicializar globalmente para permitir importação nos serviços
executor = Executor() 

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
    app.config['EXECUTOR_TYPE'] = 'thread'
    app.config['EXECUTOR_MAX_WORKERS'] = 2


    # Init Extensions
    db.init_app(app)
    migrate = Migrate(app, db) # Task 1: Flask-Migrate
    executor.init_app(app) # Apenas init_app aqui dentro

    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    # Task 2: Logging
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler('logs/sistema.log', maxBytes=10240000, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Gestão de Técnicos startup')

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Removed db.create_all() as per Task 1

    # Context Processor for Alerts
    @app.context_processor
    def inject_alerts():
        try:
            from .services.alert_service import AlertService
            alerts = AlertService.get_alerts()
            return dict(alertas=alerts, alerta_count=len(alerts))
        except Exception as e:
            app.logger.error(f"Error injecting alerts: {e}")
            return dict(alertas=[], alerta_count=0)

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
