# Catálogo de dados

Gerado automaticamente por `python governanca/gerar_catalogo.py`. Não editar manualmente.

## clientes

Cadastro e atributos dos clientes da loja online.

- **Versão do contrato:** 1
- **Dono:** Time de Cadastro e Identidade
- **Classe do conjunto:** pessoal
- **Retenção:** Enquanto a relação estiver ativa; revisar e eliminar até 5 anos após encerramento quando não houver obrigação ou disputa pendente.
- **Acesso:** Cadastro administra; Engenharia de Dados acessa por serviço; aprovação do dono para acesso humano; leituras administrativas auditadas.
- **Frescor:** até 24 horas depois da mudança na origem

| Campo | Tipo | Classe | Obrigatório | Finalidade | Descrição |
|---|---|---|---|---|---|
| `id` | inteiro | interno | true | — | Identificador interno do cliente. |
| `nome` | texto | pessoal | true | — | Nome informado no cadastro. |
| `email` | texto | pessoal | true | — | E-mail de contato. |
| `cpf` | texto | pessoal | true | — | CPF do titular. |
| `nascimento` | data | pessoal | false | Análise agregada por faixa etária; a data exata não é exposta ao consumo. | Data de nascimento; quase-identificador. Na Silver, generalizado em faixa etária. |
| `cidade` | texto | pessoal | false | Agregação de receita por cidade, com supressão de grupos abaixo de K=2. | Cidade de residência; pode atuar como quase-identificador. |
| `atualizado_em` | data_hora | interno | true | — | Momento da última atualização da linha. |

## pedidos

Pedidos e valores transacionais da loja online.

- **Versão do contrato:** 1
- **Dono:** Time de Pedidos e Pagamentos
- **Classe do conjunto:** pessoal
- **Retenção:** 5 anos após encerramento do exercício como política operacional inicial para suportar obrigações fiscais; confirmar com Jurídico/Fiscal antes de produção.
- **Acesso:** Serviço de pedidos e Financeiro por função; Engenharia de Dados com acesso mínimo; consultas humanas auditadas.
- **Frescor:** até 24 horas depois da mudança na origem

| Campo | Tipo | Classe | Obrigatório | Finalidade | Descrição |
|---|---|---|---|---|---|
| `id` | inteiro | interno | true | — | Identificador do pedido. |
| `cliente_id` | inteiro | pessoal | true | Junção analítica por pseudônimo na Silver; ID original não é exposto. | Referência ao cliente; permite associação indireta a uma pessoa. |
| `valor_centavos` | inteiro | interno | true | — | Valor do pedido em centavos. |
| `status` | texto | interno | true | — | Estado operacional do pedido. |
| `criado_em` | data_hora | interno | true | — | Data e hora de criação do pedido. |
| `observacao` | texto | pessoal | false | — | Texto livre do atendimento; pode conter dados pessoais não estruturados. |

## navegacao

Eventos de navegação dos visitantes na loja online.

- **Versão do contrato:** 1
- **Dono:** Time de Produto Digital
- **Classe do conjunto:** pessoal
- **Retenção:** 30 dias para análise operacional; depois agregar ou eliminar eventos identificáveis.
- **Acesso:** Produto recebe métricas agregadas; acesso a eventos brutos apenas por serviço autorizado e com trilha de leitura.
- **Frescor:** até 24 horas depois da publicação do evento

| Campo | Tipo | Classe | Obrigatório | Finalidade | Descrição |
|---|---|---|---|---|---|
| `evento_id` | inteiro | interno | true | — | Identificador do evento de navegação. |
| `cliente_id` | inteiro | pessoal | false | Análises de navegação com pseudônimo na Silver; ID original não é exposto. | Referência opcional ao cliente; vazio para visitante sem cadastro. |
| `ip` | texto | pessoal | true | — | Endereço IP do dispositivo; dado pessoal. |
| `pagina` | texto | interno | true | — | Página acessada; não identifica sozinha, mas ganha contexto ao ser associada. |
| `quando` | data_hora | interno | true | — | Data e hora do evento de navegação. |
