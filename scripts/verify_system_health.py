#!/usr/bin/env python
"""Verificação de integridade do sistema."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import create_app
from src.models import db, Chamado, Tecnico
from sqlalchemy import func, case, and_


def check_chamados_sem_custo():
    """Verifica chamados aprovados sem custo atribuído."""
    result = Chamado.query.filter(
        Chamado.status_validacao == 'Aprovado',
        Chamado.status_chamado.in_(['Concluído', 'SPARE']),
        (Chamado.custo_atribuido == None) | (Chamado.custo_atribuido == 0)
    ).all()
    return [c.id for c in result]


def check_cache_desatualizado():
    """Compara cache de total_a_pagar com valor calculado."""
    problemas = []
    
    pend_cond = and_(
        Chamado.status_chamado.in_(['Concluído', 'SPARE']),
        Chamado.status_validacao == 'Aprovado',
        Chamado.pago == False,
        Chamado.pagamento_id == None
    )
    
    tecnicos = Tecnico.query.filter_by(status='Ativo').all()
    
    for t in tecnicos:
        calculado = db.session.query(
            func.coalesce(func.sum(
                case((pend_cond, Chamado.custo_atribuido), else_=0)
            ), 0)
        ).filter(Chamado.tecnico_id == t.id).scalar()
        
        cached = getattr(t, 'total_a_pagar_cache', None)
        
        if cached is not None and abs(float(cached) - float(calculado)) > 0.01:
            problemas.append({
                'tecnico_id': t.id,
                'cached': float(cached),
                'calculado': float(calculado)
            })
    
    return problemas


def main():
    app = create_app()
    
    with app.app_context():
        issues_found = False
        
        sem_custo = check_chamados_sem_custo()
        if sem_custo:
            print(f"⚠️  Chamados aprovados sem custo: {sem_custo}")
            issues_found = True
        
        cache_issues = check_cache_desatualizado()
        if cache_issues:
            print(f"⚠️  Cache desatualizado: {[c['tecnico_id'] for c in cache_issues]}")
            issues_found = True
        
        if not issues_found:
            print("✅ SYSTEM HEALTHY")
            return 0
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
