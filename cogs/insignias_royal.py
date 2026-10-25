

import logging
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.insignias_royal")
ROYAL = discord.Colour.from_rgb(188, 148, 86)
BASE_DIR = Path(__file__).resolve().parent.parent
BANNER = BASE_DIR / "assets" / "insignias_royal.png"
BANNER_FILENAME = "insignias_royal.png"

INSIGNIAS = [
    ("Bruna", 1554376484637122591, "🌹",
     "Representa acolhimento e consideração pessoal. Sua concessão depende da autorização da Bruna."),
    ("Tatah", 1555370356343312486, "🌙",
     "Símbolo de confiança e proximidade, reservado às pessoas reconhecidas pelaTatah."),
    ("Pietra", 1556147238852628562, "💎",
     "Expressa apreço e reconhecimento pessoal, mediante autorização da Pietra."),
    ("Kananda", 1556147239179518022, "🪽",
     "Representa companheirismo e proteção, mediante consentimento da Kananda."),
    ("Sant's", 1554376496196493342, "👑",
     "Reconhecimento pessoal do fundador, concedido apenas mediante sua autorização."),
    ("Kael", 1554376496787886090, "⚔️",
     "Representa respeito e confiança, reservado às pessoas escolhidas por Kael."),
    ("Ruan", 1554376496548941894, "🛡️",
     "Símbolo de lealdade e consideração, atribuído somente com o aval de Ruan."),
    ("Pato", 1556147238986711070, "🪶",
     "Expressa amizade e estima pessoal, concedida a critério de Pato."),
    ("Violets", 1562498973787230339, "✨",
     "Representa vínculo especial e reconhecimento, dependendo da autorização de Violets."),
    ("Diniz", 1563986618207965246, "🌟",
     "Símbolo de proximidade e apreço, destinado a pessoas reconhecidas por Diniz."),
    ("Hanz", 1564041775000064060, "🔥",
     "Representa confiança e consideração pessoal, concedida exclusivamente por Hanz."),
]

TITULARES = {
    "Bruna": 697068974323793921,
    "Tatah": 1032084016196763688,
    "Pietra": 1295645409082867732,
    "Kananda": 1430221798389059584,
    "Sant's": 925863471902503033,
    "Kael": 1541150632554135724,
    "Ruan": 1348504492345397358,
    "Pato": 1459320617852731635,
    "Violets": 969628191268421672,
    "Diniz": 1546524499430604891,
    "Hanz": 1004088774810144859,
}

POR_CARGO = {cargo_id: (nome, emoji, descricao) for nome, cargo_id, emoji, descricao in INSIGNIAS}


