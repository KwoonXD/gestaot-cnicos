import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from src.models import Tecnico, Chamado, Pagamento
from src.services.financeiro_service import task_processar_lote

def test_batch_transaction_isolation(app, db):
    """
    Test P0: Verify that an error in one technician during batch processing 
    does not roll back successful processing of previous technicians.
    """
    # 1. Setup Data
    try:
        t1 = Tecnico(nome="Tecnico 1", valor_por_atendimento=100.0, contato="00", cidade="SP", estado="SP", data_inicio=date(2025,1,1))
        t2 = Tecnico(nome="Tecnico 2", valor_por_atendimento=100.0, contato="00", cidade="SP", estado="SP", data_inicio=date(2025,1,1))
        t3 = Tecnico(nome="Tecnico 3", valor_por_atendimento=100.0, contato="00", cidade="SP", estado="SP", data_inicio=date(2025,1,1))
        db.session.add_all([t1, t2, t3])
        db.session.flush()

        c1 = Chamado(tecnico_id=t1.id, status_chamado='Concluído', status_validacao='Aprovado', data_atendimento=date(2025,1,1), pago=False)
        c2 = Chamado(tecnico_id=t2.id, status_chamado='Concluído', status_validacao='Aprovado', data_atendimento=date(2025,1,1), pago=False)
        c3 = Chamado(tecnico_id=t3.id, status_chamado='Concluído', status_validacao='Aprovado', data_atendimento=date(2025,1,1), pago=False)
        db.session.add_all([c1, c2, c3])
        db.session.commit()

        # 2. Mock Error for T2
        # We patch 'processar_custos_chamados' to fail only for T2
        with patch('src.services.financeiro_service.processar_custos_chamados') as mock_process:
            def side_effect(chamados, tecnico):
                if tecnico.id == t2.id:
                    raise Exception("Simulated Error for T2")
                return 100.0 # Success for others
            
            mock_process.side_effect = side_effect
            
            # 3. Run Batch
            task_processar_lote([t1.id, t2.id, t3.id], '2025-01-01', '2025-01-31')

        # 4. Assertions
        # T1: Should have payment
        p1 = Pagamento.query.filter_by(tecnico_id=t1.id).first()
        assert p1 is not None, "T1 should be paid (transaction committed)"

        # T2: Should NOT have payment
        p2 = Pagamento.query.filter_by(tecnico_id=t2.id).first()
        assert p2 is None, "T2 should NOT be paid (rolled back)"
        
        # T3: Should have payment
        p3 = Pagamento.query.filter_by(tecnico_id=t3.id).first()
        assert p3 is not None, "T3 should be paid (transaction isolated)"
        
    except Exception as e:
        with open('debug_test_error.txt', 'w') as f:
            f.write(f"ERROR: {str(e)}\n")
            import traceback
            f.write(traceback.format_exc())
        raise e
