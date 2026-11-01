from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

LOG = logging.getLogger("royal.corte_imperial")
COR_OURO = discord.Colour.from_rgb(212, 175, 55)
FUSO = ZoneInfo("America/Sao_Paulo")
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
BANNER = PASTA_ASSETS / "corte_imperial_royal.png"  

CHAT_XP_PADRAO = 15
CALL_XP_PADRAO = 25
CALL_INTERVALO_SEGUNDOS = 180
CHAT_COOLDOWN_PADRAO = 30
IGNORAR_TEXTO_IDS: set[int] = set()
IGNORAR_VOZ_IDS: set[int] = set()

CARGOS_TITULOS: dict[int, int] = {
    5: 1565942575062450316,   # Plebeu
    15: 1566326355661160560,  # Escudeiro
    30: 1566326356738965504,  # Cavaleiro Real
    60: 1566326356256759828,  # Duque
    100: 1566326355811897484, # Arquiduque
}

CARGOS_BONUS_XP: dict[int, int] = {
    1554367619463913582: 20, # Oficiais da Família Royal
    1553852246104477898: 10, # Booster da Família
    1565942574957600798: 10, # VIP da Família Royal
    1565443626388164790: 5,  # Influencer
}

CANAL_LEVEL_ID = 1559311428459171880
LIMITE_LEVEL_ADMIN = 500

TITULOS: tuple[tuple[int, str, str], ...] = (
    (5, "<@&1565942575062450316>", "<:plebeu:1566330924495274064>"),
    (15, "<@&1566326355661160560>", "<:escudeiro:1566331170914959402>"),
    (30, "<@&1566326356738965504>", "<:cavaleiro:1566331288888888888>"),
    (60, "<@&1566326356256759828>", "<:duque:1566331234110410762>"),
    (100, "<@&1566326355811897484>", "<:arquiduque:1566331300000000000>"),
)


def xp_para_nivel(nivel: int) -> int:
    """Total cumulativo de XP necessário para alcançar um nível."""
    return 100 * max(0, nivel - 1) ** 2


