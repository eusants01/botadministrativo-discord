# Migração Components V2 — Etapa 2

- Cassino: painel público, seletor de jogos, carteira, perfil, ranking, contratos, cartas e resultados agora enviados com LayoutView e componentes V2.
- IDs persistentes do painel do cassino preservados.
- Modais de apostas mantidos (modais são mecanismo próprio do Discord).
- Regras de apostas, transações e banco PostgreSQL inalterados.
- Demais módulos, inclusive o módulo separado de contratos, ainda não migrados nesta etapa.
- Validado apenas por análise sintática; requer testes funcionais no Discord antes de uso em produção.
- Atenção: mensagens de painel já publicadas na versão anterior não se convertem automaticamente; publique um novo painel.
