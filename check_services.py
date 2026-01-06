from src import create_app, db
from src.models import CatalogoServico, Cliente

app = create_app()

def list_services():
    with app.app_context():
        print("--- Listando Serviços e Preços ---")
        services = CatalogoServico.query.all()
        for s in services:
            print(f"ID {s.id} | Cliente: {s.cliente.nome} | Nome: {s.nome}")
            print(f"   - Receita Integral: {s.valor_receita}")
            print(f"   - Receita Adicional: {s.valor_adicional_receita}")
            print(f"   - Custo Técnico: {s.valor_custo_tecnico}")
            print(f"   - Pagamento Integral: {s.pagamento_integral}")
            print("-" * 30)

if __name__ == "__main__":
    list_services()