def nivel_por_xp(xp: int) -> int:
    return 1 + math.isqrt(max(0, xp) // 100)


def titulo_atual(nivel: int) -> tuple[int, str, str] | None:
    return next((t for t in reversed(TITULOS) if nivel >= t[0]), None)


def mes_atual():
    return datetime.now(FUSO).date().replace(day=1)


def barra_progresso(atual: int, total: int, tamanho: int = 12) -> str:
    completo = min(tamanho, max(0, (atual * tamanho) // max(1, total)))
    return "▰" * completo + "▱" * (tamanho - completo)


def mensagem_valida(conteudo: str) -> str | None:
    """Filtro conservador: reduz spam, não promete detectar semântica humana."""
    texto = " ".join(conteudo.casefold().split())
    if len(texto) < 8 or len(texto) > 1800:
        return None
    if texto.startswith(("!", "/", ".", "?", ">")):
        return None
    sem_links = re.sub(r"https?://\S+|www\.\S+", "", texto)
    palavras = re.findall(r"[^\W\d_]{2,}", sem_links, flags=re.UNICODE)
    if len(palavras) < 2 or sum(map(len, palavras)) < 6:
        return None
    if len(set(re.sub(r"\s", "", sem_links))) <= 2:
        return None
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


class BotaoCorte(discord.ui.Button):
    def __init__(self, cog: "CorteImperial", destino: str, rotulo: str, emoji: str):
        super().__init__(
            label=rotulo,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"royal:corte:v1:{destino}",
        )
        self.cog = cog
        self.destino = destino

    async def callback(self, interaction: discord.Interaction):
        await self.cog.abrir_secao(interaction, self.destino)


class PainelImperial(discord.ui.LayoutView):
    """Painel público, persistente e com um único banner opcional."""
    def __init__(self, cog: "CorteImperial", com_banner: bool = False):
        super().__init__(timeout=None)
        caixa = discord.ui.Container(accent_colour=COR_OURO)
        if com_banner:
            caixa.add_item(discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=f"attachment://{BANNER.name}")
            ))
        caixa.add_item(discord.ui.TextDisplay(
            "# <:escudeiro:1566331170914959402> CORTE IMPERIAL\n"
            "**FAMÍLIA ROYAL • Honra · União · Lealdade**\n\n"
            "Ascenda na hierarquia da nobreza por sua presença e dedicação à Família."
        ))
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        caixa.add_item(discord.ui.TextDisplay(
            "**COMO CONQUISTAR PRESTÍGIO**\n"
            "- `👑` Mensagens válidas no chat, respeitando o intervalo de XP.\n"
            "- `👑` A cada **3 minutos** em call elegível, com ao menos duas pessoas.\n"
            "- `👑` Cargos selecionados pela Diretoria podem receber bônus de XP.\n\n"
        ))
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        caixa.add_item(discord.ui.TextDisplay(
            "**PAINEL DA NOBREZA**\n"
            "- `👑` Consulte seu progresso, a classificação e as honrarias da Corte.\"\n"
            "- `👑` As consultas aparecem somente para você."
        ))
        caixa.add_item(discord.ui.ActionRow(
            BotaoCorte(cog, "perfil", "Meu Perfil", "👤"),
            BotaoCorte(cog, "ranking", "Ranking Real", "🏆"),
            BotaoCorte(cog, "titulos", "Hierarquia", "👑"),
            BotaoCorte(cog, "historico", "Histórico", "📜"),
        ))
        caixa.add_item(discord.ui.TextDisplay(
            "-# Família Royal"
        ))
        self.add_item(caixa)


def painel_privado(titulo: str, corpo: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    bloco = discord.ui.Container(accent_colour=COR_OURO)
    bloco.add_item(discord.ui.TextDisplay(f"## {titulo}\n{corpo[:3500]}"))
    bloco.add_item(discord.ui.TextDisplay(
        "-# Família Royal • Sistema Oficial de Prestígio"
    ))
    view.add_item(bloco)
    return view


class CorteImperial(commands.Cog):
    @commands.group(name="corte", invoke_without_command=True)
    @commands.guild_only()
    async def corte(self, ctx: commands.Context):
        """Comandos de gerenciamento da Corte Imperial (prefixo !)."""
        await ctx.reply(
            "**👑 Administração da Corte Imperial**\n"
            "`!corte publicar #canal`\n"
            "`!corte ajustar_xp <chat> <voz> <cooldown>`\n"
            "`!level [@membro]` • `!rank [@membro]` • `!top [geral|mensal|call]`\n"
            "`!darlevel @membro <quantidade>` • `!setlevel @membro <nivel>`\n"
            "`!tirarlevel @membro <quantidade>`\n"
            "`!corte canal_ascensao #canal` (anúncios de nível)\n"
            "`!corte sincronizar @membro`\n\n"
            "-# Comandos de gerenciamento exigem Gerenciar Servidor; "
            "ajustes de nível exigem Administrador. IDs de títulos e bônus ficam no código.",
            mention_author=False,
        )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._configs: dict[int, dict] = {}
        # Usuários em call elegível: timestamp da última verificação + segundos parciais.
        self._voz_ultimo: dict[tuple[int, int], float] = {}
        self._voz_parcial: dict[tuple[int, int], float] = {}

    def pool(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("A Corte Imperial requer o pool PostgreSQL em bot.pool.")
        return pool

    async def cog_load(self):
        pool = self.pool()
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_config (
                guild_id BIGINT PRIMARY KEY,
                chat_xp INTEGER NOT NULL DEFAULT 15,
                voice_xp INTEGER NOT NULL DEFAULT 25,
                cooldown_seconds INTEGER NOT NULL DEFAULT 30,
                promo_channel_id BIGINT
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                xp_total BIGINT NOT NULL DEFAULT 0,
                xp_chat BIGINT NOT NULL DEFAULT 0,
                xp_voice BIGINT NOT NULL DEFAULT 0,
                chat_messages BIGINT NOT NULL DEFAULT 0,
                voice_seconds BIGINT NOT NULL DEFAULT 0,
                last_chat_at TIMESTAMPTZ,
                last_message_hash VARCHAR(24),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_monthly (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                month_date DATE NOT NULL,
                xp BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, month_date)
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_role_bonus (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                bonus_percent INTEGER NOT NULL CHECK (bonus_percent BETWEEN 0 AND 100),
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_titles (
                guild_id BIGINT NOT NULL,
                title_level INTEGER NOT NULL,
                role_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, title_level)
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_history (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                title_level INTEGER NOT NULL,
                title_name TEXT NOT NULL,
                achieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id, title_level)
            )
        """)
        await pool.execute("""
            CREATE INDEX IF NOT EXISTS royal_corte_ranking_idx
            ON royal_corte_members (guild_id, xp_total DESC)
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_corte_level_notices (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                highest_level INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        # Custom IDs fixos: botões continuam funcionando após reinicializações.
        self.bot.add_view(PainelImperial(self))
        self.verificar_voz.start()
        LOG.info("Corte Imperial carregada, tabelas preservadas.")

    def cog_unload(self):
        self.verificar_voz.cancel()
        self._voz_ultimo.clear()
        self._voz_parcial.clear()

    async def config(self, guild_id: int) -> dict:
        if guild_id not in self._configs:
            pool = self.pool()
            row = await pool.fetchrow("""
                INSERT INTO royal_corte_config (guild_id) VALUES ($1)
                ON CONFLICT (guild_id) DO UPDATE SET guild_id=EXCLUDED.guild_id
                RETURNING chat_xp, voice_xp, cooldown_seconds, promo_channel_id
            """, guild_id)
            self._configs[guild_id] = dict(row)
        return self._configs[guild_id]

    async def bonus_pct(self, membro: discord.Member) -> int:
        """Bônus configurado SOMENTE no dicionário CARGOS_BONUS_XP."""
        return max((
            max(0, min(100, CARGOS_BONUS_XP.get(cargo.id, 0)))
            for cargo in membro.roles
        ), default=0)

    async def mapa_titulos(self, guild_id: int) -> dict[int, int]:
        """IDs de títulos configurados SOMENTE no arquivo Python."""
        return {nivel: role_id for nivel, role_id in CARGOS_TITULOS.items()
                if isinstance(role_id, int) and role_id > 0}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if message.channel.id in IGNORAR_TEXTO_IDS:
            return
        if message.type is not discord.MessageType.default:
            return
        hash_msg = mensagem_valida(message.content)
        if hash_msg is None:
            return
        membro = message.author
        if not isinstance(membro, discord.Member):
            membro = message.guild.get_member(message.author.id)
        if not isinstance(membro, discord.Member):
            return
        try:
            conf = await self.config(message.guild.id)
            bonus = await self.bonus_pct(membro)
            ganho = conf["chat_xp"] * (100 + bonus) // 100
            async with self.pool().acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow("""
                        INSERT INTO royal_corte_members (
                            guild_id, user_id, xp_total, xp_chat, chat_messages,
                            last_chat_at, last_message_hash
                        ) VALUES ($1, $2, $3, $3, 1, NOW(), $4)
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET
                            xp_total = royal_corte_members.xp_total + EXCLUDED.xp_total,
                            xp_chat = royal_corte_members.xp_chat + EXCLUDED.xp_chat,
                            chat_messages = royal_corte_members.chat_messages + 1,
                            last_chat_at = NOW(),
                            last_message_hash = EXCLUDED.last_message_hash,
                            updated_at = NOW()
                        WHERE (
                            royal_corte_members.last_chat_at IS NULL OR
                            royal_corte_members.last_chat_at <= NOW() - ($5::int * INTERVAL '1 second')
                        ) AND (
                            royal_corte_members.last_message_hash IS DISTINCT FROM EXCLUDED.last_message_hash OR
                            royal_corte_members.last_chat_at < NOW() - INTERVAL '10 minutes'
                        )
                        RETURNING xp_total
                    """, message.guild.id, membro.id, ganho, hash_msg, conf["cooldown_seconds"])
                    if row:
                        await self._xp_mensal(conn, message.guild.id, membro.id, ganho)
            if row:
                await self._apos_xp(membro, row["xp_total"] - ganho, row["xp_total"])
        except Exception:
            LOG.exception("Falha ao conceder XP por mensagem a %s", membro.id)

    async def _xp_mensal(self, conn, guild_id: int, user_id: int, ganho: int):
        await conn.execute("""
            INSERT INTO royal_corte_monthly (guild_id, user_id, month_date, xp)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, month_date)
            DO UPDATE SET xp = royal_corte_monthly.xp + EXCLUDED.xp
        """, guild_id, user_id, mes_atual(), ganho)

    async def _xp_voz(self, membro: discord.Member, ciclos: int):
        if ciclos <= 0:
            return
        conf = await self.config(membro.guild.id)
        bonus = await self.bonus_pct(membro)
        ganho = conf["voice_xp"] * ciclos * (100 + bonus) // 100
        segundos = CALL_INTERVALO_SEGUNDOS * ciclos
        async with self.pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    INSERT INTO royal_corte_members (
                        guild_id, user_id, xp_total, xp_voice, voice_seconds
                    ) VALUES ($1, $2, $3, $3, $4)
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        xp_total = royal_corte_members.xp_total + EXCLUDED.xp_total,
                        xp_voice = royal_corte_members.xp_voice + EXCLUDED.xp_voice,
                        voice_seconds = royal_corte_members.voice_seconds + EXCLUDED.voice_seconds,
                        updated_at = NOW()
                    RETURNING xp_total
                """, membro.guild.id, membro.id, ganho, segundos)
                await self._xp_mensal(conn, membro.guild.id, membro.id, ganho)
        await self._apos_xp(membro, row["xp_total"] - ganho, row["xp_total"])

    def _pode_ganhar_voz(self, membro: discord.Member) -> bool:
        estado = membro.voice
        return bool(
            estado and estado.channel and
            not (estado.self_deaf or estado.deaf or estado.self_mute or estado.mute) and
            not membro.bot
        )

    def _limpar_voz_canal(self, channel: discord.abc.GuildChannel | None):
        if channel is None or not hasattr(channel, "members"):
            return
        # Uma terceira pessoa entrando não deve reiniciar os 3 minutos de quem
        # já estava conversando. Só interrompemos quem ficou sem companhia elegível.
        if len([m for m in channel.members if self._pode_ganhar_voz(m)]) >= 2:
            return
        for membro in channel.members:
            if not isinstance(membro, discord.Member):
                continue
            chave = (membro.guild.id, membro.id)
            self._voz_ultimo.pop(chave, None)
            self._voz_parcial.pop(chave, None)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member.bot:
            return
        mudou = (
            before.channel != after.channel or
            before.self_deaf != after.self_deaf or before.deaf != after.deaf or
            before.self_mute != after.self_mute or before.mute != after.mute
        )
        if mudou:
            self._limpar_voz_canal(before.channel)
            self._limpar_voz_canal(after.channel)
            chave = (member.guild.id, member.id)
            self._voz_ultimo.pop(chave, None)
            self._voz_parcial.pop(chave, None)

    @tasks.loop(seconds=15)
    async def verificar_voz(self):
        agora = time.monotonic()
        ativos: set[tuple[int, int]] = set()
        for guild in self.bot.guilds:
            afk = guild.afk_channel
            for canal in guild.voice_channels:
                if canal.id in IGNORAR_VOZ_IDS or canal.id == getattr(afk, "id", None):
                    continue
                participantes = [m for m in canal.members if self._pode_ganhar_voz(m)]
                if len(participantes) < 2:
                    continue
                for membro in participantes:
                    chave = (guild.id, membro.id)
                    ativos.add(chave)
                    anterior = self._voz_ultimo.get(chave)
                    self._voz_ultimo[chave] = agora
                    if anterior is None:
                        continue  # Inicia contagem somente após observar o estado elegível.
                    intervalo = max(0, min(20, agora - anterior))
                    total = self._voz_parcial.get(chave, 0.0) + intervalo
                    ciclos = int(total // CALL_INTERVALO_SEGUNDOS)
                    self._voz_parcial[chave] = total - ciclos * CALL_INTERVALO_SEGUNDOS
                    if ciclos:
                        try:
                            await self._xp_voz(membro, ciclos)
                        except Exception:
                            # Não perde um ciclo conquistado por erro temporário de BD.
                            self._voz_parcial[chave] += ciclos * CALL_INTERVALO_SEGUNDOS
                            LOG.exception("Falha no XP de call de %s", membro.id)
        for chave in list(self._voz_ultimo):
            if chave not in ativos:
                self._voz_ultimo.pop(chave, None)
                self._voz_parcial.pop(chave, None)

    @verificar_voz.before_loop
    async def _esperar_bot(self):
        await self.bot.wait_until_ready()

    async def _apos_xp(self, membro: discord.Member, antigo: int, novo: int,
                      *, administrativo: bool = False):
        """Anuncia CADA nível alcançado (uma mensagem por ganho, mesmo se pular níveis)."""
        nivel_antigo, nivel_novo = nivel_por_xp(antigo), nivel_por_xp(novo)
        if nivel_novo <= nivel_antigo:
            return
        try:
            titulos_alcancados = [t for t in TITULOS if nivel_antigo < t[0] <= nivel_novo]
            for nivel_titulo, nome, _ in titulos_alcancados:
                await self.pool().execute("""
                    INSERT INTO royal_corte_history (guild_id, user_id, title_level, title_name)
                    VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
                """, membro.guild.id, membro.id, nivel_titulo, nome)

            if titulos_alcancados:
                # Considera o nível ATUAL no banco para evitar atribuir um cargo
                # inferior caso chat/call/admin atualizem XP simultaneamente.
                atual = await self.pool().fetchval("""
                    SELECT xp_total FROM royal_corte_members
                    WHERE guild_id=$1 AND user_id=$2
                """, membro.guild.id, membro.id)
                await self._sincronizar_cargo(membro, nivel_por_xp(atual if atual is not None else novo))

            # Reserva atômica do nível anunciado; evita avisos duplicados.
            reservado = await self.pool().fetchrow("""
                INSERT INTO royal_corte_level_notices (guild_id, user_id, highest_level)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET highest_level=EXCLUDED.highest_level
                WHERE royal_corte_level_notices.highest_level < EXCLUDED.highest_level
                RETURNING highest_level
            """, membro.guild.id, membro.id, nivel_novo)
            if reservado is None:
                return

            conf = await self.config(membro.guild.id)
            canal_id = CANAL_LEVEL_ID or conf.get("promo_channel_id")
            canal = membro.guild.get_channel(canal_id) if canal_id else None
            if not isinstance(canal, discord.TextChannel):
                LOG.info("Sem canal de level configurado no servidor %s.", membro.guild.id)
                return

            titulo_novo = titulo_atual(nivel_novo)
            conquistou_titulo = bool(titulos_alcancados)
            faixa = (f"do nível **{nivel_antigo}** para o **{nivel_novo}**"
                     if nivel_novo > nivel_antigo + 1 else f"para o **nível {nivel_novo}**")
            corpo = (
                f"🎉 {membro.mention} avançou {faixa}!\n"
                f"**XP total:** `{novo:,}`\n"
            )
            if conquistou_titulo and titulo_novo:
                corpo += f"👑 **Novo título:** {titulo_novo[2]} {titulo_novo[1]}\n"
            if administrativo:
                corpo += "-# Progressão ajustada pela administração.\n"
            corpo += "-# Honra · União · Lealdade"
            titulo_cabecalho = "👑 CERIMÔNIA DE ASCENSÃO" if conquistou_titulo else "✨ NOVO NÍVEL IMPERIAL"
            try:
                await canal.send(
                    view=painel_privado(titulo_cabecalho, corpo),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                LOG.exception("Falha ao anunciar novo nível de %s", membro.id)
        except Exception:
            LOG.exception("Falha ao processar nível de %s", membro.id)

    async def _sincronizar_cargo(self, membro: discord.Member, nivel: int):
        titulos = await self.mapa_titulos(membro.guild.id)
        disponiveis = sorted((lv, role_id) for lv, role_id in titulos.items() if lv <= nivel)
        alvo_id = disponiveis[-1][1] if disponiveis else None
        alvo = membro.guild.get_role(alvo_id) if alvo_id else None
        me = membro.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            LOG.warning("Bot não possui Gerenciar Cargos para a Corte Imperial.")
            return
        cargos_da_corte = [membro.guild.get_role(role_id) for role_id in set(titulos.values())]
        removiveis = [r for r in cargos_da_corte if r and r != alvo and r in membro.roles and r < me.top_role]
        try:
            if removiveis:
                await membro.remove_roles(*removiveis, reason="Atualização de título da Corte Imperial")
            if alvo and alvo not in membro.roles:
                if alvo >= me.top_role:
                    LOG.warning("Cargo %s acima do cargo do bot; reorganize a hierarquia.", alvo.id)
                else:
                    await membro.add_roles(alvo, reason="Ascensão por XP na Corte Imperial")
        except discord.HTTPException:
            LOG.exception("Falha ao atualizar cargo imperial de %s", membro.id)

    async def abrir_secao(self, interaction: discord.Interaction, secao: str):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use o painel dentro da Família Royal.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        gid, uid = interaction.guild.id, interaction.user.id
        try:
            if secao == "perfil":
                registro = await self.pool().fetchrow("""
                    SELECT * FROM royal_corte_members WHERE guild_id=$1 AND user_id=$2
                """, gid, uid)
                xp = registro["xp_total"] if registro else 0
                nivel = nivel_por_xp(xp)
                titulo = titulo_atual(nivel)
                atual, proximo = xp_para_nivel(nivel), xp_para_nivel(nivel + 1)
                pct = int((xp - atual) * 100 / max(1, proximo - atual))
                bonus = await self.bonus_pct(interaction.user)
                estrelas = max(0, (nivel - 100) // 10)
                corpo = (
                    f"**Membro:** {interaction.user.mention}\n"
                    f"**Título:** {titulo[2] + ' ' + titulo[1] if titulo else 'Membro da Corte'}\n"
                    f"**Nível:** `{nivel}`  •  **XP total:** `{xp:,}`\n"
                    f"**Progresso:** `{barra_progresso(xp-atual, proximo-atual)}` {pct}%\n"
                    f"**Próximo nível:** `{proximo-xp:,} XP`\n"
                    f"**Mensagens válidas:** `{registro['chat_messages'] if registro else 0:,}`\n"
                    f"**Call elegível:** `{(registro['voice_seconds'] // 60) if registro else 0:,} min`\n"
                    f"**Bônus por cargo:** `+{bonus}%`"
                    + (f"\n**Estrelas de Prestígio:** `✦ {estrelas}`" if estrelas else "")
                )
                view = painel_privado("👤 IDENTIDADE IMPERIAL", corpo)
            elif secao == "ranking":
                geral = await self.pool().fetch("""
                    SELECT user_id, xp_total FROM royal_corte_members
                    WHERE guild_id=$1 ORDER BY xp_total DESC, user_id ASC LIMIT 10
                """, gid)
                mensal = await self.pool().fetch("""
                    SELECT user_id, xp FROM royal_corte_monthly
                    WHERE guild_id=$1 AND month_date=$2
                    ORDER BY xp DESC, user_id ASC LIMIT 10
                """, gid, mes_atual())
                voz = await self.pool().fetch("""
                    SELECT user_id, voice_seconds FROM royal_corte_members
                    WHERE guild_id=$1 AND voice_seconds > 0
                    ORDER BY voice_seconds DESC, user_id ASC LIMIT 10
                """, gid)
                linhas_geral = [f"`{i:02}.` <@{r['user_id']}> — **{r['xp_total']:,} XP**"
                                for i, r in enumerate(geral, 1)] or ["Nenhum XP registrado ainda."]
                linhas_mes = [f"`{i:02}.` <@{r['user_id']}> — **{r['xp']:,} XP**"
                              for i, r in enumerate(mensal, 1)] or ["Sem participantes neste mês."]
                linhas_voz = [f"`{i:02}.` <@{r['user_id']}> — **{r['voice_seconds'] // 60:,} min**"
                              for i, r in enumerate(voz, 1)] or ["Sem tempo elegível contabilizado ainda."]
                corpo = (
                    "**🏆 Ranking permanente**\n" + "\n".join(linhas_geral) +
                    "\n\n**📅 Ranking mensal**\n" + "\n".join(linhas_mes) +
                    "\n\n**🎧 Ranking de call**\n" + "\n".join(linhas_voz)
                )
                view = painel_privado("🏆 RANKING REAL", corpo)
            elif secao == "titulos":
                linhas = [f"{icone} **{nome}** — nível **{nivel}**, a partir de **{xp_para_nivel(nivel):,} XP**"
                          for nivel, nome, icone in TITULOS]
                corpo = (
                    "**A evolução é automática por XP.**\n\n" + "\n".join(linhas) +
                    "\n\n-# Após o nível 100, a cada 10 níveis surge uma Estrela de Prestígio."
                )
                view = painel_privado("👑 HIERARQUIA IMPERIAL", corpo)
            elif secao == "historico":
                rows = await self.pool().fetch("""
                    SELECT title_name, title_level, achieved_at
                    FROM royal_corte_history
                    WHERE guild_id=$1 AND user_id=$2
                    ORDER BY achieved_at DESC, title_level DESC LIMIT 12
                """, gid, uid)
                linhas = [f"⚜️ **{r['title_name']}** (nível {r['title_level']}) • <t:{int(r['achieved_at'].timestamp())}:d>"
                          for r in rows] or ["Sua primeira ascensão ainda está por vir."]
                view = painel_privado("📜 HISTÓRICO IMPERIAL", "\n".join(linhas))
            else:
                view = painel_privado("CORTE IMPERIAL", "Seção indisponível.")
            await interaction.followup.send(view=view, ephemeral=True)
        except Exception:
            LOG.exception("Falha ao abrir seção %s da Corte Imperial", secao)
            await interaction.followup.send("❌ Não foi possível consultar a Corte Imperial agora.", ephemeral=True)

    # --- Administração via prefixo ! -----------------------------------------
    @corte.command(name="publicar")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar(self, ctx: commands.Context, canal: discord.TextChannel):
        """!corte publicar #canal — publica um painel V2 com um único banner."""
        me = ctx.guild.me
        if me is None:
            await ctx.reply("❌ Não consegui identificar o bot no servidor.", mention_author=False)
            return
        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            await ctx.reply("❌ Preciso de permissão para acessar e enviar mensagens nesse canal.", mention_author=False)
            return

        tem_banner = BANNER.is_file()
        if tem_banner and not perms.attach_files:
            await ctx.reply("❌ Preciso da permissão Anexar Arquivos nesse canal.", mention_author=False)
            return

        try:
            view = PainelImperial(self, com_banner=tem_banner)
            if tem_banner:
                with BANNER.open("rb") as arquivo:
                    await canal.send(view=view, file=discord.File(arquivo, filename=BANNER.name))
            else:
                await canal.send(view=view)
            await ctx.reply(
                f"✅ Painel único da Corte Imperial publicado em {canal.mention}."
                + ("" if tem_banner else " Para adicionar o banner, salve assets/corte_imperial_royal.png."),
                mention_author=False,
            )
        except (discord.HTTPException, OSError):
            LOG.exception("Falha ao publicar painel imperial")
            await ctx.reply("❌ Não foi possível publicar. Confira as permissões e os logs.", mention_author=False)

    @corte.command(name="ajustar_xp")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ajustar_xp(self, ctx: commands.Context, chat_xp: int, voz_xp: int, cooldown_segundos: int):
        """!corte ajustar_xp 15 25 30 — ajusta XP do chat, voz e intervalo."""
        if not (1 <= chat_xp <= 100 and 1 <= voz_xp <= 200 and 30 <= cooldown_segundos <= 600):
            await ctx.reply(
                "❌ Valores aceitos: chat de 1 a 100 XP; voz de 1 a 200 XP; cooldown de 30 a 600 segundos.",
                mention_author=False,
            )
            return
        await self.pool().execute("""
            INSERT INTO royal_corte_config (guild_id, chat_xp, voice_xp, cooldown_seconds)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE SET
                chat_xp=EXCLUDED.chat_xp,
                voice_xp=EXCLUDED.voice_xp,
                cooldown_seconds=EXCLUDED.cooldown_seconds
        """, ctx.guild.id, chat_xp, voz_xp, cooldown_segundos)
        self._configs.pop(ctx.guild.id, None)
        await ctx.reply(
            f"✅ Chat: **{chat_xp} XP**; call: **{voz_xp} XP/3 min**; cooldown: **{cooldown_segundos}s**.",
            mention_author=False,
        )

    @corte.command(name="canal_ascensao")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def canal_ascensao(self, ctx: commands.Context, canal: discord.TextChannel):
        """!corte canal_ascensao #canal — define onde anunciar níveis e títulos."""
        await self.pool().execute("""
            INSERT INTO royal_corte_config (guild_id, promo_channel_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET promo_channel_id=EXCLUDED.promo_channel_id
        """, ctx.guild.id, canal.id)
        self._configs.pop(ctx.guild.id, None)
        await ctx.reply(
            f"✅ Subidas de nível e cerimônias de ascensão serão anunciadas em {canal.mention}.",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @corte.command(name="sincronizar")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def sincronizar(self, ctx: commands.Context, membro: discord.Member):
        """!corte sincronizar @membro — atualiza cargo pelo XP acumulado."""
        registro = await self.pool().fetchrow("""
            SELECT xp_total FROM royal_corte_members WHERE guild_id=$1 AND user_id=$2
        """, ctx.guild.id, membro.id)
        nivel = nivel_por_xp(registro["xp_total"] if registro else 0)
        await self._sincronizar_cargo(membro, nivel)
        await ctx.reply(
            f"✅ Sincronização solicitada para {membro.mention} no nível **{nivel}**. "
            "Confira os cargos e a hierarquia do bot.",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # --- Consultas públicas de nível e ranking -------------------------------
    @commands.command(name="level", aliases=["nivel", "xp"])
    @commands.guild_only()
    @commands.cooldown(2, 12, commands.BucketType.user)
    async def level(self, ctx: commands.Context, membro: discord.Member = None):
        """!level [@membro] — mostra nível, XP, progresso e título."""
        membro = membro or ctx.author
        registro = await self.pool().fetchrow("""
            SELECT xp_total, chat_messages, voice_seconds FROM royal_corte_members
            WHERE guild_id=$1 AND user_id=$2
        """, ctx.guild.id, membro.id)
        xp = registro["xp_total"] if registro else 0
        nivel = nivel_por_xp(xp)
        titulo = titulo_atual(nivel)
        inicio, fim = xp_para_nivel(nivel), xp_para_nivel(nivel + 1)
        pct = round(100 * (xp - inicio) / max(1, fim - inicio))
        bonus = await self.bonus_pct(membro)
        embed = discord.Embed(title="👑 Identidade Imperial", colour=COR_OURO)
        embed.description = (
            f"**{membro.mention}**\n"
            f"⚜️ **Título:** {titulo[2] + ' ' + titulo[1] if titulo else 'Membro da Corte'}\n"
            f"✨ **Nível:** `{nivel}`  •  **XP:** `{xp:,}`\n"
            f"`{barra_progresso(xp - inicio, fim - inicio)}` **{pct}%**\n"
            f"**Próximo nível:** `{fim - xp:,} XP`\n"
            f"💬 **Mensagens válidas:** `{registro['chat_messages'] if registro else 0:,}`\n"
            f"🎧 **Call elegível:** `{registro['voice_seconds'] // 60 if registro else 0:,} min`\n"
            f"💎 **Bônus de XP:** `+{bonus}%`"
        )
        embed.set_footer(text="Família Royal • Corte Imperial")
        await ctx.reply(embed=embed, mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="rank", aliases=["posicao"])
    @commands.guild_only()
    @commands.cooldown(2, 12, commands.BucketType.user)
    async def rank(self, ctx: commands.Context, membro: discord.Member = None):
        """!rank [@membro] — posição no ranking geral."""
        membro = membro or ctx.author
        xp = await self.pool().fetchval("""
            SELECT xp_total FROM royal_corte_members
            WHERE guild_id=$1 AND user_id=$2
        """, ctx.guild.id, membro.id)
        if xp is None:
            return await ctx.reply("📜 Este membro ainda não possui XP registrado.", mention_author=False)
        posicao = await self.pool().fetchval("""
            SELECT COUNT(*) + 1 FROM royal_corte_members
            WHERE guild_id=$1 AND (xp_total > $2 OR (xp_total=$2 AND user_id < $3))
        """, ctx.guild.id, xp, membro.id)
        await ctx.reply(f"🏆 {membro.mention} ocupa a posição **#{posicao}** "
                        f"com **{xp:,} XP** (nível **{nivel_por_xp(xp)}**).",
                        mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="top", aliases=["ranking"])
    @commands.guild_only()
    @commands.cooldown(2, 12, commands.BucketType.user)
    async def top(self, ctx: commands.Context, tipo: str = "geral"):
        """!top [geral|mensal|call] — mostra os 10 maiores."""
        tipo = tipo.casefold()
        if tipo not in ("geral", "mensal", "call", "voz"):
            return await ctx.reply("❌ Use `!top`, `!top mensal` ou `!top call`.", mention_author=False)
        if tipo == "mensal":
            rows = await self.pool().fetch("""
                SELECT user_id, xp AS valor FROM royal_corte_monthly
                WHERE guild_id=$1 AND month_date=$2
                ORDER BY xp DESC, user_id ASC LIMIT 10
            """, ctx.guild.id, mes_atual())
            titulo, unidade = "Ranking Mensal", "XP"
        elif tipo in ("call", "voz"):
            rows = await self.pool().fetch("""
                SELECT user_id, voice_seconds AS valor FROM royal_corte_members
                WHERE guild_id=$1 AND voice_seconds > 0
                ORDER BY voice_seconds DESC, user_id ASC LIMIT 10
            """, ctx.guild.id)
            titulo, unidade = "Ranking de Call", "min"
        else:
            rows = await self.pool().fetch("""
                SELECT user_id, xp_total AS valor FROM royal_corte_members
                WHERE guild_id=$1 ORDER BY xp_total DESC, user_id ASC LIMIT 10
            """, ctx.guild.id)
            titulo, unidade = "Ranking Geral", "XP"
        linhas = [
            f"`{i:02}.` <@{r['user_id']}> — **{(r['valor'] // 60 if unidade == 'min' else r['valor']):,} {unidade}**"
            for i, r in enumerate(rows, 1)
        ] or ["Ainda não há participantes neste ranking."]
        embed = discord.Embed(title=f"🏆 Corte Imperial • {titulo}",
                              description="\n".join(linhas), colour=COR_OURO)
        embed.set_footer(text="Família Royal • Honra · União · Lealdade")
        await ctx.reply(embed=embed, mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none())

    # --- Ajustes manuais, restritos a administradores -------------------------
    async def _alterar_level_admin(self, ctx: commands.Context, membro: discord.Member,
                                 quantidade: int, modo: str):
        if membro.bot:
            return await ctx.reply("❌ Bots não podem receber níveis.", mention_author=False)
        if modo == "setar" and not (1 <= quantidade <= LIMITE_LEVEL_ADMIN):
            return await ctx.reply(f"❌ Informe um nível de 1 a {LIMITE_LEVEL_ADMIN}.", mention_author=False)
        if modo != "setar" and not (1 <= quantidade <= 100):
            return await ctx.reply("❌ Informe de 1 a 100 níveis por operação.", mention_author=False)

        async with self.pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO royal_corte_members (guild_id, user_id)
                    VALUES ($1, $2) ON CONFLICT DO NOTHING
                """, ctx.guild.id, membro.id)
                xp_antigo = await conn.fetchval("""
                    SELECT xp_total FROM royal_corte_members
                    WHERE guild_id=$1 AND user_id=$2 FOR UPDATE
                """, ctx.guild.id, membro.id)
                nivel_antigo = nivel_por_xp(xp_antigo)
                if modo == "dar":
                    destino = min(LIMITE_LEVEL_ADMIN, nivel_antigo + quantidade)
                    # Conserva o XP já acumulado dentro do nível atual.
                    xp_novo = xp_antigo + xp_para_nivel(destino) - xp_para_nivel(nivel_antigo)
                elif modo == "tirar":
                    destino = max(1, nivel_antigo - quantidade)
                    xp_novo = max(0, xp_para_nivel(destino))
                else:
                    destino = quantidade
                    xp_novo = xp_para_nivel(destino)
                if xp_novo != xp_antigo:
                    await conn.execute("""
                        UPDATE royal_corte_members
                        SET xp_total=$3, updated_at=NOW()
                        WHERE guild_id=$1 AND user_id=$2
                    """, ctx.guild.id, membro.id, xp_novo)

        if xp_novo == xp_antigo:
            return await ctx.reply("ℹ️ O membro já está no nível solicitado.", mention_author=False)
        nivel_novo = nivel_por_xp(xp_novo)
        if nivel_novo > nivel_antigo:
            await self._apos_xp(membro, xp_antigo, xp_novo, administrativo=True)
        else:
            await self._sincronizar_cargo(membro, nivel_novo)
        await ctx.reply(
            f"✅ **{membro.display_name}**: nível **{nivel_antigo} → {nivel_novo}** "
            f"(`{xp_antigo:,} → {xp_novo:,} XP`).",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="darlevel", aliases=["addlevel"])
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def darlevel(self, ctx: commands.Context, membro: discord.Member, quantidade: int):
        """!darlevel @membro 5 — adiciona 5 níveis, exigindo Administrador."""
        await self._alterar_level_admin(ctx, membro, quantidade, "dar")

    @commands.command(name="setlevel")
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def setlevel(self, ctx: commands.Context, membro: discord.Member, nivel: int):
        """!setlevel @membro 30 — define exatamente o nível 30."""
        await self._alterar_level_admin(ctx, membro, nivel, "setar")

    @commands.command(name="tirarlevel", aliases=["removelevel"])
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def tirarlevel(self, ctx: commands.Context, membro: discord.Member, quantidade: int):
        """!tirarlevel @membro 2 — remove 2 níveis, exigindo Administrador."""
        await self._alterar_level_admin(ctx, membro, quantidade, "tirar")

    async def cog_command_error(self, ctx: commands.Context, erro: commands.CommandError):
        """Mostra erros de permissão e de uso para todos os subcomandos."""
        if isinstance(erro, commands.MissingPermissions):
            await ctx.reply("⛔ Você não possui a permissão necessária (Administrador ou Gerenciar Servidor).", mention_author=False)
        elif isinstance(erro, commands.MissingRequiredArgument):
            await ctx.reply(
                f"❌ Argumento ausente. Use `!corte {ctx.command.name}` com os parâmetros necessários. "
                "Use `!corte` para consultar os comandos disponíveis.", mention_author=False,
            )
        elif isinstance(erro, commands.BadArgument):
            await ctx.reply(
                "❌ Argumento inválido. Confira a menção do cargo/canal/membro ou os valores numéricos. "
                "Use `!corte` para consultar os comandos disponíveis.", mention_author=False,
            )
        else:
            LOG.error("Falha no comando da Corte Imperial", exc_info=(type(erro), erro, erro.__traceback__))
            await ctx.reply("❌ Falha ao executar o comando. Consulte os logs do bot.", mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(CorteImperial(bot))
