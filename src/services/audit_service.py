import json
from datetime import datetime
from flask_login import current_user
from ..models import db, AuditLog

class AuditService:
    @staticmethod
    def log_change(model_name, object_id, action, changes=None, user_id=None):
        """
        Logs a change in the system.
        
        :param model_name: Name of the model being changed (e.g., 'Chamado')
        :param object_id: ID of the object being changed
        :param action: Action performed ('CREATE', 'UPDATE', 'DELETE')
        :param changes: Dictionary containing changes (e.g., {'field': {'old': v1, 'new': v2}})
        :param user_id: ID of the user performing the action (defaults to current_user.id if available)
        """
        try:
            if user_id is None:
                # Try to get from flask_login, handle if outside request context
                try:
                    if current_user and current_user.is_authenticated:
                        user_id = current_user.id
                except:
                    pass

            changes_json = json.dumps(changes) if changes else None
            
            log_entry = AuditLog(
                user_id=user_id,
                model_name=model_name,
                object_id=str(object_id),
                action=action,
                changes=changes_json,
                timestamp=datetime.utcnow()
            )
            
            db.session.add(log_entry)
            # We use a separate commit or rely on the caller's commit? 
            # Ideally audit logs should happen even if main transaction fails? 
            # But usually we want them to be atomic with the transaction.
            # We'll rely on the caller to commit or flush, but we can flush here to get ID.
            db.session.flush()
            
        except Exception as e:
            # Fallback logging to file/console so we don't break the app flow if audit fails
            print(f"Failed to create audit log: {e}")
