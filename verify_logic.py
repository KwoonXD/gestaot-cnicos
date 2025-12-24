from src import create_app, db
from src.models import Tecnico, Chamado, Pagamento
from src.services.chamado_service import ChamadoService
from src.services.financeiro_service import processar_custos_chamados
from datetime import date, datetime

app = create_app()

def verify():
    with app.app_context():
        print("--- Verificando Lógica Financeira ---")
        
        # 1. Setup Data
        tecnico = Tecnico.query.filter_by(nome="Teste Financeiro").first()
        if not tecnico:
            tecnico = Tecnico(
                nome="Teste Financeiro",
                contato="000",
                cidade="SP",
                estado="SP",
                data_inicio=date.today(),
                valor_por_atendimento=120.00,
                valor_adicional_loja=20.00
            )
            db.session.add(tecnico)
            db.session.commit()
            print(f"Técnico criado: {tecnico.id}")
        else:
            print(f"Usando técnico existente: {tecnico.id}")
            
        # 2. Teste Receita
        print("\n[Teste 1] Receita (Visita + Peça)")
        chamado_data = {
            'tecnico_id': tecnico.id,
            'data_atendimento': date.today().strftime('%Y-%m-%d'),
            'tipo_servico': 'Zebra',
            'tipo_resolucao': 'Resolvido',
            'peca_usada': 'Scanner',
            'loja': 'Lojinha A'
        }
        
        # Simular cálculo interno
        rec_servico, rec_peca = ChamadoService._calcular_receita(chamado_data)
        print(f"Esperado: Servico=190.00, Peca=180.00")
        print(f"Obtido:   Servico={rec_servico}, Peca={rec_peca}")
        assert rec_servico == 190.00
        assert rec_peca == 180.00
        
        print("\n[Teste 2] Receita (Retorno SPARE)")
        chamado_data['tipo_resolucao'] = 'Retorno SPARE'
        rec_servico, rec_peca = ChamadoService._calcular_receita(chamado_data)
        print(f"Esperado: Servico=0.00")
        print(f"Obtido:   Servico={rec_servico}")
        assert rec_servico == 0.00
        
        # 3. Teste Custo (Economia de Escala)
        print("\n[Teste 3] Economia de Escala (5 chamados na mesma loja)")
        # Criar objetos em memória (não precisa salvar no BD para testar a função auxiliar)
        chamados_lote = []
        for i in range(5):
            c = Chamado(
                id=100+i, # Fake ID
                tecnico_id=tecnico.id,
                data_atendimento=date.today(),
                loja="LOJA X",
                status_chamado="Concluído",
                pago=False,
                pagamento_id=None
            )
            chamados_lote.append(c)
            
        # Misturar um de outra loja
        c_outra = Chamado(
            id=200,
            tecnico_id=tecnico.id,
            data_atendimento=date.today(),
            loja="LOJA Y",
            status_chamado="Concluído"
        )
        chamados_lote.append(c_outra)
        
        total = processar_custos_chamados(chamados_lote, tecnico)
        
        print("Valores calculados:")
        for c in chamados_lote:
            print(f"ID {c.id} ({c.loja}): R$ {c.custo_atribuido}")
            
        # Esperado: 
        # Loja X: 1x 120 + 4x 20 = 200
        # Loja Y: 1x 120 = 120
        # Total = 320
        print(f"Total Lote: {total}")
        assert total == 320.00
        
        print("\n[Teste 4] Reembolso Peça")
        c_reembolso = Chamado(
            id=300,
            tecnico_id=tecnico.id,
            data_atendimento=date.today(),
            loja="LOJA Z",
            fornecedor_peca="Tecnico",
            custo_peca=50.00
        )
        total_r = processar_custos_chamados([c_reembolso], tecnico)
        print(f"Custo Atribuído (120 + 50 reembolso): {c_reembolso.custo_atribuido}")
        assert c_reembolso.custo_atribuido == 170.00
        
        print("\nSUCESSO: Todas as regras validadas.")

if __name__ == "__main__":
    verify()
