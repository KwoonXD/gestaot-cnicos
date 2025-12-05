# Guia Rápido: Fórmulas e Exemplos Práticos

## 📐 Fórmulas Airtable

### IDs Automáticos

#### ID_Tecnico
```javascript
"TEC-" & RIGHT("0000" & {ID_Sequencial}, 4)
```
**Resultado:** TEC-0001, TEC-0002, TEC-0100

#### ID_Chamado
```javascript
"CHAM-" & YEAR(TODAY()) & "-" & RIGHT("0000" & {ID_Sequencial}, 4)
```
**Resultado:** CHAM-2024-0001, CHAM-2024-0002

#### ID_Pagamento
```javascript
"PAY-" & YEAR(TODAY()) & "-" & MONTH(TODAY()) & "-" & RIGHT("0000" & {ID_Sequencial}, 4)
```
**Resultado:** PAY-2024-12-0001, PAY-2024-12-0002

**Alternativa com formatação de mês:**
```javascript
"PAY-" & YEAR(TODAY()) & "-" & IF(LEN(MONTH(TODAY())) = 1, "0" & MONTH(TODAY()), MONTH(TODAY())) & "-" & RIGHT("0000" & {ID_Sequencial}, 4)
```

---

### Cálculos de Valores

#### Valor Total do Chamado
```javascript
{Taxa_Fixa} + IF({Horas_Trabalhadas} > 0, {Horas_Trabalhadas} * 50, 0)
```
**Explicação:** Taxa fixa + (horas trabalhadas × R$ 50,00) se houver horas

#### Valor Total do Pagamento
```javascript
{Chamados_Completos} * {Taxa_Fixa_Por_Chamado}
```
**Explicação:** Quantidade de chamados completos × taxa fixa por chamado

---

### Rollups (Agregações)

#### Total de Chamados por Técnico
**Tipo:** Rollup
**Campo:** `Total_Chamados`
**Função:** COUNT
**Campo Vinculado:** `Chamados` (todos os registros)

#### Chamados Completos por Técnico
**Tipo:** Rollup
**Campo:** `Chamados_Completos`
**Função:** COUNTIF
**Condição:** `Status = "Completo"`
**Campo Vinculado:** `Chamados`

#### Total de Pagamentos por Técnico
**Tipo:** Rollup
**Campo:** `Total_Pagamentos`
**Função:** SUM
**Campo Vinculado:** `Pagamentos.Valor_Total`

#### Taxa de Conclusão (%)
```javascript
IF({Total_Chamados} > 0, ({Chamados_Completos} / {Total_Chamados}) * 100, 0)
```
**Resultado:** Porcentagem de chamados completos (ex: 85%)

---

### Fórmulas de Data

#### Dias desde o Cadastro
```javascript
DATETIME_DIFF(TODAY(), {Data_Cadastro}, "days")
```

#### Dias até Agendamento
```javascript
DATETIME_DIFF({Data_Agendamento}, TODAY(), "days")
```

#### Período de Referência (Mês/Ano)
```javascript
MONTH({Periodo_Referencia}) & "/" & YEAR({Periodo_Referencia})
```
**Resultado:** 12/2024

#### Último Dia do Mês
```javascript
DATEADD(DATE(YEAR({Periodo_Referencia}), MONTH({Periodo_Referencia}) + 1, 1), -1, "days")
```

---

### Fórmulas Condicionais

#### Status do Técnico (Baseado em Atividade)
```javascript
IF({Total_Chamados} = 0, "Sem Atividade",
  IF({Chamados_Completos} / {Total_Chamados} >= 0.8, "Alto Desempenho",
    IF({Chamados_Completos} / {Total_Chamados} >= 0.5, "Desempenho Médio",
      "Baixo Desempenho"
    )
  )
)
```

#### Valor Pendente do Técnico
```javascript
SUM(IF({Pagamentos.Status} = "Pendente", {Pagamentos.Valor_Total}, 0))
```

#### Próximo Pagamento Previsto
```javascript
IF(
  COUNTIF({Pagamentos.Status}, "Pendente") > 0,
  "R$ " & SUM(IF({Pagamentos.Status} = "Pendente", {Pagamentos.Valor_Total}, 0)),
  "Nenhum pagamento pendente"
)
```

---

## 🔄 Automações Airtable

### Automação 1: Data de Conclusão Automática

**Trigger:** When record matches conditions
**Condições:**
- `Status` (field) `is` `Completo`
- `Data_Conclusao` (field) `is empty`

**Ações:**
1. Update record
   - Campo: `Data_Conclusao`
   - Valor: `TODAY()`

---

### Automação 2: Notificação de Novo Chamado

**Trigger:** When record is created
**Condições:**
- Tabela: `Chamados`

**Ações:**
1. Find records (Técnicos)
   - Campo: `ID_Tecnico` = `{Tecnico_ID}` do chamado
2. Send email
   - Para: `{Tecnico.Email}`
   - Assunto: `Novo Chamado Atribuído - {ID_Chamado}`
   - Corpo: Template de email

