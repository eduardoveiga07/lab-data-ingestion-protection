# Missão 9 — Resiliência, backup e recuperação

## Objetivos de serviço do laboratório

| Sistema/dado | RPO-alvo | RTO-alvo | Estratégia de recuperação |
|---|---:|---:|---|
| Origem SQLite | até 24 h | até 15 min | snapshot consistente + reaplicação de alterações disponíveis no CDC |
| Log CDC e navegação | até 5 min para o log durável; navegação pode ser reprocessada da origem quando disponível | até 15 min | incluir origem/log no snapshot; consumidores retomam pelos offsets persistidos |
| Bronze | até 24 h | até 15 min | restaurar snapshot e reconciliar CDC antes de liberar consumo |
| Silver | RPO derivado da Bronze | até 15 min | reconstruir com `CHAVE_PSEUDONIMO` recuperada do cofre de segredos |
| Gold | RPO derivado da Silver | até 15 min | reconstruir agregados a partir da Silver restaurada |
| Chave HMAC | RPO zero para perda da chave ativa | até 15 min | backup separado no cofre de segredos, acesso restrito e teste de recuperação |

RPO/RTO são alvos propostos para o exercício, não SLAs medidos de um ambiente de produção.

## Cópias e isolamento

- A rotina `backup.py` cria um snapshot consistente de `loja.db`, `bronze.db`, `silver.db` e `gold.db` usando a API de backup do SQLite.
- `manifesto.json` guarda data, tamanho e SHA-256 de cada banco; a restauração valida todos os hashes antes de substituir qualquer banco ativo.
- A regra 3-2-1 continua sendo o desenho-alvo: três cópias, duas mídias/locais diferentes e uma fora do ambiente primário. O diretório local criado pelo script é apenas uma das cópias; a cópia off-site e a imutabilidade real precisam ser fornecidas por armazenamento externo com credenciais independentes e retenção bloqueada.
- O backup da chave HMAC deve ficar separado dos bancos, em gerenciador de segredos. Não se deve colocar a chave no ZIP nem no manifesto.
- O arquivo `privacidade/lista_eliminacao.jsonl` é deliberadamente mantido fora dos snapshots de bancos. Após restaurar uma cópia antiga, a rotina procura os hashes de solicitação entre os IDs candidatos em memória, reaplica `esquecer` e só então reconstrói Silver/Gold.
- A lista de eliminação não contém IDs originais nem dados pessoais diretos. A reaplicação é testada antes de a restauração ser considerada concluída.

## Procedimento operacional

1. Criar snapshot: `python resiliencia/backup.py`.
2. Armazenar uma cópia fora do host com credencial independente e política imutável, conforme a plataforma da organização.
3. Para restaurar: `python resiliencia/restaurar.py resiliencia/backups/<snapshot>` com `CHAVE_PSEUDONIMO` definido.
4. Confirmar integridade SHA-256, reaplicação das eliminações e reconstrução de Silver/Gold.
5. Rodar `python evidencias/conferir_missao9.py` e anexar `evidencias/missao9.txt`.

## Limitações explícitas

SQLite local não implementa armazenamento off-site, WORM/imutabilidade, isolamento por credencial, cofre de chaves ou monitoramento de RPO/RTO. O laboratório testa snapshot consistente, integridade, restauração, reaplicação de eliminações e reconstrução de camadas; as garantias físicas de backup exigem infraestrutura externa.
