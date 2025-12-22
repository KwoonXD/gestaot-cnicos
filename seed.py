from app import app, db, Tecnico
from datetime import date

with app.app_context():
    db.create_all()
    t = Tecnico(
        nome='Tecnico Teste',
        contato='11999999999',
        cidade='Sao Paulo',
        estado='SP',
        status='Ativo',
        valor_por_atendimento=100.0, # Legacy value, shouldn't affect new pricing logic
        data_inicio=date.today()
    )
    db.session.add(t)
    db.session.commit()
    print("Database seeded!")
