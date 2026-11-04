from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.cargos_exclusivos")

CANAL_CARGOS_PADRAO = 1553820522322862200
BANNER_NOME = "cargos_exclusivos_royal.png"
MARCADOR = "<a:coroa:1564000189167960177> CARGOS EXCLUSIVOS | FAMÍLIA ROYAL"
COR_DESTAQUE = discord.Colour.from_rgb(137, 78, 150)

CARGOS = (
    (
        "Joker", 1553837456585920624,
        (
            ("🔑", "Obtível somente através dos proprietários."),
            ("💰", "**4x** entradas nos sorteios."),
            ("💰", "**1,60x** de multiplicador de XP."),
            ("🔊", "Call privada."),
        ),
    ),
    (
        "Diamante Royal", 1565942574957600798,
        (
            ("💰", "**2x** entradas nos sorteios."),
            ("💰", "**2x** de multiplicador de XP."),
            ("🔑", "Obtível somente através de sorteios realizados pela administração."),
        ),
    ),
    (
        "Artistas", 1554094917092118638,
        (
            ("🎨", "Canal exclusivo de arte."),
        ),
    ),
    (
        "Corregedoria Geral do E.B", 1560374403051684012,
        (
            ("🔒", "Canal administrativo."),
            ("🔑", "Obtível através da comprovação do cargo no E.B."),
        ),
    ),
    (
        "Organizador de Eventos", 1561231585993293864,
        (
            ("📅", "Responsáveis pelos eventos do servidor, incluindo sorteios."),
            ("🔑", "Escolhidos a dedo pela administração."),
        ),
    ),
    (
        "Membros oficiais da Família", 1554367619463913582,
        (
            ("💰", "**2x** de multiplicador de XP."),
            ("🔒", "Canais exclusivos."),
            ("⭐", "Permissões especiais no servidor da Família e no servidor do E.B."),
            ("💰", "**2x** entradas nos sorteios."),
            ("🎉", "Sorteios exclusivos."),
            ("🏅", "Insígnias personalizadas."),
            ("🔊", "Call privada para cada membro."),
        ),
    ),
    (
        "Skull Cat", 1567374808331587724,
        (
            ("❓", "???"),
        ),
    ),
    (
        "Contribuidor", 1566514909267894352,
        (
            ("🎁", "Pessoas que contribuem com premiações para sorteios."),
        ),
    ),
)


def canal_cargos_id() -> int:
    configurado = os.getenv("ROYAL_ROLES_CHANNEL_ID", "").strip()
    if configurado:
        try:
            numero = int(configurado)
            if numero > 0:
                return numero
        except ValueError:
            pass
        logger.warning("ROYAL_ROLES_CHANNEL_ID inválido (%r); usando padrão", configurado)
    return CANAL_CARGOS_PADRAO


def localizar_banner() -> Path | None:
    raiz_cog = Path(__file__).resolve().parent
    candidatos = (
        raiz_cog.parent / "assets" / BANNER_NOME,
        raiz_cog / "assets" / BANNER_NOME,
        Path.cwd() / "assets" / BANNER_NOME,
    )
    for caminho in candidatos:
        if caminho.is_file():
            return caminho
    return None


def components_v2_disponivel() -> bool:
    return (
        all(
            hasattr(discord.ui, atributo)
            for atributo in ("LayoutView", "Container", "TextDisplay", "Separator", "MediaGallery")
        )
        and hasattr(discord, "MediaGalleryItem")
    )


def bloco_cargo(_nome: str, role_id: int, informacoes: tuple[tuple[str, str], ...]) -> str:
    detalhes = "\n".join(f"> `{icone}` {descricao}" for icone, descricao in informacoes)
    return f"### <@&{role_id}>\n{detalhes}"


def texto_painel() -> str:
    blocos = [bloco_cargo(nome, role_id, informacoes) for nome, role_id, informacoes in CARGOS]
    corpo = "\n\n---\n\n".join(blocos)
    return (
        f"## {MARCADOR}\n"
        "Família Royal - Cargos Exclusivos\n\n"
    )


def _adicionar_bloco_com_divisorias(container: discord.ui.Container, itens: list[tuple[str, int, tuple[tuple[str, str], ...]]]) -> None:
    for i, (nome, role_id, informacoes) in enumerate(itens):
        container.add_item(discord.ui.TextDisplay(bloco_cargo(nome, role_id, informacoes)))
        if i < len(itens) - 1:
            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))


