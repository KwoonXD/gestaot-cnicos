from ..models import db, Chamado, Tecnico
from datetime import datetime
from .audit_service import AuditService

class ChamadoService:
    @staticmethod
    def get_all(filters=None, page=1, per_page=20):
        query = Chamado.query.join(Tecnico)
        
        if filters:
            if filters.get('tecnico_id'):
                query = query.filter(Chamado.tecnico_id == int(filters['tecnico_id']))
            if filters.get('status'):
                query = query.filter(Chamado.status_chamado == filters['status'])
            if filters.get('tipo'):
                query = query.filter(Chamado.tipo_servico == filters['tipo'])
            if filters.get('pago'):
                if filters['pago'] == 'sim':
                    query = query.filter(Chamado.pago == True)
                elif filters['pago'] == 'nao':
                    query = query.filter(Chamado.pago == False)
            if filters.get('search'):
                s = filters['search']
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Chamado.codigo_chamado.ilike(f"%{s}%"),
                        Tecnico.nome.ilike(f"%{s}%")
                    )
                )
        
        # Retorna o objeto Pagination, não a lista (.all)
        return query.order_by(Chamado.data_atendimento.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def get_by_id(id):
        return Chamado.query.get_or_404(id)

    @staticmethod
    def create(data):
        # Anti-duplication check
        # Criteria: Same tecnico + data + tipo OR Same codigo_chamado (if provided and not empty)
        
        tecnico_id = int(data['tecnico_id'])
        data_atendimento = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
        tipo_servico = data['tipo_servico']
        codigo_chamado = data.get('codigo_chamado', '').strip()
        
        # Check by logical key
        existing_logical = Chamado.query.filter_by(
            tecnico_id=tecnico_id,
            data_atendimento=data_atendimento,
            tipo_servico=tipo_servico
        ).first()
        
        if existing_logical:
            # We raise a ValueError to be caught by the controller
            raise ValueError(f"Já existe um chamado para este técnico nesta data e tipo de serviço (ID: {existing_logical.id_chamado}).")
            
        # Check by code if provided
        if codigo_chamado:
            existing_code = Chamado.query.filter_by(codigo_chamado=codigo_chamado).first()
            if existing_code:
                raise ValueError(f"Já existe um chamado com o código '{codigo_chamado}'.")

        horario_inicio = data.get('horario_inicio')
        horario_saida = data.get('horario_saida')
        
        chamado = Chamado(
            tecnico_id=tecnico_id,
            codigo_chamado=codigo_chamado,
            data_atendimento=data_atendimento,
            horario_inicio=datetime.strptime(horario_inicio, '%H:%M').time() if horario_inicio else None,
            horario_saida=datetime.strptime(horario_saida, '%H:%M').time() if horario_saida else None,
            fsa_codes=data.get('fsa_codes', ''),
            tipo_servico=tipo_servico,
            status_chamado=data.get('status_chamado', 'Pendente'),
            valor=float(data.get('valor', 0.0)),
            endereco=data.get('endereco', ''),
            observacoes=data.get('observacoes', '')
        )
        db.session.add(chamado)
        db.session.flush() # Flush to get ID
        
        # Audit creation
        AuditService.log_change(
            model_name='Chamado',
            object_id=chamado.id,
            action='CREATE',
            changes=data
        )
        
        db.session.commit()
        return chamado

    @staticmethod
    def update(id, data):
        chamado = ChamadoService.get_by_id(id)
        
        # Capture old state for audit
        old_data = {
            'valor': float(chamado.valor) if chamado.valor else 0.0,
            'status': chamado.status_chamado,
            'tecnico_id': chamado.tecnico_id,
            'data': chamado.data_atendimento.isoformat() if chamado.data_atendimento else None
        }
        
        horario_inicio = data.get('horario_inicio')
        horario_saida = data.get('horario_saida')
        
        chamado.tecnico_id = int(data['tecnico_id'])
        chamado.codigo_chamado = data.get('codigo_chamado', '')
        chamado.data_atendimento = datetime.strptime(data['data_atendimento'], '%Y-%m-%d').date()
        chamado.horario_inicio = datetime.strptime(horario_inicio, '%H:%M').time() if horario_inicio else None
        chamado.horario_saida = datetime.strptime(horario_saida, '%H:%M').time() if horario_saida else None
        chamado.fsa_codes = data.get('fsa_codes', '')
        chamado.tipo_servico = data['tipo_servico']
        chamado.status_chamado = data.get('status_chamado', 'Pendente')
        chamado.valor = float(data.get('valor', 0.0))
        chamado.endereco = data.get('endereco', '')
        chamado.observacoes = data.get('observacoes', '')
        
        # Calculate changes
        changes = {}
        new_data = {
            'valor': chamado.valor,
            'status': chamado.status_chamado,
            'tecnico_id': chamado.tecnico_id,
            'data': chamado.data_atendimento.isoformat()
        }
        
        for k, v in new_data.items():
            if v != old_data[k]:
                changes[k] = {'old': old_data[k], 'new': v}
        
        if changes:
             AuditService.log_change(
                model_name='Chamado',
                object_id=chamado.id,
                action='UPDATE',
                changes=changes
            )
        
        db.session.commit()
        return chamado

    @staticmethod
    def update_status(id, status):
        chamado = ChamadoService.get_by_id(id)
        chamado.status_chamado = status
        db.session.commit()
        return chamado

    @staticmethod
    def get_evolution_stats():
        from sqlalchemy import func
        from datetime import timedelta
        
        # Last 6 months
        today = datetime.now().date()
        six_months_ago = today - timedelta(days=180) # Approx
        
        # Truncate to first day of that month
        start_date = six_months_ago.replace(day=1)
        
        results = db.session.query(
            func.strftime('%Y-%m', Chamado.data_atendimento).label('mes'),
            func.sum(Chamado.valor).label('total_valor'),
            func.count(Chamado.id).label('total_qtd')
        ).filter(
            Chamado.data_atendimento >= start_date,
            Chamado.status_chamado == 'Concluído'
        ).group_by('mes').order_by('mes').all()
        
        # Format for Chart.js
        labels = []
        custos = []
        volume = []
        
        # Map results to easy lookup
        data_map = {r.mes: r for r in results}
        
        # Generate last 6 months labels strictly
        # Note: This simple loop might miss months if no data, so we fill zeros
        current = start_date
        while current <= today:
            key = current.strftime('%Y-%m')
            label = current.strftime('%b/%Y') # e.g. Dec/2025
            
            val = data_map.get(key)
            labels.append(label)
            custos.append(float(val.total_valor) if val and val.total_valor else 0.0)
            volume.append(int(val.total_qtd) if val else 0)
            
            # Increment month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
                
        return {
            'labels': labels,
            'custos': custos,
            'volume': volume
        }

    @staticmethod
    def get_dashboard_stats():
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        chamados_mes = Chamado.query.filter(
            db.extract('month', Chamado.data_atendimento) == current_month,
            db.extract('year', Chamado.data_atendimento) == current_year
        ).count()
        
        chamados_por_status = {}
        # Avoid direct import of constant to prevent circular dep, or pass it in. 
        # Assuming we can just query distinct or use list.
        # We'll use the query grouping for efficiency in real app, but for now simple:
        for status in ['Pendente', 'Em Andamento', 'Concluído', 'Cancelado']:
             chamados_por_status[status] = Chamado.query.filter_by(status_chamado=status).count()
             
        return {
            'chamados_mes': chamados_mes,
            'chamados_por_status': chamados_por_status,
            'ultimos': Chamado.query.order_by(Chamado.data_criacao.desc()).limit(5).all()
        }
