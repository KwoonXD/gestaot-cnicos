
import logging
import sys
from decimal import Decimal
from datetime import date, datetime
import json

# Configurar logging para arquivo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("verification_phase2.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from src import create_app, db
from src.models import User, Chamado, Tecnico, CatalogoServico, Cliente, ItemLPU, ContratoItem
from src.services.pricing_service import PricingService, ServicoConfig, ChamadoInput, CustoCalculado
from src.services.financeiro_service import FinanceiroService

def verify_pricing_service():
    """Verifica se o PricingService retorna Decimals e calcula corretamente."""
    logger.info("=== Verificando PricingService ===")
    
    # Teste 1: Cálculo Unitário Simples
    logistica = {
        'data_atendimento': date(2025, 1, 1),
        'cidade': 'SÃO PAULO',
        'hora_inicio': '08:00',
        'hora_fim': '10:30', # 2.5 horas
        'horas_trabalhadas': Decimal('2.5')
    }
    
    config = ServicoConfig(
        valor_custo_tecnico=Decimal('100.00'),
        valor_hora_adicional_custo=Decimal('50.00'),
        horas_franquia=Decimal('2.0')
    )
    
    chamado_input = ChamadoInput(
        id=1,
        data_atendimento=logistica['data_atendimento'],
        cidade=logistica['cidade'],
        horas_trabalhadas=logistica['horas_trabalhadas'],
        servico_config=config
    )
    
    # 2.5h trabalho - 2.0h franquia = 0.5h extra
    # Custo Base: 100.00
    # Custo Extra: 0.5 * 50.00 = 25.00
    # Total Esperado: 125.00
    
    resultado = PricingService.calcular_custo_unitario(chamado_input, is_primeiro_lote=True)
    
    logger.info(f"Custo Total Calculado: {resultado.custo_total} (Tipo: {type(resultado.custo_total)})")
    
    assert isinstance(resultado.custo_total, Decimal), "O retorno deve ser Decimal"
    assert resultado.custo_total == Decimal('125.00'), f"Esperado 125.00, recebeu {resultado.custo_total}"
    
    logger.info("Teste 1 (Cálculo Unitário) - OK")

def verify_financeiro_aggregation(app):
    """Verifica se FinanceiroService agrega corretamente com Decimal."""
    logger.info("=== Verificando FinanceiroService ===")
    
    with app.app_context():
        # Limpar chamados antigos de teste
        Chamado.query.filter(Chamado.codigo_chamado.like('TEST-PRECISION-%')).delete()
        
        # Criar Tecnico e Chamados Dummy
        tecnico = Tecnico.query.first()
        if not tecnico:
            logger.warning("Nenhum técnico encontrado para teste financeiro.")
            return

        # Chamado 1: 100.00
        # Chamado 2: 200.00
        # Chamado 3: 50.05
        # Total: 350.05
        
        c1 = Chamado(
            tecnico_id=tecnico.id,
            data_atendimento=date(2025, 2, 1),
            custo_atribuido=Decimal('100.00'),
            valor_receita_total=Decimal('200.00'),
            status_chamado='Concluído',
            codigo_chamado='TEST-PRECISION-1'
        )
        c2 = Chamado(
            tecnico_id=tecnico.id,
            data_atendimento=date(2025, 2, 1),
            custo_atribuido=Decimal('200.00'),
            valor_receita_total=Decimal('400.00'),
            status_chamado='Concluído',
            codigo_chamado='TEST-PRECISION-2'
        )
        c3 = Chamado(
            tecnico_id=tecnico.id,
            data_atendimento=date(2025, 2, 1),
            custo_atribuido=Decimal('50.05'),
            valor_receita_total=Decimal('100.10'),
            status_chamado='Concluído',
            codigo_chamado='TEST-PRECISION-3'
        )
        
        db.session.add_all([c1, c2, c3])
        db.session.commit()
        
        # Testar Projeção Mensal
        proj = FinanceiroService.get_lucro_real_mensal(2025, 2)
        
        logger.info(f"Agregação Financeira: {json.dumps(proj, indent=2)}")
        
        # Verificar precisão (não deve ter .000000001)
        # O retorno é float para JSON, mas deve ser exato
        assert proj['custo_total'] == 350.05, f"Esperado 350.05, recebeu {proj['custo_total']}"
        assert proj['receita_bruta'] == 700.10, f"Esperado 700.10, recebeu {proj['receita_bruta']}"
        
        # Limpar
        Chamado.query.filter(Chamado.codigo_chamado.like('TEST-PRECISION-%')).delete()
        db.session.commit()
        
        logger.info("Teste 2 (Agregação Financeira) - OK")

def verify():
    app = create_app()
    
    # Garantir contexto do banco
    with app.app_context():
        try:
            db.create_all()
            verify_pricing_service()
            verify_financeiro_aggregation(app)
            logger.info("=== TODOS OS TESTES PASSARAM COM SUCESSO ===")
        except Exception as e:
            logger.error(f"FALHA NA VERIFICAÇÃO: {str(e)}", exc_info=True)
            sys.exit(1)

if __name__ == '__main__':
    verify()
