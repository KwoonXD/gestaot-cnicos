from flask import Blueprint, render_template, abort
from ..models import Tecnico, Chamado, Pagamento

public_bp = Blueprint('public', __name__)

@public_bp.route('/extrato/<string:token>')
def extrato_tecnico(token):
    # Busca o técnico pelo token seguro
    tecnico = Tecnico.query.filter_by(token_acesso=token).first()
    
    if not tecnico:
        abort(404) # Não revela se o token existe ou não, apenas 404
        
    # Busca pagamentos (apenas status finalizados para não gerar ansiedade com "Pendente")
    pagamentos = tecnico.pagamentos.order_by(Pagamento.periodo_fim.desc()).all()
    
    # Chamados recentes (últimos 30 dias) para conferência
    chamados_recentes = tecnico.chamados.order_by(Chamado.data_atendimento.desc()).limit(20).all()
    
    return render_template('public_extrato.html', 
                           tecnico=tecnico, 
                           pagamentos=pagamentos,
                           chamados=chamados_recentes)
