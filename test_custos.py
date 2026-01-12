#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_custos.py - Script de Teste para Logica de Custos e Receita

Este script testa a criacao de chamados em lote e valida:
1. Calculo correto de custo_atribuido (principal vs adicional)
2. Calculo de horas extras
3. Regras de lote do PricingService

IMPORTANTE: Usa mock do current_user para rodar fora do contexto HTTP.

Uso:
    python test_custos.py
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import create_app, db
from src.models import Tecnico, Chamado, User, CatalogoServico, Cliente

app = create_app()


def create_mock_user():
    """
    Cria um mock do objeto current_user do Flask-Login.
    Simula um usuario autenticado com ID 1.
    """
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.is_anonymous = False
    mock_user.get_id.return_value = '1'
    return mock_user


def setup_test_data():
    """
    Configura dados de teste (Tecnico, Cliente, Servico).
    Retorna tuple: (tecnico, servico)
    """
    print("[*] Configurando cenario de teste...")

    # 1. Setup Tecnico Teste
    tec = Tecnico.query.filter_by(nome='Tecnico Teste Cost').first()
    if not tec:
        tec = Tecnico(
            nome='Tecnico Teste Cost',
            cidade='TesteCity',
            estado='SP',
            contato='11999999999',
            valor_por_atendimento=120.00,  # Base
            valor_adicional_loja=20.00,    # Adicional
            valor_hora_adicional=30.00,    # HE
            data_inicio=datetime.now().date()
        )
        db.session.add(tec)
        db.session.commit()
        print(f"    [+] Tecnico criado: ID {tec.id}")
    else:
        print(f"    [i] Tecnico existente: ID {tec.id}")

    # 2. Setup Cliente Teste
    cli = Cliente.query.filter_by(nome='Cliente Teste').first()
    if not cli:
        cli = Cliente(nome='Cliente Teste')
        db.session.add(cli)
        db.session.commit()
        print(f"    [+] Cliente criado: ID {cli.id}")

    # 3. Setup Servico Teste (com valores de custo definidos)
    serv = CatalogoServico.query.filter_by(nome='Servico Teste Cost').first()
    if not serv:
        serv = CatalogoServico(
            nome='Servico Teste Cost',
            cliente_id=cli.id,
            # Receita
            valor_receita=200.00,
            valor_adicional_receita=50.00,
            valor_hora_adicional_receita=40.00,
            # Custo (para o tecnico)
            valor_custo_tecnico=120.00,
            valor_adicional_custo=20.00,
            valor_hora_adicional_custo=30.00,
            # Regras
            horas_franquia=2,
            paga_tecnico=True,
            pagamento_integral=False,
            exige_peca=False,
            ativo=True
        )
        db.session.add(serv)
        db.session.commit()
        print(f"    [+] Servico criado: ID {serv.id}")
    else:
        print(f"    [i] Servico existente: ID {serv.id}")

    return tec, serv


def cleanup_test_chamados():
    """Remove chamados de teste anteriores."""
    deleted = Chamado.query.filter(
        Chamado.codigo_chamado.like('FSA-TEST-%')
    ).delete(synchronize_session=False)
    db.session.commit()
    if deleted:
        print(f"    [i] Removidos {deleted} chamados de teste anteriores.")


