from src import create_app, db
from src.models import Tecnico, Chamado, Pagamento, Cliente, CatalogoServico, ItemLPU
from src.services.chamado_service import ChamadoService
from src.services.report_service import ReportService
from datetime import date, datetime

app = create_app()

def verify():
    with app.app_context():
        print("--- Verificando Lógica de Receita e Relatório ---")
        
        # 1. Setup Models - Recuperar ou Criar
        cliente = Cliente.query.filter_by(nome="Cliente Teste Verify").first()
        if not cliente:
            print("Criando Cliente...")
            cliente = Cliente(nome="Cliente Teste Verify", ativo=True)
            db.session.add(cliente)
            db.session.commit()
            # Refresh to get ID
            db.session.refresh(cliente)
        print(f"Cliente ID: {cliente.id}")
            
        tecnico = Tecnico.query.filter_by(nome="Tecnico Verify").first()
        if not tecnico:
            print("Criando Técnico...")
            tecnico = Tecnico(nome="Tecnico Verify", contato="88", cidade="Sao Paulo", estado="SP", data_inicio=date.today())
            db.session.add(tecnico)
            db.session.commit()
            db.session.refresh(tecnico)
        print(f"Técnico ID: {tecnico.id}")
            
        # Serviço Padrão: 100 reais receita, 0.0033? algo assim para gerar centavos?
        # Vamos testar com 100.00 e 0.00 (Caso do Lote)
        servico = CatalogoServico.query.filter_by(nome="Servico Verify", cliente_id=cliente.id).first()
        if not servico:
            print("Criando Serviço...")
            servico = CatalogoServico(
                nome="Servico Verify",
                cliente_id=cliente.id,
                valor_receita=100.00,        # Principal
                valor_custo_tecnico=50.00,
                valor_adicional_receita=0.00,# Adicional
                valor_adicional_custo=0.00,
                pagamento_integral=False     # Aplica regra de lote
            )
            db.session.add(servico)
            db.session.commit()
            db.session.refresh(servico)
        print(f"Serviço ID: {servico.id}")
            
        # 2. Simular Lote de 4 Chamados
        # Enviando como Batch (Formulário Multiplo)
        print(f"\nCriando lote de 4 chamados para Tecnico {tecnico.id}...")
        logistica = {
            'tecnico_id': tecnico.id,
            'data_atendimento': '2026-01-05',
            'cidade': 'Sao Paulo',
            'hora_inicio': '08:00',
            'hora_fim': '12:00'
        }
        
        fsas = []
        for i in range(4):
            fsas.append({
                'codigo_chamado': f'FSA-VERIFY-{datetime.now().microsecond}-{i}',
                'catalogo_servico_id': servico.id,
                'hora_inicio': '08:00',
                'hora_fim': '09:00'
            })
            
        chamados_criados = ChamadoService.create_multiplo(logistica, fsas)
        
        print("\nChamados Criados:")
        total_receita_db = 0.0
        for c in chamados_criados:
            val = float(c.valor_receita_total or 0)
            print(f"ID {c.id}: Receita Total={val} | Adicional={c.is_adicional}")
            total_receita_db += val
            
        print(f"Total Receita (DB Soma Manual): {total_receita_db}")
        
        # 3. Validar ReportService
        inicio = datetime.strptime('2026-01-01', '%Y-%m-%d').date()
        fim = datetime.strptime('2026-01-31', '%Y-%m-%d').date()
        
        print("\nExecutando ReportService.rentabilidade_geografica...")
        report = ReportService.rentabilidade_geografica(inicio, fim)
        
        print("Resultados para Sao Paulo:")
        for row in report:
            if row['cidade'] == 'Sao Paulo':
                print(row)

if __name__ == "__main__":
    verify()
