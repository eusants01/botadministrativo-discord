# Monitoramento Família Sant’s

## Configuração

1. Crie um webhook em cada canal do Discord: `logs-commit` e `logs-erros` (Editar canal → Integrações → Webhooks).
2. No GitHub, abra **Settings → Secrets and variables → Actions** e crie os secrets `LOGS_COMMIT_WEBHOOK_URL` e `LOGS_ERROS_WEBHOOK_URL` com as URLs correspondentes.
3. No Railway, adicione a variável `LOGS_ERROS_WEBHOOK_URL` com a URL do webhook de erros.
4. Faça push do projeto. O workflow `.github/workflows/commit-monitor.yml` enviará um registro V2 por push na branch `main` e validará sintaxe Python.

## Limitações importantes

- O registro do GitHub indica **push e verificação de sintaxe**, não confirma deploy concluído no Railway.
- O monitor Python envia logs de nível ERROR ou superior e exceções não tratadas do asyncio enquanto o processo estiver ativo.
- Falhas que matam o processo instantaneamente, erros antes do monitor iniciar e indisponibilidade total da Railway exigem integração externa com alertas do Railway ou monitor independente.
- Para monitorar status real de deploy, configure alertas nativos do Railway ou uma integração autenticada com seus eventos; não declare sucesso do deploy a partir de um push.
- Não publique URLs de webhooks, tokens ou logs contendo segredos. O filtro implementado mascara variáveis conhecidas, mas não garante a remoção de todo dado sensível.
- O workflow verifica sintaxe; não executa testes de integração nem garante ausência de bugs.
- O webhook é uma credencial: se vazar, revogue-o e crie outro.
