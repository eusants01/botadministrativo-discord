from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger("royal.insignias")
COR_ROYAL = discord.Colour.from_rgb(139, 32, 45)
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
BANNERS = {
    "catalogo": "insignias_royal.png",
    "solicitacao": "insignias_solicitacao_royal.png",
    "decisao": "insignias_decisao_royal.png",
}
INSIGNIAS = [
    {"nome": "Noel", "cargo_id": 1568866728237211668, "emoji": "🎅", "titular_id": 0, "descricao_curta": "Edição natalina · Permissões especiais.", "descricao_completa": "Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração."},
    {"nome": "Natalina", "cargo_id": 1568866716723839038, "emoji": "🎄", "titular_id": 0, "descricao_curta": "Edição natalina · Permissões especiais.", "descricao_completa": "Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração."},
    {"nome": "Candy", "cargo_id": 1568866728031559742, "emoji": "🍬", "titular_id": 0, "descricao_curta": "Edição natalina · Permissões especiais.", "descricao_completa": "Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração."},
    {"nome": "Bruna", "cargo_id": 1554376484637122591, "emoji": "🌹", "titular_id": 697068974323793921, "descricao_curta": "Fundadora · Lealdade e acolhimento.", "descricao_completa": "Fundadora da Família Royal, integrante mais antiga e esposa de Sant's. Sua insígnia simboliza acolhimento, confiança e lealdade."},
    {"nome": "Pietra", "cargo_id": 1556147238852628562, "emoji": "💐", "titular_id": 1295645409082867732, "descricao_curta": "Apreço e reconhecimento.", "descricao_completa": "Simboliza apreço, reconhecimento e consideração pessoal."},
    {"nome": "Kananda", "cargo_id": 1556147239179518022, "emoji": "🪽", "titular_id": 1430221798389059584, "descricao_curta": "Companheirismo e proteção.", "descricao_completa": "Reconhece laços de companheirismo, cuidado e proteção."},
    {"nome": "Tatah", "cargo_id": 1555370356343312486, "emoji": "🌙", "titular_id": 1032084016196763688, "descricao_curta": "Confiança e proximidade.", "descricao_completa": "Distinção de confiança e proximidade, concedida a critério de Tatah."},
    {"nome": "Lívia", "cargo_id": 1565443617651294278, "emoji": "🎀", "titular_id": 1399464764760920145, "descricao_curta": "Lealdade e consideração.", "descricao_completa": "Expressa lealdade, consideração e vínculos pessoais."},
    {"nome": "Nathy", "cargo_id": 1565443626002026526, "emoji": "🌵", "titular_id": 775086637386301524, "descricao_curta": "Tengo lengo tengo", "descricao_completa": "Simboliza amizade, proximidade e lealdade."},
    {"nome": "Soso", "cargo_id": 1565942565767745699, "emoji": "🌺", "titular_id": 1525265476425355337, "descricao_curta": "Lealdade e consideração.", "descricao_completa": "Representa lealdade e consideração pessoal de um corregedor."},
    {"nome": "Sant's", "cargo_id": 1554376496196493342, "emoji": "👑", "titular_id": 925863471902503033, "descricao_curta": "Criador da Família Royal.", "descricao_completa": "Distinção pessoal de Sant's, criador da Família Royal. Sua concessão depende de sua autorização."},
    {"nome": "Ruan", "cargo_id": 1554376496548941894, "emoji": "🛡️", "titular_id": 1348504492345397358, "descricao_curta": "Lealdade e consideração.", "descricao_completa": "Símbolo de lealdade e consideração pessoal."},
    {"nome": "Pato", "cargo_id": 1556147238986711070, "emoji": "🦆", "titular_id": 1459320617852731635, "descricao_curta": "quack quack.", "descricao_completa": "Expressa amizade e estima pessoal, concedida a critério de Pato."},
    {"nome": "Violets", "cargo_id": 1562498973787230339, "emoji": "🪐", "titular_id": 969628191268421672, "descricao_curta": "Vínculo e reconhecimento.", "descricao_completa": "Representa vínculo especial e reconhecimento."},
    {"nome": "Diniz", "cargo_id": 1563986618207965246, "emoji": "🌟", "titular_id": 1546524499430604891, "descricao_curta": "Proximidade e apreço.", "descricao_completa": "Símbolo de proximidade e apreço pessoal."},
    {"nome": "Mateus", "cargo_id": 1564494650327437363, "emoji": "🔍", "titular_id": 1481369480482394223, "descricao_curta": "Confiança e consideração.", "descricao_completa": "Representa confiança e consideração pessoal."},
    {"nome": "Hanz", "cargo_id": 1564041775000064060, "emoji": "🔥", "titular_id": 1004088774810144859, "descricao_curta": "Lealdade e consideração.", "descricao_completa": "Representa lealdade e consideração pessoal."},
    {"nome": "Gostosãodanaty", "cargo_id": 1565441465243541625, "emoji": "⚖️", "titular_id": 529781932976898058, "descricao_curta": "Justiça e integridade.", "descricao_completa": "Insígnia pessoal de Teteu, juiz do Poder Judiciário, símbolo de justiça, integridade e respeito."},
    {"nome": "Golgos", "cargo_id": 1565443033787277394, "emoji": "🎥", "titular_id": 525837977545605132, "descricao_curta": "Criatividade e influência.", "descricao_completa": "Distinção pessoal de Golgos, editor de vídeo e influenciador, associada à criatividade e à comunicação."},
    {"nome": "Dark", "cargo_id": 1565443625523880137, "emoji": "🐦‍⬛", "titular_id": 1089646065084534854, "descricao_curta": "Lealdade e consideração.", "descricao_completa": "Representa lealdade e consideração pessoal de um corregedor."},
    {"nome": "PH", "cargo_id": 1565942574676705330, "emoji": "❄️", "titular_id": 896496513251962992, "descricao_curta": "Esperança e perseverança", "descricao_completa": "Representa lealdade e consideração pessoal de um corregedor."},
    {"nome": "Gomez", "cargo_id": 1566322721363726447, "emoji": "👿", "titular_id": 793130893643874337, "descricao_curta": "Esperança da destruição", "descricao_completa": "Representa lealdade e consideração pessoal de um corregedor."},

]

