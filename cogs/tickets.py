from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

# ╔══════════════════════════════════════════════════════════════╗
# ║                        CONFIGURAÇÃO                          ║
# ╚══════════════════════════════════════════════════════════════╝
#
# O bot precisa da permissão "Gerenciar Cargos" e o cargo dele precisa estar
# ACIMA dos cargos de notificação na lista de cargos do servidor.
# O PostgreSQL (bot.pool) é usado só para lembrar em quais mensagens o painel está,
# para o !atualizarpings conseguir aplicar mudanças de texto nos painéis já enviados.
# Sem o pool, tudo funciona normalmente.

NOME_SERVIDOR = "Família Sant's"

# Mesma identidade do painel de tickets
COR_PRINCIPAL = 0x1A3C8C
COR_SUCESSO = 0x2ECC71
COR_ALERTA = 0xE67E22
COR_ERRO = 0xE74C3C
COR_NEUTRA = 0x95A5A6

# Linha divisória usada nas mensagens do painel
SEPARADOR = "▬" * 16


IMAGEM_PINGS_ARQUIVO = "https://i.imgur.com/BU2ot5J.png"
IMAGEM_PINGS_URL = ""
ICONE_PINGS = ""

# Quem pode usar os comandos: Administrador OU algum destes cargos.
CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

# Canal (só da staff) que recebe um registro quando alguém muda as notificações.
# 0 = desligado.
LOG_CANAL_ID = 0

# Tempo mínimo (segundos) entre duas alterações da mesma pessoa.
COOLDOWN_SEG = 3

# ── Texto do painel (EDITE AQUI e use !atualizarpings para aplicar) ────────────
# É o texto inteiro do painel: markdown normal do Discord. Pode mudar à vontade.
PAINEL_DESCRICAO = """\
# <a:animated_Notifications:1557622860569120821> **Central de Notificações**
Escolha no menu abaixo as notificações que deseja receber.

**Escolha suas Notificações**
> `🎁` **Sorteios** — Seja avisado quando rolar um sorteio.
> `🎉` **Eventos** — Eventos e atividades do servidor.
> `📢` **Anúncios** — Comunicados importantes da administração.
> `⚠️` **Avisos** — Avisos gerais e lembretes rápidos.
> `📰` **Notícias** — Novidades e atualizações da família.

**Como funciona**
> `✅` Escolha uma opção no menu para **ativar**.
> `🚫` Escolha a mesma opção de novo para **desativar**.

**Aviso**
> `⚠️` Ative só o que você quer acompanhar — você pode mudar quando quiser.
"""

# chave → dados de cada notificação (a ordem aqui é a ordem no menu)
NOTIFICACOES: dict[str, dict] = {
    "sorteios": {
        "nome": "Sorteios",
        "emoji": "🎁",
        "cargo_id": 1555798698410377246,
        "desc": "Seja avisado quando rolar um sorteio.",
    },
    "eventos": {
        "nome": "Eventos",
        "emoji": "🎉",
        "cargo_id": 1555798699643375717,
        "desc": "Eventos e atividades do servidor.",
    },
    "anuncio": {
        "nome": "Anúncios",
        "emoji": "📢",
        "cargo_id": 1555798703586152458,
        "desc": "Comunicados importantes da administração.",
    },
    "avisos": {
        "nome": "Avisos",
        "emoji": "⚠️",
        "cargo_id": 1555798705775448084,
        "desc": "Avisos gerais e lembretes rápidos.",
    },
    "noticias": {
        "nome": "Notícias",
        "emoji": "📰",
        "cargo_id": 1557612576798544002,
        "desc": "Novidades e atualizações da família.",
    },
}

VALOR_TODAS = "__todas"
VALOR_NENHUMA = "__nenhuma"

SQL_CRIAR_TABELA = """
CREATE TABLE IF NOT EXISTS pings_paineis (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, message_id)
);
"""

_ultimo_uso: dict[int, float] = {}


# ════════════════════════════════════════════════════════════════
#                              AUXILIARES
# ════════════════════════════════════════════════════════════════


def eh_staff(membro) -> bool:
    if not isinstance(membro, discord.Member):
        return False
    if membro.guild_permissions.administrator:
        return True
    ids = {r.id for r in membro.roles}
    return any(c in ids for c in CARGOS_STAFF)


