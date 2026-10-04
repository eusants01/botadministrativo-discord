from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone

import discord
from discord.ext import commands

# ╔══════════════════════════════════════════════════════════════╗
# ║                        CONFIGURAÇÃO                          ║
# ╚══════════════════════════════════════════════════════════════╝
#
# O bot precisa da permissão "Gerenciar Servidor" (para ler os convites) e das
# intents de Members e Invites (a de Invites já vem ligada por padrão).

# Canal (só da staff) onde cada entrada é registrada. 0 = não envia mensagens
# (os dados continuam sendo salvos e os comandos funcionam).
CANAL_CONVITES_ID = 1556310089328099429

# Quem pode usar os comandos: Administrador OU algum destes cargos.
CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

# Contas com menos dias que isso recebem o aviso "⚠️ conta nova".
ALERTA_CONTA_NOVA_DIAS = 7

# Registrar também as saídas no canal? (a contagem de "ativos/saíram" funciona
# de qualquer jeito, isto só controla se aparece mensagem.)
LOGAR_SAIDAS = False

# Entradas que acontecem dentro desta janela (segundos) são analisadas juntas.
# É isso que permite acertar quando várias pessoas entram ao mesmo tempo.
JANELA_AGRUPAR = 2.0

# Um convite que sumiu só é considerado "usado até o limite" se o Discord avisou
# da exclusão dele nos últimos X segundos.
JANELA_DELETE = 30

PASTA_DADOS = "dados_convites"
os.makedirs(PASTA_DADOS, exist_ok=True)
F_CONVITES = os.path.join(PASTA_DADOS, "convites.json")

SEM_MENCOES = discord.AllowedMentions.none()


# ════════════════════════════════════════════════════════════════
#                         ARMAZENAMENTO (JSON)
# ════════════════════════════════════════════════════════════════
#
# Estrutura:
# { "guilds": { "<guild_id>": {
#       "nomes":   { "<user_id>": "último nome conhecido" },
#       "membros": { "<user_id>": {
#           "nome", "inviter" (id ou None), "inviter_nome", "codigo",
#           "tipo": convite | vanity | ambiguo | desconhecido | bot,
#           "candidatos": [ {"inviter", "nome", "codigo"} ]  (só em "ambiguo"),
#           "conta_ts", "entrou_ts", "ultima_entrada_ts", "saiu_ts", "entradas"
#       } } } } }
#
# Regra de contagem: cada PESSOA conta uma única vez, para quem a convidou na
# primeira entrada identificada. Quem sai e volta não é contado de novo.


def _ler_json(caminho: str, padrao):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return padrao


def _salvar_json(caminho: str, dados):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _carregar() -> dict:
    dados = _ler_json(F_CONVITES, {"guilds": {}})
    dados.setdefault("guilds", {})
    return dados


def _guild(dados: dict, gid: int) -> dict:
    g = dados["guilds"].setdefault(str(gid), {})
    g.setdefault("nomes", {})
    g.setdefault("membros", {})
    return g


def ler_guild(gid: int) -> dict:
    return _guild(_carregar(), gid)


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
        if eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def pessoas(n: int) -> str:
    return f"{n} pessoa" if n == 1 else f"{n} pessoas"


