from __future__ import annotations

import logging

import secrets

from datetime import datetime, timedelta, timezone

from decimal import Decimal, InvalidOperation

from pathlib import Path

from urllib.parse import urlparse

import discord

from discord.ext import commands

LOGGER = logging.getLogger("sants.bot.lucky_block")

# ===========================================================================

# CONFIGURAÇÃO PRIVADA — MUDE AQUI E APENAS AQUI PARA ADICIONAR PREMIAÇÕES

# ===========================================================================

CANAL_PAINEL = 1572785659108917439

CANAL_REGISTROS = 1572355776377266176

ABERTURAS_POR_CICLO = 3

DURACAO_CICLO_HORAS = 24

# 0 = somente o proprietário real da aplicação/bot (bot.is_owner).

# Para restringir a um único usuário, substitua 0 pelo SEU ID do Discord.

ID_DONO_DISCORD = 0

BANNER_PAINEL = "assets/lucky_block/painel.png"           # assets/lucky_block/painel.png (ou assets/painel.png)

BANNER_CAIXA_VAZIA = "caixa_vazia" # assets/lucky_block/caixa_vazia.png

MOSTRAR_CHANCES_NO_PAINEL = False # Recomenda-se False para o catálogo secreto

ANUNCIAR_SECRETOS = True         # Se False, prêmios da raridade secreta ficam sem log público

CONCEDER_CARGOS_AUTOMATICAMENTE = True  # Exige 'Gerenciar Cargos' e hierarquia

# Chance = probabilidade ABSOLUTA por abertura, escrita em % (5 casas decimais).

# Ex.: 0.5 = 0,5% | 0.02 = 0,02% | 0.0001 = 0,0001% (1 em 1.000.000).

# Use número entre aspas (ex.: "0.0001") para evitar imprecisão de ponto flutuante.

# A chance de 'caixa vazia' é automaticamente 100% menos a soma das premiações.

# Se um prêmio for sorteado sem estoque, a caixa ficará vazia SEM refazer sorteio.

# 'estoque': total configurado. Ao aumentar o total, somam-se novas unidades ao saldo.

# 'ativo': False bloqueia novos sorteios sem perder o histórico.

# 'cargo_id': ID para atribuição automática de cargos; 0 para entrega manual.

# 'banner': nome de arquivo na pasta assets (vazio = detectar pelo código do prêmio).

PREMIACOES = {

    # =================== RARAS ===================

    "candidato_divisao": {

        "nome": "Candidato em uma divisão",

        "raridade": "rare",

        "chance": "0.0050",

        "estoque": 2,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Divisão e requisitos definidos pela administração.",

    },

    "sub_civil": {

        "nome": "Sub Civil",

        "raridade": "secret",

        "chance": "0.030",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Prêmio sujeito às regras e validação da equipe.",

    },

    # =================== ÉPICAS ===================

    "100_robux": {

        "nome": "100 Robux",

        "raridade": "legendary",

        "chance": "0.00065",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Entrega manual de 100 Robux.",

    },

    "200_robux": {

        "nome": "200 Robux",

        "raridade": "legendary",

        "chance": "0.00035",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Entrega manual de 200 Robux.",

    },

    "nitro_basico": {

        "nome": "Discord Nitro Básico",

        "raridade": "epic",

        "chance": "0.00045",

        "estoque": 0,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Assinatura sujeita à disponibilidade e elegibilidade.",

    },

    "decoracao_perfil": {

        "nome": "Decoração de Perfil Aleatória (Discord)",

        "raridade": "epic",

        "chance": "0.00035",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Item de perfil selecionado pela equipe na entrega.",

    },

    # =================== LENDÁRIAS ===================

    "300_robux": {

        "nome": "300 Robux",

        "raridade": "legendary",

        "chance": "0.0007",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Entrega manual de 300 Robux.",

    },

    "400_robux": {

        "nome": "400 Robux",

        "raridade": "legendary",

        "chance": "0.00045",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Entrega manual de 400 Robux.",

    },

    "500_robux": {

        "nome": "500 Robux",

        "raridade": "legendary",

        "chance": "0.00035",

        "estoque": 1,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Entrega manual de 500 Robux.",

    },

    "nitro_normal": {

        "nome": "Discord Nitro Normal",

        "raridade": "legendary",

        "chance": "0.00048",

        "estoque": 0,

        "banner": "",

        "cargo_id": 0,

        "ativo": True,

        "descricao": "Assinatura Nitro sujeita à disponibilidade e elegibilidade.",

    },

    "clover": {

        "nome": "Clover",

        "raridade": "legendary",

        "chance": "0.0002",  # 1 chance em 500.000 aberturas

        "estoque": 1,        # ALTERE PARA 1 quando quiser liberar este cargo

        "banner": "",       # COLOQUE O BANNER DA CLOVER AQUI

        "cargo_id": 1572848152548085871,

        "ativo": True,

        "descricao": "Cargo exclusivo Clover da Família ROYAL.",

    },

    # =================== SECRETA ===================

    "demon_night": {

        "nome": "Demon Night",

        "raridade": "legendary",

        "chance": "0.0001",  # 1 chance em 1.000.000 aberturas

        "estoque": 1,        # ALTERE PARA 1 quando quiser liberar este cargo

        "banner": "",       # COLOQUE O BANNER DA DEMON NIGHT AQUI

        "cargo_id": 1569948996573597726,

        "ativo": True,

        "descricao": "Cargo secreto Demon Night da Família ROYAL.",

    },

}

# Detecta automaticamente banners por código, sem exigir configurações individuais.

for _codigo_banner, _premio_banner in PREMIACOES.items():

    if not _premio_banner["banner"]:

        _premio_banner["banner"] = _codigo_banner

# ===========================================================================

# IMPLEMENTAÇÃO — NÃO É NECESSÁRIO EDITAR A PARTIR DESTE PONTO

