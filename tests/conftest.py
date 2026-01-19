import os
import pytest
from src import create_app, db as _db

@pytest.fixture(scope='session')
def app():
    """Create application for the tests."""
    # Enforce TESTING mode and usage of a separate DATABASE_URL if needed
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['TESTING'] = 'true'
    
    # Check for Test DB URL
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        pytest.fail("DATABASE_URL not set. Please set a test database connection string to run tests.")
    
    if 'test' not in db_url and 'localhost' not in db_url and '127.0.0.1' not in db_url and '.db' not in db_url:
         pytest.fail(f"DATABASE_URL seems unsafe for testing (does not contain 'test', 'localhost', '127.0.0.1' or '.db'): {db_url}")

    _app = create_app()
    _app.config['TESTING'] = True
    _app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    
    with _app.app_context():
        _db.create_all()
        yield _app
        _db.drop_all()

@pytest.fixture(scope='function')
def db(app):
    """
    Fixture for cleaning up database between tests.
    Uses delete() instead of drop_all() for speed if possible, or simple transaction rollback.
    For simplicity in this monolith, we'll try to keep it clean.
    """
    # Create a new connection execution context
    connection = _db.engine.connect()
    transaction = connection.begin()
    
    # Bind the session to the connection
    options = dict(bind=connection, binds={})
    session = _db.create_scoped_session(options=options)
    
    # Override the default session with our scoped session
    _db.session = session
    
    yield _db
    
    # Rollback the transaction and close connection
    session.remove()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope='function')
def client(app):
    return app.test_client()