def painel_catalogo(cog: "InsigniasRoyal", com_banner: bool = False) -> discord.ui.LayoutView:
    """Uma única mensagem V2: imagem, lista compacta e seletor."""
    view = discord.ui.LayoutView(timeout=None)
    painel = discord.ui.Container(accent_colour=ROYAL)
    if com_banner:
        painel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{BANNER_FILENAME}")
        ))

    painel.add_item(discord.ui.TextDisplay(
        "## <a:coroa:1564000189167960177>・INSÍGNIAS DA FAMÍLIA ROYAL\n"
        "> `👑` Distinções pessoais dos membros oficiais.\n"
        "> `📜` Cada insígnia exige aprovação de seu titular."
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

    linhas = []
    for nome, cargo_id, emoji, descricao in INSIGNIAS:
        linhas.append(f"> `{emoji}` <@&{cargo_id}>\n{descricao}")
    painel.add_item(discord.ui.TextDisplay("\n".join(linhas)))

    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    painel.add_item(discord.ui.TextDisplay(
        "> `✉️` **SOLICITAR INSÍGNIA**\n"
        "Selecione uma opção para enviar seu pedido ao titular. "
        "Somente ele pode aprovar a concessão."
    ))
    seletor = discord.ui.Select(
        placeholder="Escolha uma insígnia Royal",
        min_values=1,
        max_values=1,
        custom_id="royal:insignias:selecionar:v1",
        options=[discord.SelectOption(
            label=f"Insígnia {nome}", value=str(cargo_id),
            description=f"Titular: {nome} • Autorização obrigatória",
            emoji=emoji
        ) for nome, cargo_id, emoji, _ in INSIGNIAS]
    )

    async def selecionar(interaction: discord.Interaction):
        await cog.solicitar(interaction, int(seletor.values[0]))

    seletor.callback = selecionar
    painel.add_item(discord.ui.ActionRow(seletor))
    view.add_item(painel)
    return view


class AprovacaoView(discord.ui.LayoutView):
    def __init__(self, cog: "InsigniasRoyal", pedido_id: int, nome: str = "Royal", solicitante: int = 0, servidor: str = ""):
        super().__init__(timeout=None)
        panel = discord.ui.Container(accent_colour=ROYAL)
        panel.add_item(discord.ui.TextDisplay(
            "## <:ImagemdoChatGPT25deoutde202615_4:1563986790753378424>・AUTORIZAÇÃO DE INSÍGNIA\n"
            f"> `👑` **Insígnia {nome}**\n"
            f"> `👤` Solicitante: <@{solicitante}> (`{solicitante}`)\n"
            f"> `🏰` Servidor: **{servidor or 'Família Royal'}**\n\n"
            "`📜` Somente você pode aprovar ou recusar a concessão."
        ))
        aprovar = discord.ui.Button(
            label="Aprovar", style=discord.ButtonStyle.success,
            custom_id=f"royal:insig:aprovar:{pedido_id}",
        )
        recusar = discord.ui.Button(
            label="Recusar", style=discord.ButtonStyle.danger,
            custom_id=f"royal:insig:recusar:{pedido_id}",
        )

        async def aprovar_cb(interaction: discord.Interaction):
            await cog.decidir(interaction, pedido_id, aprovar=True)

        async def recusar_cb(interaction: discord.Interaction):
            await cog.decidir(interaction, pedido_id, aprovar=False)

        aprovar.callback = aprovar_cb
        recusar.callback = recusar_cb
        panel.add_item(discord.ui.ActionRow(aprovar, recusar))
        self.add_item(panel)


class InsigniasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def pool(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("PostgreSQL indisponível: confira DATABASE_URL e bot.pool.")
        return pool

    async def cog_load(self):
        # Os pedidos ficam no PostgreSQL para sobreviver a deploys no Railway.
        try:
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
            pending = await pool.fetch("""
                SELECT id, dm_message_id, insignia_name, requester_id FROM royal_insignia_requests
                WHERE status = 'pending' AND dm_message_id IS NOT NULL
            """)
            for item in pending:
                self.bot.add_view(
                    AprovacaoView(self, item["id"], item["insignia_name"], item["requester_id"]),
                    message_id=item["dm_message_id"],
                )
            # A seleção pública permanece ativa após reiniciar o bot.
            self.bot.add_view(painel_catalogo(self, com_banner=False))
        except Exception:
            logger.exception("Falha ao preparar banco e painéis de insígnias")
            raise

    async def solicitar(self, interaction: discord.Interaction, role_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "❌ Solicite a insígnia dentro do servidor.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        info = POR_CARGO.get(role_id)
        if not info:
            return await interaction.followup.send("❌ Insígnia desconhecida.", ephemeral=True)
        nome, _, _ = info
        owner_id = TITULARES.get(nome)
        if not isinstance(owner_id, int) or owner_id <= 0:
            return await interaction.followup.send(
                f"⚠️ O titular da insígnia **{nome}** ainda não foi configurado.",
                ephemeral=True,
            )
        role = interaction.guild.get_role(role_id)
        if role is None:
            return await interaction.followup.send("❌ Cargo não encontrado no servidor.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.followup.send("✅ Você já possui esta insígnia.", ephemeral=True)
        if interaction.user.id == owner_id:
            return await interaction.followup.send(
                "Você já é o titular desta insígnia; não precisa solicitá-la.", ephemeral=True
            )
        try:
            pool = self.pool()
            pedido = await pool.fetchrow("""
                INSERT INTO royal_insignia_requests
                (guild_id, requester_id, owner_id, role_id, insignia_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING RETURNING id
            """, interaction.guild.id, interaction.user.id, owner_id, role_id, nome)
            if pedido is None:
                return await interaction.followup.send(
                    "⏳ Você já possui um pedido pendente para esta insígnia.",
                    ephemeral=True,
                )
            pedido_id = pedido["id"]
            try:
                titular = await self.bot.fetch_user(owner_id)
                # No Components V2 o TextDisplay deve conter todo o texto da DM.
                # Enviar content=... junto com LayoutView resulta em HTTP 400.
                dm = await titular.send(
                    view=AprovacaoView(self, pedido_id, nome,
                                      interaction.user.id, interaction.guild.name),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as exc:
                await pool.execute(
                    "DELETE FROM royal_insignia_requests WHERE id=$1 AND status='pending'",
                    pedido_id,
                )
                logger.exception("Erro na DM: titular=%s HTTP=%s codigo=%s corpo=%s",
                                 owner_id, exc.status, exc.code, exc.text)
                if exc.code in (50007, 50278):
                    motivo = ("O Discord não permitiu enviar DM ao titular. "
                              "Ele deve verificar as configurações de privacidade, "
                              "bloqueios e o servidor compartilhado.")
                else:
                    motivo = (f"Erro no envio do painel: HTTP {exc.status} "
                              f"/ código {exc.code}. Consulte os logs no Railway.")
                return await interaction.followup.send(f"❌ {motivo}", ephemeral=True)
            await pool.execute(
                "UPDATE royal_insignia_requests SET dm_message_id=$1 WHERE id=$2",
                dm.id, pedido_id,
            )
            self.bot.add_view(
                AprovacaoView(self, pedido_id, nome, interaction.user.id,
                             interaction.guild.name), message_id=dm.id
            )
            await interaction.followup.send(
                f"✅ Seu pedido da **Insígnia {nome}** foi enviado ao titular. "
                "Aguarde a decisão dele.",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao solicitar insígnia")
            await interaction.followup.send(
                "❌ Falha ao registrar a solicitação. Confira os logs.",
                ephemeral=True,
            )

    async def decidir(self, interaction: discord.Interaction, pedido_id: int, *, aprovar: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            pool = self.pool()
            pedido = await pool.fetchrow(
                "SELECT * FROM royal_insignia_requests WHERE id=$1", pedido_id
            )
            if pedido is None:
                return await interaction.followup.send("❌ Pedido não encontrado.", ephemeral=True)
            if interaction.user.id != pedido["owner_id"]:
                return await interaction.followup.send(
                    "⛔ Apenas o titular pode decidir sobre esta insígnia.",
                    ephemeral=True,
                )
            if pedido["status"] != "pending":
                return await interaction.followup.send(
                    f"Este pedido já foi processado: {pedido['status']}.", ephemeral=True
                )

            # Bloqueia decisões simultâneas em instâncias/reinicializações diferentes.
            status = "processing" if aprovar else "rejected"
            changed = await pool.fetchrow("""
                UPDATE royal_insignia_requests
                SET status=$2, decided_at=now()
                WHERE id=$1 AND status='pending'
                RETURNING id
            """, pedido_id, status)
            if not changed:
                return await interaction.followup.send(
                    "Este pedido já foi atendido.", ephemeral=True
                )

            if aprovar:
                try:
                    guild = self.bot.get_guild(pedido["guild_id"])
                    if guild is None:
                        raise RuntimeError("Servidor não encontrado pelo bot.")
                    membro = guild.get_member(pedido["requester_id"])
                    if membro is None:
                        membro = await guild.fetch_member(pedido["requester_id"])
                    role = guild.get_role(pedido["role_id"])
                    if role is None:
                        raise RuntimeError("Cargo da insígnia não encontrado.")
                    await membro.add_roles(
                        role,
                        reason=f"Insígnia {pedido['insignia_name']} aprovada por {interaction.user.id}",
                    )
                    await pool.execute(
                        "UPDATE royal_insignia_requests SET status='approved' WHERE id=$1",
                        pedido_id,
                    )
                except (discord.HTTPException, RuntimeError) as exc:
                    logger.exception("Não foi possível conceder insígnia %s", pedido_id)
                    await pool.execute(
                        "UPDATE royal_insignia_requests SET status='pending', decided_at=NULL "
                        "WHERE id=$1 AND status='processing'", pedido_id,
                    )
                    return await interaction.followup.send(
                        f"❌ Aprovação não concluída: `{str(exc)[:200]}`. "
                        "Verifique permissões e posição do cargo do bot; tente novamente.",
                        ephemeral=True,
                    )
            resultado = "APROVADO" if aprovar else "RECUSADO"
            await interaction.followup.send(
                f"✅ Pedido **{resultado}**: Insígnia {pedido['insignia_name']}.",
                ephemeral=True,
            )
            try:
                requester = await self.bot.fetch_user(pedido["requester_id"])
                await requester.send(
                    f"{'✅' if aprovar else '❌'} Seu pedido da "
                    f"**Insígnia {pedido['insignia_name']}** foi "
                    f"{'aprovado e o cargo foi concedido' if aprovar else 'recusado'} "
                    f"pelo respectivo titular."
                )
            except discord.HTTPException:
                logger.info("Não foi possível notificar solicitante %s", pedido["requester_id"])
            try:
                await interaction.message.edit(view=decisao_encerrada(pedido, resultado))
            except discord.HTTPException:
                logger.warning("Não foi possível atualizar os botões do pedido %s", pedido_id)
        except Exception:
            logger.exception("Erro ao processar pedido %s", pedido_id)
            await interaction.followup.send(
                "❌ Falha no processamento; consulte os logs.", ephemeral=True
            )

    async def _publicar(self, ctx: commands.Context, canal: discord.TextChannel):
        try:
            me = canal.guild.me
            if me is None and self.bot.user:
                me = await canal.guild.fetch_member(self.bot.user.id)
            if me is None:
                raise RuntimeError("Bot não encontrado no servidor.")
            perms = canal.permissions_for(me)
            if not (perms.view_channel and perms.send_messages):
                raise RuntimeError("Preciso das permissões Ver canal e Enviar mensagens.")
            if BANNER.is_file():
                if not perms.attach_files:
                    raise RuntimeError("Preciso da permissão Anexar arquivos para enviar o banner.")
                with BANNER.open("rb") as arquivo:
                    await canal.send(
                        view=painel_catalogo(self, com_banner=True),
                        file=discord.File(arquivo, filename=BANNER_FILENAME),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            else:
                logger.warning("Banner não encontrado: %s. Catálogo enviado sem imagem.", BANNER)
                await canal.send(
                    view=painel_catalogo(self, com_banner=False),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            await ctx.reply(f"✅ Painel único publicado em {canal.mention}.",
                            mention_author=False)
        except (discord.HTTPException, RuntimeError) as exc:
            logger.exception("Erro ao publicar painel")
            await ctx.reply(f"❌ {str(exc)[:240]}", mention_author=False)

    @commands.command(name="painelinsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painelinsignias(self, ctx: commands.Context, canal: discord.TextChannel):
        """!painelinsignias #insignias"""
        await self._publicar(ctx, canal)

    @commands.command(name="previainsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def previainsignias(self, ctx: commands.Context):
        """!previainsignias"""
        if isinstance(ctx.channel, discord.TextChannel):
            await self._publicar(ctx, ctx.channel)


def decisao_encerrada(pedido, resultado: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    panel = discord.ui.Container(accent_colour=ROYAL)
    panel.add_item(discord.ui.TextDisplay(
        f"## <a:coroa:1564000189167960177>・SOLICITAÇÃO {resultado}\n"
        f"**Insígnia {pedido['insignia_name']}**\n"
        f"Solicitante: <@{pedido['requester_id']}>\n"
        "Decisão registrada. Esta solicitação está encerrada."
    ))
    view.add_item(panel)
    return view


async def setup(bot: commands.Bot):
    await bot.add_cog(InsigniasRoyal(bot))