INSIGNIAS_NATAL = {
    "noel": 697068974323793921,
    "natalina": 775086637386301524,
    "candy": 1430221798389059584,
}


def eh_insignia_natal(cargo_id: int) -> bool:
    return cargo_id in INSIGNIAS_NATAL.values()


def catalogo() -> dict[int, dict]:
    return {item["cargo_id"]: item for item in INSIGNIAS}


def caminho_banner(tipo: str) -> Path | None:
    preferido = PASTA_ASSETS / BANNERS[tipo]
    if preferido.is_file():
        return preferido
    reserva = PASTA_ASSETS / BANNERS["catalogo"]
    return reserva if reserva.is_file() else None


def painel_com_banner(painel: discord.ui.Container, tipo: str) -> Path | None:
    arquivo = caminho_banner(tipo)
    if arquivo:
        painel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{arquivo.name}")
        ))
    return arquivo


async def enviar_layout(destino, view: discord.ui.LayoutView, banner: Path | None):
    """Envia V2 sem content/embed; uma única mensagem com banner quando disponível."""
    if banner:
        with banner.open("rb") as f:
            return await destino.send(
                view=view, file=discord.File(f, filename=banner.name),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    return await destino.send(view=view, allowed_mentions=discord.AllowedMentions.none())


def montar_catalogo(cog: "InsigniasRoyal", com_banner: bool = False) -> discord.ui.LayoutView:
    """Painel V2 compacto: banner, instruções e seleção das insígnias."""
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "catalogo")

    bloco.add_item(discord.ui.TextDisplay(
        "## <a:snow:1568873857509490888> INSÍGNIAS DA FAMÍLIA ROYAL - EDIÇÃO DE NATAL\n"
        "Catálogo oficial das distinções da Família Royal no clima natalino.\n"
        "Distinções concedidas exclusivamente com a autorização de seus titulares.\n"
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        "**<:tree:1568871853970165820> INSÍGNIAS NATALINAS EM DESTAQUE**\n"
        "`🎅` <@&1568866728237211668> — *Espírito de Natal* · Insígnia especial com **permissões especiais**.\n"
        "`🎄` <@&1568866716723839038> — *Celebração Real* · Insígnia especial com **permissões especiais**.\n"
        "`🍬` <@&1568866728031559742> — *Doçura e União* · Insígnia especial com **permissões especiais**.\n\n"
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        "**🎄 COMO SOLICITAR**\n"
        "Selecione uma opção no menu abaixo. O pedido será enviado em privado ao titular\n"
        "responsável, que poderá **aprovar** ou **recusar** sua solicitação."
    ))
    bloco.add_item(discord.ui.ActionRow(InsigniaSelect(cog, persistente=True)))
    if len(INSIGNIAS) > 25:
        bloco.add_item(discord.ui.ActionRow(MaisInsignias(cog)))

    view.add_item(bloco)
    return view


