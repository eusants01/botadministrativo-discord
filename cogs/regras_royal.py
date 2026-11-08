

from __future__ import annotations



import logging

import os

from pathlib import Path



import discord

from discord.ext import commands



logger = logging.getLogger("sants.bot.regras_royal")



CANAL_REGRAS_PADRAO = 1553829609160835342

NOME_BANNER = "regras_royal.png"

MARCADOR_PAINEL = "REGIMENTO INTERNO"

COR_ROYAL = discord.Colour.from_rgb(187, 149, 82)  

RAIZ = Path(__file__).resolve().parent.parent



ARTIGOS = (

    (

        "`⚖️`", "Do Respeito e da Convivência",

        "Todos os integrantes deverão manter uma conduta respeitosa. São vedadas "

        "ofensas, discriminação, ameaças, perseguições e atitudes que comprometam "

        "a integridade ou a convivência da comunidade.",

    ),

    (

        "`⚖️`", "Da Conduta no Servidor",

        "São proibidos spam, flood, divulgação não autorizada, exposição de dados "

        "pessoais, contas alternativas para contornar punições e conteúdos inadequados.",

    ),

    (

        "`⚖️`", "Da Imagem Institucional",

        "Os membros deverão preservar a reputação e os princípios da Família Royal, "

        "sem utilizar seu nome para promover conflitos, fraudes ou obter vantagens indevidas.",

    ),

    (

        "`⚖️`", "Do Abuso de Autoridade",

        "É proibido o abuso de autoridade, independentemente do cargo. Intimidação, "

        "favorecimento pessoal, perseguição, punições arbitrárias e uso indevido "

        "de permissões constituem infrações disciplinares.",

    ),

    (

        "`⚖️`", "Da Hierarquia e dos Cargos",

        "Os cargos deverão ser exercidos com responsabilidade e imparcialidade. "

        "É vedado exceder atribuições, conceder privilégios irregulares ou impor "

        "ordens contrárias a este regimento.",

    ),

    (

        "`⚖️`", "Da Confidencialidade",

        "Denúncias, registros internos, informações administrativas e dados pessoais "

        "deverão ser protegidos. A divulgação dependerá de autorização ou de "

        "encaminhamento legítimo às autoridades competentes.",

    ),

    (

        "`⚖️`", "Do Vínculo com o E.B. do ALPHA",

        "O integrante banido do servidor oficial do E.B. do ALPHA também será "

        "banido do servidor da Família Royal, após confirmação da identidade "

        "e da penalidade, independentemente do cargo ocupado.",

    ),

    (

        "`⚖️`", "Das Denúncias e da Imparcialidade",

        "As denúncias serão analisadas com discrição e imparcialidade. Autoridades "

        "envolvidas nos fatos ou em conflito de interesses não poderão conduzir "

        "nem decidir o procedimento.",

    ),

    (

        "`⚖️`", "Das Infrações e Penalidades",

        "As infrações poderão resultar em advertência, suspensão de privilégios, "

        "destituição de cargo, expulsão ou banimento permanente, conforme a "

        "gravidade, as provas, as circunstâncias e a reincidência.",

    ),

    (

        "`⚖️`", "Do Direito de Defesa e Revisão",

        "O integrante poderá apresentar sua versão dos fatos e solicitar revisão "

        "fundamentada da penalidade, preferencialmente por autoridade distinta "

        "daquela que aplicou a decisão inicial.",

    ),

)



CABECALHO = (

    f"# ⚖️ {MARCADOR_PAINEL}\n"

    "-# Normas oficiais de convivência."

)



RODAPE = (

    "-# Família Royal · Fundada em 28/01/2026 · EB do ALPHA"

)



PLACEHOLDER_BANNER = (

    "**🖼️ Espaço reservado ao banner oficial**\n"

    "-# A imagem aparecerá aqui ao adicionar `assets/regras_royal.png` "

    "e atualizar/publicar o painel."

)





def canal_regras_id() -> int:

    """Permite sobrescrever o canal por ROYAL_RULES_CHANNEL_ID no Railway/.env."""

    value = os.getenv("ROYAL_RULES_CHANNEL_ID", "").strip()

    if value:

        try:

            channel_id = int(value)

            if channel_id > 0:

                return channel_id

        except ValueError:

            pass

        logger.warning("ROYAL_RULES_CHANNEL_ID inválido (%r); usando padrão.", value)

    return CANAL_REGRAS_PADRAO





def caminho_banner() -> Path | None:

    """Busca o banner apenas pelo nome reservado, sem usar imagens de outros painéis."""

    locais = (

        RAIZ / "assets" / NOME_BANNER,

        Path(__file__).resolve().parent / "assets" / NOME_BANNER,

        Path.cwd() / "assets" / NOME_BANNER,

    )

    return next((p for p in locais if p.is_file()), None)





