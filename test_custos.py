"""
Script de Teste para Lógica de Custos e Receita (Refatoração)
"""
from src import create_app, db
from src.models import Tecnico, Chamado, User, CatalogoServico, Cliente
from src.services.chamado_service import ChamadoService
from datetime import datetime

app = create_app()

def run_test():
    with app.app_context():
        print("🔧 Configurando Cenário de Teste...")
        
        # 1. Setup Técnico Teste
        tec = Tecnico.query.filter_by(nome='Tecnico Teste Cost').first()
        if not tec:
            tec = Tecnico(
                nome='Tecnico Teste Cost',
                cidade='TesteCity',
                estado='SP',
                contato='1199999999',
                valor_por_atendimento=120.00,  # Base
                valor_adicional_loja=20.00,    # Adicional
                valor_hora_adicional=30.00,    # HE
                data_inicio=datetime.now().date()
            )
            db.session.add(tec)
            db.session.commit()
            print(f"✅ Técnico criado: ID {tec.id}")
        else:
            print(f"ℹ️ Técnico existente: ID {tec.id}")
            
        # 2. Setup Serviço Teste
        # Ensure Cliente exists
        cli = Cliente.query.filter_by(nome='Cliente Teste').first()
        if not cli:
            cli = Cliente(nome='Cliente Teste')
            db.session.add(cli)
            db.session.commit()
            
        serv = CatalogoServico.query.filter_by(nome='Servico Teste').first()
        if not serv:
            serv = CatalogoServico(
                nome='Servico Teste',
                valor_receita=200.00, # Receita
                cliente_id=cli.id
            )
            db.session.add(serv)
            db.session.commit()
            print(f"✅ Serviço criado: ID {serv.id}")
        else:
            print(f"ℹ️ Serviço existente: ID {serv.id}")

        # 3. Simular Dados de Entrada (Lote de 3 FSAs, 4 horas de duração)
        # 4 horas de trabalho -> 2h Franquia = 2h Extras
        # HE Valor = 2 * 30.00 = 60.00
        # Custo Esperado Principal: 120.00 + 60.00 = 180.00
        # Custo Esperado Adicional: 20.00
        
        logistica = {
            'tecnico_id': tec.id,
            'data_atendimento': datetime.now().strftime('%Y-%m-%d'),
            'cidade': 'TesteCity',
            'cliente_nome': 'Cliente Teste'
        }
        
        fsas = [
            {
                'codigo_chamado': 'FSA-TEST-01',
                'catalogo_servico_id': serv.id,
                'hora_inicio': '08:00',
                'hora_fim': '12:00', # 4h
            },
            {
                'codigo_chamado': 'FSA-TEST-02', # Adicional
                'catalogo_servico_id': serv.id,
                 # Horas ignoradas no adicional, pega do lote
            },
            {
                'codigo_chamado': 'FSA-TEST-03', # Adicional
                'catalogo_servico_id': serv.id,
            }
        ]
        
        print("\n🚀 Executando create_multiplo...")
        chamados = ChamadoService.create_multiplo(logistica, fsas)
        
        print(f"\n📊 Resultados ({len(chamados)} chamados criados):")
        
        erro = False
        
        # Validação Index 0 (Principal)
        c0 = chamados[0]
        custo_esp_0 = 120.00 + (2.0 * 30.00) # 180.00
        print(f"🔸 Chamado 0 (Principal): {c0.codigo_chamado}")
        print(f"   - Is Adicional: {c0.is_adicional} (Esperado: False)")
        print(f"   - Custo Atribuído: R$ {c0.custo_atribuido} (Esperado: R$ {custo_esp_0:.2f})")
        print(f"   - Valor HE: R$ {c0.valor_horas_extras} (Esperado: R$ 60.00)")
        
        if float(c0.custo_atribuido) != custo_esp_0:
            print("❌ ERRO NO CUSTO DO PRINCIPAL")
            erro = True
            
        # Validação Index 1 (Adicional)
        c1 = chamados[1]
        custo_esp_1 = 20.00
        print(f"🔹 Chamado 1 (Adicional): {c1.codigo_chamado}")
        print(f"   - Is Adicional: {c1.is_adicional} (Esperado: True)")
        print(f"   - Custo Atribuído: R$ {c1.custo_atribuido} (Esperado: R$ {custo_esp_1:.2f})")
        
        if float(c1.custo_atribuido) != custo_esp_1:
            print("❌ ERRO NO CUSTO DO ADICIONAL")
            erro = True
            
        # Limpeza (Rollback manual para não sujar banco de dev, mas aqui vamos deixar para audit)
        # db.session.delete(tec) ...
        
        if not erro:
            print("\n✅ TESTE DE CUSTOS SUCESSO! A lógica está correta.")
            print(f"Receita Total: R$ {sum(float(c.valor_receita_total) for c in chamados):.2f} (Esperado: 600.00)")
        else:
            print("\n❌ TESTE FALHOU.")

if __name__ == '__main__':
    run_test()
