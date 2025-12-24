from src import create_app, db
from src.models import User, AuditLog
from flask_login import current_user

app = create_app()

def verify_admin_logic():
    with app.app_context():
        print("--- Verificando Lógica Admin & Audit ---")
        
        # 1. Setup Admin User if not exists
        admin = User.query.filter_by(username='admin_test').first()
        if not admin:
            print("Criando usuário admin_test...")
            admin = User(username='admin_test', role='Admin')
            admin.set_password('123456')
            db.session.add(admin)
            db.session.commit()
            
            # Simulate Audit Log for creation (normally done in route)
            audit = AuditLog(
                user_id=admin.id, # Self-created or system
                model_name='User',
                object_id=str(admin.id),
                action='CREATE',
                changes="Created admin_test"
            )
            db.session.add(audit)
            db.session.commit()
            
        print(f"Admin User ID: {admin.id}, Role: {admin.role}")
        
        # 2. Verify Audit Log Creation
        print("\n[Teste 1] Criando Audit Log Manual")
        log = AuditLog(
            user_id=admin.id,
            model_name='TesteModel',
            object_id='999',
            action='UPDATE',
            changes='{"field": "old" -> "new"}'
        )
        db.session.add(log)
        db.session.commit()
        
        retrieved_log = AuditLog.query.get(log.id)
        assert retrieved_log is not None
        assert retrieved_log.model_name == 'TesteModel'
        assert retrieved_log.user.username == 'admin_test'
        print(f"Audit Log criado com sucesso: ID {log.id}")
        
        # 3. Verify Pagination Query (matches route logic)
        print("\n[Teste 2] Verificando Query de Paginação")
        query = AuditLog.query.order_by(AuditLog.timestamp.desc())
        count = query.count()
        print(f"Total Audit Logs: {count}")
        assert count >= 1
        
        page_1 = query.paginate(page=1, per_page=5)
        print(f"Items na pág 1: {len(page_1.items)}")
        
        print("\nSUCESSO: Lógica Admin verificada.")

if __name__ == "__main__":
    verify_admin_logic()
