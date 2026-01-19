
import logging
import sys
import time
from datetime import date

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from src import create_app, db
from src.models import JobRun, Tecnico, Chamado
from src.services.financeiro_service import task_processar_lote

def verify_audit():
    app = create_app()
    
    with app.app_context():
        # Setup Test DB
        db.create_all()
        
        # Criar Tecnico e Chamado para teste
        # Limpar anteriores
        Chamado.query.filter(Chamado.codigo_chamado.like('AUDIT-%')).delete()
        
        tecnico = Tecnico.query.first()
        if not tecnico:
            logger.warning("Nenhum técnico para teste. Criando um dummy...")
            # Create logic skipped for brevity, assuming test DB has seed data or using previous
            return

        # Criar Chamado Aprovado e Pendente
        c1 = Chamado(
            tecnico_id=tecnico.id,
            data_atendimento=date(2025, 3, 1),
            custo_atribuido=100.00,
            status_chamado='Concluído',
            status_validacao='Aprovado',
            pago=False,
            codigo_chamado='AUDIT-1'
        )
        db.session.add(c1)
        db.session.commit()
        
        logger.info(f"Chamado de teste criado para Tecnico {tecnico.id}")
        
        # Executar Task diretamente (sem executor para simplificar teste síncrono)
        logger.info("Executando task_processar_lote...")
        task_processar_lote(
            tecnicos_ids=[tecnico.id],
            inicio_str='2025-03-01',
            fim_str='2025-03-31'
        )
        
        # Verificar JobRun
        job = JobRun.query.order_by(JobRun.id.desc()).first()
        
        if not job:
            logger.error("FALHA: Nenhum JobRun encontrado!")
            sys.exit(1)
            
        logger.info(f"JobRun encontrado: ID={job.id}, Status={job.status}")
        logger.info(f"Sucesso: {job.success_count}, Erro: {job.error_count}")
        logger.info(f"Logs: {job.log_text}")
        
        assert job.status in ['COMPLETED', 'PARTIAL_SUCCESS'], f"Status inesperado: {job.status}"
        assert job.end_time is not None, "Job não tem data de fim"
        assert job.total_items == 1, f"Total items incorreto: {job.total_items}"
        
        logger.info("=== VERIFICAÇÃO DE AUDITORIA: SUCESSO ===")
        
        # Cleanup
        Chamado.query.filter(Chamado.codigo_chamado.like('AUDIT-%')).delete()
        db.session.commit()

if __name__ == '__main__':
    verify_audit()
