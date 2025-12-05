# Diagrama de Estrutura do Banco de Dados

## 🗂️ Estrutura Relacional

```
┌─────────────────────────────────────────────────────────────────┐
│                        TABELA: TECNICOS                         │
├─────────────────────────────────────────────────────────────────┤
│ • ID_Tecnico (Fórmula: "TEC-0001")                              │
│ • ID_Sequencial (Auto Number)                                   │
│ • Nome (Text)                                                    │
│ • Email (Email, Único)                                          │
│ • Telefone (Phone)                                              │
│ • Regiao (Single Select)                                        │
│ • Cargo (Single Select)                                         │
│ • Status (Single Select: Ativo/Inativo)                         │
│ • Data_Cadastro (Date, Auto)                                    │
│ • Data_Ultima_Atualizacao (Date, Auto)                          │
│                                                                  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ROLLUPS (Calculados Automaticamente)                       │  │
│ ├────────────────────────────────────────────────────────────┤  │
│ │ • Total_Chamados (COUNT de Chamados)                       │  │
│ │ • Chamados_Completos (COUNTIF Status="Completo")           │  │
│ │ • Total_Pagamentos (SUM de Pagamentos.Valor_Total)         │  │
│ └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N (Tem muitos)
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│   TABELA: CHAMADOS      │           │  TABELA: PAGAMENTOS     │
├─────────────────────────┤           ├─────────────────────────┤
│ • ID_Chamado (Fórmula)  │           │ • ID_Pagamento (Fórmula)│
│ • ID_Sequencial (Auto)  │           │ • ID_Sequencial (Auto)  │
│ • Tecnico (Link) ───────┼───────────┼─• Tecnico (Link)        │
│ • Cliente (Text)        │           │ • Periodo_Referencia    │
│ • Endereco (Long Text)  │           │ • Chamados_Completos    │
│ • Tipo_Servico (Select) │           │   (Rollup)              │
│ • Data_Agendamento      │           │ • Taxa_Fixa_Por_Chamado │
│ • Data_Conclusao (Date) │           │ • Valor_Total (Fórmula) │
│ • Status (Select)       │           │ • Status (Select)       │
│ • Valor_Servico         │           │ • Data_Pagamento        │
│ • Taxa_Fixa (Currency)  │           │ • Metodo_Pagamento      │
│ • Horas_Trabalhadas     │           │ • Comprovante (File)    │
│ • Observacoes (Text)    │           │ • Observacoes (Text)    │
│ • Data_Criacao (Auto)   │           │ • Data_Criacao (Auto)   │
│                         │           │                         │
│ ┌─────────────────────┐ │           │ ┌─────────────────────┐ │
│ │ LOOKUPS             │ │           │ │ LOOKUPS             │ │
│ ├─────────────────────┤ │           │ ├─────────────────────┤ │
│ │ • Tecnico_ID        │ │           │ │ • Tecnico_ID        │ │
│ │ • Tecnico_Nome      │ │           │ │ • Tecnico_Nome      │ │
│ └─────────────────────┘ │           │ │ • Tecnico_Email     │ │
└─────────────────────────┘           │ └─────────────────────┘ │
                                      └─────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    TABELA: CONFIGURACOES                        │
│                         (Opcional)                              │
├─────────────────────────────────────────────────────────────────┤
│ • Chave (Text, Único)                                           │
│ • Valor (Text)                                                  │
│ • Descricao (Long Text)                                         │
│                                                                  │
│ Exemplos:                                                       │
│ • TAXA_FIXA_POR_CHAMADO = 150.00                               │
│ • TAXA_HORA_EXTRA = 50.00                                       │
│ • DIAS_PAGAMENTO = 5                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔗 Relacionamentos Detalhados

### Relação 1: Tecnicos → Chamados
```
TECNICOS (1) ──────< (N) CHAMADOS

Cardinalidade: Um técnico pode ter muitos chamados
Tipo: One-to-Many (1:N)
Campo de Relação: Chamados.Tecnico → Tecnicos.ID_Tecnico
Comportamento: Quando técnico é excluído, chamados podem:
  - Manter referência (recomendado)
  - Ser excluídos (cascata)
  - Ser atribuídos a outro técnico
```

### Relação 2: Tecnicos → Pagamentos
```
TECNICOS (1) ──────< (N) PAGAMENTOS

Cardinalidade: Um técnico pode ter muitos pagamentos
Tipo: One-to-Many (1:N)
Campo de Relação: Pagamentos.Tecnico → Tecnicos.ID_Tecnico
Comportamento: Quando técnico é excluído, pagamentos devem:
  - Manter referência (histórico financeiro)
  - NÃO excluir (dados financeiros são importantes)
```

### Relação 3: Chamados → Pagamentos (Indireta)
```
CHAMADOS ──(via Rollup)──> PAGAMENTOS

Cardinalidade: Muitos chamados completos → Um pagamento
Tipo: Many-to-One (indireto via cálculo)
Cálculo: Pagamentos.Chamados_Completos = COUNTIF(Chamados.Status="Completo")
Filtro: Por período (mês/ano) e técnico
```

---

## 📊 Fluxo de Dados

### Fluxo 1: Criação de Chamado
```
1. Usuário cria CHAMADO
   ↓