def apenas_staff():
    async def predicate(ctx: commands.Context):
        if ctx.guild is not None and eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def _banner_local() -> str | None:
    if IMAGEM_PINGS_ARQUIVO and os.path.isfile(IMAGEM_PINGS_ARQUIVO):
        return IMAGEM_PINGS_ARQUIVO
    return None


def banner_arquivo() -> discord.File | None:
    """Novo discord.File a cada envio (um File só pode ser usado uma vez)."""
    caminho = _banner_local()
    if caminho:
        return discord.File(caminho, filename=os.path.basename(caminho))
    return None


def banner_url() -> str | None:
    caminho = _banner_local()
    if caminho:
        return f"attachment://{os.path.basename(caminho)}"
    return IMAGEM_PINGS_URL or None


def embed_base(
    titulo: str | None,
    descricao: str | None = None,
    cor: int = COR_PRINCIPAL,
    banner: bool = False,
) -> discord.Embed:
    e = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor,
        timestamp=datetime.now(timezone.utc),
    )
    kwargs = {"text": f"{NOME_SERVIDOR} • Central de Notificações"}
    if ICONE_PINGS:
        kwargs["icon_url"] = ICONE_PINGS
    e.set_footer(**kwargs)
    if banner and (url := banner_url()):
        e.set_image(url=url)
    return e


def cargo_de(guild: discord.Guild, chave: str) -> discord.Role | None:
    return guild.get_role(NOTIFICACOES[chave]["cargo_id"])


def cargos_usaveis(guild: discord.Guild) -> tuple[dict[str, discord.Role], list[str]]:
    """
    Retorna (cargos que o bot consegue gerenciar, lista de problemas).
    Um cargo com problema não derruba os outros: só ele fica indisponível.
    """
    me = guild.me
    usaveis: dict[str, discord.Role] = {}
    problemas: list[str] = []

    if not me.guild_permissions.manage_roles:
        problemas.append("O bot está sem a permissão **Gerenciar Cargos**.")
        return usaveis, problemas

    for chave, n in NOTIFICACOES.items():
        cargo = cargo_de(guild, chave)
        if cargo is None:
            problemas.append(f"O cargo de **{n['nome']}** (`{n['cargo_id']}`) não foi encontrado.")
        elif cargo >= me.top_role:
            problemas.append(
                f"O cargo {cargo.mention} está acima (ou igual) ao cargo do bot — "
                "mova o cargo do bot para cima dele."
            )
        else:
            usaveis[chave] = cargo
    return usaveis, problemas


def fmt_notificacoes(chaves) -> str:
    return ", ".join(
        f"{NOTIFICACOES[c]['emoji']} **{NOTIFICACOES[c]['nome']}**"
        for c in NOTIFICACOES
        if c in chaves
    )


def status_linhas(ativas) -> str:
    return "\n".join(
        f"{'🟢' if c in ativas else '⚪'} {n['emoji']} {n['nome']}"
        for c, n in NOTIFICACOES.items()
    )


# ════════════════════════════════════════════════════════════════
#                  PAINEL (MENU PERSISTENTE, COMO O TICKET)
# ════════════════════════════════════════════════════════════════


def embed_minhas(guild: discord.Guild, membro: discord.Member) -> discord.Embed:
    tem = {c for c in NOTIFICACOES if (cargo := cargo_de(guild, c)) and cargo in membro.roles}
    embed = embed_base(
        "📋 Suas notificações",
        f"{membro.mention}, veja o que você recebe hoje.\n{SEPARADOR}",
        cor=COR_PRINCIPAL,
    )
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(
        name=f"📊 Seu status • {len(tem)}/{len(NOTIFICACOES)} ativas",
        value=status_linhas(tem),
        inline=False,
    )
    return embed