class InsigniaSelect(discord.ui.Select):
    def __init__(self, cog: "InsigniasRoyal", pagina: int = 0, persistente: bool = False):
        itens = INSIGNIAS[pagina * 25:(pagina + 1) * 25]
        super().__init__(
            placeholder="🎄 Solicite",
            min_values=1, max_values=1,
            custom_id=("royal:insignias:selecionar:v1" if persistente
                       else f"royal:insignias:pagina:{pagina}"),
            options=[discord.SelectOption(
                label=f"Insígnia {i['nome']}"[:100],
                value=str(i["cargo_id"]),
                description=i["descricao_curta"][:100],
                emoji=("🐦" if i["nome"] == "Dark" else i["emoji"]),
            ) for i in itens],
        )
        self.cog = cog
    async def callback(self, interaction: discord.Interaction):
        await self.cog.solicitar(interaction, int(self.values[0]))


class PaginaInsignias(discord.ui.View):
    """Lista paginada privada: funciona com qualquer número de insígnias."""
    def __init__(self, cog: "InsigniasRoyal", pagina: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.pagina = pagina
        self.total_paginas = (len(INSIGNIAS) + 24) // 25
        self.add_item(InsigniaSelect(cog, pagina=pagina))
        if pagina > 0:
            anterior = discord.ui.Button(label="Anterior", emoji="⬅️", style=discord.ButtonStyle.secondary)
            async def voltar(interaction: discord.Interaction):
                await interaction.response.edit_message(view=PaginaInsignias(self.cog, self.pagina - 1))
            anterior.callback = voltar
            self.add_item(anterior)
        if pagina + 1 < self.total_paginas:
            proxima = discord.ui.Button(label="Próxima", emoji="➡️", style=discord.ButtonStyle.secondary)
            async def avancar(interaction: discord.Interaction):
                await interaction.response.edit_message(view=PaginaInsignias(self.cog, self.pagina + 1))
            proxima.callback = avancar
            self.add_item(proxima)


class MaisInsignias(discord.ui.Button):
    def __init__(self, cog: "InsigniasRoyal"):
        super().__init__(label="Outras insígnias", emoji="📜",
                         style=discord.ButtonStyle.secondary,
                         custom_id="royal:insignias:mais:v1")
        self.cog = cog
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "**<:7913xmasgift:1568875584208109728> Outras insígnias** — escolha uma opção:",
            view=PaginaInsignias(self.cog, pagina=1), ephemeral=True
        )