2. Seleciona TECNICO
   ↓
3. Sistema atualiza ROLLUPS em TECNICOS
   - Total_Chamados (+1)
   ↓
4. Chamado aparece na lista do técnico
```

### Fluxo 2: Conclusão de Chamado
```
1. Usuário atualiza STATUS do CHAMADO para "Completo"
   ↓
2. Sistema atualiza DATA_CONCLUSAO (automático)
   ↓
3. Sistema atualiza ROLLUPS em TECNICOS
   - Chamados_Completos (+1)
   ↓
4. Chamado fica disponível para cálculo de pagamento
```

### Fluxo 3: Geração de Pagamento
```
1. Usuário solicita gerar PAGAMENTO para TECNICO
   ↓
2. Sistema busca CHAMADOS do técnico:
   - Status = "Completo"
   - Data_Conclusao no período selecionado
   - Ainda não pagos (não vinculados a pagamento pago)
   ↓
3. Sistema calcula:
   - Chamados_Completos = COUNT(chamados encontrados)
   - Valor_Total = Chamados_Completos × Taxa_Fixa
   ↓
4. Sistema cria PAGAMENTO:
   - Tecnico = TECNICO selecionado
   - Status = "Pendente"
   - Valor_Total = valor calculado
   ↓
5. Sistema atualiza ROLLUPS em TECNICOS
   - (não muda, pagamento ainda está pendente)
```

### Fluxo 4: Marcação de Pagamento como Pago
```
1. Usuário marca PAGAMENTO como "Pago"
   ↓
2. Sistema atualiza:
   - Status = "Pago"
   - Data_Pagamento = TODAY()
   ↓
3. Sistema atualiza ROLLUPS em TECNICOS
   - Total_Pagamentos (+Valor_Total)
   ↓
4. Sistema pode marcar CHAMADOS como "Pagos" (opcional)
```

---

## 🎯 Campos Chave por Tabela

### Tecnicos
```
PRIMARY KEY: ID_Tecnico
UNIQUE: Email
INDEXED: Status, Regiao
ROLLUPS: Total_Chamados, Chamados_Completos, Total_Pagamentos
```

### Chamados
```
PRIMARY KEY: ID_Chamado
FOREIGN KEY: Tecnico → Tecnicos.ID_Tecnico
INDEXED: Status, Data_Agendamento, Data_Conclusao
LOOKUPS: Tecnico_ID, Tecnico_Nome
```

### Pagamentos
```
PRIMARY KEY: ID_Pagamento
FOREIGN KEY: Tecnico → Tecnicos.ID_Tecnico
INDEXED: Status, Periodo_Referencia
LOOKUPS: Tecnico_ID, Tecnico_Nome, Tecnico_Email
ROLLUPS: Chamados_Completos (via filtro)
```

---

## 📋 Views Recomendadas por Tabela

### Tecnicos
```
1. Todos os Técnicos
   - Filtro: Nenhum
   - Ordenação: Nome (A-Z)

2. Técnicos Ativos
   - Filtro: Status = "Ativo"
   - Ordenação: Nome (A-Z)

3. Por Região
   - Agrupamento: Regiao
   - Ordenação: Nome (A-Z)

4. Performance (Top 10)
   - Ordenação: Chamados_Completos (maior para menor)
   - Limite: 10 registros

5. Com Pagamentos Pendentes
   - Filtro: Existe Pagamento com Status = "Pendente"
   - Ordenação: Total_Pagamentos (menor para maior)
```

### Chamados
```
1. Todos os Chamados
   - Filtro: Nenhum
   - Ordenação: Data_Agendamento (mais recente primeiro)

2. Agendados
   - Filtro: Status = "Agendado"
   - Ordenação: Data_Agendamento (próximos primeiro)

3. Em Andamento
   - Filtro: Status = "Em Andamento"
   - Ordenação: Data_Agendamento (mais antigo primeiro)

4. Completos
   - Filtro: Status = "Completo"
   - Ordenação: Data_Conclusao (mais recente primeiro)

5. Por Técnico
   - Agrupamento: Tecnico_Nome
   - Ordenação: Data_Agendamento (mais recente primeiro)

6. Do Mês Atual
   - Filtro: MONTH(Data_Criacao) = MONTH(TODAY())
   - Ordenação: Data_Criacao (mais recente primeiro)

7. Pendentes de Pagamento
   - Filtro: Status = "Completo" AND não vinculado a Pagamento Pago
   - Ordenação: Data_Conclusao (mais antigo primeiro)
```

### Pagamentos
```
1. Todos os Pagamentos
   - Filtro: Nenhum
   - Ordenação: Data_Criacao (mais recente primeiro)

2. Pendentes
   - Filtro: Status = "Pendente"
   - Ordenação: Valor_Total (maior para menor)

3. Pagos
   - Filtro: Status = "Pago"
   - Ordenação: Data_Pagamento (mais recente primeiro)

