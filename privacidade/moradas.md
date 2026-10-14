# Missão 8 — Inventário de moradas e técnica de eliminação

Titular de teste: cliente 5. O inventário abaixo descreve as moradas por sistema, sem reproduzir nome, e-mail, CPF, telefone ou IP.

| Morada | Técnica aplicada | Justificativa / limite |
|---|---|---|
| Origem: `clientes` | DELETE propagado | O cadastro já havia sido removido na Missão 2; a rotina confirma a ausência. |
| Origem: `pedidos` / pedido 106 | Desvincular e limpar texto livre | `cliente_id` e `observacao` são anulados; valor, status e data do pedido são mantidos para continuidade financeira. |
| Origem: `navegacao` | Remoção dos eventos identificáveis | Os dois eventos do titular são removidos, incluindo o IP associado. |
| Origem: `mudancas` (CDC) | Tombstone mínimo | O evento DELETE é mantido para auditoria do fluxo; contém somente tabela, operação e chave, sem cópia do cadastro. |
| Origem: `log_navegacao` | Expurgo dos eventos do titular | O log de navegação não pode continuar expondo os eventos/IP; eventos remanescentes mantêm sua sequência original. |
| Bronze: `clientes` | DELETE | O cadastro não pode reaparecer nas camadas brutas de destino. |
| Bronze: `pedidos` / pedido 106 | Desvincular e limpar texto livre | Preserva a linha financeira, sem ligação com o titular. |
| Bronze: `navegacao` | DELETE | Remove os dois eventos e seus IPs. |
| Bronze: `visitas` e `eventos_por_cliente` | Recalcular agregados | Corrige contagens afetadas pelos eventos eliminados e remove a chave por cliente. |
| Bronze: `pedidos_lote`, `quarentena_pedidos`, `silver_pedidos` | Limpeza de referências e texto livre | A rotina limpa o pedido 106 onde houver cópia; demais linhas e motivos de qualidade são preservados. |
| Silver: `clientes`, `pedidos`, `navegacao` | DELETE / desvinculação | Remove o pseudônimo do titular do cadastro, desvincula o pedido 106 e elimina os eventos de navegação. |
| Gold: `receita_por_cidade`, `k_anonimato`, `resumo_consumo` | Preservar agregados | A visão já suprime grupos abaixo de K. O total pago permanece R$ 844,90, sem reatribuir o pedido 106 a uma cidade. |
| Arquivos de evidência | Evidência sem identificadores | A evidência guarda apenas chave derivada, data e nomes das moradas tratadas; nunca dados diretos do titular. |
| Cópias de segurança | Expiração controlada + reaplicação da lista | Não se edita uma cópia imutável. Na restauração, a lista de eliminação deve ser reaplicada antes de disponibilizar os dados. |

## Limites e decisão

O laboratório usa bancos SQLite locais e não implementa backup imutável real. Por isso, a rotina cobre os bancos ativos disponíveis no projeto e documenta o tratamento das cópias como expiração controlada e reaplicação da lista. Os CSVs em `dados/` são fixtures sintéticas de inicialização para reconstruir o laboratório; não são uma cópia operacional restaurada. Em ambiente real, a origem dos arquivos, exports, logs externos, réplicas e backups deve estar no inventário de eliminação.

A retenção de um tombstone mínimo no CDC é intencional: não contém o payload pessoal, mas impede que o consumidor perca a informação de exclusão. O log de navegação, por conter IP e comportamento associado, é expurgado dos eventos do titular.
