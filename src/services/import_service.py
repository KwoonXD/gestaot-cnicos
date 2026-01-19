import pandas as pd
from ..models import db, Tecnico
import re
from sqlalchemy import or_

class ImportService:
    @staticmethod
    def clean_cpf_cnpj(documento):
        if not documento:
            return None
        # Remove anything that is not a digit
        cleaned = re.sub(r'[^0-9]', '', str(documento))
        return cleaned if cleaned else None

    @staticmethod
    def normalize_columns(df):
        """Normalize column names to lower case without accents/spaces for easier matching."""
        normalized = {}
        for col in df.columns:
            clean_col = col.lower().strip().replace('ç', 'c').replace('ã', 'a').replace('é', 'e').replace(' ', '_')
            normalized[clean_col] = col
        return normalized

    @staticmethod
    def analisar_arquivo(file_storage):
        """
        Lê o arquivo e retorna preview para validação antes da importação real.
        """
        filename = file_storage.filename
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file_storage)
            else:
                df = pd.read_excel(file_storage)
        except Exception as e:
            return {'success': False, 'message': f'Erro ao ler arquivo: {str(e)}'}
            
        col_map = ImportService.normalize_columns(df)
        
        # Mapeamento
        def get_col(candidates):
            for c in candidates:
                if c in col_map: return col_map[c]
            return None
            
        mapping = {
            'nome': get_col(['nome', 'nome_completo', 'tecnico', 'nome_tecnico']),
            'documento': get_col(['documento', 'cpf', 'cnpj', 'doc', 'cpf_cnpj']),
            'telefone': get_col(['telefone', 'celular', 'contato', 'whatsapp', 'tel']),
            'cidade': get_col(['cidade', 'municipio']),
            'estado': get_col(['estado', 'uf']),
            'pix': get_col(['pix', 'chave_pix', 'chave_pagamento'])
        }
        
        # Validação Básica
        missing_required = []
        if not mapping['nome']: missing_required.append('Nome')
        if not mapping['documento']: missing_required.append('Documento/CPF')
        
        # Preview das primeiras 5 linhas
        preview_rows = []
        df_head = df.head(10).fillna('')
        
        for _, row in df_head.iterrows():
            preview_rows.append(row.to_dict())
            
        return {
            'success': True,
            'total_rows': len(df),
            'columns': list(df.columns),
            'mapping': mapping,
            'missing_required': missing_required,
            'preview': preview_rows
        }

    @staticmethod
    def importar_tecnicos(file_storage):
        filename = file_storage.filename
        
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file_storage)
            else:
                df = pd.read_excel(file_storage)
        except Exception as e:
            return {'success': False, 'message': f'Erro ao ler arquivo: {str(e)}'}

        # Column Mapping Logic
        # Expected keys (our internal names) -> Possible external headers
        col_map = ImportService.normalize_columns(df)
        
        # Helper to find column in df by fuzzy validation
        def get_col(candidates):
            for c in candidates:
                if c in col_map:
                    return col_map[c]
            return None

        col_nome = get_col(['nome', 'nome_completo', 'tecnico', 'nome_tecnico'])
        col_doc = get_col(['documento', 'cpf', 'cnpj', 'doc', 'cpf_cnpj'])
        col_tel = get_col(['telefone', 'celular', 'contato', 'whatsapp', 'tel'])
        col_cidade = get_col(['cidade', 'municipio'])
        col_estado = get_col(['estado', 'uf'])
        col_pix = get_col(['pix', 'chave_pix', 'chave_pagamento'])
        
        if not col_nome:
            return {'success': False, 'message': 'Coluna "Nome" não encontrada.'}
        if not col_doc:
            return {'success': False, 'message': 'Coluna "Documento" (ou CPF) não encontrada.'}

        stats = {'total': 0, 'created': 0, 'updated': 0, 'errors': 0}
        
        for index, row in df.iterrows():
            stats['total'] += 1
            try:
                nome = str(row[col_nome]).strip()
                raw_doc = row[col_doc]
                documento = ImportService.clean_cpf_cnpj(raw_doc)
                
                if not nome:
                    raise ValueError(f"Erro na linha {index + 2}: Nome não pode ser vazio.")
                if not documento:
                    raise ValueError(f"Erro na linha {index + 2}: Documento (CPF/CNPJ) não pode ser vazio ou inválido.")

                # Optional fields
                contato = str(row[col_tel]).strip() if col_tel and pd.notna(row[col_tel]) else ''
                cidade = str(row[col_cidade]).strip() if col_cidade and pd.notna(row[col_cidade]) else 'Desconhecida'
                estado = str(row[col_estado]).strip().upper() if col_estado and pd.notna(row[col_estado]) else 'UF'
                chave_pagamento = str(row[col_pix]).strip() if col_pix and pd.notna(row[col_pix]) else None
                
                # Check duplication by Documento
                existing = Tecnico.query.filter_by(documento=documento).first()
                
                if existing:
                    # Update
                    existing.nome = nome
                    if contato: existing.contato = contato
                    if cidade != 'Desconhecida': existing.cidade = cidade
                    if estado != 'UF': existing.estado = estado
                    if chave_pagamento: existing.chave_pagamento = chave_pagamento
                    stats['updated'] += 1
                else:
                    # Create
                    new_tecnico = Tecnico(
                        nome=nome,
                        documento=documento,
                        contato=contato,
                        cidade=cidade,
                        estado=estado,
                        chave_pagamento=chave_pagamento,
                        # Defaults
                        valor_por_atendimento=150.00, # Default logic
                        data_inicio=pd.Timestamp.now().date()
                    )
                    db.session.add(new_tecnico)
                    stats['created'] += 1
                    
            except Exception as e:
                # C1: Standardize contract - Raise exception to trigger rollback in caller
                raise ValueError(f"Erro na linha {index + 2}: {str(e)}")
        
        # Transação agora é gerenciada pela rota (Unit of Work)
        # Retorno de sucesso implica que nenhuma exceção ocorreu
        
        return {
            'success': True, 
            'message': f"Importação concluída com sucesso! Novos: {stats['created']}, Atualizados: {stats['updated']}",
            'stats': stats
        }