def idade_conta_txt(criada: datetime, ate: datetime | None = None) -> tuple[str, int]:
    """Retorna (texto, dias inteiros) da idade da conta."""
    ate = ate or datetime.now(timezone.utc)
    seg = max(0, (ate - criada).total_seconds())
    dias = int(seg // 86400)
    if dias < 1:
        horas = int(seg // 3600)
        return f"menos de 1 dia ({horas}h)", 0
    return f"{dias} dia" + ("" if dias == 1 else "s"), dias


def nome_de(guild: discord.Guild, g: dict, uid: int) -> str:
    m = guild.get_member(uid)
    if m:
        return m.display_name
    return g.get("nomes", {}).get(str(uid)) or f"ID {uid}"


def resumo_inviter(g: dict, uid: int) -> dict:
    total = ativos = saiu = novas = 0
    for rec in g["membros"].values():
        if rec.get("inviter") != uid:
            continue
        total += 1
        if rec.get("saiu_ts"):
            saiu += 1
        else:
            ativos += 1
        dias = (rec.get("entrou_ts", 0) - rec.get("conta_ts", 0)) // 86400
        if dias < ALERTA_CONTA_NOVA_DIAS:
            novas += 1
    return {"total": total, "ativos": ativos, "saiu": saiu, "novas": novas}


def ranking(g: dict) -> list[tuple[int, int]]:
    cont = Counter(
        rec["inviter"] for rec in g["membros"].values() if rec.get("inviter") is not None
    )
    return sorted(cont.items(), key=lambda kv: (-kv[1], kv[0]))


def sem_origem(g: dict) -> int:
    """Pessoas cuja origem não deu para identificar com certeza."""
    return sum(
        1 for rec in g["membros"].values() if rec.get("tipo") in ("ambiguo", "desconhecido")
        and rec.get("inviter") is None
    )


async def enviar_em_partes(destino, linhas: list[str], limite: int = 1900):
    bloco = ""
    for linha in linhas:
        if len(bloco) + len(linha) + 1 > limite:
            await destino.send(bloco, allowed_mentions=SEM_MENCOES)
            bloco = ""
        bloco += linha + "\n"
    if bloco.strip():
        await destino.send(bloco, allowed_mentions=SEM_MENCOES)


# ════════════════════════════════════════════════════════════════
#                                  COG
# ════════════════════════════════════════════════════════════════


class ConvitesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: dict[int, dict] = {}                 # guild -> {codigo: dados}
        self.locks: dict[int, asyncio.Lock] = {}
        self.fila: dict[int, list[discord.Member]] = {}
        self.processando: set[int] = set()
        self.deletados: dict[tuple[int, str], float] = {}
        self.aviso_perm: dict[int, float] = {}
        self.tarefas: set[asyncio.Task] = set()

    def _lock(self, gid: int) -> asyncio.Lock:
        return self.locks.setdefault(gid, asyncio.Lock())

    def _criar_tarefa(self, coro):
        t = asyncio.create_task(coro)
        self.tarefas.add(t)
        t.add_done_callback(self.tarefas.discard)

    # ── Inicialização ───────────────────────────────────────────
    async def cog_load(self):
        self._criar_tarefa(self._iniciar())

    async def _iniciar(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._iniciar_guild(guild)

    async def _iniciar_guild(self, guild: discord.Guild):
        if guild.id in self.cache:
            return
        async with self._lock(guild.id):
            if guild.id in self.cache:
                return
            try:
                self.cache[guild.id] = await self._buscar_estado(guild)
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"[convites] não consegui ler os convites de {guild.name}: {e}")

    async def _buscar_estado(self, guild: discord.Guild) -> dict:
        estado: dict[str, dict] = {}
        for inv in await guild.invites():
            estado[inv.code] = {
                "uses": inv.uses or 0,
                "max": inv.max_uses or 0,
                "inviter": inv.inviter.id if inv.inviter else None,
                "inviter_nome": inv.inviter.display_name if inv.inviter else None,
                "vanity": False,
            }
        if guild.vanity_url_code:
            try:
                v = await guild.vanity_invite()
            except (discord.Forbidden, discord.HTTPException):
                v = None
            if v is not None:
                estado["vanity:" + v.code] = {
                    "uses": v.uses or 0,
                    "max": 0,
                    "inviter": None,
                    "inviter_nome": None,
                    "vanity": True,
                }
        return estado

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._iniciar_guild(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        self.cache.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        gid = invite.guild.id if invite.guild else None
        if gid is None or gid not in self.cache:
            return
        async with self._lock(gid):
            self.cache[gid].setdefault(
                invite.code,
                {
                    "uses": invite.uses or 0,
                    "max": invite.max_uses or 0,
                    "inviter": invite.inviter.id if invite.inviter else None,
                    "inviter_nome": invite.inviter.display_name if invite.inviter else None,
                    "vanity": False,
                },
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        gid = invite.guild.id if invite.guild else None
        if gid is not None:
            self.deletados[(gid, invite.code)] = time.monotonic()

    # ── Entrada de membros ──────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        gid = member.guild.id
        self.fila.setdefault(gid, []).append(member)
        if gid not in self.processando:
            self.processando.add(gid)
            self._criar_tarefa(self._processar_fila(member.guild))

    async def _processar_fila(self, guild: discord.Guild):
        try:
            while self.fila.get(guild.id):
                await asyncio.sleep(JANELA_AGRUPAR)
                lote = self.fila[guild.id]
                self.fila[guild.id] = []
                try:
                    await self._resolver_lote(guild, lote)
                except Exception as e:  # noqa: BLE001 - nunca deixar a fila morrer
                    print(f"[convites] erro ao processar entradas: {type(e).__name__}: {e}")
        finally:
            self.processando.discard(guild.id)

    def _calcular_usos(self, gid: int, antes: dict, depois: dict, n: int) -> dict[str, int]:
        """Quantos usos novos cada convite teve desde a última leitura."""
        usos: dict[str, int] = {}
        for code, d in depois.items():
            base = antes.get(code, {}).get("uses", 0)
            if d["uses"] > base:
                usos[code] = d["uses"] - base

        # Convites que desapareceram porque atingiram o limite de usos.
        faltam = n - sum(usos.values())
        if faltam > 0:
            agora = time.monotonic()
            sumiram = [
                (c, a)
                for c, a in antes.items()
                if c not in depois
                and not a.get("vanity")
                and a["max"] > a["uses"]
                and agora - self.deletados.get((gid, c), -1e9) <= JANELA_DELETE
            ]
            if len(sumiram) == 1:
                c, a = sumiram[0]
                usos[c] = min(a["max"] - a["uses"], faltam)
        return usos

    async def _resolver_lote(self, guild: discord.Guild, lote: list[discord.Member]):
        gid = guild.id
        async with self._lock(gid):
            depois = None
            erro = None
            try:
                depois = await self._buscar_estado(guild)
            except discord.Forbidden:
                erro = "sem_permissao"
            except discord.HTTPException:
                erro = "falha_api"

            # Quem entrou enquanto consultávamos entra no mesmo lote.
            extra = self.fila.get(gid)
            if extra:
                lote.extend(extra)
                self.fila[gid] = []

            humanos = [m for m in lote if not m.bot]
            bots = [m for m in lote if m.bot]
            resultados: dict[int, dict] = {}

            for b in bots:
                resultados[b.id] = {"tipo": "bot"}

            if humanos:
                if depois is None:
                    base = {"tipo": "desconhecido", "motivo": erro}
                    for m in humanos:
                        resultados[m.id] = dict(base)
                else:
                    antes = self.cache.get(gid)
                    self.cache[gid] = depois
                    if antes is None:
                        for m in humanos:
                            resultados[m.id] = {"tipo": "desconhecido", "motivo": "sem_base"}
                    else:
                        usos = self._calcular_usos(gid, antes, depois, len(humanos))
                        total = sum(usos.values())
                        if total == 0:
                            base = {"tipo": "desconhecido", "motivo": "sem_uso"}
                        elif total == len(humanos) and len(usos) == 1:
                            code = next(iter(usos))
                            info = depois.get(code) or antes.get(code)
                            if info.get("vanity"):
                                base = {"tipo": "vanity", "codigo": code.split(":", 1)[1]}
                            else:
                                base = {
                                    "tipo": "convite",
                                    "codigo": code,
                                    "inviter": info["inviter"],
                                    "inviter_nome": info.get("inviter_nome"),
                                }
                        else:
                            cands = []
                            for code in usos:
                                info = depois.get(code) or antes.get(code)
                                cands.append(
                                    {
                                        "inviter": info.get("inviter"),
                                        "nome": info.get("inviter_nome"),
                                        "codigo": code.split(":", 1)[-1],
                                    }
                                )
                            base = {"tipo": "ambiguo", "candidatos": cands}
                        for m in humanos:
                            resultados[m.id] = dict(base)

            # limpa registros antigos de exclusão
            limite = time.monotonic() - 300
            for k in [k for k, v in self.deletados.items() if v < limite]:
                self.deletados.pop(k, None)

            for membro in lote:
                res = resultados[membro.id]
                rec, reentrada, inviter_antes = self._registrar_entrada(guild, membro, res)
                await self._enviar_log_entrada(guild, membro, res, rec, reentrada, inviter_antes)

            if erro == "sem_permissao":
                await self._avisar_permissao(guild)

    def _registrar_entrada(self, guild: discord.Guild, membro: discord.Member, res: dict):
        """Salva a entrada. Sem nenhum await aqui dentro, então é atômico."""
        dados = _carregar()
        g = _guild(dados, guild.id)
        agora = int(time.time())
        mid = str(membro.id)
        conta_ts = int(membro.created_at.timestamp())

        g["nomes"][mid] = membro.display_name
        if res.get("inviter") is not None and res.get("inviter_nome"):
            g["nomes"][str(res["inviter"])] = res["inviter_nome"]
        for c in res.get("candidatos", []):
            if c.get("inviter") is not None and c.get("nome"):
                g["nomes"][str(c["inviter"])] = c["nome"]

        rec = g["membros"].get(mid)
        reentrada = rec is not None
        inviter_antes = rec.get("inviter") if rec else None

        if rec is None:
            rec = {
                "nome": membro.display_name,
                "inviter": res.get("inviter") if res["tipo"] == "convite" else None,
                "inviter_nome": res.get("inviter_nome") if res["tipo"] == "convite" else None,
                "codigo": res.get("codigo"),
                "tipo": res["tipo"],
                "candidatos": res.get("candidatos", []),
                "conta_ts": conta_ts,
                "entrou_ts": agora,
                "ultima_entrada_ts": agora,
                "saiu_ts": None,
                "entradas": 1,
            }
            g["membros"][mid] = rec
        else:
            rec["nome"] = membro.display_name
            rec["entradas"] = int(rec.get("entradas", 1)) + 1
            rec["ultima_entrada_ts"] = agora
            rec["saiu_ts"] = None
            # Só "promove" o registro se antes a origem era incerta.
            if rec.get("inviter") is None and res["tipo"] == "convite":
                rec.update(
                    inviter=res.get("inviter"),
                    inviter_nome=res.get("inviter_nome"),
                    codigo=res.get("codigo"),
                    tipo="convite",
                    candidatos=[],
                )
            elif rec.get("tipo") in ("ambiguo", "desconhecido") and res["tipo"] == "vanity":
                rec.update(tipo="vanity", codigo=res.get("codigo"), candidatos=[])

        _salvar_json(F_CONVITES, dados)
        return rec, reentrada, inviter_antes

    # ── Mensagem no canal de convites ───────────────────────────
    async def _canal_log(self, guild: discord.Guild):
        return guild.get_channel(CANAL_CONVITES_ID) if CANAL_CONVITES_ID else None

    async def _enviar_log_entrada(self, guild, membro, res, rec, reentrada, inviter_antes):
        canal = await self._canal_log(guild)
        if canal is None:
            return
        g = ler_guild(guild.id)
        idade, dias = idade_conta_txt(membro.created_at)
        alerta = " ⚠️ **conta nova**" if dias < ALERTA_CONTA_NOVA_DIAS else ""
        titulo = "🔁 Reentrada" if reentrada else "📥 Entrada"
        linhas = [
            f"{titulo}: **{membro.display_name}** ({membro.mention}) • ID `{membro.id}`",
            f"🕒 Conta criada em <t:{int(membro.created_at.timestamp())}:D> → **{idade}**{alerta}",
        ]
        tipo = res["tipo"]
        credito = rec.get("inviter")  # quem leva o crédito (primeiro convite identificado)

        if tipo == "bot":
            linhas.append("🤖 Bot adicionado ao servidor (não conta como convite).")
        elif tipo == "convite":
            nome_inv = nome_de(guild, g, res["inviter"]) if res["inviter"] else "desconhecido"
            mencao = f"<@{res['inviter']}>" if res["inviter"] else ""
            linhas.append(f"🔗 Convidado por **{nome_inv}** {mencao} — código `{res['codigo']}`")
            if reentrada and credito is not None and credito != res["inviter"]:
                linhas.append(
                    f"ℹ️ Já tinha entrado antes: o crédito continua com "
                    f"**{nome_de(guild, g, credito)}** (primeiro convite)."
                )
            elif reentrada:
                linhas.append("ℹ️ Já tinha entrado antes: **não conta de novo**.")
        elif tipo == "vanity":
            linhas.append(f"🔗 Entrou pelo link personalizado `discord.gg/{res['codigo']}`")
        elif tipo == "ambiguo":
            opcoes = ", ".join(
                f"**{c['nome'] or ('ID ' + str(c['inviter']))}** (`{c['codigo']}`)"
                for c in res["candidatos"]
            )
            linhas.append(
                "❓ **Indeterminado:** várias pessoas entraram ao mesmo tempo por "
                f"convites diferentes. Veio de um destes: {opcoes}. *(não contabilizado)*"
            )
        else:
            motivo = {
                "sem_permissao": "o bot está sem a permissão **Gerenciar Servidor**",
                "falha_api": "falha ao consultar o Discord",
                "sem_base": "o bot acabou de iniciar neste servidor",
                "sem_uso": "pode ser Descoberta, link direto ou um convite que não deu para identificar",
            }.get(res.get("motivo"), "origem não identificada")
            linhas.append(f"❓ **Origem desconhecida** — {motivo}. *(não contabilizado)*")

        if credito is not None:
            r = resumo_inviter(g, credito)
            linhas.append(
                f"📊 **{nome_de(guild, g, credito)}** convidou **{pessoas(r['total'])}** "
                f"({r['ativos']} ativos • {r['saiu']} saíram)"
            )
        try:
            await canal.send("\n".join(linhas), allowed_mentions=SEM_MENCOES)
        except discord.HTTPException:
            pass

    async def _avisar_permissao(self, guild: discord.Guild):
        agora = time.monotonic()
        if agora - self.aviso_perm.get(guild.id, -1e9) < 3600:
            return
        self.aviso_perm[guild.id] = agora
        canal = await self._canal_log(guild)
        if canal:
            try:
                await canal.send(
                    "⚠️ **Não consigo rastrear convites:** o bot precisa da permissão "
                    "**Gerenciar Servidor**. Enquanto isso, as entradas ficam como "
                    "origem desconhecida."
                )
            except discord.HTTPException:
                pass

    # ── Saída de membros ────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        dados = _carregar()
        g = _guild(dados, member.guild.id)
        rec = g["membros"].get(str(member.id))
        if rec is None:
            return
        rec["saiu_ts"] = int(time.time())
        _salvar_json(F_CONVITES, dados)

        if not LOGAR_SAIDAS:
            return
        canal = await self._canal_log(member.guild)
        if canal is None:
            return
        texto = f"📤 Saída: **{member.display_name}** ({member.mention}) • ID `{member.id}`"
        if rec.get("inviter") is not None:
            texto += f" — convidado por **{nome_de(member.guild, g, rec['inviter'])}**"
        ficou = rec["saiu_ts"] - rec.get("ultima_entrada_ts", rec["saiu_ts"])
        if ficou >= 0:
            m, s = divmod(int(ficou), 60)
            h, m = divmod(m, 60)
            d, h = divmod(h, 24)
            texto += f" • ficou {d}d {h}h {m}min"
        try:
            await canal.send(texto, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException:
            pass

    # ── Erros de comando ────────────────────────────────────────
    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=5)
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(
                f"⚠️ Uso incorreto. Veja `{ctx.clean_prefix}conviteajuda`.", delete_after=7
            )
        else:
            raise error

    # ── Comandos ────────────────────────────────────────────────
    @commands.command(name="convites")
    @apenas_staff()
    async def convites(self, ctx: commands.Context, membro: discord.User = None):
        """Quantas pessoas um membro convidou."""
        membro = membro or ctx.author
        g = ler_guild(ctx.guild.id)
        r = resumo_inviter(g, membro.id)
        nome = nome_de(ctx.guild, g, membro.id)
        pos = next((i for i, (uid, _) in enumerate(ranking(g), 1) if uid == membro.id), None)
        linhas = [
            f"📊 **{nome}** convidou **{pessoas(r['total'])}**",
            f"• Ativos no servidor: **{r['ativos']}**",
            f"• Já saíram: **{r['saiu']}**",
            f"• Contas novas (menos de {ALERTA_CONTA_NOVA_DIAS} dias na entrada): **{r['novas']}**",
        ]
        if pos:
            linhas.append(f"• Posição no ranking: **#{pos}**")
        await ctx.send("\n".join(linhas), allowed_mentions=SEM_MENCOES)

    @commands.command(name="topconvites")
    @apenas_staff()
    async def topconvites(self, ctx: commands.Context, quantidade: int = 10):
        """Ranking de quem mais convidou."""
        quantidade = max(1, min(quantidade, 30))
        g = ler_guild(ctx.guild.id)
        rank = ranking(g)
        if not rank:
            return await ctx.send("📭 Ainda não há convites registrados.")
        linhas = ["🏆 **Ranking de convites**"]
        for i, (uid, total) in enumerate(rank[:quantidade], 1):
            r = resumo_inviter(g, uid)
            linhas.append(
                f"**{i}.** {nome_de(ctx.guild, g, uid)} — **{pessoas(total)}** "
                f"({r['ativos']} ativos • {r['saiu']} saíram)"
            )
        total_ok = sum(t for _, t in rank)
        linhas.append(
            f"\nTotal identificado: **{pessoas(total_ok)}** • "
            f"Sem origem identificada: **{sem_origem(g)}**"
        )
        await enviar_em_partes(ctx, linhas)

    @commands.command(name="quemconvidou")
    @apenas_staff()
    async def quemconvidou(self, ctx: commands.Context, membro: discord.User):
        """Mostra quem convidou um membro e os dados da entrada."""
        g = ler_guild(ctx.guild.id)
        rec = g["membros"].get(str(membro.id))
        if rec is None:
            return await ctx.send(
                "📭 Não tenho registro de entrada desse usuário (ele pode ter entrado "
                "antes de o bot começar a registrar)."
            )
        idade, dias = idade_conta_txt(
            datetime.fromtimestamp(rec["conta_ts"], timezone.utc),
            datetime.fromtimestamp(rec["entrou_ts"], timezone.utc),
        )
        tipo = rec.get("tipo")
        if tipo == "convite" and rec.get("inviter") is not None:
            origem = f"**{nome_de(ctx.guild, g, rec['inviter'])}** (código `{rec['codigo']}`)"
        elif tipo == "vanity":
            origem = f"link personalizado `discord.gg/{rec.get('codigo')}`"
        elif tipo == "ambiguo":
            origem = "indeterminado (entrou junto com outras pessoas) — " + ", ".join(
                f"{c['nome'] or c['inviter']} (`{c['codigo']}`)" for c in rec.get("candidatos", [])
            )
        elif tipo == "bot":
            origem = "bot adicionado (OAuth2)"
        else:
            origem = "desconhecida"
        status = "❌ saiu" if rec.get("saiu_ts") else "✅ no servidor"
        linhas = [
            f"🔎 **{rec.get('nome', membro.name)}** • ID `{membro.id}`",
            f"• Convidado por: {origem}",
            f"• Conta criada: <t:{rec['conta_ts']}:D> ({idade} na primeira entrada)",
            f"• Primeira entrada: <t:{rec['entrou_ts']}:f>",
            f"• Entradas no total: **{rec.get('entradas', 1)}**",
            f"• Situação: {status}",
        ]
        await ctx.send("\n".join(linhas), allowed_mentions=SEM_MENCOES)

    @commands.command(name="convidados")
    @apenas_staff()
    async def convidados(self, ctx: commands.Context, membro: discord.User = None):
        """Lista as pessoas que um membro convidou (as 30 mais recentes)."""
        membro = membro or ctx.author
        g = ler_guild(ctx.guild.id)
        lista = [
            (uid, rec) for uid, rec in g["membros"].items() if rec.get("inviter") == membro.id
        ]
        if not lista:
            return await ctx.send("📭 Esse membro ainda não convidou ninguém.")
        lista.sort(key=lambda x: x[1].get("entrou_ts", 0), reverse=True)
        linhas = [
            f"📋 **{nome_de(ctx.guild, g, membro.id)}** convidou **{pessoas(len(lista))}** "
            f"(mostrando {min(30, len(lista))} mais recentes)"
        ]
        for uid, rec in lista[:30]:
            dias = (rec["entrou_ts"] - rec["conta_ts"]) // 86400
            alerta = " ⚠️" if dias < ALERTA_CONTA_NOVA_DIAS else ""
            status = "❌ saiu" if rec.get("saiu_ts") else "✅ ativo"
            linhas.append(
                f"• {rec.get('nome', uid)} — conta com **{dias}d** na entrada{alerta} "
                f"• entrou <t:{rec['entrou_ts']}:d> • {status}"
            )
        await enviar_em_partes(ctx, linhas)

    @commands.command(name="statusconvites")
    @apenas_staff()
    async def statusconvites(self, ctx: commands.Context):
        """Diagnóstico do rastreador de convites."""
        guild = ctx.guild
        g = ler_guild(guild.id)
        perm = guild.me.guild_permissions.manage_guild
        cache = self.cache.get(guild.id)
        canal = guild.get_channel(CANAL_CONVITES_ID) if CANAL_CONVITES_ID else None
        linhas = [
            "🩺 **Status do rastreador de convites**",
            f"• Permissão Gerenciar Servidor: {'✅' if perm else '❌ FALTANDO'}",
            "• Convites em cache: "
            + (f"**{len(cache)}**" if cache is not None else "❌ cache não iniciado"),
            f"• Link personalizado: {'✅ ' + guild.vanity_url_code if guild.vanity_url_code else 'não tem'}",
            "• Canal de registro: "
            + (canal.mention if canal else "⚠️ não configurado (`CANAL_CONVITES_ID`)"),
            f"• Intent Members: {'✅' if self.bot.intents.members else '❌ DESLIGADA'}",
            f"• Pessoas registradas: **{len(g['membros'])}**",
            f"• Sem origem identificada: **{sem_origem(g)}**",
        ]
        await ctx.send("\n".join(linhas), allowed_mentions=SEM_MENCOES)

    @commands.command(name="conviteajuda")
    @apenas_staff()
    async def conviteajuda(self, ctx: commands.Context):
        """Lista os comandos do rastreador de convites."""
        p = ctx.clean_prefix
        await ctx.send(
            "📖 **Comandos de convites**\n"
            f"`{p}convites [@membro]` — quantas pessoas o membro convidou\n"
            f"`{p}topconvites [quantidade]` — ranking de convites\n"
            f"`{p}quemconvidou @membro` — quem convidou e idade da conta\n"
            f"`{p}convidados [@membro]` — lista de quem o membro convidou\n"
            f"`{p}statusconvites` — diagnóstico do sistema",
            allowed_mentions=SEM_MENCOES,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ConvitesCog(bot))