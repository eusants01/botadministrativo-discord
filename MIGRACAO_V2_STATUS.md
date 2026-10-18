# Migração Discord Components V2 — Estado real

## Concluído nesta versão
- `cogs/ajuda_publica.py`: painel público convertido para `discord.ui.LayoutView`, `Container`, `TextDisplay`, `MediaGallery`, `Separator` e `ActionRow` com `Select` persistente.
- As páginas de ajuda enviadas em resposta privada também usam LayoutView nativo.
- A sintaxe dos arquivos Python foi validada com `compileall`.

## Ainda pendente
- Cassino, contratos, convites, economia, formulários, leilões, notificações, sorteios e tickets continuam com implementações de View/Embed tradicionais.
- `utils/components_v2.py` possui um adaptador global que converte mensagens dinamicamente, mas isso **não** equivale a migrar callbacks e layouts de cada módulo de forma nativa; seu comportamento deve ser auditado antes do deploy.
- Testes de integração reais no Discord, com PostgreSQL e reinícios do Railway não foram executados.

## Riscos importantes
- Alterar uma mensagem legada para V2 exige tratar corretamente flags, conteúdo e embeds; não aplicar conversão em massa sem testes.
- Preservar `custom_id`, respostas de interação, permissões, estados e mensagens persistentes.
- Não realizar migrações destrutivas no banco.
- Existe mais de um arquivo de leilões (`leiloes.py` e `leil#U00f5es.py`); revisar qual é carregado antes de editar.

## Próxima sequência
1. Migrar Cassino e contratos, validando botões, aposta e saldos.
2. Migrar leilões, garantindo débitos atômicos e sem duplicidade.
3. Migrar tickets, formulários e sorteios com preservação de mensagens existentes.
4. Migrar os demais módulos e remover o adaptador global após testes.
5. Implementar Expresso Fantasma em V2 nativo, com partidas e economia PostgreSQL.
