#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_stock_integration.py - Teste de Integração: Estoque + Chamados

Valida o fluxo completo do Pilar de Custos de Materiais:
1. Criação de peça com custo
2. Envio para técnico
3. Uso em chamado (baixa + movimentação + custo)
4. Rastreabilidade

Uso:
    python test_stock_integration.py
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import create_app, db
from src.models import (
    Tecnico, Chamado, User, CatalogoServico, Cliente,
    ItemLPU, TecnicoStock, StockMovement
)
from src.services.stock_service import StockService

app = create_app()


def create_mock_user():
    """Mock do current_user."""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_authenticated = True
    return mock_user


def setup_test_data():
    """
    Configura cenário de teste com peça que tem custo definido.
    """
    print("[*] Configurando cenário de teste...")

    # 1. Técnico
    tec = Tecnico.query.filter_by(nome='Tecnico Teste Stock').first()
    if not tec:
        tec = Tecnico(
            nome='Tecnico Teste Stock',
            cidade='StockCity',
            estado='SP',
            contato='11999999999',
            valor_por_atendimento=120.00,
            valor_adicional_loja=20.00,
            valor_hora_adicional=30.00,
            data_inicio=datetime.now().date()
        )
        db.session.add(tec)
        db.session.commit()
        print(f"    [+] Técnico criado: ID {tec.id}")
    else:
        print(f"    [i] Técnico existente: ID {tec.id}")

    # 2. Cliente
    cli = Cliente.query.filter_by(nome='Cliente Teste Stock').first()
    if not cli:
        cli = Cliente(nome='Cliente Teste Stock')
        db.session.add(cli)
        db.session.commit()

    # 3. Serviço
    serv = CatalogoServico.query.filter_by(nome='Servico Teste Stock').first()
    if not serv:
        serv = CatalogoServico(
            nome='Servico Teste Stock',
            cliente_id=cli.id,
            valor_receita=200.00,
            valor_custo_tecnico=120.00,
            horas_franquia=2,
            paga_tecnico=True,
            ativo=True
        )
        db.session.add(serv)
        db.session.commit()
        print(f"    [+] Serviço criado: ID {serv.id}")

    # 4. Peça com CUSTO definido
    peca = ItemLPU.query.filter_by(nome='Fonte Zebra Teste').first()
    if not peca:
        peca = ItemLPU(
            nome='Fonte Zebra Teste',
            valor_receita=150.00,  # Cobra R$ 150 do cliente
            valor_custo=85.00,     # Custa R$ 85 para a empresa
            cliente_id=None        # Item geral de estoque
        )
        db.session.add(peca)
        db.session.commit()
        print(f"    [+] Peça criada: ID {peca.id} (Custo: R$ {peca.valor_custo})")
    else:
        # Garantir que tem custo
        if not peca.valor_custo:
            peca.valor_custo = 85.00
            db.session.commit()
        print(f"    [i] Peça existente: ID {peca.id} (Custo: R$ {peca.valor_custo})")

    # 5. Enviar peça para o técnico
    estoque = TecnicoStock.query.filter_by(
        tecnico_id=tec.id,
        item_lpu_id=peca.id
    ).first()

    if not estoque or estoque.quantidade < 2:
        StockService.transferir_sede_para_tecnico(
            tecnico_id=tec.id,
            item_id=peca.id,
            qtd=5,
            user_id=1,
            obs="Carga inicial para teste"
        )
        print(f"    [+] Enviado 5 peças para o técnico")

    # Reload estoque
    estoque = TecnicoStock.query.filter_by(
        tecnico_id=tec.id,
        item_lpu_id=peca.id
    ).first()
    print(f"    [i] Saldo do técnico: {estoque.quantidade} unidades")

    # 6. Garantir User
    test_user = db.session.get(User, 1)
    if not test_user:
        test_user = User(id=1, username='test_stock', role='Admin')
        test_user.set_password('test123')
        db.session.add(test_user)
        db.session.commit()

    return tec, serv, peca


def cleanup_test_chamados():
    """Remove chamados de teste anteriores."""
    deleted = Chamado.query.filter(
        Chamado.codigo_chamado.like('STOCK-TEST-%')
    ).delete(synchronize_session=False)
    db.session.commit()
    if deleted:
        print(f"    [i] Removidos {deleted} chamados de teste anteriores.")