def componentes_v2_disponiveis() -> bool:

    return all(

        hasattr(discord.ui, name)

        for name in ("LayoutView", "Container", "TextDisplay", "Separator", "MediaGallery")

    ) and hasattr(discord, "MediaGalleryItem")





def texto_artigo(numero: str, titulo: str, descricao: str) -> str:

    return f"**{numero} — {titulo}**\n> {descricao}"





def grupos_artigos() -> tuple[str, str, str]:

    textos = [texto_artigo(*artigo) for artigo in ARTIGOS]

    return (

        "\n\n".join(textos[:3]),

        "\n\n".join(textos[3:7]),

        "\n\n".join(textos[7:]),

    )





def montar_painel(*, com_banner: bool) -> discord.ui.LayoutView:

    """Um único container com banner, 10 artigos e disposições finais."""

    if not componentes_v2_disponiveis():

        raise RuntimeError("O painel requer discord.py 2.6 ou superior (Components V2).")



    painel = discord.ui.Container(accent_colour=COR_ROYAL)

    if com_banner:

        painel.add_item(discord.ui.MediaGallery(

            discord.MediaGalleryItem(

                media=f"attachment://{NOME_BANNER}",

                description="Banner oficial do Regimento Interno da Família Royal.",

            )

        ))

    else:

        painel.add_item(discord.ui.TextDisplay(PLACEHOLDER_BANNER))



    painel.add_item(discord.ui.TextDisplay(CABECALHO))

    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))



    for indice, grupo in enumerate(grupos_artigos()):

        if indice:

            painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        painel.add_item(discord.ui.TextDisplay(grupo))



    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

    painel.add_item(discord.ui.TextDisplay(RODAPE))



    view = discord.ui.LayoutView(timeout=None)

    view.add_item(painel)

    # Discord limita o conteúdo textual agregado de LayoutView a 4.000 caracteres.

    if view.content_length() > 4000:

        raise RuntimeError(f"Painel ultrapassou o limite V2: {view.content_length()} caracteres.")

    return view