class PingsSelect(discord.ui.Select):
    """Menu único. Escolher uma notificação alterna: ativa se não tem, remove se já tem."""

    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label=n["nome"], value=chave, description=n["desc"], emoji=n["emoji"]
            )
            for chave, n in NOTIFICACOES.items()
        ]
        opcoes += [
            discord.SelectOption(
                label="Ativar todas",
                value=VALOR_TODAS,
                description="Receber todas as notificações.",
                emoji="✅",
            ),
            discord.SelectOption(
                label="Desativar todas",
                value=VALOR_NENHUMA,
                description="Remover todas as notificações.",
                emoji="🚫",
            ),
        ]
        super().__init__(
            custom_id="pings:select",
            placeholder="🔔 Escolha suas notificações...",
            min_values=1,
            max_values=len(opcoes),
            options=opcoes,
        )

    async def callback(self, interaction: discord.Interaction):
        # Reseta o menu do painel (some a seleção) e libera a interação.
        await interaction.response.edit_message(view=PainelPingsView())

        guild = interaction.guild
        membro = interaction.user
        if guild is None or not isinstance(membro, discord.Member):
            return

        # Cooldown por pessoa
        agora = time.monotonic()
        if agora - _ultimo_uso.get(membro.id, -1e9) < COOLDOWN_SEG:
            embed = embed_base(
                "⏳ Calma aí",
                "Aguarde alguns segundos antes de mudar de novo.",
                cor=COR_ALERTA,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)
        _ultimo_uso[membro.id] = agora

        usaveis, problemas = cargos_usaveis(guild)
        tem = {c for c in NOTIFICACOES if (cargo := cargo_de(guild, c)) and cargo in membro.roles}
        escolhidas = set(self.values)


        # Sem permissão nenhuma → nada a fazer
        if not usaveis:
            embed = embed_base(
                "❌ Não consegui alterar suas notificações",
                "Avise a administração. Detalhes:\n" + "\n".join(f"• {p}" for p in problemas),
                cor=COR_ERRO,
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Decide o que ativar/remover
        if VALOR_NENHUMA in escolhidas:
            alvo_add: set[str] = set()
            alvo_rem = set(tem)
        elif VALOR_TODAS in escolhidas:
            alvo_add = set(NOTIFICACOES) - tem
            alvo_rem = set()
        else:
            alvo_add = {c for c in escolhidas if c not in tem}
            alvo_rem = {c for c in escolhidas if c in tem}

        # Ignora o que o bot não consegue gerenciar (e avisa)
        indisponiveis = (alvo_add | alvo_rem) - set(usaveis)
        alvo_add -= indisponiveis
        alvo_rem -= indisponiveis

        # Uma única chamada à API para aplicar tudo
        if alvo_add or alvo_rem:
            rem_cargos = {usaveis[c] for c in alvo_rem}
            novos = [r for r in membro.roles if r not in rem_cargos]
            novos += [usaveis[c] for c in alvo_add if usaveis[c] not in novos]
            try:
                await membro.edit(roles=novos, reason="Painel de notificações")
            except discord.Forbidden:
                embed = embed_base(
                    "❌ Sem permissão",
                    "Não consegui alterar seus cargos. Avise a administração.",
                    cor=COR_ERRO,
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException:
                embed = embed_base(
                    "⚠️ Falha ao falar com o Discord",
                    "Tente novamente em alguns segundos.",
                    cor=COR_ERRO,
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

        ativas_agora = (tem | alvo_add) - alvo_rem

        linhas = []
        if alvo_add:
            linhas.append(f"✅ **Ativadas:** {fmt_notificacoes(alvo_add)}")
        if alvo_rem:
            linhas.append(f"🚫 **Desativadas:** {fmt_notificacoes(alvo_rem)}")
        if indisponiveis:
            linhas.append(
                f"⚠️ **Indisponíveis no momento:** {fmt_notificacoes(indisponiveis)} "
                "(avise a administração)"
            )
        if not linhas:
            linhas.append("Nada mudou — você já estava assim.")

        embed = embed_base(
            "🔔 Notificações atualizadas",
            f"{membro.mention}, suas preferências foram salvas.\n{SEPARADOR}\n" + "\n".join(linhas),
            cor=COR_ALERTA if indisponiveis else COR_SUCESSO,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(
            name=f"📊 Seu status • {len(ativas_agora)}/{len(NOTIFICACOES)} ativas",
            value=status_linhas(ativas_agora),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Registro opcional para a staff
        if (alvo_add or alvo_rem) and LOG_CANAL_ID:
            canal = guild.get_channel(LOG_CANAL_ID)
            if canal:
                log = embed_base("🧾 Notificações alteradas", cor=COR_PRINCIPAL)
                log.set_thumbnail(url=membro.display_avatar.url)
                log.description = f"{membro.mention} • **{membro.display_name}** • ID `{membro.id}`"
                if alvo_add:
                    log.add_field(name="✅ Ativou", value=fmt_notificacoes(alvo_add), inline=True)
                if alvo_rem:
                    log.add_field(name="🚫 Desativou", value=fmt_notificacoes(alvo_rem), inline=True)
                try:
                    await canal.send(embed=log, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass


class BotaoMinhasNotificacoes(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Ver minhas notificações",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            custom_id="pings:minhas",
        )

    async def callback(self, interaction: discord.Interaction):
        membro = interaction.user
        if interaction.guild is None or not isinstance(membro, discord.Member):
            return await interaction.response.send_message(
                "❌ Não foi possível verificar suas notificações.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=embed_minhas(interaction.guild, membro), ephemeral=True
        )


class PainelPingsView(discord.ui.View):
    """View persistente (custom_id fixo): continua funcionando depois de reiniciar."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PingsSelect())
        self.add_item(BotaoMinhasNotificacoes())


# ════════════════════════════════════════════════════════════════
#                                COG
# ════════════════════════════════════════════════════════════════


class PingsCog(commands.Cog, name="Notificações"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def pool(self):
        return getattr(self.bot, "pool", None)

    async def cog_load(self):
        self.bot.add_view(PainelPingsView())

    # ── Painel ──────────────────────────────────────────────────
    def embed_painel(self, guild: discord.Guild | None = None) -> discord.Embed:
        return embed_base(None, PAINEL_DESCRICAO.strip(), banner=True)

    # ── Atualizar painéis já enviados ───────────────────────────
    async def _atualizar_guild(self, gid: int) -> int:
        """Reaplica o texto/banner em todos os painéis da guild. Retorna quantos foram atualizados."""
        guild = self.bot.get_guild(gid)
        if guild is None or self.pool is None:
            return 0

        try:
            await self.pool.execute(SQL_CRIAR_TABELA)
            rows = await self.pool.fetch(
                "SELECT channel_id, message_id FROM pings_paineis WHERE guild_id=$1", gid
            )
        except Exception as e:  # noqa: BLE001
            print(f"[pings] erro ao ler painéis: {type(e).__name__}: {e}")
            return 0

        embed = self.embed_painel(guild)
        atualizados = 0
        for r in rows:
            canal = guild.get_channel(r["channel_id"])
            if canal is None:
                await self.pool.execute(
                    "DELETE FROM pings_paineis WHERE guild_id=$1 AND message_id=$2",
                    gid, r["message_id"],
                )
                continue
            try:
                await canal.get_partial_message(r["message_id"]).edit(embed=embed)
                atualizados += 1
            except discord.NotFound:
                await self.pool.execute(
                    "DELETE FROM pings_paineis WHERE guild_id=$1 AND message_id=$2",
                    gid, r["message_id"],
                )
            except discord.HTTPException:
                pass
        return atualizados

    # ── Erros de comando ────────────────────────────────────────
    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=5)
        else:
            raise error

    # ── Comandos ────────────────────────────────────────────────
    async def _registrar_painel(self, guild_id: int, channel_id: int, message_id: int):
        """Salva a mensagem do painel no PostgreSQL (para a atualização automática)."""
        if self.pool is None:
            return
        try:
            await self.pool.execute(SQL_CRIAR_TABELA)
            await self.pool.execute(
                """
                INSERT INTO pings_paineis (guild_id, channel_id, message_id)
                VALUES ($1,$2,$3) ON CONFLICT DO NOTHING
                """,
                guild_id, channel_id, message_id,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[pings] erro ao salvar painel: {type(e).__name__}: {e}")

    @commands.command(name="painelpings", aliases=["painel_notificacoes"])
    @apenas_staff()
    async def painelpings(self, ctx: commands.Context):
        """Envia o painel de notificações neste canal."""
        usaveis, problemas = cargos_usaveis(ctx.guild)
        if problemas:
            embed = embed_base(
                "⚠️ Atenção antes de usar o painel",
                "\n".join(f"• {p}" for p in problemas)
                + ("\n\nO painel foi enviado mesmo assim." if usaveis else ""),
                cor=COR_ERRO,
            )
            await ctx.send(embed=embed, delete_after=20)
            if not usaveis:
                return

        if IMAGEM_PINGS_ARQUIVO and not _banner_local() and not IMAGEM_PINGS_URL:
            await ctx.send(
                f"ℹ️ Banner não encontrado em `{IMAGEM_PINGS_ARQUIVO}` — painel enviado sem imagem.",
                delete_after=10,
            )

        msg = await ctx.send(
            embed=self.embed_painel(ctx.guild),
            view=PainelPingsView(),
            file=banner_arquivo(),
        )
        await self._registrar_painel(ctx.guild.id, ctx.channel.id, msg.id)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @app_commands.command(
        name="painel_notificacoes",
        description="🔔 Envia o painel de notificações neste canal.",
    )
    @app_commands.guild_only()
    async def painel_slash(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(
                "❌ Apenas a staff pode usar este comando.", ephemeral=True
            )

        usaveis, problemas = cargos_usaveis(interaction.guild)
        if not usaveis:
            embed = embed_base(
                "⚠️ Ajuste antes de usar o painel",
                "\n".join(f"• {p}" for p in problemas),
                cor=COR_ERRO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        kwargs = {}
        arquivo = banner_arquivo()
        if arquivo:
            kwargs["file"] = arquivo

        await interaction.response.send_message(
            embed=self.embed_painel(interaction.guild),
            view=PainelPingsView(),
            **kwargs,
        )
        msg = await interaction.original_response()
        await self._registrar_painel(interaction.guild.id, interaction.channel_id, msg.id)

        if problemas:
            aviso = embed_base(
                "⚠️ Atenção",
                "\n".join(f"• {p}" for p in problemas),
                cor=COR_ERRO,
            )
            await interaction.followup.send(embed=aviso, ephemeral=True)

    @commands.command(name="atualizarpings")
    @apenas_staff()
    async def atualizarpings(self, ctx: commands.Context):
        """Aplica o texto atual (PAINEL_DESCRICAO) nos painéis já enviados."""
        if self.pool is None:
            return await ctx.send("❌ O pool do PostgreSQL não está configurado.", delete_after=8)
        n = await self._atualizar_guild(ctx.guild.id)
        await ctx.send(f"✅ {n} painel(is) atualizado(s).", delete_after=8)

    @commands.command(name="statuspings")
    @apenas_staff()
    async def statuspings(self, ctx: commands.Context):
        """Mostra quantas pessoas têm cada notificação e a saúde da configuração."""
        embed = embed_base("📊 Status das notificações", banner=True)
        linhas = []
        for chave, n in NOTIFICACOES.items():
            cargo = cargo_de(ctx.guild, chave)
            if cargo is None:
                linhas.append(f"{n['emoji']} **{n['nome']}** — ❌ cargo não encontrado")
            else:
                linhas.append(f"{n['emoji']} {cargo.mention} — **{len(cargo.members)}** pessoas")
        embed.description = "\n".join(linhas)

        _, problemas = cargos_usaveis(ctx.guild)
        embed.add_field(
            name="🩺 Cargos e permissões",
            value="✅ Tudo certo." if not problemas else "\n".join(f"• {p}" for p in problemas),
            inline=False,
        )

        if _banner_local():
            banner = f"✅ Arquivo `{IMAGEM_PINGS_ARQUIVO}`"
        elif IMAGEM_PINGS_URL:
            banner = "✅ Link configurado"
        else:
            banner = "⚠️ Nenhum banner configurado"

        if self.pool is not None:
            try:
                qtd = await self.pool.fetchval(
                    "SELECT COUNT(*) FROM pings_paineis WHERE guild_id=$1", ctx.guild.id
                )
                paineis = f"**{qtd}** registrado(s)"
            except Exception:  # noqa: BLE001
                paineis = "❌ erro ao consultar o banco"
        else:
            paineis = "⚠️ sem PostgreSQL (!atualizarpings indisponível)"

        embed.add_field(name="🖼️ Banner", value=banner, inline=True)
        embed.add_field(name="🗄️ Painéis", value=paineis, inline=True)
        embed.add_field(
            name="🧾 Log de alterações",
            value=f"<#{LOG_CANAL_ID}>" if LOG_CANAL_ID else "desligado",
            inline=True,
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(PingsCog(bot))