def run_test():
    """
    Executa o teste de criacao de chamados em lote.
    Valida custos calculados pelo PricingService.
    """
    print("\n" + "=" * 60)
    print("TEST_CUSTOS.PY - Teste de Logica de Custos")
    print("=" * 60)

    with app.app_context():
        # Limpa chamados de teste anteriores
        cleanup_test_chamados()

        # Setup dados
        tec, serv = setup_test_data()

        # Garantir que existe um User para o mock
        test_user = User.query.get(1)
        if not test_user:
            test_user = User(id=1, username='test_user', role='Admin')
            test_user.set_password('test123')
            db.session.add(test_user)
            db.session.commit()
            print(f"    [+] Usuario de teste criado: ID {test_user.id}")

        # Dados de entrada para o lote
        # Cenario: 3 FSAs, primeiro com 4 horas (2h extras)
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
                'hora_fim': '12:00',  # 4h de trabalho -> 2h extras
            },
            {
                'codigo_chamado': 'FSA-TEST-02',  # Adicional (mesmo lote)
                'catalogo_servico_id': serv.id,
                # Sem horas - assume franquia
            },
            {
                'codigo_chamado': 'FSA-TEST-03',  # Adicional (mesmo lote)
                'catalogo_servico_id': serv.id,
            }
        ]

        # Calculos esperados:
        # FSA-01 (Principal): custo_tecnico(120) + horas_extras(2 * 30) = R$ 180.00
        # FSA-02 (Adicional): valor_adicional_custo = R$ 20.00
        # FSA-03 (Adicional): valor_adicional_custo = R$ 20.00
        # Total Custo: R$ 220.00

        print("\n[*] Executando ChamadoService.create_multiplo()...")
        print(f"    Tecnico: {tec.nome} (ID: {tec.id})")
        print(f"    Servico: {serv.nome} (ID: {serv.id})")
        print(f"    FSAs: {len(fsas)}")

        # MOCK do current_user para evitar AttributeError
        mock_user = create_mock_user()

        # Patch do current_user no modulo chamado_service
        with patch('src.services.chamado_service.current_user', mock_user):
            from src.services.chamado_service import ChamadoService
            chamados = ChamadoService.create_multiplo(logistica, fsas)

        print(f"\n[*] {len(chamados)} chamados criados com sucesso!")

        # Validacao
        print("\n" + "-" * 60)
        print("RESULTADOS")
        print("-" * 60)

        erros = []

        # Ordenar por is_adicional para ter principal primeiro
        chamados_sorted = sorted(chamados, key=lambda c: (c.is_adicional, c.id))

        for i, chamado in enumerate(chamados_sorted):
            is_principal = not chamado.is_adicional
            tipo = "PRINCIPAL" if is_principal else "ADICIONAL"

            print(f"\n[{i}] {chamado.codigo_chamado} ({tipo})")
            print(f"    is_adicional:    {chamado.is_adicional}")
            print(f"    horas_trabalhadas: {chamado.horas_trabalhadas}")
            print(f"    valor_horas_extras: R$ {float(chamado.valor_horas_extras or 0):.2f}")
            print(f"    custo_atribuido:   R$ {float(chamado.custo_atribuido or 0):.2f}")
            print(f"    valor_receita:     R$ {float(chamado.valor_receita_total or 0):.2f}")

            # Validacoes
            custo = float(chamado.custo_atribuido or 0)

            if is_principal:
                # Principal: 120 + (2h * 30) = 180
                esperado = 180.00
                if abs(custo - esperado) > 0.01:
                    erros.append(f"Chamado {chamado.codigo_chamado}: custo={custo}, esperado={esperado}")
                    print(f"    [ERRO] Custo esperado: R$ {esperado:.2f}")
                else:
                    print(f"    [OK] Custo correto!")
            else:
                # Adicional: 20
                esperado = 20.00
                if abs(custo - esperado) > 0.01:
                    erros.append(f"Chamado {chamado.codigo_chamado}: custo={custo}, esperado={esperado}")
                    print(f"    [ERRO] Custo esperado: R$ {esperado:.2f}")
                else:
                    print(f"    [OK] Custo correto!")

        # Resumo
        print("\n" + "=" * 60)
        print("RESUMO DO TESTE")
        print("=" * 60)

        total_custo = sum(float(c.custo_atribuido or 0) for c in chamados)
        total_receita = sum(float(c.valor_receita_total or 0) for c in chamados)

        print(f"\n  Total Custo (tecnico):  R$ {total_custo:.2f}")
        print(f"  Total Receita (empresa): R$ {total_receita:.2f}")
        print(f"  Margem Bruta:            R$ {total_receita - total_custo:.2f}")

        if erros:
            print(f"\n  [FALHOU] {len(erros)} erro(s) encontrado(s):")
            for erro in erros:
                print(f"    - {erro}")
            return False
        else:
            print("\n  [SUCESSO] Todos os calculos estao corretos!")
            return True


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