def painel_v2(*, com_banner: bool) -> discord.ui.LayoutView:
    """Layout mais formal, com divisórias elegantes entre os cargos."""
    view = discord.ui.LayoutView(timeout=None)

    topo = discord.ui.Container(accent_colour=COR_DESTAQUE)
    if com_banner:
        topo.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                media=f"attachment://{BANNER_NOME}",
                description="Sants, Kael e Mateus — Cargos Exclusivos da Família Royal",
            )
        ))
    topo.add_item(discord.ui.TextDisplay(
        f"## {MARCADOR}\n"
        "Família Royal - Cargos Exclusivos\n\n"
    ))
    view.add_item(topo)

    # Divide em 3 seções para respeitar o limite de componentes do Discord.
    secoes = (CARGOS[0:3], CARGOS[3:6], CARGOS[6:8])
    for secao in secoes:
        container = discord.ui.Container(accent_colour=COR_DESTAQUE)
        _adicionar_bloco_com_divisorias(container, list(secao))
        view.add_item(container)

    rodape = discord.ui.Container(accent_colour=COR_DESTAQUE)
    rodape.add_item(discord.ui.TextDisplay(
        "-# Família Royal - Cargos Exclusivos\n"
    ))
    view.add_item(rodape)
    return view


def _texto_componentes(componentes) -> str:
    textos: list[str] = []

    def visitar(itens):
        for item in itens or ():
            conteudo = getattr(item, "content", None)
            if isinstance(conteudo, str):
                textos.append(conteudo)
            filhos = getattr(item, "children", None)
            if filhos is None:
                filhos = getattr(item, "components", None)
            if filhos is not None:
                visitar(filhos)

    visitar(componentes)
    return "\n\n".join(textos)


def _texto_mensagem(mensagem: discord.Message) -> str:
    return _texto_componentes(getattr(mensagem, "components", ())) or (mensagem.content or "")


class CargosExclusivosRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self.ultima_falha: str | None = None

    async def _canal(self) -> discord.TextChannel | None:
        cid = canal_cargos_id()
        canal = self.bot.get_channel(cid)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(cid)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                logger.warning("Canal de cargos indisponível (%s): %s", cid, exc)
                return None
        return canal if isinstance(canal, discord.TextChannel) else None

    async def _mensagem_existente(self, canal: discord.TextChannel) -> discord.Message | None:
        async for mensagem in canal.history(limit=500):
            if (
                self.bot.user is not None
                and mensagem.author.id == self.bot.user.id
                and MARCADOR in _texto_mensagem(mensagem)
            ):
                return mensagem
        return None

    async def publicar(self) -> tuple[bool, str]:
        async with self._lock:
            try:
                canal = await self._canal()
                if canal is None:
                    return self._erro("O canal de cargos não foi encontrado ou está inacessível.")
                if self.bot.user is None:
                    return self._erro("O bot ainda não está conectado.")

                guild = canal.guild
                membro_bot = guild.me or guild.get_member(self.bot.user.id)
                if membro_bot is None:
                    membro_bot = await guild.fetch_member(self.bot.user.id)

                permissoes = canal.permissions_for(membro_bot)
                ausentes = []
                if not permissoes.view_channel:
                    ausentes.append("Ver canal")
                if not permissoes.send_messages:
                    ausentes.append("Enviar mensagens")
                if not permissoes.read_message_history:
                    ausentes.append("Ler histórico de mensagens")
                if ausentes:
                    return self._erro("Permissões ausentes: " + ", ".join(ausentes))

                banner = localizar_banner()
                if banner is None:
                    logger.warning("Banner ausente: assets/%s; painel será enviado sem imagem", BANNER_NOME)
                com_banner = banner is not None and bool(permissoes.attach_files)
                tamanho = banner.stat().st_size if com_banner and banner else None
                mencoes = discord.AllowedMentions.none()
                anterior = await self._mensagem_existente(canal)
                v2 = components_v2_disponivel()
                esperado = texto_painel()

                if anterior is not None:
                    painel_anterior_v2 = bool(getattr(anterior.flags, "is_components_v2", False))
                    banner_atual = (
                        any(a.filename == BANNER_NOME and a.size == tamanho for a in anterior.attachments)
                        if com_banner else not any(a.filename == BANNER_NOME for a in anterior.attachments)
                    )
                    if (
                        _texto_mensagem(anterior).strip() == esperado
                        and banner_atual
                        and painel_anterior_v2 == v2
                    ):
                        self.ultima_falha = None
                        return True, "O painel já está atualizado; nenhuma mensagem duplicada foi criada."
                    if painel_anterior_v2 and not v2:
                        return self._erro(
                            "O painel atual utiliza Components V2. Atualize o discord.py para 2.6+ antes de editá-lo."
                        )

                async def enviar_v2(usando_imagem: bool) -> None:
                    view = painel_v2(com_banner=usando_imagem)
                    if anterior is not None:
                        if usando_imagem and banner is not None:
                            with banner.open("rb") as imagem:
                                await anterior.edit(
                                    content=None,
                                    embed=None,
                                    attachments=[discord.File(imagem, filename=BANNER_NOME)],
                                    view=view,
                                    allowed_mentions=mencoes,
                                )
                        else:
                            await anterior.edit(
                                content=None,
                                embed=None,
                                attachments=[],
                                view=view,
                                allowed_mentions=mencoes,
                            )
                    elif usando_imagem and banner is not None:
                        with banner.open("rb") as imagem:
                            await canal.send(
                                view=view,
                                file=discord.File(imagem, filename=BANNER_NOME),
                                allowed_mentions=mencoes,
                            )
                    else:
                        await canal.send(view=view, allowed_mentions=mencoes)

                if v2:
                    try:
                        await enviar_v2(bool(com_banner))
                        self.ultima_falha = None
                        return True, f"Painel {'atualizado' if anterior else 'publicado'} com Components V2" + (
                            " e banner." if com_banner else " (sem banner)."
                        )
                    except discord.HTTPException as exc:
                        if exc.status != 400:
                            raise
                        logger.warning("Discord recusou o painel V2 com banner: %s", exc)
                        if com_banner:
                            try:
                                await enviar_v2(False)
                                self.ultima_falha = None
                                return True, "Painel publicado sem banner: Discord recusou o anexo."
                            except discord.HTTPException as segunda:
                                if segunda.status != 400:
                                    raise
                        if anterior is not None and bool(getattr(anterior.flags, "is_components_v2", False)):
                            return self._erro("O Discord recusou a atualização do painel V2 (HTTP 400).")

                if anterior is not None:
                    if com_banner and banner is not None:
                        with banner.open("rb") as imagem:
                            await anterior.edit(
                                content=esperado,
                                view=None,
                                attachments=[discord.File(imagem, filename=BANNER_NOME)],
                                allowed_mentions=mencoes,
                            )
                    else:
                        await anterior.edit(content=esperado, view=None, attachments=[], allowed_mentions=mencoes)
                elif com_banner and banner is not None:
                    with banner.open("rb") as imagem:
                        await canal.send(
                            content=esperado,
                            file=discord.File(imagem, filename=BANNER_NOME),
                            allowed_mentions=mencoes,
                        )
                else:
                    await canal.send(content=esperado, allowed_mentions=mencoes)
                self.ultima_falha = None
                return True, f"Painel {'atualizado' if anterior else 'publicado'} em texto simples."
            except (discord.HTTPException, OSError, ValueError, TypeError) as exc:
                logger.exception("Erro ao publicar cargos exclusivos")
                return self._erro(f"{type(exc).__name__}: {str(exc)[:180]}")

    def _erro(self, mensagem: str) -> tuple[bool, str]:
        self.ultima_falha = mensagem
        return False, mensagem

    @commands.Cog.listener()
    async def on_ready(self):
        ok, mensagem = await self.publicar()
        (logger.info if ok else logger.warning)("Painel de cargos exclusivos: %s", mensagem)

    @commands.command(name="cargosexclusivos")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def comando_publicar(self, ctx: commands.Context):
        canal = await self._canal()
        if canal is None or canal.guild.id != ctx.guild.id:
            await ctx.reply("❌ Comando disponível apenas no servidor da Família Royal.", mention_author=False)
            return
        ok, mensagem = await self.publicar()
        await ctx.reply(("✅ " if ok else "❌ ") + mensagem, mention_author=False)

    @commands.command(name="statuscargosexclusivos")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def comando_status(self, ctx: commands.Context):
        canal = await self._canal()
        if canal is None or canal.guild.id != ctx.guild.id:
            await ctx.reply("❌ Comando disponível apenas no servidor da Família Royal.", mention_author=False)
            return
        b = localizar_banner()
        painel_atual = await self._mensagem_existente(canal)
        await ctx.reply(
            "**👑 Status dos Cargos Exclusivos**\n"
            f"• Canal: <#{canal_cargos_id()}>\n"
            f"• Components V2: {'disponível' if components_v2_disponivel() else 'indisponível'}\n"
            f"• Banner: {b.name if b else 'NÃO encontrado'}\n"
            f"• Publicação: {'localizada' if painel_atual else 'não encontrada no histórico recente'}\n"
            f"• Última falha: {self.ultima_falha or 'nenhuma'}",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CargosExclusivosRoyal(bot))