# ===========================================================================

TOTAL_SORTEIO = 10_000_000  # 1 unidade = 0,00001%; inclui chances como 0,00065%

COR_ROYAL = discord.Colour.from_rgb(91, 79, 187)

PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"

FORMATOS_BANNER = (".png", ".jpg", ".jpeg", ".webp", ".gif")

RARIDADES = {

    "empty": ("Caixa vazia", 0),

    "rare": ("Rara", 10),

    "epic": ("Épica", 100),

    "legendary": ("Lendária", 1000),

    "secret": ("Secreta", 10000),

}

def agora_utc() -> datetime:

    return datetime.now(timezone.utc)

def validar_url(url: str) -> None:

    if not url:

        return

    if url.startswith("https://"):

        parsed = urlparse(url)

        if (not parsed.netloc or parsed.username or parsed.password

                or len(url) > 1500 or any(x.isspace() for x in url)):

            raise ValueError("URL HTTPS de banner inválida.")

        return

    caminho = Path(url)

    if (caminho.is_absolute() or ".." in caminho.parts or ":" in url

            or len(url) > 1500 or any(x.isspace() for x in url)):

        raise ValueError("Banner local precisa ser nome de arquivo dentro de assets.")

def porcentagem_para_tickets(valor: str, codigo: str) -> int:

    try:

        proporcao = Decimal(str(valor)) * Decimal(100_000)

    except (InvalidOperation, ValueError) as exc:

        raise ValueError(f"Chance inválida no prêmio '{codigo}'.") from exc

    if not proporcao.is_finite() or proporcao < 0 or proporcao != proporcao.to_integral_value():

        raise ValueError(f"Chance de '{codigo}' precisa ser múltipla de 0,00001%.")

    if proporcao > TOTAL_SORTEIO:

        raise ValueError(f"Chance maior que 100% em '{codigo}'.")

    return int(proporcao)

def validar_configuracao() -> None:

    if not (1 <= ABERTURAS_POR_CICLO <= 25 and 1 <= DURACAO_CICLO_HORAS <= 720):

        raise ValueError("Intervalos de abertura inválidos.")

    validar_url(BANNER_PAINEL)

    validar_url(BANNER_CAIXA_VAZIA)

    total = 0

    for codigo, p in PREMIACOES.items():

        if (not codigo or len(codigo) > 60 or

                not all(ch.isalnum() or ch == "_" for ch in codigo)):

            raise ValueError(f"Código de prêmio inválido: {codigo!r}")

        if p["raridade"] not in {"rare", "epic", "legendary", "secret"}:

            raise ValueError(f"Raridade inválida: {codigo}")

        if not isinstance(p["estoque"], int) or not 0 <= p["estoque"] <= 100_000:

            raise ValueError(f"Estoque inválido: {codigo}")

        if not isinstance(p["cargo_id"], int) or p["cargo_id"] < 0:

            raise ValueError(f"ID de cargo inválido: {codigo}")

        validar_url(p["banner"])

        if not isinstance(p["ativo"], bool):

            raise ValueError(f"Campo ativo inválido: {codigo}")

        if not isinstance(p["nome"], str) or not p["nome"].strip():

            raise ValueError(f"Nome inválido: {codigo}")

        if p["ativo"]:

            total += porcentagem_para_tickets(p["chance"], codigo)

    if total > TOTAL_SORTEIO:

        raise ValueError(f"Soma das chances excede 100% ({total / 100000:.5f}%).")

def sortear_codigo() -> str | None:

    """Sorteio de chances ABSOLUTAS, com caixa vazia como probabilidade restante."""

    sorteio = secrets.randbelow(TOTAL_SORTEIO)

    limite = 0

    for codigo, premio in PREMIACOES.items():

        if not premio["ativo"]:

            continue

        limite += porcentagem_para_tickets(premio["chance"], codigo)

        if sorteio < limite:

            return codigo

    return None

def nome_raridade(codigo: str) -> str:

    return RARIDADES.get(codigo, ("Desconhecida", 0))[0]

def visivel_em_registros(raridade: str) -> bool:

    return raridade in {"epic", "legendary"} or (raridade == "secret" and ANUNCIAR_SECRETOS)

def localizar_banner(banner: str) -> str | Path | None:

    """Busca imagens locais em assets/lucky_block e assets.

    Aceita 'painel', 'painel.png', 'assets/lucky_block/painel.png',

    'lucky_block/painel.png' e nomes próprios de cada premiação.

    """

    if not banner:

        return None

    if banner.startswith("https://"):

        return banner  # Compatibilidade com registros antigos.

    nome = banner.replace("\\\\", "/").strip()

    relativo = Path(nome)

    if relativo.is_absolute() or ".." in relativo.parts or ":" in nome:

        LOGGER.warning("Banner com caminho inválido: %s", banner)

        return None

    # O usuário pode escrever um caminho completo relativo ao projeto.

    if relativo.parts and relativo.parts[0].lower() == "assets":

        relativo = Path(*relativo.parts[1:])

    if not relativo.parts:

        return None

    prefixo = Path("lucky_block")

    possibilidades = [PASTA_ASSETS / relativo]

    if relativo.parts[0].lower() != "lucky_block":

        possibilidades.insert(0, PASTA_ASSETS / prefixo / relativo)

    else:

        # Também aceita o banner na raiz de assets/.

        possibilidades.append(PASTA_ASSETS / relativo.name)

    candidatos = []

    for base in possibilidades:

        if base.suffix:

            candidatos.append(base)

        else:

            candidatos.extend(base.with_suffix(ext) for ext in FORMATOS_BANNER)

    raiz = PASTA_ASSETS.resolve()

    for caminho in candidatos:

        if caminho.resolve().is_relative_to(raiz) and caminho.is_file():

            return caminho

    # Diferentes sistemas podem ter nomes com extensões em maiúsculo.

    for base in possibilidades:

        diretorio = base.parent

        if not diretorio.is_dir():

            continue

        for arquivo in diretorio.iterdir():

            if (arquivo.is_file() and arquivo.suffix.lower() in FORMATOS_BANNER

                and arquivo.stem.casefold() == base.stem.casefold()

                and (not base.suffix or arquivo.suffix.casefold() == base.suffix.casefold())):

                return arquivo

    LOGGER.warning("Banner não encontrado em assets: %s", banner)

    return None

