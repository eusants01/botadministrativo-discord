"""História da Família Royal — Components V2, capítulos e memórias moderadas.

Instalação: cogs/historia_royal.py + assets/historia_royal.png.
Comandos por prefixo (!), sem slash; nenhuma alteração no main.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger("royal.historia")
BANNER = Path(__file__).resolve().parent.parent / "assets" / "historia_royal.png"
COR = discord.Colour.from_rgb(179, 138, 76)
OFC_ROLE_ID = 1554367619463913582
DIRETORIA_IDS = {
    1553944794957615175,  # Fundadores
    1553923854877990945,  # Manager
    1562909560430264420,  # Administrador
    1553832097255260260,  # Coordenador
    1562950237117481000,  # Supervisor
}

# Conteúdo histórico público; não se confunde com fatos cadastrados pelos membros.
CHAPTERS = (
    (
        "I. O início de um legado",
        "28 de janeiro de 2026",
        "A nossa história começou em **28 de janeiro de 2026**, sob o nome de **Família Sant’s**, "
        "no universo do E.B do DELTA, no Roblox.\n\n"
        "Idealizada por **Sant’s**, a Família nasceu para reunir pessoas em torno da amizade, "
        "do respeito e da lealdade. **Bruna**, esposa de Sant’s e fundadora, esteve presente "
        "desde os primeiros momentos. **Kael**, também fundador, ajudou a construir as bases "
        "dessa comunidade.\n\n"
        "Mais do que um grupo, começava ali uma história feita por pessoas.",
    ),
    (
        "II. Os primeiros capítulos",
        "Amizades e resenhas",
        "Com novos integrantes, vieram conversas que atravessavam a madrugada, brincadeiras, "
        "eventos, desafios e aquelas situações inesperadas que só quem estava presente entende.\n\n"
        "Cada membro acrescentou algo próprio à Família: houve quem organizasse, quem criasse, "
        "quem ajudasse — e quem transformasse qualquer conversa tranquila em uma boa resenha.\n\n"
        "**Foi assim que a Família começou a crescer também em memórias.**",
    ),
    (
        "III. Um novo começo",
        "E.B do ALPHA",
        "Mudanças relacionadas ao E.B do DELTA encerraram uma etapa importante. Mesmo com os "
        "desafios, as amizades e a identidade da Família permaneceram.\n\n"
        "A trajetória encontrou um novo espaço no **E.B do ALPHA**, marcando o retorno oficial "
        "e o fortalecimento dos integrantes. O passado não foi apagado; tornou-se parte do "
        "caminho que nos trouxe até aqui.",
    ),
    (
        "IV. O nascimento da Royal",
        "25 de outubro de 2026",
        "Em **25 de outubro de 2026**, foi anunciada a transformação da antiga Família Sant’s "
        "em **Família Royal**.\n\n"
        "A nova identidade trouxe a coroa e a Fênix Real como símbolos de união e renovação, "
        "além de novas insígnias, benefícios aos membros oficiais, eventos e uma fase mais "
        "ambiciosa para o bot e para a comunidade.\n\n"
        "**O nome mudou. As histórias e os laços permaneceram.**",
    ),
    (
        "V. O próximo capítulo",
        "Uma história viva",
        "Hoje a Royal é formada por pessoas com diferentes personalidades e talentos. "
        "Tem quem organize, quem crie, quem cante, quem ajude e quem seja responsável pelas "
        "resenhas mais improváveis.\n\n"
        "A comunidade não é feita apenas de cargos, símbolos ou sistemas: ela é feita dos "
        "momentos que viram lembranças. Por isso, nossos integrantes podem sugerir registros "
        "para o **Acervo de Memórias**, sujeitos à análise da Diretoria.\n\n"
        "**Família Royal — Diferentes histórias, o mesmo lar.**",
    ),
)

MARCOS = (
    ("28/01/2026", "Fundação da Família Sant’s, no E.B do DELTA."),
    ("2026", "Reorganização e retomada das atividades no E.B do ALPHA."),
    ("25/10/2026", "Anúncio oficial da nova identidade: Família Royal."),
    ("Hoje", "A história continua com os integrantes e as memórias da comunidade."),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS royal_history_settings (
  guild_id BIGINT PRIMARY KEY,
  panel_channel_id BIGINT,
  panel_message_id BIGINT,
  review_channel_id BIGINT
);
CREATE TABLE IF NOT EXISTS royal_history_memories (
  id BIGSERIAL PRIMARY KEY,
  guild_id BIGINT NOT NULL,
  author_id BIGINT NOT NULL,
  title VARCHAR(90) NOT NULL,
  story TEXT NOT NULL,
  event_when VARCHAR(60) NOT NULL DEFAULT '',
  status VARCHAR(12) NOT NULL DEFAULT 'pending',
  review_channel_id BIGINT,
  review_message_id BIGINT,
  decided_by BIGINT,
  decided_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS royal_history_memories_status_idx
  ON royal_history_memories (guild_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS royal_history_memories_author_idx
  ON royal_history_memories (guild_id, author_id, created_at DESC);
"""


