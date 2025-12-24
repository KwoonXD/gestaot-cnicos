"""
Script to add notification and created_by columns.
"""
from src import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    
    # Create notifications table
    create_notifications = """
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        title VARCHAR(150) NOT NULL,
        message TEXT NOT NULL,
        notification_type VARCHAR(20) DEFAULT 'info',
        is_read BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    
    try:
        conn.execute(text(create_notifications))
        conn.commit()
        print("OK: Created notifications table")
    except Exception as e:
        print(f"Notifications table: {e}")
    
    # Add created_by_id to chamados if not exists
    try:
        conn.execute(text('ALTER TABLE chamados ADD COLUMN created_by_id INTEGER REFERENCES users(id)'))
        conn.commit()
        print("OK: Added created_by_id column")
    except Exception as e:
        if 'duplicate column' in str(e).lower():
            print("SKIP: created_by_id already exists")
        else:
            print(f"created_by_id: {e}")
    
    print("\nSchema update complete!")
