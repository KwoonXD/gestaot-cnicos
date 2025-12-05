# Gestão de Técnicos de Campo

Sistema completo para gestão interna de técnicos de campo, atendimentos e pagamentos.

## Visão Geral

Este aplicativo permite gerenciar:
- **Técnicos**: Cadastro e acompanhamento de técnicos de campo em todo o Brasil
- **Chamados**: Registro de serviços de atendimento (Americanas, Escolas, Telmex, Esteira)
- **Pagamentos**: Geração e controle de pagamentos para técnicos

## Estrutura do Projeto

```
/
├── app.py              # Aplicação Flask principal
├── models.py           # Modelos do banco de dados
├── templates/          # Templates HTML (Jinja2)
│   ├── base.html
│   ├── dashboard.html
│   ├── tecnicos.html
│   ├── tecnico_form.html
│   ├── tecnico_detalhes.html
│   ├── chamados.html
│   ├── chamado_form.html
│   ├── pagamentos.html
│   ├── pagamento_gerar.html
│   └── pagamento_detalhes.html
├── static/
│   └── style.css       # Estilos CSS
└── replit.md           # Esta documentação
```

## Banco de Dados

O sistema utiliza PostgreSQL com as seguintes tabelas:

### Tecnicos
- ID automático (T-001, T-002, ...)
- Nome, Contato
- Cidade, Estado (cobertura nacional)
- Status (Ativo/Inativo)
- Valor por Atendimento
- Forma de Pagamento (PIX, Transferência Bancária, Boleto, Dinheiro)
- Chave de Pagamento (CPF, CNPJ, E-mail, Telefone ou Chave aleatória)
- Técnico Principal (para empresas com múltiplos técnicos)

### Chamados
- ID automático (CHAM-2024-0001, ...)
- Código do Chamado (referência do sistema do cliente)
- Vinculado ao Técnico
- Data de Atendimento
- Tipo de Serviço: Americanas, Escolas, Telmex, Esteira
- Status: Pendente, Em Andamento, Concluído, Cancelado
- Endereço, Observações

### Pagamentos
- ID automático (PAG-T001-202412, ...)
- Vinculado ao Técnico
- Período de referência
- Lista de chamados incluídos
- Valor total calculado automaticamente

## Funcionalidades

### Dashboard
- Total de técnicos ativos
- Chamados do mês
- Valor total pendente
- Gráfico de chamados por status

### Técnicos
- Listagem com filtros (estado, status, pagamento)
- Cadastro com dados de pagamento (forma e chave)
- Vinculação entre técnicos (técnico principal)
- Visualização detalhada com histórico
- Lista de técnicos vinculados

### Chamados
- Listagem com filtros (técnico, status, tipo, pago)
- Registro com código de referência do chamado
- Tipos de serviço: Americanas, Escolas, Telmex, Esteira
- Atualização de status
- Marcação como concluído

### Pagamentos
- Geração automática baseada em chamados concluídos
- Seleção de período
- Marcação como pago
- Histórico completo

## Fluxo de Trabalho

1. Cadastrar técnicos no sistema (com dados de pagamento)
2. Registrar chamados de serviço com código de referência
3. Atualizar status dos chamados para "Concluído"
4. Gerar pagamentos para técnicos com chamados concluídos
5. Marcar pagamentos como pagos

## Tecnologias

- **Backend**: Python + Flask
- **Banco de Dados**: PostgreSQL
- **Frontend**: HTML + Bootstrap 5 + Chart.js
- **ORM**: SQLAlchemy
- **Produção**: Gunicorn

## Alterações Recentes

### 05/12/2024
- Removido campo "Função" dos técnicos
- Substituído "Região" por "Cidade/Estado" para cobertura nacional
- Adicionado campo "Forma de Pagamento" (PIX, Transferência, etc.)
- Adicionado campo "Chave de Pagamento" para dados bancários
- Adicionado vínculo entre técnicos (Técnico Principal)
- Tipos de serviço alterados para: Americanas, Escolas, Telmex, Esteira
- Removido campo "Cliente" dos chamados
- Adicionado campo "Código do Chamado" para referência