def inserir_banner(container: discord.ui.Container, banner: str) -> Path | None:

    origem = localizar_banner(banner)

    if origem:

        galeria = discord.ui.MediaGallery()

        media = f"attachment://{origem.name}" if isinstance(origem, Path) else origem

        galeria.add_item(media=media, description="Banner personalizado da Família ROYAL")

        container.add_item(galeria)

    return origem if isinstance(origem, Path) else None

def arquivo_do_banner(view: discord.ui.LayoutView) -> dict:

    """Anexo para envios: channel.send, DM.send e followup.send."""

    caminho = getattr(view, "_royal_banner_path", None)

    return {"file": discord.File(str(caminho), filename=caminho.name)} if caminho else {}

def anexos_para_edicao(view: discord.ui.LayoutView) -> dict:

    """Message.edit aceita 'attachments' (inclusive File), mas não 'file'."""

    caminho = getattr(view, "_royal_banner_path", None)

    return {"attachments": [discord.File(str(caminho), filename=caminho.name)]} if caminho else {"attachments": []}

def cartao(titulo: str, texto: str, banner: str = "", *, teste: bool = False) -> discord.ui.LayoutView:

    painel = discord.ui.LayoutView(timeout=180)

    caixa = discord.ui.Container(accent_colour=COR_ROYAL)

    painel._royal_banner_path = inserir_banner(caixa, banner)

    prefixo = "🧪 **SIMULAÇÃO — NÃO É PREMIAÇÃO REAL**\n\n" if teste else ""

    caixa.add_item(discord.ui.TextDisplay(f"{prefixo}## {titulo}\n{texto}"))

    painel.add_item(caixa)

    return painel

class BotaoLucky(discord.ui.Button):

    def __init__(self, acao: str, rotulo: str, estilo: discord.ButtonStyle, emoji: str):

        super().__init__(label=rotulo, style=estilo, emoji=emoji,

                         custom_id=f"royal_lucky:v1:{acao}")

        self.acao = acao

    async def callback(self, interaction: discord.Interaction) -> None:

        cog = interaction.client.get_cog("LuckyBlockRoyal")

        if cog is None:

            await interaction.response.send_message("❌ Sistema temporariamente indisponível.", ephemeral=True)

            return

        await cog.interagir(interaction, self.acao)

class PainelLucky(discord.ui.LayoutView):

    def __init__(self, *, teste: bool = False):

        super().__init__(timeout=180 if teste else None)

        caixa = discord.ui.Container(accent_colour=COR_ROYAL)

        self._royal_banner_path = inserir_banner(caixa, BANNER_PAINEL)

        texto = (

            ("🧪 **PRÉVIA — BOTÕES DESATIVADOS**\n\n" if teste else "")

            + "## <:luckblock:1572868783725609083> LUCKY BLOCK - FAMÍLIA ROYAL\n\n"

            + "Teste a sua sorte através das nossas Lucky Blocks e concorra a prêmios exclusivos. "

              "A contagem começa a partir da sua **primeira abertura** e você tem "

              "apenas **três tentativas** por ciclo, que se renovam após 24h!\n\n"

            + "### Premiações\n"

              "> ☰ `👹` Cargo exclusivo <@&1572848152548085871> ou <@&1569948996573597726>\n"

              "> ☰ `💜` Discord Nitro (**Básico** ou **Normal**)\n"

              "> ☰ `🎨` Decoração de Perfil\n"

              "> ☰ `🤓` Sub Civil no **E.B**\n"

              "> ☰ `💸` Robux de **100 a 500**\n"

            + "### Observações\n"

              "> ☰ `🛎️` As chances são __extremamente baixas__, então depende muito da sua sorte.\n"

              "> ☰ `🛎️` Novo estoque __será notificado__ a todos quando chegar.\n"

              "> ☰ `🛎️` Não é possível doar a recompensa a outro usuário."

        )

        if MOSTRAR_CHANCES_NO_PAINEL:

            acumulado = {chave: 0 for chave in RARIDADES}

            for codigo, premio in PREMIACOES.items():

                if premio["ativo"]:

                    acumulado[premio["raridade"]] += porcentagem_para_tickets(premio["chance"], codigo)

            texto += "\n\n**Probabilidades por raridade:** " + " · ".join(

                f"{nome_raridade(k)} {Decimal(v) / Decimal(100000):f}%"

                for k, v in acumulado.items() if k != "empty" and v > 0

            )

        caixa.add_item(discord.ui.TextDisplay(texto))

        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        botoes = discord.ui.ActionRow()

        botoes.add_item(BotaoLucky("abrir", "Abrir", discord.ButtonStyle.success, "<:luckblock:1572868783725609083>"))

        botoes.add_item(BotaoLucky("historico", "Histórico", discord.ButtonStyle.secondary, "📜"))

        botoes.add_item(BotaoLucky("ranking", "Ranking", discord.ButtonStyle.secondary, "<:versustrophy:1564669597440016485>"))

        if teste:

            for botao in botoes.children:

                botao.disabled = True

        caixa.add_item(botoes)

        self.add_item(caixa)

