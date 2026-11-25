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
from discord import app_commands
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

TITULOS: tuple[tuple[int, str, str], ...] = (
    (5, "Barão da Corte", "♜"),
    (15, "Visconde da Coroa", "◇"),
    (30, "Conde Imperial", "✧"),
    (45, "Marquês do Trono", "◆"),
    (60, "Duque da Coroa", "⚜️"),
    (80, "Grão-Duque do Império", "✦"),
    (100, "Príncipe Imperial", "♛"),
)

PRIVILEGIOS: tuple[str, ...] = (
    "**Barão:** acesso ao Salão da Nobreza.",
    "**Visconde:** sorteios especiais da Corte.",
    "**Conde:** recompensas e experiências exclusivas.",
    "**Marquês:** personalização do perfil imperial.",
    "**Duque:** eventos VIP e desafios reservados.",
    "**Grão-Duque:** Conselho de Prestígio e honrarias especiais.",
    "**Príncipe Imperial:** insígnia suprema e registro no Museu.",
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
            "# ♛ CORTE IMPERIAL\n"
            "**FAMÍLIA ROYAL • Honra · União · Lealdade**\n\n"
            "Ascenda na hierarquia da nobreza por sua presença e dedicação à Família."
        ))
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        caixa.add_item(discord.ui.TextDisplay(
            "**⚜️ COMO CONQUISTAR PRESTÍGIO**\n"
            "• Mensagens válidas no chat, respeitando o intervalo de XP.\n"
            "• A cada **3 minutos** em call elegível, com ao menos duas pessoas.\n"
            "• Cargos selecionados pela Diretoria podem receber bônus de XP.\n\n"
            "-# O bot desconsidera spam, bots, salas AFK e chamadas inativas."
        ))
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        caixa.add_item(discord.ui.TextDisplay(
            "**<a:coroa:1564000189167960177> PAINEL DA NOBREZA**\n"
            "Consulte seu progresso, a classificação e as honrarias da Corte. "
            "As consultas aparecem somente para você."
        ))
        caixa.add_item(discord.ui.ActionRow(
            BotaoCorte(cog, "perfil", "Meu Perfil", "👤"),
            BotaoCorte(cog, "ranking", "Ranking Real", "🏆"),
            BotaoCorte(cog, "titulos", "Hierarquia", "👑"),
        ))
        caixa.add_item(discord.ui.ActionRow(
            BotaoCorte(cog, "beneficios", "Benefícios", "💎"),
            BotaoCorte(cog, "historico", "Histórico", "📜"),
        ))
        caixa.add_item(discord.ui.TextDisplay(
            "-# <a:coroa:1564000189167960177> Família Royal"
        ))
        self.add_item(caixa)


