# Correções do Railway — 18/10/2026

- `cogs/ajuda_publica.py`: corrigido `discord.ui.MediaGalleryItem` para `discord.MediaGalleryItem`, que impedia o carregamento do cog e dos comandos `!ajuda` e `!publicarajuda`.
- `utils/components_v2.py`: corrigida a mesma referência incorreta em duas ocorrências para prevenir falhas em painéis que usem a conversão.
- `cogs/leil#U00f5es.py`: cópia duplicada removida. Mantido `cogs/leiloes.py`, evitando a exceção `Cog named Leilao already loaded`.

## Importante ao publicar
Se o GitHub ainda tiver arquivos de leilões com outros nomes (`leilões.py` ou `leil#U00f5es.py`), exclua-os também. O deploy deve ter **somente** `cogs/leiloes.py`.

Após deploy, confirme nos logs `Cog carregado: cogs.ajuda_publica` e `Cog carregado: cogs.leiloes`, e teste `!publicarajuda`. Não foram executados testes com Discord/Railway ao vivo.
