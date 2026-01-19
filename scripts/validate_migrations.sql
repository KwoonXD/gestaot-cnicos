-- =============================================================================
-- VALIDAÇÃO DE MIGRATIONS PARA PRODUCÃO (PostgreSQL)
-- =============================================================================
-- Execute: psql -d DATABASE_NAME -f scripts/validate_migrations.sql
-- =============================================================================

\echo '========================================'
\echo 'VALIDAÇÃO DE MIGRATIONS - PRODUÇÃO'
\echo '========================================'

-- 1. Verificar versão do Alembic
\echo ''
\echo '[CHECK 1] Versão do Alembic'
SELECT 
    CASE 
        WHEN version_num = 'a004' THEN '✓ OK: ' || version_num
        ELSE '⚠ WARN: ' || COALESCE(version_num, 'NULL') || ' (esperado: a004)'
    END AS status
FROM alembic_version;

-- 2. Verificar se chamados.valor é nullable
\echo ''
\echo '[CHECK 2] chamados.valor nullable'
SELECT 
    CASE 
        WHEN is_nullable = 'YES' THEN '✓ OK: campo é nullable'
        ELSE '✗ FAIL: campo é NOT NULL (drift detectado)'
    END AS status
FROM information_schema.columns
WHERE table_name = 'chamados' AND column_name = 'valor';

-- 3. Verificar constraints de integridade
\echo ''
\echo '[CHECK 3] Constraints de integridade'
SELECT 
    conname AS constraint_name,
    contype AS type,
    '✓ Presente' AS status
FROM pg_constraint
WHERE conname IN (
    'uq_tecnico_stock_tecnico_item',
    'ck_stock_movements_quantidade_positive',
    'ck_stock_movements_tipo_movimento',
    'ck_solicitacoes_reposicao_status',
    'ck_chamados_status_chamado',
    'ck_chamados_status_validacao'
)
ORDER BY conname;

-- 4. Verificar duplicidades em tecnico_stock
\echo ''
\echo '[CHECK 4] Duplicidades em tecnico_stock'
SELECT 
    CASE 
        WHEN COUNT(*) = 0 THEN '✓ OK: Sem duplicidades'
        ELSE '✗ FAIL: ' || COUNT(*) || ' duplicidades encontradas'
    END AS status
FROM (
    SELECT tecnico_id, item_lpu_id
    FROM tecnico_stock
    GROUP BY tecnico_id, item_lpu_id
    HAVING COUNT(*) > 1
) duplicates;

-- 5. Verificar quantidades inválidas em stock_movements
\echo ''
\echo '[CHECK 5] Quantidades em stock_movements'
SELECT 
    CASE 
        WHEN COUNT(*) = 0 THEN '✓ OK: Todas quantidades válidas'
        ELSE '✗ FAIL: ' || COUNT(*) || ' quantidades <= 0 ou NULL'
    END AS status
FROM stock_movements
WHERE quantidade IS NULL OR quantidade <= 0;

-- 6. Verificar tipos monetários (devem ser numeric, não float)
\echo ''
\echo '[CHECK 6] Tipos monetários'
SELECT 
    table_name,
    column_name,
    data_type,
    CASE 
        WHEN data_type = 'numeric' THEN '✓ OK'
        WHEN data_type = 'double precision' THEN '⚠ WARN: é FLOAT'
        ELSE '? ' || data_type
    END AS status
FROM information_schema.columns
WHERE table_name IN ('catalogo_servicos', 'itens_lpu', 'chamados', 'stock_movements')
AND column_name IN (
    'valor_receita', 'valor_custo', 'valor_custo_tecnico',
    'valor_adicional_receita', 'valor_adicional_custo',
    'valor_hora_adicional_receita', 'valor_hora_adicional_custo',
    'custo_atribuido', 'valor', 'custo_unitario'
)
ORDER BY table_name, column_name;

-- 7. Verificar status inválidos em chamados
\echo ''
\echo '[CHECK 7] Status inválidos em chamados'
SELECT 
    'status_chamado' AS campo,
    status_chamado AS valor,
    COUNT(*) AS quantidade,
    '⚠ Valor fora do domínio' AS status
FROM chamados
WHERE status_chamado NOT IN (
    'Pendente', 'Em Análise', 'Em Andamento', 
    'Concluído', 'Cancelado', 'SPARE', 'Finalizado'
)
AND status_chamado IS NOT NULL
GROUP BY status_chamado
UNION ALL
SELECT 
    'status_validacao' AS campo,
    status_validacao AS valor,
    COUNT(*) AS quantidade,
    '⚠ Valor fora do domínio' AS status
FROM chamados
WHERE status_validacao NOT IN ('Pendente', 'Aprovado', 'Rejeitado')
AND status_validacao IS NOT NULL
GROUP BY status_validacao;

-- 8. Resumo de chamados (informativo)
\echo ''
\echo '[CHECK 8] Resumo de chamados'
SELECT 
    COUNT(*) AS total_chamados,
    SUM(CASE WHEN pago THEN 1 ELSE 0 END) AS pagos,
    SUM(CASE WHEN NOT pago THEN 1 ELSE 0 END) AS pendentes,
    SUM(CASE WHEN custo_atribuido > 0 AND (valor IS NULL OR valor = 0) THEN 1 ELSE 0 END) AS migrados_para_custo_atribuido
FROM chamados;

\echo ''
\echo '========================================'
\echo 'VALIDAÇÃO CONCLUÍDA'
\echo '========================================'