**Template de Email:**
```
Olá {Nome},

Um novo chamado foi atribuído a você:

- ID: {ID_Chamado}
- Cliente: {Cliente}
- Endereço: {Endereco}
- Data Agendada: {Data_Agendamento}
- Tipo: {Tipo_Servico}

Por favor, acesse o sistema para mais detalhes.

Atenciosamente,
Equipe de Operações
```

---

### Automação 3: Geração Mensal de Pagamentos

**Trigger:** On a schedule
**Frequência:** Monthly
**Dia:** 5th of each month
**Hora:** 9:00 AM

**Ações:**
1. Find records (Técnicos)
   - Condição: `Status` = `Ativo`
2. For each record:
   - Find records (Chamados)
     - Condição: `Tecnico` = `{Current Record}`
     - Condição: `Status` = `Completo`
     - Condição: `Data_Conclusao` está no mês anterior
   - If count > 0:
     - Create record (Pagamentos)
       - `Tecnico` = `{Current Record}`
       - `Periodo_Referencia` = `First day of previous month`
       - `Chamados_Completos` = `Count from step 2`
       - `Valor_Total` = `{Chamados_Completos} * 150`
       - `Status` = `Pendente`

---

### Automação 4: Notificação de Pagamento Pendente

**Trigger:** When record is created
**Condições:**
- Tabela: `Pagamentos`
- `Status` = `Pendente`

**Ações:**
1. Find records (Técnicos)
   - Campo: `ID_Tecnico` = `{Tecnico_ID}` do pagamento
2. Send email
   - Para: Gerente de Finanças (email fixo)
   - CC: `{Tecnico.Email}` (opcional)
   - Assunto: `Novo Pagamento Pendente - {Tecnico_Nome}`
   - Corpo: Template de email

**Template de Email:**
```
Olá,

Foi gerado um novo pagamento pendente:

- Técnico: {Tecnico_Nome}
- ID do Pagamento: {ID_Pagamento}
- Período: {Periodo_Referencia}
- Chamados Completos: {Chamados_Completos}
- Valor Total: R$ {Valor_Total}

Acesse o sistema para processar o pagamento.

Atenciosamente,
Sistema de Gestão
```

---

### Automação 5: Atualização de Status do Técnico

**Trigger:** When record matches conditions
**Condições:**
- Tabela: `Chamados`
- `Status` muda para `Completo`

**Ações:**
1. Find records (Tecnicos)
   - Campo: `ID_Tecnico` = `{Tecnico_ID}` do chamado
2. Update record
   - Campo: `Data_Ultima_Atualizacao` = `TODAY()`

---

## 🎨 Fórmulas para Softr/Interface

### Exibição de Status com Cores

#### Badge de Status (Chamado)
```javascript
IF({Status} = "Completo", "✅ Completo",
  IF({Status} = "Em Andamento", "🔄 Em Andamento",
    IF({Status} = "Agendado", "📅 Agendado",
      "❌ Cancelado"
    )
  )
)
```

#### Badge de Status (Pagamento)
```javascript
IF({Status} = "Pago", "✅ Pago",
  IF({Status} = "Pendente", "⏳ Pendente",
    "❌ Cancelado"
  )
)
```

---

### Formatação de Valores

#### Valor Formatado (R$)
```javascript
"R$ " & IF(LEN({Valor_Total}) > 0, FORMAT({Valor_Total}, "0.00"), "0,00")
```
**Resultado:** R$ 1.500,00

#### Valor com Separador de Milhares
```javascript
REPLACE(FORMAT({Valor_Total}, "0.00"), ".", ",")
```
**Resultado:** 1500,00

---

### Textos Dinâmicos

#### Resumo do Técnico
```javascript
{Nome} & " (" & {Regiao} & ") - " & {Total_Chamados} & " chamados"
```
**Resultado:** João Silva (Norte) - 25 chamados

#### Resumo do Pagamento
```javascript
{Chamados_Completos} & " chamados × R$ " & {Taxa_Fixa_Por_Chamado} & " = R$ " & {Valor_Total}
```
**Resultado:** 10 chamados × R$ 150,00 = R$ 1.500,00

---

## 📊 Fórmulas para Gráficos

### Dados para Gráfico de Pizza (Chamados por Status)

**Query Airtable:**
```
GROUPBY(
  {Status},
  COUNT({ID_Chamado})
)
```

### Dados para Gráfico de Barras (Chamados por Técnico)

**Query Airtable:**
```
GROUPBY(
  {Tecnico_Nome},
  COUNT({ID_Chamado})
)
```

### Dados para Gráfico de Linha (Tendência Mensal)

**Query Airtable:**
```
GROUPBY(
  MONTH({Data_Criacao}) & "/" & YEAR({Data_Criacao}),
  COUNT({ID_Chamado})
)
```

---

## 🔍 Fórmulas de Filtro

### Técnicos com Pagamentos Pendentes
```javascript
FIND("Pendente", {Pagamentos.Status}) >= 0
```

### Chamados do Mês Atual
```javascript
MONTH({Data_Criacao}) = MONTH(TODAY()) AND YEAR({Data_Criacao}) = YEAR(TODAY())
```