class LuckyBlockRoyal(commands.Cog):

    def __init__(self, bot: commands.Bot):

        self.bot = bot

    async def cog_load(self) -> None:

        validar_configuracao()

        pool = getattr(self.bot, "pool", None)

        if pool is None:

            raise RuntimeError("Lucky Block necessita de bot.pool (PostgreSQL).")

        async with pool.acquire() as con:

            await con.execute("""

                CREATE TABLE IF NOT EXISTS lucky_settings (

                    guild_id BIGINT PRIMARY KEY,

                    panel_banner_url TEXT,

                    empty_banner_url TEXT,

                    panel_message_id BIGINT

                )

            """)

            await con.execute("""

                CREATE TABLE IF NOT EXISTS lucky_reward_stock (

                    guild_id BIGINT NOT NULL,

                    code TEXT NOT NULL,

                    stock_total INTEGER NOT NULL CHECK (stock_total >= 0),

                    stock_available INTEGER NOT NULL CHECK (stock_available >= 0),

                    PRIMARY KEY (guild_id, code)

                )

            """)

            await con.execute("""

                CREATE TABLE IF NOT EXISTS lucky_users (

                    guild_id BIGINT NOT NULL,

                    user_id BIGINT NOT NULL,

                    next_open_at TIMESTAMPTZ NOT NULL,

                    window_started_at TIMESTAMPTZ,

                    opens_used INTEGER NOT NULL DEFAULT 0,

                    PRIMARY KEY (guild_id, user_id)

                )

            """)

            await con.execute("ALTER TABLE lucky_users ADD COLUMN IF NOT EXISTS window_started_at TIMESTAMPTZ")

            await con.execute("ALTER TABLE lucky_users ADD COLUMN IF NOT EXISTS opens_used INTEGER NOT NULL DEFAULT 0")

            await con.execute("""

                CREATE TABLE IF NOT EXISTS lucky_openings (

                    id BIGSERIAL PRIMARY KEY,

                    guild_id BIGINT NOT NULL,

                    user_id BIGINT NOT NULL,

                    reward_code TEXT,

                    rarity TEXT NOT NULL,

                    reward_name TEXT,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

                )

            """)

            await con.execute("ALTER TABLE lucky_openings ADD COLUMN IF NOT EXISTS reward_name TEXT")

            await con.execute("""

                CREATE INDEX IF NOT EXISTS lucky_openings_user_idx

                ON lucky_openings(guild_id, user_id, created_at DESC)

            """)

            await con.execute("""

                CREATE TABLE IF NOT EXISTS lucky_wins (

                    opening_id BIGINT PRIMARY KEY REFERENCES lucky_openings(id),

                    guild_id BIGINT NOT NULL,

                    user_id BIGINT NOT NULL,

                    reward_code TEXT NOT NULL,

                    reward_name TEXT,

                    reward_rarity TEXT,

                    reward_banner_url TEXT,

                    role_id BIGINT,

                    status TEXT NOT NULL DEFAULT 'pending',

                    public_message_id BIGINT,

                    public_claimed_at TIMESTAMPTZ,

                    delivered_by BIGINT,

                    delivered_at TIMESTAMPTZ,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

                )

            """)

            for coluna, tipo in (

                ("reward_name", "TEXT"), ("reward_rarity", "TEXT"),

                ("reward_banner_url", "TEXT"), ("role_id", "BIGINT"),

                ("public_claimed_at", "TIMESTAMPTZ"),

            ):

                await con.execute(f"ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS {coluna} {tipo}")

        # O mesmo custom_id do painel anterior continua funcionando.

        self.bot.add_view(PainelLucky())

        LOGGER.info("Lucky Block carregado; painel=%s registros=%s", CANAL_PAINEL, CANAL_REGISTROS)

    async def garantir_guild(self, guild_id: int) -> None:

        """Sincroniza apenas saldo de estoque. Não armazena nome/chance/banner no DB.

        Um novo 'estoque' no código altera o saldo por diferença; se só reiniciar,

        o saldo permanece intacto. O usuário pode zerar o estoque com estoque=0.

        """

        async with self.bot.pool.acquire() as con:

            async with con.transaction():

                await con.execute("""

                    INSERT INTO lucky_settings(guild_id) VALUES($1) ON CONFLICT DO NOTHING

                """, guild_id)

                for code, premio in PREMIACOES.items():

                    quantidade = int(premio["estoque"])

                    await con.execute("""

                        INSERT INTO lucky_reward_stock(guild_id, code, stock_total, stock_available)

                        VALUES($1, $2, $3, $3)

                        ON CONFLICT (guild_id, code) DO UPDATE

                        SET stock_available = GREATEST(0,

                            lucky_reward_stock.stock_available +

                            (EXCLUDED.stock_total - lucky_reward_stock.stock_total)),

                            stock_total = EXCLUDED.stock_total

                        WHERE lucky_reward_stock.stock_total IS DISTINCT FROM EXCLUDED.stock_total

                    """, guild_id, code, quantidade)

    async def pegar_canal(self, guild: discord.Guild, id_canal: int) -> discord.TextChannel:

        canal = guild.get_channel(id_canal)

        if not isinstance(canal, discord.TextChannel):

            canal = await guild.fetch_channel(id_canal)

        if not isinstance(canal, discord.TextChannel) or canal.guild.id != guild.id:

            raise ValueError(f"Canal {id_canal} inválido neste servidor.")

        return canal

    async def saldo(self, guild_id: int, user_id: int) -> tuple[int, datetime | None]:

        row = await self.bot.pool.fetchrow("""

            SELECT next_open_at, window_started_at, opens_used

            FROM lucky_users WHERE guild_id=$1 AND user_id=$2

        """, guild_id, user_id)

        if not row or row["window_started_at"] is None or row["next_open_at"] <= agora_utc():

            return ABERTURAS_POR_CICLO, None

        return max(0, ABERTURAS_POR_CICLO - row["opens_used"]), row["next_open_at"]

    async def abrir(self, guild_id: int, user_id: int) -> dict:

        """Operação atômica: trava o usuário, decrementa estoque e salva resultado."""

        instante = agora_utc()

        async with self.bot.pool.acquire() as con:

            async with con.transaction():

                await con.execute("""

                    INSERT INTO lucky_users(guild_id,user_id,next_open_at,window_started_at,opens_used)

                    VALUES($1,$2,$3,NULL,0) ON CONFLICT DO NOTHING

                """, guild_id, user_id, instante)

                membro = await con.fetchrow("""

                    SELECT next_open_at, window_started_at, opens_used

                    FROM lucky_users WHERE guild_id=$1 AND user_id=$2 FOR UPDATE

                """, guild_id, user_id)

                novo_ciclo = membro["window_started_at"] is None or membro["next_open_at"] <= instante

                usadas = 0 if novo_ciclo else membro["opens_used"]

                renovacao = (instante + timedelta(hours=DURACAO_CICLO_HORAS)

                            if novo_ciclo else membro["next_open_at"])

                if usadas >= ABERTURAS_POR_CICLO:

                    return {"limite": renovacao}

                codigo = sortear_codigo()

                premio = PREMIACOES.get(codigo) if codigo else None

                if premio is not None:

                    # UPDATE condicional é atômico sob concorrência: somente 1 vence

                    # a disputa pela última unidade do prêmio.

                    disponivel = await con.fetchval("""

                        UPDATE lucky_reward_stock SET stock_available=stock_available-1

                        WHERE guild_id=$1 AND code=$2 AND stock_available>0

                        RETURNING stock_available

                    """, guild_id, codigo)

                    if disponivel is None:

                        premio = None

                        codigo = None

                raridade = premio["raridade"] if premio else "empty"

                await con.execute("""

                    UPDATE lucky_users SET next_open_at=$3, window_started_at=$4, opens_used=$5

                    WHERE guild_id=$1 AND user_id=$2

                """, guild_id, user_id, renovacao,

                    instante if novo_ciclo else membro["window_started_at"], usadas + 1)

                abertura_id = await con.fetchval("""

                    INSERT INTO lucky_openings(guild_id,user_id,reward_code,rarity,reward_name)

                    VALUES($1,$2,$3,$4,$5) RETURNING id

                """, guild_id, user_id, codigo, raridade, premio["nome"] if premio else None)

                if premio:

                    await con.execute("""

                        INSERT INTO lucky_wins(opening_id,guild_id,user_id,reward_code,

                            reward_name,reward_rarity,reward_banner_url,role_id)

                        VALUES($1,$2,$3,$4,$5,$6,$7,$8)

                    """, abertura_id, guild_id, user_id, codigo, premio["nome"],

                        raridade, premio["banner"], premio["cargo_id"] or None)

                return {

                    "id": abertura_id, "codigo": codigo, "premio": premio,

                    "raridade": raridade, "restantes": ABERTURAS_POR_CICLO - (usadas + 1),

                    "renovacao": renovacao,

                }

    async def entregar_cargo_automaticamente(self, membro: discord.Member, abertura_id: int,

                                              premio: dict) -> bool:

        if not CONCEDER_CARGOS_AUTOMATICAMENTE or not premio["cargo_id"]:

            return False

        role = membro.guild.get_role(premio["cargo_id"])

        if role is None or role in membro.roles:

            return False  # caso já possua, a equipe decide como proceder

        try:

            await membro.add_roles(role, reason=f"Lucky Block ROYAL #{abertura_id}")

        except (discord.Forbidden, discord.HTTPException):

            LOGGER.exception("Falha ao atribuir cargo de Lucky Block #%d", abertura_id)

            return False

        await self.bot.pool.execute("""

            UPDATE lucky_wins SET status='delivered', delivered_at=NOW(), delivered_by=$2

            WHERE opening_id=$1 AND status='pending'

        """, abertura_id, self.bot.user.id if self.bot.user else membro.guild.me.id)

        return True

    @staticmethod

    def texto_premio(nome: str, raridade: str, numero: str,

                     situacao: str, usuario: str = "") -> str:

        return ((f"👤 **Vencedor:** {usuario}\n" if usuario else "")

                + f"🎁 **Recompensa:** {nome}\n"

                  f"💎 **Raridade:** {nome_raridade(raridade)}\n"

                  f"📦 **Registro:** `#LB-{numero}`\n"

                  f"📋 **Situação:** {situacao}")

    async def anunciar(self, guild: discord.Guild, abertura_id: int) -> bool:

        """Reserva anúncio por 5 min para evitar duplicação em tentativas paralelas."""

        row = await self.bot.pool.fetchrow("""

            UPDATE lucky_wins SET public_claimed_at=NOW()

            WHERE guild_id=$1 AND opening_id=$2

              AND public_message_id IS NULL

              AND (public_claimed_at IS NULL OR public_claimed_at < NOW() - INTERVAL '5 minutes')

            RETURNING opening_id, user_id, reward_code, reward_name,

                      reward_rarity, reward_banner_url, status

        """, guild.id, abertura_id)

        if row is None:

            return False

        # Para histórico antigo, os campos opcionais podem estar vazios.

        premio_atual = PREMIACOES.get(row["reward_code"], {})

        raridade = row["reward_rarity"] or premio_atual.get("raridade", "empty")

        if not visivel_em_registros(raridade):

            await self.bot.pool.execute("""

                UPDATE lucky_wins SET public_claimed_at=NULL WHERE opening_id=$1

            """, abertura_id)

            return False

        nome = row["reward_name"] or premio_atual.get("nome", row["reward_code"])

        banner = row["reward_banner_url"] or premio_atual.get("banner", "")

        texto = self.texto_premio(nome, raridade, f"{abertura_id:06d}",

                                  "Entregue" if row["status"] == "delivered" else "Aguardando entrega",

                                  usuario=f"<@{row['user_id']}>")

        try:

            canal = await self.pegar_canal(guild, CANAL_REGISTROS)

            view = cartao("<a:1151259013175054336:1553900891315376240> PRÊMIO ESPECIAL ENCONTRADO!", texto, banner)

            mensagem = await canal.send(

                view=view,

                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),

                **arquivo_do_banner(view),

            )

            await self.bot.pool.execute("""

                UPDATE lucky_wins SET public_message_id=$2, public_claimed_at=NULL

                WHERE opening_id=$1

            """, abertura_id, mensagem.id)

            return True

        except Exception:

            await self.bot.pool.execute("""

                UPDATE lucky_wins SET public_claimed_at=NULL WHERE opening_id=$1

            """, abertura_id)

            raise

    async def atualizar_anuncio(self, guild: discord.Guild, abertura_id: int) -> None:

        item = await self.bot.pool.fetchrow("""

            SELECT w.public_message_id,w.user_id,w.status,w.reward_code,

                w.reward_name,w.reward_rarity,w.reward_banner_url

            FROM lucky_wins w WHERE w.guild_id=$1 AND w.opening_id=$2

        """, guild.id, abertura_id)

        if not item or item["public_message_id"] is None:

            return

        premio_atual = PREMIACOES.get(item["reward_code"], {})

        nome = item["reward_name"] or premio_atual.get("nome", item["reward_code"])

        raridade = item["reward_rarity"] or premio_atual.get("raridade", "empty")

        banner = item["reward_banner_url"] or premio_atual.get("banner", "")

        texto = self.texto_premio(nome, raridade, f"{abertura_id:06d}",

                                  "Entregue" if item["status"] == "delivered" else "Aguardando entrega",

                                  usuario=f"<@{item['user_id']}>")

        canal = await self.pegar_canal(guild, CANAL_REGISTROS)

        msg = await canal.fetch_message(item["public_message_id"])

        view = cartao("<a:1151259013175054336:1553900891315376240> PRÊMIO ESPECIAL ENCONTRADO!", texto, banner)

        await msg.edit(view=view, content=None, embeds=[], **anexos_para_edicao(view))

    async def interagir(self, interaction: discord.Interaction, acao: str) -> None:

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):

            await interaction.response.send_message("❌ Use o Lucky Block dentro do servidor.", ephemeral=True)

            return

        if interaction.channel_id != CANAL_PAINEL:

            await interaction.response.send_message("❌ Este painel não pertence ao canal oficial.", ephemeral=True)

            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild_id = interaction.guild.id

        try:

            if acao == "abrir":

                await self.garantir_guild(guild_id)

                resultado = await self.abrir(guild_id, interaction.user.id)

                if "limite" in resultado:

                    renovacao = int(resultado["limite"].timestamp())

                    await interaction.followup.send(

                        f"⏳ Você usou suas {ABERTURAS_POR_CICLO} aberturas. "

                        f"Novas tentativas <t:{renovacao}:R>.", ephemeral=True)

                    return

                premio = resultado["premio"]

                if premio:

                    entregue = await self.entregar_cargo_automaticamente(

                        interaction.user, resultado["id"], premio)

                    situacao = "Cargo entregue automaticamente" if entregue else "Aguardando entrega"

                    texto = self.texto_premio(

                        premio["nome"], resultado["raridade"],

                        f"{resultado['id']:06d}", situacao)

                    texto += (f"\n`🎟️` **Restantes:** {resultado['restantes']}/{ABERTURAS_POR_CICLO}"

                              f"\n`⏳` **Renovação:** <t:{int(resultado['renovacao'].timestamp())}:R>")

                    view = cartao("<a:1151259013175054336:1553900891315376240> VOCÊ ENCONTROU UMA RECOMPENSA!", texto, premio["banner"])

                else:

                    texto = ("A caixa veio vazia, boa sorte na próxima!"

                             f"\n`🎟️` **Restantes:** {resultado['restantes']}/{ABERTURAS_POR_CICLO}"

                             f"\n`⏳` **Renovação:** <t:{int(resultado['renovacao'].timestamp())}:R>")

                    view = cartao("<:gift:1570666397745549322> CAIXA VAZIA", texto, BANNER_CAIXA_VAZIA)

                await interaction.followup.send(view=view, ephemeral=True,

                                                **arquivo_do_banner(view))

                if premio and visivel_em_registros(resultado["raridade"]):

                    try:

                        await self.anunciar(interaction.guild, resultado["id"])

                    except (discord.HTTPException, ValueError):

                        LOGGER.exception("Falha ao publicar #%d. Use !luckypublicar", resultado["id"])

                return

            if acao == "historico":

                restantes, renovacao = await self.saldo(guild_id, interaction.user.id)

                rows = await self.bot.pool.fetch("""

                    SELECT id, reward_code, reward_name, rarity, created_at

                    FROM lucky_openings WHERE guild_id=$1 AND user_id=$2

                    ORDER BY id DESC LIMIT 10

                """, guild_id, interaction.user.id)

                linhas = []

                for item in rows:

                    antigo = PREMIACOES.get(item["reward_code"], {})

                    nome = (item["reward_name"] or antigo.get("nome")

                            or (item["reward_code"] if item["reward_code"] else "Caixa vazia"))

                    linhas.append(

                        f"`#{item['id']}` · {nome} · {nome_raridade(item['rarity'])} "

                        f"· <t:{int(item['created_at'].timestamp())}:R>")

                texto = "\n".join(linhas) if linhas else "Você ainda não abriu nenhuma caixa."

                texto += f"\n\n`🎟️` **Disponíveis:** {restantes}/{ABERTURAS_POR_CICLO}"

                if renovacao:

                    texto += f"\n`⏳` **Renovação:** <t:{int(renovacao.timestamp())}:R>"

                await interaction.followup.send(view=cartao("📜 MEU HISTÓRICO", texto), ephemeral=True)

                return

            if acao == "ranking":

                rows = await self.bot.pool.fetch("""

                    SELECT user_id, COUNT(*) AS total,

                        SUM(CASE rarity WHEN 'rare' THEN 10 WHEN 'epic' THEN 100

                            WHEN 'legendary' THEN 1000 WHEN 'secret' THEN 10000

                            ELSE 0 END) AS pontos

                    FROM lucky_openings WHERE guild_id=$1

                    GROUP BY user_id ORDER BY pontos DESC, total DESC, user_id LIMIT 10

                """, guild_id)

                texto = "\n".join(

                    f"**{i}.** <@{item['user_id']}> — **{item['pontos']} pontos**"

                    f" (`{item['total']} caixas`)" for i, item in enumerate(rows, 1)

                ) or "Ainda não houve nenhuma abertura."

                await interaction.followup.send(view=cartao("🏆 RANKING DOS SORTUDOS", texto), ephemeral=True)

                return

            await interaction.followup.send("❌ Ação desconhecida.", ephemeral=True)

        except Exception:

            LOGGER.exception("Erro no Lucky Block: guild=%s, acao=%s", guild_id, acao)

            await interaction.followup.send("❌ Erro interno ao executar a ação.", ephemeral=True)

    async def e_dono(self, ctx: commands.Context) -> bool:

        if ID_DONO_DISCORD:

            return ctx.author.id == ID_DONO_DISCORD

        return await self.bot.is_owner(ctx.author)

    async def exigir_dono(self, ctx: commands.Context) -> bool:

        if await self.e_dono(ctx):

            return True

        await ctx.send("❌ Este comando é exclusivo do proprietário do bot.", delete_after=10)

        return False

    @staticmethod

    async def apagar_comando(ctx: commands.Context) -> None:

        try:

            await ctx.message.delete()

        except (discord.Forbidden, discord.HTTPException):

            pass

    async def enviar_dm(self, ctx: commands.Context, mensagem: str = "",

                       view: discord.ui.LayoutView | None = None) -> bool:

        try:

            if view:

                await ctx.author.send(view=view, **arquivo_do_banner(view))

            else:

                await ctx.author.send(mensagem, allowed_mentions=discord.AllowedMentions.none())

            return True

        except discord.Forbidden:

            await ctx.send("❌ Abra suas DMs para receber a prévia privada.", delete_after=10)

            return False
        except discord.HTTPException:
            LOGGER.exception("Falha HTTP ao enviar a prévia do Lucky Block por DM")
            await ctx.send("❌ Não consegui enviar a prévia. Confira o log do bot e o banner em assets.", delete_after=15)
            return False

    @commands.command(name="painellucky")

    @commands.guild_only()

    async def painel_lucky(self, ctx: commands.Context) -> None:

        """!painellucky — publica/atualiza painel, sem revelar recompensas."""

        if not await self.exigir_dono(ctx):

            return

        await self.garantir_guild(ctx.guild.id)

        canal = await self.pegar_canal(ctx.guild, CANAL_PAINEL)

        antigo = await self.bot.pool.fetchval("""

            SELECT panel_message_id FROM lucky_settings WHERE guild_id=$1

        """, ctx.guild.id)

        if antigo:

            try:

                msg = await canal.fetch_message(antigo)

                view = PainelLucky()

                await msg.edit(view=view, content=None, embeds=[],
                               allowed_mentions=discord.AllowedMentions.none(),
                               **anexos_para_edicao(view))

                await ctx.send(f"✅ Painel atualizado em {canal.mention}.")

                return

            except (discord.NotFound, discord.HTTPException):

                LOGGER.warning("Painel anterior indisponível; publicando novo.")

        view = PainelLucky()

        msg = await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none(),

                               **arquivo_do_banner(view))

        await self.bot.pool.execute("""

            UPDATE lucky_settings SET panel_message_id=$2 WHERE guild_id=$1

        """, ctx.guild.id, msg.id)

        await ctx.send(f"✅ Painel instalado em {canal.mention}.")

    @commands.command(name="testarlucky", aliases=["testelucky"])

    async def testar_lucky(self, ctx: commands.Context,

                           codigo: str = "lista", destino: str = "dm") -> None:

        """!testarlucky <codigo|lista|todos|vazia|painel> [dm|registros].

        Pode rodar em DM com o bot para manter os códigos privados.

        Somente a prévia pública `registros` exige execução no servidor.

        TESTES NÃO gastam tentativas, não alteram estoque e não criam sorteios.

        """

        if not await self.exigir_dono(ctx):

            return

        await self.apagar_comando(ctx)

        codigo, destino = codigo.strip().lower(), destino.strip().lower()

        # Aceita também a abreviação comum do nome Clover.
        if codigo == "clove":
            codigo = "clover"

        if destino not in {"dm", "registros"}:

            await self.enviar_dm(ctx, "❌ Destino deve ser `dm` ou `registros`.")

            return

        if codigo == "lista":

            linhas = [f"`!testarlucky {key}` — {p['nome']} [{nome_raridade(p['raridade'])}]"

                     for key, p in PREMIACOES.items()]

            linhas.extend(["`!testarlucky vazia`", "`!testarlucky painel`",

                           "`!testarlucky todos`", "`!testarlucky clover registros` (público)"])

            await self.enviar_dm(ctx, "**🧪 Comandos privados de teste**\n" + "\n".join(linhas))

            return

        if codigo == "painel":

            await self.enviar_dm(ctx, view=PainelLucky(teste=True))

            return

        if codigo == "todos":

            if destino == "registros":

                await self.enviar_dm(ctx, "❌ `todos` só pode ser enviado por DM.")

                return

            codigos = list(PREMIACOES) + ["vazia"]

        else:

            codigos = [codigo]

        if destino == "registros":

            if ctx.guild is None:

                await self.enviar_dm(ctx, "❌ Para testar no canal de registros, execute o comando dentro do servidor.")

                return

            if codigo not in PREMIACOES or not visivel_em_registros(PREMIACOES[codigo]["raridade"]):

                await self.enviar_dm(ctx, "❌ Este prêmio não gera anúncio público. Teste por DM.")

                return

            canal = await self.pegar_canal(ctx.guild, CANAL_REGISTROS)

        else:

            canal = None

        total = 0

        for cod in codigos:

            if cod == "vazia":

                view = cartao("📦 CAIXA VAZIA", "Simulação de uma abertura vazia.",

                              BANNER_CAIXA_VAZIA, teste=True)

            else:

                premio = PREMIACOES.get(cod)

                if premio is None:

                    from difflib import get_close_matches
                    sugestoes = get_close_matches(cod, PREMIACOES.keys(), n=1, cutoff=0.55)
                    dica = f" Você quis dizer `!testarlucky {sugestoes[0]}`?" if sugestoes else " Use `!testarlucky lista`."
                    await self.enviar_dm(ctx, f"❌ Código não encontrado: `{cod}`.{dica}")

                    return

                texto = self.texto_premio(

                    premio["nome"], premio["raridade"], "TESTE",

                    "Simulação, não resgatável",

                    usuario=ctx.author.mention if canal else "")

                view = cartao(

                    "🎉 PRÊMIO ESPECIAL ENCONTRADO!" if canal else "🎁 PRÉVIA DE RECOMPENSA",

                    texto, premio["banner"], teste=True)

            if canal:

                await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none(),

                                 **arquivo_do_banner(view))

            else:

                if not await self.enviar_dm(ctx, view=view):

                    return

            total += 1

        await self.enviar_dm(ctx,

            f"✅ **{total} prévia(s)** enviadas para {'registros' if canal else 'suas DMs'}. "

            "Nenhuma premiação real foi gerada.")

    @commands.command(name="luckyestoques")

    @commands.guild_only()

    async def lucky_estoques(self, ctx: commands.Context) -> None:

        """!luckyestoques — relatório privado; estoque CONFIGURADO no código."""

        if not await self.exigir_dono(ctx):

            return

        await self.apagar_comando(ctx)

        await self.garantir_guild(ctx.guild.id)

        linhas = await self.bot.pool.fetch("""

            SELECT code,stock_total,stock_available FROM lucky_reward_stock

            WHERE guild_id=$1 ORDER BY code

        """, ctx.guild.id)

        validos = {r["code"]: r for r in linhas if r["code"] in PREMIACOES}

        texto = "**📦 Estoques (privado)**\n" + "\n".join(

            f"`{code}` — **{validos[code]['stock_available']}** restante(s) / "

            f"{validos[code]['stock_total']} configurado(s)"

            for code in PREMIACOES if code in validos)

        await self.enviar_dm(ctx, texto)

    @commands.command(name="luckysaldo")

    @commands.guild_only()

    async def lucky_saldo(self, ctx: commands.Context) -> None:

        """!luckysaldo — membro pode consultar as tentativas sem revelar prêmios."""

        restantes, renovacao = await self.saldo(ctx.guild.id, ctx.author.id)

        texto = f"🎟️ Você tem **{restantes}/{ABERTURAS_POR_CICLO}** abertura(s)."

        if renovacao:

            texto += f" Renova <t:{int(renovacao.timestamp())}:R>."

        await ctx.send(texto)

    @commands.command(name="luckyentregar")

    @commands.guild_only()

    async def lucky_entregar(self, ctx: commands.Context, abertura_id: int) -> None:

        """!luckyentregar <ID> — use APENAS DEPOIS DE ENTREGAR manualmente."""

        if not await self.exigir_dono(ctx):

            return

        await self.apagar_comando(ctx)

        row = await self.bot.pool.fetchrow("""

            UPDATE lucky_wins SET status='delivered',delivered_by=$3,delivered_at=NOW()

            WHERE opening_id=$1 AND guild_id=$2 AND status='pending'

            RETURNING user_id,reward_code

        """, abertura_id, ctx.guild.id, ctx.author.id)

        if not row:

            await self.enviar_dm(ctx, "❌ Registro inexistente ou já entregue.")

            return

        try:

            await self.atualizar_anuncio(ctx.guild, abertura_id)

        except (discord.HTTPException, ValueError):

            LOGGER.exception("Entrega registrada, mas não atualizou o anúncio #%s", abertura_id)

        await self.enviar_dm(ctx, f"✅ Entrega de `#LB-{abertura_id:06d}` "

                                 f"(`{row['reward_code']}`) registrada como concluída.")

    @commands.command(name="luckypublicar")

    @commands.guild_only()

    async def lucky_publicar(self, ctx: commands.Context, abertura_id: int) -> None:

        """!luckypublicar <ID> — repete anúncio público só se elegível e ausente."""

        if not await self.exigir_dono(ctx):

            return

        await self.apagar_comando(ctx)

        try:

            enviado = await self.anunciar(ctx.guild, abertura_id)

        except (discord.HTTPException, ValueError):

            await self.enviar_dm(ctx, "❌ Falha ao publicar; veja os logs do bot.")

            return

        await self.enviar_dm(ctx,

            "✅ Anúncio publicado." if enviado else "ℹ️ Registro inexistente, secreto ou já anunciado.")

async def setup(bot: commands.Bot) -> None:

    obrigatorios = ("LayoutView", "Container", "TextDisplay", "MediaGallery", "ActionRow")

    if not all(hasattr(discord.ui, nome) for nome in obrigatorios):

        raise RuntimeError("Lucky Block necessita de discord.py 2.6+ com Components V2.")

    await bot.add_cog(LuckyBlockRoyal(bot))