def staff(member: discord.abc.User) -> bool:
    return (isinstance(member, discord.Member) and (
        member.guild_permissions.manage_guild
        or any(role.id in DIRETORIA_IDS for role in member.roles)
    ))


def official(member: discord.abc.User) -> bool:
    return staff(member) or (isinstance(member, discord.Member)
                             and any(role.id == OFC_ROLE_ID for role in member.roles))


def safe(text: str) -> str:
    """Impede menções, formatações indesejadas e links disfarçados em textos públicos."""
    return discord.utils.escape_markdown(discord.utils.escape_mentions(text.strip()))


def dt_ymd(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y") if value else "—"


def article(title: str, body: str, *, note: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=240)
    c = discord.ui.Container(accent_colour=COR)
    c.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    if note:
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        c.add_item(discord.ui.TextDisplay(note))
    view.add_item(c)
    return view


async def private(interaction: discord.Interaction, title: str, body: str):
    await interaction.response.send_message(
        view=article(title, body), ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


class MainButton(discord.ui.Button):
    def __init__(self, cog: "HistoriaRoyal", action: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary,
                         custom_id=f"royal_history:main:{action}")
        self.cog, self.action = cog, action

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await private(interaction, "Canal indisponível", "Use este painel no servidor da Família Royal.")
        if self.action == "chapters":
            return await interaction.response.send_message(
                view=ChapterIndex(self.cog), ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
        if self.action == "timeline":
            lines = "\n".join(f"> `📜` **{when}** — {description}" for when, description in MARCOS)
            return await private(interaction, "Linha do Tempo Royal", lines)
        if self.action == "archive":
            try:
                v = await ArchivePage.make(self.cog, interaction.guild_id, 0)
                return await interaction.response.send_message(
                    view=v, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            except Exception as exc:
                LOG.exception("Falha ao consultar o acervo: %s", exc)
                return await private(interaction, "Acervo indisponível", "O arquivo está temporariamente indisponível.")
        if self.action == "suggest":
            if not official(interaction.user):
                return await private(interaction, "Acesso reservado", "Somente membros oficiais podem sugerir registros históricos.")
            try:
                setting = await self.cog.settings(interaction.guild_id)
            except RuntimeError:
                return await private(interaction, "Sistema indisponível", "O banco de dados está indisponível.")
            if not setting or not setting["review_channel_id"]:
                return await private(interaction, "Envio ainda não habilitado", "A Diretoria precisa configurar o canal de análise usando `!canalmemorias #canal`.")
            return await interaction.response.send_modal(MemoryModal(self.cog))


class HistoryPanel(discord.ui.LayoutView):
    def __init__(self, cog: "HistoriaRoyal"):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=COR)
        if BANNER.is_file():
            c.add_item(discord.ui.MediaGallery(
                discord.MediaGalleryItem(media="attachment://historia_royal.png")))
        c.add_item(discord.ui.TextDisplay(
            "## <:ImagemdoChatGPT25deoutde202615_4:1563986647144730826> HISTÓRIA DA FAMÍLIA ROYAL\n"
            "*Diferentes histórias, o mesmo lar.*\n\n"
            "Fundada em **28 de janeiro de 2026**, nossa Família nasceu como **Sant’s**, "
            "atravessou novas etapas no E.B e se transformou na **Royal**. "
            "Aqui preservamos nossas origens, conquistas e, claro, as resenhas que também fizeram história."))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        c.add_item(discord.ui.TextDisplay(
            "**<:ImagemdoChatGPT25deoutde202615_4:1563986702140440626> ARQUIVO HISTÓRICO**\n"
            "> `📖` **Capítulos** — conheça nossa trajetória.\n"
            "> `🕰️` **Linha do tempo** — os marcos da Família.\n"
            "> `📷` **Memórias** — histórias aprovadas pela Diretoria.\n"
            "> `✍️` **Contribuir** — sugira um novo acontecimento."))
        c.add_item(discord.ui.ActionRow(
            MainButton(cog, "chapters", "Capítulos"),
            MainButton(cog, "timeline", "Linha do tempo"),
            MainButton(cog, "archive", "Memórias"),
            MainButton(cog, "suggest", "Registrar memória"),
        ))
        c.add_item(discord.ui.TextDisplay(
            "-# 📚 O acervo é público; propostas de novos registros passam por aprovação."))
        self.add_item(c)


class ChapterSelect(discord.ui.Select):
    def __init__(self, cog: "HistoriaRoyal"):
        opts = [discord.SelectOption(label=name[:100], value=str(i), description=subtitle[:100])
                for i, (name, subtitle, _) in enumerate(CHAPTERS)]
        super().__init__(placeholder="Escolha um capítulo para ler", options=opts, min_values=1, max_values=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        ix = int(self.values[0])
        await interaction.response.edit_message(view=ChapterDetail(self.cog, ix))


class ChapterIndex(discord.ui.LayoutView):
    def __init__(self, cog: "HistoriaRoyal"):
        super().__init__(timeout=240)
        c = discord.ui.Container(accent_colour=COR)
        c.add_item(discord.ui.TextDisplay(
            "## 📖 OS CINCO CAPÍTULOS\n"
            "Da Família Sant’s à Royal: escolha um trecho do nosso livro de memórias."))
        c.add_item(discord.ui.ActionRow(ChapterSelect(cog)))
        self.add_item(c)


class ChapterNav(discord.ui.Button):
    def __init__(self, cog: "HistoriaRoyal", index: int, step: int | None, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary,
                         disabled=step is not None and not 0 <= index + step < len(CHAPTERS))
        self.cog, self.index, self.step = cog, index, step

    async def callback(self, interaction: discord.Interaction):
        view = ChapterIndex(self.cog) if self.step is None else ChapterDetail(self.cog, self.index + self.step)
        await interaction.response.edit_message(view=view)


class ChapterDetail(discord.ui.LayoutView):
    def __init__(self, cog: "HistoriaRoyal", index: int):
        super().__init__(timeout=240)
        heading, date, prose = CHAPTERS[index]
        c = discord.ui.Container(accent_colour=COR)
        c.add_item(discord.ui.TextDisplay(
            f"## {heading}\n-# {date}\n\n{prose}"))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        c.add_item(discord.ui.ActionRow(
            ChapterNav(cog, index, -1, "Anterior"),
            ChapterNav(cog, index, None, "Índice"),
            ChapterNav(cog, index, 1, "Próximo"),
        ))
        self.add_item(c)


class MemorySelect(discord.ui.Select):
    def __init__(self, cog: "HistoriaRoyal", items):
        opts = [discord.SelectOption(
            label=str(row["title"])[:100], value=str(row["id"]),
            description=f"Registro #{row['id']} · {dt_ymd(row['created_at'])}"[:100]
        ) for row in items]
        super().__init__(placeholder="Abrir uma memória", options=opts)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        try:
            entry = await self.cog.pool().fetchrow(
                "SELECT * FROM royal_history_memories WHERE id=$1 AND guild_id=$2 AND status='approved'",
                int(self.values[0]), interaction.guild_id)
        except Exception:
            LOG.exception("Erro ao abrir memória")
            return await private(interaction, "Acervo indisponível", "Não foi possível consultar essa memória.")
        if not entry:
            return await interaction.response.edit_message(
                view=article("Registro indisponível", "Esta memória não está mais publicada."))
        body = (f"-# Registro #{entry['id']} · {dt_ymd(entry['created_at'])}\n"
                f"**Quando aconteceu:** {safe(entry['event_when']) if entry['event_when'] else 'Não informado'}\n\n"
                f"{safe(entry['story'])}\n\n"
                f"-# Enviado por <@{entry['author_id']}> · Aprovado para o acervo oficial.")
        view = article("📷 " + safe(entry["title"]), body)
        view.children[0].add_item(discord.ui.ActionRow(BackToArchive(self.cog, interaction.guild_id)))
        await interaction.response.edit_message(view=view)


class BackToArchive(discord.ui.Button):
    def __init__(self, cog: "HistoriaRoyal", guild_id: int):
        super().__init__(label="Voltar ao acervo", style=discord.ButtonStyle.secondary)
        self.cog, self.guild_id = cog, guild_id

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(view=await ArchivePage.make(self.cog, self.guild_id, 0))
        except Exception:
            LOG.exception("Erro ao voltar para o acervo")
            await private(interaction, "Acervo indisponível", "Tente novamente mais tarde.")


class ArchiveNav(discord.ui.Button):
    def __init__(self, cog: "HistoriaRoyal", guild_id: int, page: int, step: int, total: int):
        target = page + step
        super().__init__(label="Anterior" if step < 0 else "Próxima",
                         style=discord.ButtonStyle.secondary,
                         disabled=target < 0 or target * 20 >= total)
        self.cog, self.guild_id, self.target = cog, guild_id, target

    async def callback(self, interaction: discord.Interaction):
        new = await ArchivePage.make(self.cog, self.guild_id, self.target)
        await interaction.response.edit_message(view=new)


class ArchivePage(discord.ui.LayoutView):
    @classmethod
    async def make(cls, cog: "HistoriaRoyal", guild_id: int, page: int):
        pool = cog.pool()
        total = await pool.fetchval(
            "SELECT count(*) FROM royal_history_memories WHERE guild_id=$1 AND status='approved'", guild_id)
        entries = await pool.fetch(
            """SELECT id,title,created_at FROM royal_history_memories
               WHERE guild_id=$1 AND status='approved'
               ORDER BY created_at DESC,id DESC LIMIT 20 OFFSET $2""", guild_id, page * 20)
        return cls(cog, guild_id, page, total, entries)

    def __init__(self, cog, guild_id: int, page: int, total: int, items):
        super().__init__(timeout=240)
        c = discord.ui.Container(accent_colour=COR)
        page_max = max(1, (total + 19) // 20)
        c.add_item(discord.ui.TextDisplay(
            f"## 📷 ACERVO DE MEMÓRIAS\n"
            f"**{total}** registros aprovados · Página {page + 1}/{page_max}\n"
            "-# Aqui estão as histórias enviadas pelos integrantes e aprovadas pela Diretoria."))
        if items:
            c.add_item(discord.ui.TextDisplay(
                "\n".join(f"> `📜` **{safe(item['title'])}**" for item in items[:8])))
            c.add_item(discord.ui.ActionRow(MemorySelect(cog, items)))
            if page_max > 1:
                c.add_item(discord.ui.ActionRow(
                    ArchiveNav(cog, guild_id, page, -1, total),
                    ArchiveNav(cog, guild_id, page, 1, total),
                ))
        else:
            c.add_item(discord.ui.TextDisplay(
                "O acervo ainda não possui registros publicados. Em breve, as primeiras memórias estarão aqui."))
        self.add_item(c)


class MemoryModal(discord.ui.Modal, title="Registrar memória Royal"):
    title_field = discord.ui.TextInput(
        label="Título da memória", min_length=5, max_length=90,
        placeholder="Ex.: Nosso primeiro grande evento")
    when_field = discord.ui.TextInput(
        label="Quando aconteceu? (opcional)", required=False, max_length=60,
        placeholder="Ex.: Outubro de 2026")
    story_field = discord.ui.TextInput(
        label="Conte o que aconteceu", style=discord.TextStyle.paragraph,
        min_length=30, max_length=1200, placeholder="Descreva os fatos e as pessoas envolvidas...")

    def __init__(self, cog: "HistoriaRoyal"):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not official(interaction.user):
            return await private(interaction, "Acesso reservado", "Somente integrantes oficiais podem enviar memórias.")
        try:
            setting = await self.cog.settings(interaction.guild_id)
            if not setting or not setting["review_channel_id"]:
                return await private(interaction, "Canal não configurado", "Peça à Diretoria que configure o canal de análise.")
            pool = self.cog.pool()
            pending = await pool.fetchval(
                """SELECT count(*) FROM royal_history_memories
                   WHERE guild_id=$1 AND author_id=$2 AND status='pending'""",
                interaction.guild_id, interaction.user.id)
            recent = await pool.fetchval(
                """SELECT count(*) FROM royal_history_memories
                   WHERE guild_id=$1 AND author_id=$2 AND created_at > NOW() - INTERVAL '24 hours'""",
                interaction.guild_id, interaction.user.id)
            if pending >= 2 or recent >= 5:
                return await private(interaction, "Limite de envios", "Você já possui pedidos pendentes ou atingiu o limite diário. Aguarde a análise da Diretoria.")
            await interaction.response.defer(ephemeral=True, thinking=True)
            row = await pool.fetchrow(
                """INSERT INTO royal_history_memories (guild_id,author_id,title,story,event_when)
                   VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                interaction.guild_id, interaction.user.id,
                str(self.title_field).strip(), str(self.story_field).strip(),
                str(self.when_field).strip())
            sent = await self.cog.send_review(interaction.guild, row["id"])
            message = (f"✅ Memória registrada como **#{row['id']}** e enviada à Diretoria."
                       if sent else
                       f"⚠️ Memória **#{row['id']}** salva, mas a entrega para análise falhou. A Diretoria poderá reenviá-la com `!revisarmemorias`.")
            await interaction.followup.send(message, ephemeral=True)
        except Exception:
            LOG.exception("Falha ao receber memória Royal")
            if interaction.response.is_done():
                await interaction.followup.send("❌ Não foi possível concluir o envio. Tente novamente mais tarde.", ephemeral=True)
            else:
                await private(interaction, "Erro ao registrar", "O sistema está temporariamente indisponível.")


class DecisionButton(discord.ui.Button):
    def __init__(self, cog: "HistoriaRoyal", memory_id: int, action: str):
        super().__init__(label="Aprovar" if action == "approved" else "Recusar",
                         style=discord.ButtonStyle.success if action == "approved" else discord.ButtonStyle.danger,
                         custom_id=f"royal_history:review:{memory_id}:{action}")
        self.cog, self.memory_id, self.action = cog, memory_id, action

    async def callback(self, interaction: discord.Interaction):
        if not staff(interaction.user):
            return await private(interaction, "Sem permissão", "Apenas a Diretoria pode avaliar registros históricos.")
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            pool = self.cog.pool()
            row = await pool.fetchrow(
                """UPDATE royal_history_memories
                   SET status=$3,decided_by=$4,decided_at=NOW()
                   WHERE id=$1 AND guild_id=$2 AND status='pending'
                   RETURNING id,author_id,title""",
                self.memory_id, interaction.guild_id, self.action, interaction.user.id)
            if row is None:
                return await interaction.followup.send("Este registro já foi avaliado.", ephemeral=True)
            try:
                await interaction.message.edit(view=ReviewPanel(self.cog, self.memory_id,
                                                                status=self.action, reviewer=interaction.user.id))
            except discord.HTTPException:
                LOG.warning("Não foi possível atualizar o painel da memória %s", self.memory_id)
            action_label = "aprovada e incluída no acervo" if self.action == "approved" else "recusada"
            try:
                user = self.cog.bot.get_user(row["author_id"]) or await self.cog.bot.fetch_user(row["author_id"])
                await user.send(f"📜 Sua memória **{row['title']}** (#{row['id']}) foi {action_label} pela Diretoria Royal.",
                                allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                pass
            await interaction.followup.send(f"✅ Memória #{row['id']} {action_label}.", ephemeral=True)
        except Exception:
            LOG.exception("Erro ao avaliar memória %s", self.memory_id)
            await interaction.followup.send("❌ Não foi possível registrar esta decisão.", ephemeral=True)


class ReviewPanel(discord.ui.LayoutView):
    def __init__(self, cog: "HistoriaRoyal", memory_id: int, *, entry=None, status=None, reviewer=None):
        super().__init__(timeout=None if status is None else 300)
        c = discord.ui.Container(accent_colour=COR)
        if status is not None:
            c.add_item(discord.ui.TextDisplay(
                f"## 📜 MEMÓRIA #{memory_id}\n**Situação:** {('Aprovada' if status == 'approved' else 'Recusada')}\n"
                f"-# Decisão de <@{reviewer}>. O pedido foi encerrado."))
        else:
            if entry is None:
                # Na restauração do bot, apenas os custom_ids dos botões são necessários.
                c.add_item(discord.ui.TextDisplay(f"## 📜 MEMÓRIA #{memory_id} · Aguardando avaliação"))
            else:
                when = safe(entry["event_when"]) if entry["event_when"] else "Não informado"
                c.add_item(discord.ui.TextDisplay(
                    f"## 📜 MEMÓRIA PARA ANÁLISE · #{memory_id}\n"
                    f"**Título:** {safe(entry['title'])}\n"
                    f"**Enviado por:** <@{entry['author_id']}>\n"
                    f"**Quando ocorreu:** {when}\n\n"
                    f"{safe(entry['story'])}\n\n"
                    "-# Apenas a Diretoria pode aprovar. Registros aprovados aparecem no acervo público."))
            c.add_item(discord.ui.ActionRow(
                DecisionButton(cog, memory_id, "approved"),
                DecisionButton(cog, memory_id, "rejected")))
        self.add_item(c)


class HistoriaRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._schema_ready = False

    def pool(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("PostgreSQL indisponível")
        return pool

    async def cog_load(self):
        self.bot.add_view(HistoryPanel(self))
        try:
            await self.pool().execute(SCHEMA)
            self._schema_ready = True
            rows = await self.pool().fetch(
                """SELECT id,review_message_id FROM royal_history_memories
                   WHERE status='pending' AND review_message_id IS NOT NULL""")
            for row in rows:
                self.bot.add_view(ReviewPanel(self, row["id"]), message_id=row["review_message_id"])
            LOG.info("História Royal pronta; %s revisões restauradas", len(rows))
        except Exception:
            LOG.exception("A inicialização do acervo falhou; confira DATABASE_URL e permissões")

    async def settings(self, guild_id: int):
        return await self.pool().fetchrow(
            "SELECT * FROM royal_history_settings WHERE guild_id=$1", guild_id)

    async def send_review(self, guild: discord.Guild, memory_id: int) -> bool:
        row = await self.pool().fetchrow(
            "SELECT * FROM royal_history_memories WHERE id=$1 AND guild_id=$2", memory_id, guild.id)
        if not row or row["status"] != "pending":
            return False
        setting = await self.settings(guild.id)
        cid = setting["review_channel_id"] if setting else None
        if not cid:
            return False
        channel = guild.get_channel(cid)
        if channel is None:
            try:
                channel = await guild.fetch_channel(cid)
            except discord.HTTPException:
                return False
        if not isinstance(channel, discord.TextChannel):
            return False
        view = ReviewPanel(self, memory_id, entry=row)
        try:
            msg = await channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())
            await self.pool().execute(
                """UPDATE royal_history_memories
                   SET review_message_id=$2,review_channel_id=$3 WHERE id=$1""",
                memory_id, msg.id, cid)
            self.bot.add_view(ReviewPanel(self, memory_id), message_id=msg.id)
            return True
        except (discord.HTTPException, discord.Forbidden):
            LOG.exception("Falha ao enviar memória #%s para análise", memory_id)
            return False

    async def publish(self, channel: discord.TextChannel):
        if not BANNER.is_file():
            raise FileNotFoundError("assets/historia_royal.png não encontrado")
        setting = await self.settings(channel.guild.id)
        # Atualiza a mesma mensagem, se já houver um quadro neste canal.
        if (setting and setting["panel_channel_id"] == channel.id
                and setting["panel_message_id"]):
            try:
                msg = await channel.fetch_message(setting["panel_message_id"])
                await msg.edit(view=HistoryPanel(self))
                return msg, False
            except discord.NotFound:
                pass
        with BANNER.open("rb") as banner:
            msg = await channel.send(
                view=HistoryPanel(self),
                file=discord.File(banner, filename="historia_royal.png"),
                allowed_mentions=discord.AllowedMentions.none())
        await self.pool().execute(
            """INSERT INTO royal_history_settings (guild_id,panel_channel_id,panel_message_id)
               VALUES ($1,$2,$3) ON CONFLICT (guild_id) DO UPDATE
               SET panel_channel_id=$2,panel_message_id=$3""",
            channel.guild.id, channel.id, msg.id)
        # O painel anterior é retirado somente depois de o novo ser publicado.
        if setting and setting["panel_channel_id"] and setting["panel_message_id"]:
            old_channel = channel.guild.get_channel(setting["panel_channel_id"])
            if isinstance(old_channel, discord.TextChannel):
                try:
                    old = await old_channel.fetch_message(setting["panel_message_id"])
                    if old.id != msg.id:
                        await old.delete()
                except discord.HTTPException:
                    LOG.warning("Não foi possível remover o antigo painel de história")
        return msg, True

    @commands.command(name="previahistoria")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def preview(self, ctx: commands.Context):
        if not BANNER.is_file():
            return await ctx.reply("❌ Banner ausente: `assets/historia_royal.png`.", mention_author=False)
        with BANNER.open("rb") as banner:
            await ctx.send(view=HistoryPanel(self), file=discord.File(banner, filename="historia_royal.png"),
                           allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="painelhistoria")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def panel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        try:
            if not self._schema_ready:
                await self.pool().execute(SCHEMA)
                self._schema_ready = True
            msg, created = await self.publish(channel)
            await ctx.reply(
                f"✅ {'Publicado' if created else 'Atualizado'}: {msg.jump_url}", mention_author=False)
        except Exception:
            LOG.exception("Falha ao publicar quadro histórico")
            await ctx.reply("❌ Não foi possível publicar. Confira o banco, a imagem e as permissões do bot.",
                            mention_author=False)

    @commands.command(name="canalmemorias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def set_review(self, ctx: commands.Context, channel: discord.TextChannel):
        try:
            await self.pool().execute(SCHEMA)
            await self.pool().execute(
                """INSERT INTO royal_history_settings (guild_id,review_channel_id)
                   VALUES ($1,$2) ON CONFLICT (guild_id) DO UPDATE SET review_channel_id=$2""",
                ctx.guild.id, channel.id)
            await ctx.reply(f"✅ Canal de análise definido: {channel.mention}.", mention_author=False)
        except Exception:
            LOG.exception("Não foi possível definir canal de revisão")
            await ctx.reply("❌ Não foi possível salvar o canal. Confira o PostgreSQL.", mention_author=False)

    @commands.command(name="revisarmemorias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def resend_pending(self, ctx: commands.Context):
        try:
            rows = await self.pool().fetch(
                """SELECT id FROM royal_history_memories
                   WHERE guild_id=$1 AND status='pending' AND review_message_id IS NULL
                   ORDER BY created_at LIMIT 10""", ctx.guild.id)
            count = sum([await self.send_review(ctx.guild, r["id"]) for r in rows])
            total = await self.pool().fetchval(
                "SELECT count(*) FROM royal_history_memories WHERE guild_id=$1 AND status='pending'",
                ctx.guild.id)
            await ctx.reply(f"📚 Pendentes: **{total}** · Reenviadas para análise: **{count}**.",
                            mention_author=False)
        except Exception:
            LOG.exception("Erro ao revisar memórias")
            await ctx.reply("❌ Falha ao consultar as memórias pendentes.", mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(HistoriaRoyal(bot))