4. Por Técnico
   - Agrupamento: Tecnico_Nome
   - Ordenação: Data_Criacao (mais recente primeiro)

5. Do Mês Atual
   - Filtro: MONTH(Periodo_Referencia) = MONTH(TODAY())
   - Ordenação: Status, Valor_Total

6. Por Período
   - Agrupamento: Periodo_Referencia
   - Ordenação: Periodo_Referencia (mais recente primeiro)
```

---

## 🔄 Ciclo de Vida dos Dados

### Ciclo de Vida de um Chamado
```
CRIADO (Status: Agendado)
   ↓
AGENDADO (Status: Agendado, Data_Agendamento preenchida)
   ↓
EM ANDAMENTO (Status: Em Andamento, técnico iniciou serviço)
   ↓
COMPLETO (Status: Completo, Data_Conclusao preenchida)
   ↓
[OPCIONAL] PAGO (vinculado a Pagamento com Status: Pago)
```

### Ciclo de Vida de um Pagamento
```
GERADO (Status: Pendente, Valor_Total calculado)
   ↓
PENDENTE (Status: Pendente, aguardando processamento)
   ↓
PAGO (Status: Pago, Data_Pagamento preenchida, Comprovante anexado)
   ↓
[FINALIZADO] (histórico mantido para auditoria)
```

---

## 🎨 Estrutura de Dados para Dashboards

### Dashboard: Visão Geral
```
Métricas Principais:
├── Total de Técnicos Ativos (COUNT Tecnicos WHERE Status="Ativo")
├── Total de Chamados do Mês (COUNT Chamados WHERE MONTH(Data_Criacao)=MONTH(TODAY()))
├── Chamados Pendentes (COUNT Chamados WHERE Status="Agendado" OR Status="Em Andamento")
└── Valor Total Pendente (SUM Pagamentos.Valor_Total WHERE Status="Pendente")

Gráficos:
├── Chamados por Status (Pizza)
├── Chamados por Técnico (Barras - Top 10)
├── Pagamentos por Status (Pizza)
└── Tendência de Chamados (Linha - últimos 6 meses)
```

### Dashboard: Performance
```
Métricas por Técnico:
├── Nome
├── Total de Chamados
├── Chamados Completos
├── Taxa de Conclusão (%)
├── Total Recebido (R$)
└── Pagamentos Pendentes (R$)

Ordenação: Por Taxa de Conclusão (maior para menor)
Filtros: Região, Cargo, Status
```

### Dashboard: Financeiro
```
Métricas:
├── Total Pendente (SUM Pagamentos.Valor_Total WHERE Status="Pendente")
├── Total Pago no Mês (SUM Pagamentos.Valor_Total WHERE Status="Pago" AND MONTH(Data_Pagamento)=MONTH(TODAY()))
├── Média por Técnico (AVG Total_Pagamentos)
└── Top 5 Técnicos (por Total_Pagamentos)

Tabela: Pagamentos Pendentes
├── Técnico
├── Período
├── Valor
└── Dias Pendente (DATETIME_DIFF(TODAY(), Data_Criacao, "days"))
```

---

## 🔐 Permissões Sugeridas

### Administrador
```
Tecnicos: Criar, Ler, Editar, Excluir
Chamados: Criar, Ler, Editar, Excluir
Pagamentos: Criar, Ler, Editar, Excluir
Configuracoes: Criar, Ler, Editar, Excluir
```

### Operações
```
Tecnicos: Criar, Ler, Editar (não pode excluir)
Chamados: Criar, Ler, Editar (não pode excluir)
Pagamentos: Ler (somente visualização)
Configuracoes: Ler (somente visualização)
```

### Finanças
```
Tecnicos: Ler (somente visualização)
Chamados: Ler (somente visualização)
Pagamentos: Criar, Ler, Editar (não pode excluir)
Configuracoes: Ler (somente visualização)
```

### Técnico (Auto-visualização)
```
Tecnicos: Ler (apenas próprio registro)
Chamados: Ler (apenas próprios chamados)
Pagamentos: Ler (apenas próprios pagamentos)
Configuracoes: Sem acesso
```

---

## 📐 Índices e Performance

### Índices Recomendados
```
Tecnicos:
- Status (filtro frequente)
- Regiao (filtro frequente)
- Email (único, busca)

Chamados:
- Status (filtro frequente)
- Data_Agendamento (ordenação e filtro)
- Data_Conclusao (cálculo de pagamentos)
- Tecnico (join com Tecnicos)

Pagamentos:
- Status (filtro frequente)
- Periodo_Referencia (filtro e agrupamento)
- Tecnico (join com Tecnicos)
```

### Otimizações
```
1. Usar Rollups em vez de fórmulas quando possível
2. Limitar views a registros necessários (filtros)
3. Usar Lookups para evitar joins repetidos
4. Indexar campos usados em filtros frequentes
5. Agrupar dados quando apropriado
6. Usar fórmulas calculadas apenas quando necessário
```

---

**Documento criado em:** 2024
**Versão:** 1.0
**Autor:** Diagrama de Estrutura do Banco de Dados

