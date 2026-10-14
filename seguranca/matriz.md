# Missão 6 — Matriz de proteção

As proteções são cumulativas: cada classe herda os controles das classes anteriores.

| Classe | Controles mínimos no laboratório |
|---|---|
| Público / interno | Cifra em trânsito e em repouso como piso universal. No ambiente local SQLite, isso fica documentado como requisito de implantação; o arquivo SQLite não implementa criptografia por si só. |
| Confidencial | Controles anteriores + acesso fino, máscara para papéis amplos e trilha de leitura. |
| Pessoal | Controles anteriores + máscara por padrão, token/pseudônimo no pipeline e retenção executada. |
| Pessoal sensível | Controles anteriores + criptografia de coluna, acesso por exceção auditada e cofre de reversão. O CPF é tratado como dado pessoal identificável neste exercício; não se afirma que ele seja, por si só, dado pessoal sensível na classificação legal da LGPD. |
| Todas | Varredura de dados que escaparam do mapa e testes com dados sintéticos ou mascarados. |

## Trajeto do CPF

- **Origem (`origem/loja.db`, tabela `clientes`)**: CPF em texto de teste; em produção, restringir acesso e proteger o banco e os backups.
- **CDC (`mudancas`)**: eventos de INSERT/UPDATE podem conter a linha completa, inclusive CPF. A tabela de log tem de ser tratada como dado pessoal e coberta por retenção e eliminação.
- **Bronze (`camadas/bronze.db`)**: preserva o dado como chegou, portanto ainda contém CPF e exige acesso restrito. Bronze não é camada de consumo.
- **Silver (`camadas/silver.db`)**: CPF, nome, e-mail e ID original não são copiados. A junção usa `cliente_ps`, pseudônimo determinístico calculado com HMAC-SHA-256 e chave externa ao código.
- **Cópias, logs e evidências**: também são superfícies de dados; não registrar valores pessoais em logs e não incluir bancos de execução no ZIP.

## Pseudonimização implementada

`gerar_silver.py` lê `CHAVE_PSEUDONIMO` do ambiente e calcula:

`HMAC-SHA-256(chave, "cliente:" + id_original)`

O mesmo cliente produz o mesmo pseudônimo nos conjuntos de clientes, pedidos e navegação, permitindo junções. O pseudônimo é dado pseudonimizado, não anônimo: quem tiver a chave e o mapeamento da origem pode relacioná-lo ao titular. A chave não é salva no repositório nem na Silver. Para produção, usar um gerenciador de segredos, rotação planejada e controles de acesso à chave; a rotação muda os pseudônimos e requer reconstrução coordenada das tabelas.

A Silver contém somente:

- `clientes`: `cliente_ps`, `faixa_etaria`, `cidade` (nascimento exato generalizado);
- `pedidos`: `id`, `cliente_ps`, `valor_centavos`, `status`, `criado_em`;
- `navegacao`: `evento_id`, `cliente_ps`, `pagina`, `quando`.

Campos excluídos da Silver: `nome`, `email`, `cpf`, `cliente_id`, `observacao` e `ip`. O ID do pedido e o evento permanecem para rastreabilidade operacional; sua necessidade deve ser reavaliada conforme a finalidade de consumo.

## Limitações explícitas

A implementação é uma simulação local com SQLite e chave fornecida pelo ambiente. Ela não habilita automaticamente criptografia em trânsito/em repouso, autorização por usuário do banco, auditoria de leituras ou um cofre de reversão. Esses controles são requisitos de arquitetura para uma implantação real, não funcionalidades que o arquivo SQLite oferece sozinho.


## Missão 7 — generalização e consumo

`gerar_silver.py` generaliza nascimento em faixas 25–34, 35–44 e 45–54 e não persiste a data exata na Silver. O contrato registra a finalidade analítica da faixa e da cidade. `privacidade/gerar_consumo.py` mede K para `cidade + faixa_etaria` e constrói `camadas/gold.db`: a visão `receita_por_cidade` suprime contagem e receita quando há menos de 2 clientes. O total geral permanece separado para não perder a receita paga de grupos suprimidos nem do pedido 106, cujo cadastro foi excluído.