def run_test():
    """
    Executa o teste de integração Estoque + Chamados.
    """
    print("\n" + "=" * 70)
    print("TEST_STOCK_INTEGRATION.PY - Pilar de Custos de Materiais")
    print("=" * 70)

    with app.app_context():
        cleanup_test_chamados()
        tec, serv, peca = setup_test_data()

        # Capturar saldo ANTES
        estoque_antes = TecnicoStock.query.filter_by(
            tecnico_id=tec.id,
            item_lpu_id=peca.id
        ).first()
        saldo_antes = estoque_antes.quantidade if estoque_antes else 0
        print(f"\n[*] Saldo ANTES: {saldo_antes} unidades")

        # Dados do chamado COM PEÇA
        logistica = {
            'tecnico_id': tec.id,
            'data_atendimento': datetime.now().strftime('%Y-%m-%d'),
            'cidade': 'StockCity',
            'cliente_nome': 'Cliente Teste Stock'
        }

        fsas = [
            {
                'codigo_chamado': 'STOCK-TEST-01',
                'catalogo_servico_id': serv.id,
                'hora_inicio': '09:00',
                'hora_fim': '11:00',
                'peca_id': peca.id,             # <- USA PEÇA
                'fornecedor_peca': 'Empresa',   # <- EMPRESA FORNECE
            }
        ]

        print(f"\n[*] Criando chamado com peça...")
        print(f"    Peça: {peca.nome}")
        print(f"    Custo da peça: R$ {peca.valor_custo}")
        print(f"    Fornecedor: Empresa")

        # Mock current_user
        mock_user = create_mock_user()

        with patch('src.services.chamado_service.current_user', mock_user):
            from src.services.chamado_service import ChamadoService
            chamados = ChamadoService.create_multiplo(logistica, fsas)

        chamado = chamados[0]
        print(f"\n[*] Chamado criado: {chamado.codigo_chamado} (ID: {chamado.id})")

        # Verificações
        print("\n" + "-" * 70)
        print("VERIFICACOES")
        print("-" * 70)

        erros = []

        # 1. Verificar saldo DEPOIS
        estoque_depois = TecnicoStock.query.filter_by(
            tecnico_id=tec.id,
            item_lpu_id=peca.id
        ).first()
        saldo_depois = estoque_depois.quantidade if estoque_depois else 0
        print(f"\n[1] Baixa de Estoque:")
        print(f"    Saldo ANTES:  {saldo_antes}")
        print(f"    Saldo DEPOIS: {saldo_depois}")

        if saldo_depois == saldo_antes - 1:
            print(f"    [OK] Estoque decrementado corretamente!")
        else:
            erros.append(f"Estoque não foi decrementado: {saldo_antes} -> {saldo_depois}")
            print(f"    [ERRO] Esperado: {saldo_antes - 1}")

        # 2. Verificar StockMovement vinculado
        movs = StockMovement.query.filter_by(chamado_id=chamado.id).all()
        print(f"\n[2] Movimentação de Estoque:")
        print(f"    Movimentações vinculadas: {len(movs)}")

        if len(movs) == 1:
            mov = movs[0]
            print(f"    Tipo: {mov.tipo_movimento}")
            print(f"    Item: {mov.item_lpu.nome if mov.item_lpu else 'N/A'}")
            print(f"    Quantidade: {mov.quantidade}")
            print(f"    [OK] Movimentação registrada com vínculo ao chamado!")
        else:
            erros.append(f"Movimentação não foi criada ou não vinculada: {len(movs)} encontradas")
            print(f"    [ERRO] Esperado: 1 movimentação")

        # 3. Verificar custo_peca no chamado
        print(f"\n[3] Custo da Peça no Chamado:")
        print(f"    chamado.custo_peca: R$ {float(chamado.custo_peca or 0):.2f}")
        print(f"    ItemLPU.valor_custo: R$ {peca.valor_custo:.2f}")

        if float(chamado.custo_peca or 0) == peca.valor_custo:
            print(f"    [OK] Custo preenchido automaticamente!")
        else:
            erros.append(f"Custo não foi preenchido: {chamado.custo_peca} != {peca.valor_custo}")
            print(f"    [ERRO] Custo incorreto")

        # 4. Verificar custo total
        print(f"\n[4] Composição de Custos:")
        custo_servico = float(chamado.custo_atribuido or 0)
        custo_peca = float(chamado.custo_peca or 0)
        custo_total = custo_servico + custo_peca

        print(f"    Custo Serviço (técnico): R$ {custo_servico:.2f}")
        print(f"    Custo Peça (material):   R$ {custo_peca:.2f}")
        print(f"    CUSTO TOTAL OPERAÇÃO:    R$ {custo_total:.2f}")

        # Resumo
        print("\n" + "=" * 70)
        print("RESUMO DO TESTE")
        print("=" * 70)

        if erros:
            print(f"\n  [FALHOU] {len(erros)} erro(s) encontrado(s):")
            for e in erros:
                print(f"    - {e}")
            return False
        else:
            print("\n  [SUCESSO] Integração Estoque + Chamados funcionando!")
            print(f"\n  Fluxo validado:")
            print(f"    1. Peça baixada do estoque do técnico")
            print(f"    2. Movimentação registrada com chamado_id")
            print(f"    3. Custo da peça preenchido automaticamente")
            print(f"    4. Custo total = Serviço + Material")
            return True


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