def montar_pedido(cog: "InsigniasRoyal", pedido_id: int, item: dict,
                  solicitante: int, servidor: str, com_banner: bool = False) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "solicitacao")
    bloco.add_item(discord.ui.TextDisplay(
        "## <a:coroa:1564000189167960177> PEDIDO DE AUTORIZAÇÃO\n"
        f"> `{item['emoji']}` **Insígnia {item['nome']}**\n"
        f"> `👤` Solicitante: <@{solicitante}>\n"
        f"> `🏰` Comunidade: **{servidor or 'Família Royal'}**"
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        f"**⚜️ SIGNIFICADO**\n{item['descricao_completa']}\n\n"
        "-# 📜 A aprovação é uma decisão pessoal e exclusiva do titular."
    ))
    aprovar = discord.ui.Button(label="Aprovar", emoji="✅",
                                style=discord.ButtonStyle.success,
                                custom_id=f"royal:insig:aprovar:{pedido_id}")
    recusar = discord.ui.Button(label="Recusar", emoji="✖️",
                                style=discord.ButtonStyle.danger,
                                custom_id=f"royal:insig:recusar:{pedido_id}")
    async def aprovar_cb(interaction: discord.Interaction):
        await cog.decidir(interaction, pedido_id, aprovar=True)
    async def recusar_cb(interaction: discord.Interaction):
        await cog.decidir(interaction, pedido_id, aprovar=False)
    aprovar.callback = aprovar_cb
    recusar.callback = recusar_cb
    bloco.add_item(discord.ui.ActionRow(aprovar, recusar))
    view.add_item(bloco)
    return view


def montar_resultado(pedido, aprovado: bool, com_banner: bool = False) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "decisao")
    nome = pedido["insignia_name"]
    bloco.add_item(discord.ui.TextDisplay(
        f"## {'✅ APROVADA' if aprovado else '📜 NÃO APROVADA'}\n"
        f"**Insígnia {nome}**\n"
        f"> `👤` Solicitante: <@{pedido['requester_id']}>\n"
        f"> `⚜️` {'Cargo concedido com autorização do titular.' if aprovado else 'Solicitação encerrada por decisão do titular.'}\n\n"
        "-# Família Royal • Registro de decisão"
    ))
    view.add_item(bloco)
    return view


class InsigniasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    def pool(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("PostgreSQL indisponível: confira DATABASE_URL e bot.pool.")
        return pool
    async def cog_load(self):
        pool = self.pool()
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_insignia_requests (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                requester_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                insignia_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                dm_message_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                decided_at TIMESTAMPTZ
            )
        """)
        await pool.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS royal_insignia_pending_unique
            ON royal_insignia_requests(guild_id, requester_id, role_id)
            WHERE status IN ('pending', 'processing')
        """)
        # Donos das insígnias de Natal são configurados pela administração.
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_christmas_insignia_owners (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (guild_id, role_id),
                UNIQUE (guild_id, owner_id)
            )
        """)

        # Mesmo custom_id histórico: painéis antigos continuam operando.
        self.bot.add_view(montar_catalogo(self, com_banner=False))
        pendentes = await pool.fetch("""
            SELECT id, insignia_name, requester_id, role_id, dm_message_id
            FROM royal_insignia_requests
            WHERE status='pending' AND dm_message_id IS NOT NULL
        """)
        por_cargo = catalogo()
        for pedido in pendentes:
            item = por_cargo.get(pedido["role_id"])
            if item is None:
                item = {"nome": pedido["insignia_name"], "emoji": "👑",
                        "descricao_completa": "Distinção pessoal Royal."}
            self.bot.add_view(
                montar_pedido(self, pedido["id"], item, pedido["requester_id"],
                             "Família Royal", com_banner=False),
                message_id=pedido["dm_message_id"],
            )
        LOG.info("Sistema de insígnias Royal inicializado (%d pendentes).", len(pendentes))
    async def solicitar(self, interaction: discord.Interaction, cargo_id: int):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "❌ Utilize este painel dentro da Família Royal.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        item = catalogo().get(cargo_id)
        if not item:
            return await interaction.followup.send("❌ Insígnia indisponível.", ephemeral=True)
        titular_id = item["titular_id"]
        if cargo_id in INSIGNIAS_NATAL.values():
            titular_id = await self.pool().fetchval("""
                SELECT owner_id FROM royal_christmas_insignia_owners
                WHERE guild_id=$1 AND role_id=$2
            """, interaction.guild.id, cargo_id)

        cargo = interaction.guild.get_role(cargo_id)
        if cargo is None:
            return await interaction.followup.send("❌ Cargo não encontrado no servidor.", ephemeral=True)
        if cargo in interaction.user.roles:
            return await interaction.followup.send("✅ Você já possui esta insígnia.", ephemeral=True)
        if titular_id == interaction.user.id:
            return await interaction.followup.send("Você já é o titular dessa insígnia.", ephemeral=True)
        if not isinstance(titular_id, int) or titular_id <= 0:
            return await interaction.followup.send(
                "⚠️ O titular desta insígnia ainda não foi definido pela administração.", ephemeral=True
            )
        pool = self.pool()
        pedido = await pool.fetchrow("""
            INSERT INTO royal_insignia_requests
                (guild_id, requester_id, owner_id, role_id, insignia_name)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING RETURNING id
        """, interaction.guild.id, interaction.user.id, titular_id, cargo_id, item["nome"])
        if pedido is None:
            return await interaction.followup.send(
                "⏳ Você já possui uma solicitação pendente desta insígnia.", ephemeral=True
            )
        pedido_id = pedido["id"]
        banner = caminho_banner("solicitacao")
        try:
            titular = await self.bot.fetch_user(titular_id)
            mensagem = await enviar_layout(
                titular,
                montar_pedido(self, pedido_id, item, interaction.user.id,
                              interaction.guild.name, com_banner=bool(banner)),
                banner,
            )
        except (discord.HTTPException, OSError) as exc:
            await pool.execute("DELETE FROM royal_insignia_requests WHERE id=$1 AND status='pending'", pedido_id)
            LOG.exception("Falha ao encaminhar solicitação de insígnia: %s", exc)
            return await interaction.followup.send(
                "❌ Não foi possível encaminhar o pedido ao titular. "
                "Confira as DMs dele e as permissões do bot.", ephemeral=True
            )
        await pool.execute("UPDATE royal_insignia_requests SET dm_message_id=$1 WHERE id=$2",
                           mensagem.id, pedido_id)
        self.bot.add_view(
            montar_pedido(self, pedido_id, item, interaction.user.id,
                         interaction.guild.name, com_banner=False),
            message_id=mensagem.id,
        )
        await interaction.followup.send(
            f"📨 Pedido da **Insígnia {item['nome']}** encaminhado ao titular. "
            "A decisão será comunicada em mensagem privada.", ephemeral=True
        )
    async def decidir(self, interaction: discord.Interaction, pedido_id: int, *, aprovar: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)
        pool = self.pool()
        pedido = await pool.fetchrow("SELECT * FROM royal_insignia_requests WHERE id=$1", pedido_id)
        if pedido is None:
            return await interaction.followup.send("❌ Pedido não encontrado.", ephemeral=True)
        if interaction.user.id != pedido["owner_id"]:
            return await interaction.followup.send("⛔ Apenas o titular pode decidir.", ephemeral=True)
        if pedido["status"] != "pending":
            return await interaction.followup.send("Esta solicitação já foi processada.", ephemeral=True)
        proximo_status = "processing" if aprovar else "rejected"
        alterado = await pool.fetchrow("""
            UPDATE royal_insignia_requests SET status=$2, decided_at=now()
            WHERE id=$1 AND status='pending' RETURNING id
        """, pedido_id, proximo_status)
        if alterado is None:
            return await interaction.followup.send("O pedido já foi atendido.", ephemeral=True)
        if aprovar:
            try:
                guild = self.bot.get_guild(pedido["guild_id"])
                if guild is None:
                    raise RuntimeError("Servidor não encontrado.")
                membro = guild.get_member(pedido["requester_id"])
                if membro is None:
                    membro = await guild.fetch_member(pedido["requester_id"])
                cargo = guild.get_role(pedido["role_id"])
                if cargo is None:
                    raise RuntimeError("Cargo não encontrado.")
                await membro.add_roles(cargo, reason=f"Insígnia {pedido['insignia_name']} autorizada por {interaction.user.id}")
                await pool.execute("UPDATE royal_insignia_requests SET status='approved' WHERE id=$1", pedido_id)
            except (discord.HTTPException, RuntimeError) as exc:
                await pool.execute("""
                    UPDATE royal_insignia_requests SET status='pending', decided_at=NULL
                    WHERE id=$1 AND status='processing'
                """, pedido_id)
                LOG.exception("Falha ao conceder a insígnia %s", pedido_id)
                return await interaction.followup.send(
                    f"❌ Não foi possível entregar o cargo: {str(exc)[:160]}", ephemeral=True
                )
        await interaction.followup.send(
            f"✅ Decisão registrada: **{'aprovada' if aprovar else 'recusada'}**.", ephemeral=True
        )
        try:
            solicitante = await self.bot.fetch_user(pedido["requester_id"])
            banner = caminho_banner("decisao")
            await enviar_layout(solicitante, montar_resultado(pedido, aprovar, bool(banner)), banner)
        except (discord.HTTPException, OSError):
            LOG.warning("Não foi possível notificar o solicitante %s", pedido["requester_id"])
        try:
            await interaction.message.edit(view=montar_resultado(pedido, aprovar))
        except discord.HTTPException:
            LOG.warning("Falha ao atualizar a DM de decisão do pedido %s", pedido_id)
    async def publicar(self, ctx: commands.Context, canal: discord.TextChannel):
        me = canal.guild.me
        if me is None and self.bot.user:
            me = await canal.guild.fetch_member(self.bot.user.id)
        if me is None:
            return await ctx.reply("❌ Bot não encontrado no servidor.", mention_author=False)
        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            return await ctx.reply("❌ Preciso de acesso e permissão para enviar mensagens.", mention_author=False)
        try:
            cat_banner = caminho_banner("catalogo")
            if cat_banner and not perms.attach_files:
                return await ctx.reply("❌ Preciso da permissão Anexar arquivos.", mention_author=False)
            await enviar_layout(canal, montar_catalogo(self, bool(cat_banner)), cat_banner)
        except (discord.HTTPException, OSError):
            LOG.exception("Não foi possível publicar os painéis de insígnias")
            return await ctx.reply("❌ Falha ao enviar painéis. Confira os logs do Railway.", mention_author=False)
        await ctx.reply(f"✅ Painel unificado de insígnias publicado em {canal.mention}.", mention_author=False)
    @commands.command(name="titularnatal")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def titularnatal(self, ctx: commands.Context,
                           nome: str | None = None,
                           titular: discord.Member | None = None):
        """!titularnatal Noel @membro | sem argumentos: exibe os titulares."""
        pool = self.pool()
        if nome is None:
            atribuidos = await pool.fetch("""
                SELECT role_id, owner_id FROM royal_christmas_insignia_owners
                WHERE guild_id=$1
            """, ctx.guild.id)
            titulares = {r["role_id"]: r["owner_id"] for r in atribuidos}
            texto = ["🎄 **Titulares das insígnias de Natal**"]
            for nome_insignia, role_id in INSIGNIAS_NATAL.items():
                responsavel = titulares.get(role_id)
                texto.append(f"• **{nome_insignia.capitalize()}**: " +
                             (f"<@{responsavel}>" if responsavel else "Ainda não definido"))
            texto.append("\n-# Para definir: `!titularnatal Noel @membro`")
            return await ctx.reply("\n".join(texto), mention_author=False)

        cargo_id = INSIGNIAS_NATAL.get(nome.casefold())
        if cargo_id is None:
            return await ctx.reply("❌ Escolha: `Noel`, `Natalina` ou `Candy`.", mention_author=False)
        if titular is None:
            return await ctx.reply(f"❌ Utilize `!titularnatal {nome.capitalize()} @membro`.", mention_author=False)
        if titular.bot:
            return await ctx.reply("❌ Escolha um membro da Família, não um bot.", mention_author=False)
        if ctx.guild.get_role(cargo_id) is None:
            return await ctx.reply("❌ O cargo desta insígnia ainda não existe no servidor.", mention_author=False)

        anterior = await pool.fetchval("""
            SELECT owner_id FROM royal_christmas_insignia_owners
            WHERE guild_id=$1 AND role_id=$2
        """, ctx.guild.id, cargo_id)
        if anterior is not None and anterior != titular.id:
            pendentes = await pool.fetchval("""
                SELECT COUNT(*) FROM royal_insignia_requests
                WHERE guild_id=$1 AND role_id=$2 AND status IN ('pending', 'processing')
            """, ctx.guild.id, cargo_id)
            if pendentes:
                return await ctx.reply(
                    "⚠️ Há solicitações pendentes desta insígnia. "
                    "Finalize-as antes de trocar seu titular.", mention_author=False
                )

        usado = await pool.fetchval("""
            SELECT role_id FROM royal_christmas_insignia_owners
            WHERE guild_id=$1 AND owner_id=$2 AND role_id<>$3
        """, ctx.guild.id, titular.id, cargo_id)
        if usado is not None:
            return await ctx.reply(
                "❌ Esse membro já é titular de outra insígnia natalina. "
                "Escolha três integrantes diferentes.", mention_author=False
            )

        await pool.execute("""
            INSERT INTO royal_christmas_insignia_owners (guild_id, role_id, owner_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, role_id) DO UPDATE
            SET owner_id=EXCLUDED.owner_id, updated_at=now()
        """, ctx.guild.id, cargo_id, titular.id)
        await ctx.reply(
            f"✅ **{nome.capitalize()}** agora pertence a {titular.mention}. "
            "As novas solicitações serão enviadas a essa pessoa para decisão.",
            mention_author=False
        )

    @commands.command(name="atualizarinsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def atualizarinsignias(self, ctx: commands.Context):
        """Atualiza, sem duplicar, o painel ao responder à mensagem existente."""
        referencia = ctx.message.reference
        if referencia is None or referencia.message_id is None:
            return await ctx.reply(
                "❌ Responda à mensagem do painel com `!atualizarinsignias`.",
                mention_author=False
            )
        try:
            mensagem = await ctx.channel.fetch_message(referencia.message_id)
            if self.bot.user is None or mensagem.author.id != self.bot.user.id:
                raise RuntimeError("O painel precisa ter sido publicado por este bot.")
            if not getattr(mensagem.flags, "components_v2", False):
                raise RuntimeError("A mensagem selecionada não utiliza Components V2.")
            anterior = discord.ui.LayoutView.from_message(mensagem, timeout=None)
            conteudos = [item.content for item in anterior.walk_children()
                        if isinstance(item, discord.ui.TextDisplay)]
            if not any("INSÍGNIAS DA FAMÍLIA ROYAL" in texto for texto in conteudos):
                raise RuntimeError("A mensagem selecionada não é o painel de insígnias.")

            banner = caminho_banner("catalogo")
            if banner is None:
                await mensagem.edit(view=montar_catalogo(self), attachments=[],
                                    allowed_mentions=discord.AllowedMentions.none())
            else:
                me = ctx.guild.me or await ctx.guild.fetch_member(self.bot.user.id)
                if not ctx.channel.permissions_for(me).attach_files:
                    raise RuntimeError("O bot precisa da permissão Anexar Arquivos.")
                with banner.open("rb") as arquivo:
                    await mensagem.edit(
                        view=montar_catalogo(self, com_banner=True),
                        attachments=[discord.File(arquivo, filename=banner.name)],
                        allowed_mentions=discord.AllowedMentions.none()
                    )
        except (discord.DiscordException, RuntimeError, OSError, ValueError) as exc:
            LOG.exception("Falha ao atualizar o painel de insígnias")
            return await ctx.reply(f"❌ Não foi possível atualizar: {str(exc)[:200]}",
                                   mention_author=False)

        await ctx.reply(f"✅ Painel atualizado: {mensagem.jump_url}", mention_author=False)

    @commands.command(name="painelinsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painelinsignias(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.publicar(ctx, canal)
    @commands.command(name="previainsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def previainsignias(self, ctx: commands.Context):
        if isinstance(ctx.channel, discord.TextChannel):
            await self.publicar(ctx, ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(InsigniasRoyal(bot))