def painel_privado(titulo: str, corpo: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    bloco = discord.ui.Container(accent_colour=COR_OURO)
    bloco.add_item(discord.ui.TextDisplay(f"## {titulo}\n{corpo[:3500]}"))
    bloco.add_item(discord.ui.TextDisplay(
        "-# <a:coroa:1564000189167960177> Família Royal • Sistema Oficial de Prestígio"
    ))
    view.add_item(bloco)
    return view


class CorteImperial(commands.Cog):
    corte = app_commands.Group(name="corte", description="Gerenciar a Corte Imperial da Família Royal")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._configs: dict[int, dict] = {}
        self._bonus: dict[int, dict[int, int]] = {}
        self._titulos_cargos: dict[int, dict[int, int]] = {}
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
        guild_id = membro.guild.id
        if guild_id not in self._bonus:
            rows = await self.pool().fetch("""
                SELECT role_id, bonus_percent FROM royal_corte_role_bonus
                WHERE guild_id=$1
            """, guild_id)
            self._bonus[guild_id] = {r["role_id"]: r["bonus_percent"] for r in rows}
        tabela = self._bonus[guild_id]
        return max((tabela.get(role.id, 0) for role in membro.roles), default=0)

    async def mapa_titulos(self, guild_id: int) -> dict[int, int]:
        if guild_id not in self._titulos_cargos:
            rows = await self.pool().fetch("""
                SELECT title_level, role_id FROM royal_corte_titles WHERE guild_id=$1
            """, guild_id)
            self._titulos_cargos[guild_id] = {r["title_level"]: r["role_id"] for r in rows}
        return self._titulos_cargos[guild_id]

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

    async def _apos_xp(self, membro: discord.Member, antigo: int, novo: int):
        n1, n2 = nivel_por_xp(antigo), nivel_por_xp(novo)
        promovidos = [t for t in TITULOS if n1 < t[0] <= n2]
        if not promovidos:
            return
        try:
            promovido = None
            for nivel, nome, simbolo in promovidos:
                row = await self.pool().fetchrow("""
                    INSERT INTO royal_corte_history (guild_id, user_id, title_level, title_name)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING RETURNING title_level
                """, membro.guild.id, membro.id, nivel, nome)
                if row:
                    promovido = (nivel, nome, simbolo)
            if promovido is not None:
                await self._sincronizar_cargo(membro, n2)
                conf = await self.config(membro.guild.id)
                canal = membro.guild.get_channel(conf.get("promo_channel_id") or 0)
                if isinstance(canal, discord.TextChannel):
                    try:
                        await canal.send(
                            f"👑 **CERIMÔNIA DE ASCENSÃO**\n"
                            f"{membro.mention} conquistou o título **{promovido[2]} {promovido[1]}** "
                            f"e alcançou o **nível {n2}** da Corte Imperial.\n"
                            f"*Honra · União · Lealdade*",
                            allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                        )
                    except discord.HTTPException:
                        LOG.exception("Falha ao anunciar ascensão no servidor %s", membro.guild.id)
        except Exception:
            LOG.exception("Falha ao processar nova ascensão de %s", membro.id)

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
            elif secao == "beneficios":
                corpo = (
                    "**Privilégios sugeridos, liberados conforme a configuração da Diretoria:**\n\n"
                    + "\n".join(f"⚜️ {linha}" for linha in PRIVILEGIOS)
                    + "\n\n-# Benefícios não concedem permissões administrativas."
                )
                view = painel_privado("💎 PRIVILÉGIOS DA COROA", corpo)
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

    # --- Administração (slash commands) ---------------------------------------
    @corte.command(name="publicar", description="Publica o painel V2 da Corte Imperial em um canal")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def publicar(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            tem_banner = BANNER.is_file()
            view = PainelImperial(self, com_banner=tem_banner)
            if tem_banner:
                with BANNER.open("rb") as file:
                    await canal.send(view=view, file=discord.File(file, filename=BANNER.name))
            else:
                await canal.send(view=view)
            await interaction.followup.send(
                f"✅ Painel único da Corte Imperial publicado em {canal.mention}."
                + ("" if tem_banner else " Para adicionar o banner, salve assets/corte_imperial_royal.png."),
                ephemeral=True,
            )
        except (discord.HTTPException, OSError):
            LOG.exception("Falha ao publicar painel imperial")
            await interaction.followup.send("❌ Não foi possível publicar. Confira permissões de mensagem/anexo.", ephemeral=True)

    @corte.command(name="ajustar_xp", description="Ajusta XP de chat, call e cooldown")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ajustar_xp(
        self, interaction: discord.Interaction,
        chat_xp: app_commands.Range[int, 1, 100],
        voz_xp: app_commands.Range[int, 1, 200],
        cooldown_segundos: app_commands.Range[int, 30, 600],
    ):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        await self.pool().execute("""
            INSERT INTO royal_corte_config (guild_id, chat_xp, voice_xp, cooldown_seconds)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE SET
                chat_xp=EXCLUDED.chat_xp,
                voice_xp=EXCLUDED.voice_xp,
                cooldown_seconds=EXCLUDED.cooldown_seconds
        """, interaction.guild_id, chat_xp, voz_xp, cooldown_segundos)
        self._configs.pop(interaction.guild_id, None)
        await interaction.response.send_message(
            f"✅ Chat: {chat_xp} XP; call: {voz_xp} XP/3 min; cooldown: {cooldown_segundos}s.", ephemeral=True
        )

    @corte.command(name="bonus_definir", description="Define o bônus percentual de XP de um cargo")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bonus_definir(
        self, interaction: discord.Interaction, cargo: discord.Role,
        percentual: app_commands.Range[int, 1, 100],
    ):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        await self.pool().execute("""
            INSERT INTO royal_corte_role_bonus (guild_id, role_id, bonus_percent)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, role_id) DO UPDATE
            SET bonus_percent=EXCLUDED.bonus_percent
        """, interaction.guild_id, cargo.id, percentual)
        self._bonus.pop(interaction.guild_id, None)
        await interaction.response.send_message(
            f"✅ {cargo.mention} agora concede **+{percentual}% de XP**. "
            "Se houver mais de um cargo com bônus, apenas o maior vale.", ephemeral=True,
        )

    @corte.command(name="bonus_remover", description="Remove um bônus de XP de um cargo")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bonus_remover(self, interaction: discord.Interaction, cargo: discord.Role):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        await self.pool().execute("""
            DELETE FROM royal_corte_role_bonus WHERE guild_id=$1 AND role_id=$2
        """, interaction.guild_id, cargo.id)
        self._bonus.pop(interaction.guild_id, None)
        await interaction.response.send_message(f"✅ Bônus removido de {cargo.mention}.", ephemeral=True)

    @corte.command(name="vincular_titulo", description="Vincula um título da Corte a um cargo do Discord")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def vincular_titulo(self, interaction: discord.Interaction, nivel: int, cargo: discord.Role):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        titulo = next((t for t in TITULOS if t[0] == nivel), None)
        if titulo is None:
            niveis = ", ".join(map(str, (t[0] for t in TITULOS)))
            return await interaction.response.send_message(f"Níveis válidos: {niveis}.", ephemeral=True)
        if cargo.is_default() or cargo.managed:
            return await interaction.response.send_message("Escolha um cargo normal, não gerenciado.", ephemeral=True)
        await self.pool().execute("""
            INSERT INTO royal_corte_titles (guild_id, title_level, role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, title_level) DO UPDATE SET role_id=EXCLUDED.role_id
        """, interaction.guild_id, nivel, cargo.id)
        self._titulos_cargos.pop(interaction.guild_id, None)
        await interaction.response.send_message(
            f"✅ **{titulo[1]}** (nível {nivel}) agora concede {cargo.mention}. "
            "Deixe esse cargo abaixo do cargo do bot na hierarquia.", ephemeral=True,
        )

    @corte.command(name="canal_ascensao", description="Define onde anunciar as promoções imperiais")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def canal_ascensao(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        await self.pool().execute("""
            INSERT INTO royal_corte_config (guild_id, promo_channel_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET promo_channel_id=EXCLUDED.promo_channel_id
        """, interaction.guild_id, canal.id)
        self._configs.pop(interaction.guild_id, None)
        await interaction.response.send_message(
            f"✅ Cerimônias de ascensão serão anunciadas em {canal.mention}.", ephemeral=True,
        )

    @corte.command(name="sincronizar", description="Atualiza o cargo imperial de um membro pelo XP acumulado")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sincronizar(self, interaction: discord.Interaction, membro: discord.Member):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Use no servidor.", ephemeral=True)
        registro = await self.pool().fetchrow("""
            SELECT xp_total FROM royal_corte_members WHERE guild_id=$1 AND user_id=$2
        """, interaction.guild_id, membro.id)
        nivel = nivel_por_xp(registro["xp_total"] if registro else 0)
        await self._sincronizar_cargo(membro, nivel)
        await interaction.response.send_message(
            f"✅ Sincronização solicitada para {membro.mention} no nível {nivel}. "
            "Confira os cargos e a hierarquia do bot.", ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CorteImperial(bot))
