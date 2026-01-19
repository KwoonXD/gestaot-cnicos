# Runbook de Deploy - Migrations de Estabilização

## Visão Geral

Este pacote estabiliza o schema do banco de dados PostgreSQL:
- Conversão Float → Numeric(10,2)
- Constraints de integridade
- Deprecação de `chamados.valor`
- Correção de nullable drift

## Pré-Requisitos

- Python 3.10+
- PostgreSQL 13+
- psycopg2-binary (`pip install psycopg2-binary`)
- Acesso de escrita ao banco

## Migrations

| Revisão | Descrição |
|---------|-----------|
| `2908569d81de` | Baseline (schema inicial) |
| `a001` | Float → Numeric(10,2) |
| `a002` | Constraints de integridade + Saneamento |
| `a003` | Deprecação chamados.valor (backfill) |
| `a004` | Fix nullable drift |

---

## Procedimento de Deploy

### 1. Backup (OBRIGATÓRIO)

```bash
pg_dump -Fc -d DATABASE_NAME > backup_$(date +%Y%m%d_%H%M%S).dump
```

### 2. Pré-Check

```bash
# Verificar versão atual
flask db current

# Executar validação
psql -d DATABASE_NAME -f scripts/validate_migrations.sql
# ou
python scripts/validate_migrations.py
```

### 3. Upgrade

```bash
flask db upgrade head
```

### 4. Pós-Check

```bash
# Verificar versão final
flask db current  # Deve retornar: a004

# Validar integridade
python scripts/validate_migrations.py
```

### 5. Verificação Manual

```sql
-- Verificar constraints
SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%' OR conname LIKE 'uq_%';

-- Verificar nullable
SELECT column_name, is_nullable FROM information_schema.columns
WHERE table_name = 'chamados' AND column_name = 'valor';
```

---

## Rollback

### Rollback Completo (Último Recurso)

```bash
# Restaurar backup
pg_restore -d DATABASE_NAME backup_YYYYMMDD_HHMMSS.dump
```

### Rollback por Migration

```bash
# Voltar para a003
flask db downgrade a003

# Voltar para a002
flask db downgrade a002
```

---

## Troubleshooting

### Erro: Constraint já existe
```
[SKIP] já existe
```
Comportamento esperado - idempotência.

### Erro: Dados violam constraint
Execute saneamento manual antes do upgrade:
```sql
-- Exemplo: corrigir tipo_movimento inválido
UPDATE stock_movements SET tipo_movimento = 'AJUSTE'
WHERE tipo_movimento NOT IN ('ENVIO', 'DEVOLUCAO', 'USO', 'AJUSTE');
```

### Erro: Float persistence
Se ainda houver colunas FLOAT após upgrade, execute manualmente:
```sql
ALTER TABLE table_name ALTER COLUMN column_name TYPE NUMERIC(10,2);
```

---

## Fresh Install

Para novos ambientes (sem dados):

```bash
flask db upgrade head
```

O schema será criado com todas as constraints e tipos corretos desde o início.

---

## Checklist de Deploy

- [ ] Backup realizado
- [ ] `flask db current` anotado
- [ ] Pré-check executado (sem FAIL)
- [ ] `flask db upgrade head` executado
- [ ] Versão = `a004`
- [ ] Pós-check executado (sem FAIL)
- [ ] Aplicação testada