### Chamados dos Últimos 30 Dias
```javascript
DATETIME_DIFF(TODAY(), {Data_Criacao}, "days") <= 30
```

### Técnicos Ativos com Mais de 10 Chamados
```javascript
{Status} = "Ativo" AND {Total_Chamados} > 10
```

---

## 🧮 Exemplos de Cálculos Avançados

### Média de Chamados por Técnico
```javascript
AVERAGE({Total_Chamados})
```
*Nota: Esta fórmula deve ser usada em uma view agregada*

### Técnico com Mais Chamados
```javascript
MAX({Total_Chamados})
```

### Total de Pagamentos Pendentes (Soma Geral)
```javascript
SUM(IF({Pagamentos.Status} = "Pendente", {Pagamentos.Valor_Total}, 0))
```

### Valor Médio por Chamado
```javascript
IF({Total_Chamados} > 0, {Total_Pagamentos} / {Total_Chamados}, 0)
```

---

## 📅 Fórmulas de Período

### Primeiro Dia do Mês
```javascript
DATE(YEAR(TODAY()), MONTH(TODAY()), 1)
```

### Último Dia do Mês
```javascript
DATEADD(DATE(YEAR(TODAY()), MONTH(TODAY()) + 1, 1), -1, "days")
```

### Primeiro Dia do Mês Anterior
```javascript
DATE(YEAR(DATEADD(TODAY(), -1, "months")), MONTH(DATEADD(TODAY(), -1, "months")), 1)
```

### Último Dia do Mês Anterior
```javascript
DATEADD(DATE(YEAR(TODAY()), MONTH(TODAY()), 1), -1, "days")
```

---

## 🎯 Validações

### Validar Email Único
**Tipo:** Field Validation
**Condição:** Unique
**Campo:** `Email` (Tabela: Tecnicos)

### Validar Data de Agendamento Futura
```javascript
{Data_Agendamento} >= TODAY()
```

### Validar Valor Positivo
```javascript
{Valor_Total} > 0
```

---

## 🔗 Exemplos de Lookups

### Nome do Técnico (no Chamado)
**Tipo:** Lookup
**Campo Vinculado:** `Tecnico.Nome`

### Email do Técnico (no Pagamento)
**Tipo:** Lookup
**Campo Vinculado:** `Tecnico.Email`

### Região do Técnico (no Chamado)
**Tipo:** Lookup
**Campo Vinculado:** `Tecnico.Regiao`

---

## 📱 Fórmulas para Mobile (Glide)

### Badge de Notificação (Chamados Pendentes)
```javascript
IF({Status} = "Agendado" OR {Status} = "Em Andamento", "🔔", "")
```

### Formatação de Telefone
```javascript
REPLACE(REPLACE(REPLACE({Telefone}, "(", ""), ")", ""), "-", "")
```

### Link de Navegação (Google Maps)
```javascript
"https://www.google.com/maps/search/?api=1&query=" & {Endereco}
```

---

## 🚨 Tratamento de Erros

### Evitar Divisão por Zero
```javascript
IF({Total_Chamados} > 0, {Chamados_Completos} / {Total_Chamados}, 0)
```

### Valores Padrão
```javascript
IF(ISBLANK({Valor_Total}), 0, {Valor_Total})
```

### Validação de Campo Obrigatório
```javascript
IF(ISBLANK({Nome}), "Campo obrigatório", {Nome})
```

---

## 📋 Checklist de Fórmulas

### Tabela: Tecnicos
- [ ] `ID_Tecnico` (fórmula)
- [ ] `Total_Chamados` (rollup)
- [ ] `Chamados_Completos` (rollup)
- [ ] `Total_Pagamentos` (rollup)
- [ ] `Taxa_Conclusao` (fórmula - opcional)

### Tabela: Chamados
- [ ] `ID_Chamado` (fórmula)
- [ ] `Valor_Total` (fórmula - opcional)
- [ ] `Tecnico_Nome` (lookup)
- [ ] `Tecnico_ID` (lookup)
- [ ] `Dias_Ate_Agendamento` (fórmula - opcional)

### Tabela: Pagamentos
- [ ] `ID_Pagamento` (fórmula)
- [ ] `Valor_Total` (fórmula)
- [ ] `Chamados_Completos` (rollup)
- [ ] `Tecnico_Nome` (lookup)
- [ ] `Tecnico_Email` (lookup)
- [ ] `Periodo_Formatado` (fórmula - opcional)

---

## 🎓 Dicas e Boas Práticas

1. **Teste fórmulas em campos de teste** antes de aplicar em campos importantes
2. **Use nomes descritivos** para campos de fórmula
3. **Documente fórmulas complexas** com comentários (se possível)
4. **Valide dados** antes de usar em fórmulas
5. **Use rollups** em vez de fórmulas quando possível (mais eficiente)
6. **Evite fórmulas muito complexas** - quebre em múltiplos campos se necessário
7. **Teste automações** com dados de exemplo antes de ativar
8. **Mantenha backups** antes de fazer mudanças importantes

---

**Documento criado em:** 2024
**Versão:** 1.0
**Autor:** Guia Rápido de Fórmulas