class RegrasRoyal(commands.Cog):

    def __init__(self, bot: commands.Bot):

        self.bot = bot



    async def cog_load(self) -> None:

        if not componentes_v2_disponiveis():

            logger.error("O cog Regras Royal requer discord.py >= 2.6.")

        logger.info("Regras Royal carregadas | canal=%s | banner=%s",

                    canal_regras_id(), bool(caminho_banner()))



    async def canal_padrao(self, guild: discord.Guild) -> discord.TextChannel:

        cid = canal_regras_id()

        canal = guild.get_channel(cid)

        if canal is None:

            canal = await guild.fetch_channel(cid)

        if not isinstance(canal, discord.TextChannel):

            raise RuntimeError(f"Canal de regras {cid} não é um canal de texto válido.")

        if canal.guild.id != guild.id:

            raise RuntimeError("O canal configurado não pertence a este servidor.")

        return canal



    async def conferir_permissoes(self, canal: discord.TextChannel, *, atualizar=False, banner=False) -> None:

        if self.bot.user is None:

            raise RuntimeError("O bot ainda não está pronto.")

        me = canal.guild.me or canal.guild.get_member(self.bot.user.id)

        if me is None:

            me = await canal.guild.fetch_member(self.bot.user.id)

        permissoes = canal.permissions_for(me)

        if not permissoes.view_channel:

            raise RuntimeError("O bot precisa da permissão Ver Canal.")

        if not atualizar and not permissoes.send_messages:

            raise RuntimeError("O bot precisa da permissão Enviar Mensagens.")

        if atualizar and not permissoes.read_message_history:

            raise RuntimeError("O bot precisa da permissão Ler Histórico de Mensagens.")

        if banner and not permissoes.attach_files:

            raise RuntimeError("O bot precisa da permissão Anexar Arquivos para exibir o banner.")



    async def publicar(self, canal: discord.TextChannel) -> discord.Message:

        banner = caminho_banner()

        await self.conferir_permissoes(canal, banner=banner is not None)

        view = montar_painel(com_banner=banner is not None)

        if banner is None:

            return await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none())

        with banner.open("rb") as arquivo:

            return await canal.send(

                view=view,

                file=discord.File(arquivo, filename=NOME_BANNER),

                allowed_mentions=discord.AllowedMentions.none(),

            )



    async def executar_publicacao(self, ctx: commands.Context, canal: discord.TextChannel) -> None:

        try:

            mensagem = await self.publicar(canal)

        except (discord.DiscordException, RuntimeError, OSError, ValueError) as exc:

            logger.exception("Falha ao publicar o Regimento Interno da Royal")

            await ctx.reply(f"❌ Não foi possível publicar: {str(exc)[:300]}", mention_author=False)

            return

        await ctx.reply(f"✅ Regimento publicado em {canal.mention}: {mensagem.jump_url}", mention_author=False)



    @commands.command(name="painelregras", aliases=["publicarregras"])

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def painelregras(self, ctx: commands.Context, canal: discord.TextChannel | None = None):

        """Publica o painel V2 no canal oficial ou no canal indicado."""

        try:

            destino = canal or await self.canal_padrao(ctx.guild)

        except (discord.DiscordException, RuntimeError) as exc:

            await ctx.reply(f"❌ {exc}", mention_author=False)

            return

        await self.executar_publicacao(ctx, destino)



    @commands.command(name="previarregras")

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def previarregras(self, ctx: commands.Context):

        """Exibe o painel completo em teste no canal atual."""

        if not isinstance(ctx.channel, discord.TextChannel):

            await ctx.reply("❌ Execute em um canal de texto do servidor.", mention_author=False)

            return

        await self.executar_publicacao(ctx, ctx.channel)



    @commands.command(name="atualizarregras")

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def atualizarregras(self, ctx: commands.Context, mensagem_id: int | None = None):

        """Atualiza um painel V2 existente sem duplicar (por ID ou resposta à mensagem)."""

        referencia = ctx.message.reference

        if mensagem_id is None and referencia is not None:

            mensagem_id = referencia.message_id

        if mensagem_id is None:

            await ctx.reply(

                "❌ Informe o ID do painel ou responda à mensagem dele com `!atualizarregras`.",

                mention_author=False,

            )

            return

        try:

            # Por ID: pesquisa no canal oficial. Em resposta: pesquisa no canal atual.

            canal = (ctx.channel if referencia is not None and referencia.message_id == mensagem_id

                     else await self.canal_padrao(ctx.guild))

            if not isinstance(canal, discord.TextChannel):

                raise RuntimeError("Utilize um canal de texto.")

            banner = caminho_banner()

            await self.conferir_permissoes(canal, atualizar=True, banner=banner is not None)

            mensagem = await canal.fetch_message(mensagem_id)

            if self.bot.user is None or mensagem.author.id != self.bot.user.id:

                raise RuntimeError("Apenas painéis publicados por este bot podem ser atualizados.")

            if not getattr(mensagem.flags, "components_v2", False):

                raise RuntimeError("A mensagem indicada não é um painel Components V2.")



            anterior = discord.ui.LayoutView.from_message(mensagem, timeout=None)

            textos = [item.content for item in anterior.walk_children()

                      if isinstance(item, discord.ui.TextDisplay)]

            if not any(MARCADOR_PAINEL in texto for texto in textos):

                raise RuntimeError("A mensagem indicada não é o Regimento Interno da Royal.")



            view = montar_painel(com_banner=banner is not None)

            if banner is None:

                atualizada = await mensagem.edit(

                    view=view, attachments=[], allowed_mentions=discord.AllowedMentions.none()

                )

            else:

                with banner.open("rb") as arquivo:

                    atualizada = await mensagem.edit(

                        view=view,

                        attachments=[discord.File(arquivo, filename=NOME_BANNER)],

                        allowed_mentions=discord.AllowedMentions.none(),

                    )

        except (discord.DiscordException, RuntimeError, OSError, ValueError) as exc:

            logger.exception("Falha ao atualizar o Regimento Interno da Royal")

            await ctx.reply(f"❌ Não foi possível atualizar: {str(exc)[:300]}", mention_author=False)

            return

        await ctx.reply(f"✅ Regimento atualizado: {atualizada.jump_url}", mention_author=False)



    @commands.command(name="regras")

    @commands.guild_only()

    async def regras(self, ctx: commands.Context):

        """Direciona qualquer integrante para o canal de regras."""

        await ctx.reply(f"📜 Consulte o Regimento Interno da Família Royal em <#{canal_regras_id()}>.",

                        mention_author=False)



    @commands.command(name="statusregras")

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def statusregras(self, ctx: commands.Context):

        banner = caminho_banner()

        versao = getattr(discord, "__version__", "desconhecida")

        await ctx.reply(

            f"📜 **Status do Regimento Royal**\n"

            f"• Versão discord.py: `{versao}`\n"

            f"• Components V2: `{'OK' if componentes_v2_disponiveis() else 'INDISPONÍVEL'}`\n"

            f"• Canal de regras: <#{canal_regras_id()}>\n"

            f"• Banner: `{'ENCONTRADO' if banner else 'AGUARDANDO assets/' + NOME_BANNER}`\n"

            f"• Artigos: `{len(ARTIGOS)}`\n"

            f"• Caracteres V2: `{sum(len(v) for v in (CABECALHO, *grupos_artigos(), RODAPE, PLACEHOLDER_BANNER))}` (sem banner)",

            mention_author=False,

        )





async def setup(bot: commands.Bot):

    await bot.add_cog(RegrasRoyal(bot))
