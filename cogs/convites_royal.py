from __future__ import annotations



import asyncio

import json

import os
from pathlib import Path
import time
from datetime import datetime, timezone
import discord

from discord.ext import commands


CANAL_CONVITES_ID = 1569924797259980820

CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

ALERTA_CONTA_NOVA_DIAS = 3
LOGAR_SAIDAS = False
JANELA_AGRUPAR = 2.0
JANELA_DELETE = 30
NOME_SERVIDOR = "Família Royal"

COR_PRINCIPAL = 0x8B202D  
COR_SUCESSO = 0x237A53
COR_ALERTA = 0xD4AF37
COR_ERRO = 0xB54148
COR_NEUTRA = 0x5D6880
COR_REENTRADA = 0xA27B42

NOME_BANNER = "convites_royal.png"
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
SEM_MENCOES = discord.AllowedMentions.none()


def caminho_banner() -> Path | None:
    """Encontra o arquivo local mesmo se o processo iniciar fora da raiz do projeto."""
    candidatos = (
        PASTA_ASSETS / NOME_BANNER,
        Path(__file__).resolve().parent / "assets" / NOME_BANNER,
        Path.cwd() / "assets" / NOME_BANNER,
    )
    return next((arquivo for arquivo in candidatos if arquivo.is_file()), None)


async def enviar_v2(destino, view: discord.ui.LayoutView, banner: Path | None = None):
    """Um único Components V2 com banner anexado, se existir."""
    if banner is not None:
        with banner.open("rb") as arq:
            return await destino.send(
                view=view, file=discord.File(arq, filename=NOME_BANNER),
                allowed_mentions=SEM_MENCOES,
            )
    return await destino.send(view=view, allowed_mentions=SEM_MENCOES)


# Quantas pessoas aparecem nas listas.
LIMITE_CONVIDADOS = 30



PASTA_DADOS = "dados_convites"

F_CONVITES = os.path.join(PASTA_DADOS, "convites.json")  # só para a migração antiga
SEM_MENCOES = discord.AllowedMentions.none()





# ════════════════════════════════════════════════════════════════
#                    ARMAZENAMENTO (POSTGRESQL)
# ════════════════════════════════════════════════════════════════
SQL_CRIAR_TABELAS = """

CREATE TABLE IF NOT EXISTS convite_membros (

    guild_id BIGINT NOT NULL,

    user_id BIGINT NOT NULL,

    nome TEXT NOT NULL,

    inviter_id BIGINT,

    inviter_nome TEXT,

    codigo TEXT,

    tipo TEXT NOT NULL,

    candidatos JSONB NOT NULL DEFAULT '[]'::jsonb,

    conta_ts BIGINT NOT NULL,

    entrou_ts BIGINT NOT NULL,

    ultima_entrada_ts BIGINT NOT NULL,

    saiu_ts BIGINT,

    entradas INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (guild_id, user_id)

);



CREATE INDEX IF NOT EXISTS idx_convite_membros_inviter

    ON convite_membros (guild_id, inviter_id);



CREATE TABLE IF NOT EXISTS convite_nomes (

    guild_id BIGINT NOT NULL,

    user_id BIGINT NOT NULL,

    nome TEXT NOT NULL,

    PRIMARY KEY (guild_id, user_id)

);

"""



SQL_UPSERT_NOME = """

INSERT INTO convite_nomes (guild_id, user_id, nome)

VALUES ($1, $2, $3)

ON CONFLICT (guild_id, user_id) DO UPDATE SET nome = EXCLUDED.nome

"""





def _ler_json(caminho: str, padrao):

    if os.path.exists(caminho):

        try:

            with open(caminho, "r", encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError):

            pass

    return padrao





def _cands(valor) -> list:

    """JSONB pode voltar como str (asyncpg sem codec) ou como lista."""

    if isinstance(valor, str):

        try:

            valor = json.loads(valor)

        except json.JSONDecodeError:

            return []

    return valor if isinstance(valor, list) else []





def _row_para_rec(row) -> dict:

    return {

        "nome": row["nome"],

        "inviter": row["inviter_id"],

        "inviter_nome": row["inviter_nome"],

        "codigo": row["codigo"],

        "tipo": row["tipo"],

        "candidatos": _cands(row["candidatos"]),

        "conta_ts": row["conta_ts"],

        "entrou_ts": row["entrou_ts"],

        "ultima_entrada_ts": row["ultima_entrada_ts"],

        "saiu_ts": row["saiu_ts"],

        "entradas": row["entradas"],

    }





async def criar_tabelas_postgres(pool):

    """Cria as tabelas necessárias sem apagar nenhum dado existente."""

    async with pool.acquire() as conn:

        await conn.execute(SQL_CRIAR_TABELAS)





async def migrar_json_para_postgres(pool) -> int:

    """

    Migra o antigo dados_convites/convites.json (só roda se a tabela de membros

    estiver vazia, evitando duplicações).

    """

    if not os.path.exists(F_CONVITES):

        return 0



    dados = _ler_json(F_CONVITES, {"guilds": {}})

    guilds = dados.get("guilds", {}) if isinstance(dados, dict) else {}

    if not guilds:

        return 0



    async with pool.acquire() as conn:

        if await conn.fetchval("SELECT COUNT(*) FROM convite_membros"):

            return 0



        migrados = 0

        async with conn.transaction():

            for gid_str, g in guilds.items():

                try:

                    gid = int(gid_str)

                except (TypeError, ValueError):

                    continue



                for uid_str, nome in g.get("nomes", {}).items():

                    try:

                        uid = int(uid_str)

                    except (TypeError, ValueError):

                        continue

                    if nome:

                        await conn.execute(SQL_UPSERT_NOME, gid, uid, str(nome))



                for uid_str, rec in g.get("membros", {}).items():

                    try:

                        uid = int(uid_str)

                    except (TypeError, ValueError):

                        continue



                    await conn.execute(

                        """

                        INSERT INTO convite_membros (

                            guild_id, user_id, nome, inviter_id, inviter_nome,

                            codigo, tipo, candidatos, conta_ts, entrou_ts,

                            ultima_entrada_ts, saiu_ts, entradas

                        )

                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,$13)

                        ON CONFLICT (guild_id, user_id) DO NOTHING

                        """,

                        gid,

                        uid,

                        rec.get("nome") or f"ID {uid}",

                        rec.get("inviter"),

                        rec.get("inviter_nome"),

                        rec.get("codigo"),

                        rec.get("tipo") or "desconhecido",

                        json.dumps(_cands(rec.get("candidatos")), ensure_ascii=False),

                        int(rec.get("conta_ts", 0)),

                        int(rec.get("entrou_ts", 0)),

                        int(rec.get("ultima_entrada_ts", rec.get("entrou_ts", 0))),

                        rec.get("saiu_ts"),

                        int(rec.get("entradas", 1)),

                    )

                    migrados += 1



        if migrados:

            print(f"[convites] Migração JSON → PostgreSQL concluída: {migrados} registros.")

        return migrados





# ── Consultas agregadas (feitas direto no banco, sem carregar tudo) ─────────
async def db_resumo(pool, gid: int, uid: int) -> dict:

    row = await pool.fetchrow(

        """

        SELECT COUNT(*)                                          AS total,

               COUNT(*) FILTER (WHERE saiu_ts IS NULL)           AS ativos,

               COUNT(*) FILTER (WHERE saiu_ts IS NOT NULL)       AS saiu,

               COUNT(*) FILTER (WHERE (entrou_ts - conta_ts) < $3 * 86400) AS novas

        FROM convite_membros

        WHERE guild_id = $1 AND inviter_id = $2

        """,

        gid, uid, ALERTA_CONTA_NOVA_DIAS,

    )

    return {k: int(row[k] or 0) for k in ("total", "ativos", "saiu", "novas")}





async def db_ranking(pool, gid: int) -> list[dict]:

    rows = await pool.fetch(

        """

        SELECT inviter_id,

               COUNT(*)                                    AS total,

               COUNT(*) FILTER (WHERE saiu_ts IS NULL)     AS ativos,

               COUNT(*) FILTER (WHERE saiu_ts IS NOT NULL) AS saiu

        FROM convite_membros

        WHERE guild_id = $1 AND inviter_id IS NOT NULL

        GROUP BY inviter_id

        ORDER BY total DESC, inviter_id ASC

        """,

        gid,

    )

    return [

        {

            "uid": r["inviter_id"],

            "total": int(r["total"]),

            "ativos": int(r["ativos"]),

            "saiu": int(r["saiu"]),

        }

        for r in rows

    ]





async def db_sem_origem(pool, gid: int) -> int:

    return int(

        await pool.fetchval(

            """

            SELECT COUNT(*) FROM convite_membros

            WHERE guild_id = $1 AND inviter_id IS NULL

              AND tipo IN ('ambiguo', 'desconhecido')

            """,

            gid,

        )

        or 0

    )





async def db_totais(pool, gid: int) -> dict:

    row = await pool.fetchrow(

        """

        SELECT COUNT(*)                                    AS registrados,

               COUNT(*) FILTER (WHERE saiu_ts IS NULL)     AS ativos,

               COUNT(*) FILTER (WHERE tipo = 'vanity')     AS vanity

        FROM convite_membros WHERE guild_id = $1

        """,

        gid,

    )

    return {k: int(row[k] or 0) for k in ("registrados", "ativos", "vanity")}





async def db_nomes(pool, gid: int, ids: list[int]) -> dict[int, str]:

    if not ids:

        return {}

    rows = await pool.fetch(

        "SELECT user_id, nome FROM convite_nomes WHERE guild_id=$1 AND user_id = ANY($2::bigint[])",

        gid, list(set(ids)),

    )

    return {r["user_id"]: r["nome"] for r in rows}





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





def duracao_txt(segundos: int) -> str:

    m, _ = divmod(max(0, int(segundos)), 60)

    h, m = divmod(m, 60)

    d, h = divmod(h, 24)

    partes = []

    if d:

        partes.append(f"{d}d")

    if h:

        partes.append(f"{h}h")

    partes.append(f"{m}min")

    return " ".join(partes)





def pct(parte: int, total: int) -> str:

    return f"{round(parte * 100 / total)}%" if total else "—"





def embed_base(

    titulo: str,

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

    footer_kwargs = {"text": f"{NOME_SERVIDOR} • Natal 2026"}

    e.set_footer(**footer_kwargs)

    # Embeds secundários permanecem sem fotos; o banner é reservado aos painéis V2.
    return e





MEDALHAS = {1: "🥇", 2: "🥈", 3: "🥉"}





# ════════════════════════════════════════════════════════════════
#                       PAINEL (BOTÕES PERSISTENTES)
# ════════════════════════════════════════════════════════════════
def montar_registro_v2(titulo: str, cor: int, partes: list[str], *, com_banner: bool):
    """Um registro de entrada/saída; sem thumbnail/foto do membro."""
    view = discord.ui.LayoutView(timeout=None)
    painel = discord.ui.Container(accent_colour=discord.Colour(cor))
    if com_banner:
        painel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                media=f"attachment://{NOME_BANNER}",
                description="Banner oficial de convites da Família Royal",
            )
        ))
    painel.add_item(discord.ui.TextDisplay(
        f"## {titulo}\n -# FAMÍLIA ROYAL • NATAL 2026"
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    for parte in partes:
        painel.add_item(discord.ui.TextDisplay(parte))
    view.add_item(painel)
    return view



class PainelConvitesView(discord.ui.LayoutView):
    """Central Components V2 com botões persistentes e IDs preservados."""

    def __init__(self, cog: "ConvitesCog", *, com_banner: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        bloco = discord.ui.Container(accent_colour=discord.Colour(COR_PRINCIPAL))
        if com_banner:
            bloco.add_item(discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    media=f"attachment://{NOME_BANNER}",
                    description="Banner da Central de Convites Royal",
                )
            ))
        else:
            bloco.add_item(discord.ui.TextDisplay(
                "-# 🖼️ Banner reservado: `assets/convites_royal.png`"
            ))

        bloco.add_item(discord.ui.TextDisplay(
            "## 👑 CENTRAL DE CONVITES  •  FAMÍLIA ROYAL\n"
            "╭┈ ✦ **Convites, crescimento e reconhecimento**\n"
            "╰┈ Acompanhe quem fortalece o reino trazendo novos integrantes."
        ))
        bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        bloco.add_item(discord.ui.TextDisplay(
            "**✉️  PAINEL DE CONTROLE**\n"
            "╭ 📊 **Meus convites** — histórico e retenção\n"
            "├ 🏆 **Ranking** — destaques dos recrutadores\n"
            "├ 🩺 **Status** — integridade do rastreamento\n"
            "╰ 📖 **Ajuda** — comandos disponíveis"
        ))
        bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        bloco.add_item(discord.ui.TextDisplay(
            "-# ⚜️ Reentradas não concedem um segundo crédito. Entradas sem origem confiável não são atribuídas."
        ))

        acoes = discord.ui.ActionRow()
        for label, emoji, estilo, custom_id, callback in (
            ("Meus convites", "📊", discord.ButtonStyle.primary, "convites:meus", self.btn_meus),
            ("Ranking", "🏆", discord.ButtonStyle.success, "convites:ranking", self.btn_ranking),
            ("Status", "🩺", discord.ButtonStyle.secondary, "convites:status", self.btn_status),
            ("Ajuda", "📖", discord.ButtonStyle.secondary, "convites:ajuda", self.btn_ajuda),
        ):
            botao = discord.ui.Button(label=label, emoji=emoji, style=estilo, custom_id=custom_id)
            botao.callback = callback
            acoes.add_item(botao)
        bloco.add_item(acoes)
        self.add_item(bloco)

    async def _somente_staff(self, interaction: discord.Interaction) -> bool:
        if eh_staff(interaction.user):
            return True
        await interaction.response.send_message(
            "⛔ Este painel é reservado à administração da Família Royal.", ephemeral=True
        )
        return False

    async def btn_meus(self, interaction: discord.Interaction):
        if not await self._somente_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.cog.embed_resumo(interaction.guild, interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def btn_ranking(self, interaction: discord.Interaction):
        if not await self._somente_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.cog.embed_ranking(interaction.guild, 10)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def btn_status(self, interaction: discord.Interaction):
        if not await self._somente_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.cog.embed_status(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def btn_ajuda(self, interaction: discord.Interaction):
        if not await self._somente_staff(interaction):
            return
        prefixo = self.cog.bot.command_prefix
        prefixo = prefixo if isinstance(prefixo, str) else "!"
        await interaction.response.send_message(
            embed=self.cog.embed_ajuda(prefixo), ephemeral=True
        )


# ════════════════════════════════════════════════════════════════
#                                COG
# ════════════════════════════════════════════════════════════════
class ConvitesCog(commands.Cog, name="Convites"):

    def __init__(self, bot: commands.Bot):

        self.bot = bot

        self.cache: dict[int, dict] = {}

        self.locks: dict[int, asyncio.Lock] = {}

        self.fila: dict[int, list[discord.Member]] = {}

        self.processando: set[int] = set()

        self.deletados: dict[tuple[int, str], float] = {}

        self.aviso_perm: dict[int, float] = {}

        self.tarefas: set[asyncio.Task] = set()



    @property

    def pool(self):

        return getattr(self.bot, "pool", None)



    def _lock(self, gid: int) -> asyncio.Lock:

        return self.locks.setdefault(gid, asyncio.Lock())



    def _criar_tarefa(self, coro):

        t = asyncio.create_task(coro)

        self.tarefas.add(t)

        t.add_done_callback(self.tarefas.discard)



    async def cog_load(self):

        self.bot.add_view(PainelConvitesView(self))

        self._criar_tarefa(self._iniciar())



    async def cog_unload(self):

        for t in list(self.tarefas):

            t.cancel()



    async def _iniciar(self):

        await self.bot.wait_until_ready()



        if self.pool is None:

            print(

                "[convites] ERRO: bot.pool não existe. Configure o pool PostgreSQL "

                "no main.py antes de carregar este Cog."

            )

            return



        try:

            await criar_tabelas_postgres(self.pool)

            await migrar_json_para_postgres(self.pool)

        except Exception as e:  # noqa: BLE001
            print(f"[convites] ERRO ao preparar PostgreSQL: {type(e).__name__}: {e}")

            return



        for guild in self.bot.guilds:

            await self._iniciar_guild(guild)



    # ── Cache de convites ───────────────────────────────────────
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



            extra = self.fila.get(gid)

            if extra:

                lote.extend(extra)

                self.fila[gid] = []



            humanos = [m for m in lote if not m.bot]

            bots = [m for m in lote if m.bot]

            resultados: dict[int, dict] = {b.id: {"tipo": "bot"} for b in bots}



            if humanos:

                if depois is None:

                    for m in humanos:

                        resultados[m.id] = {"tipo": "desconhecido", "motivo": erro}

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

                try:

                    rec, reentrada = await self._registrar_entrada(guild, membro, res)

                except Exception as e:  # noqa: BLE001
                    print(f"[convites] erro ao salvar {membro.id}: {type(e).__name__}: {e}")

                    continue

                await self._enviar_log_entrada(guild, membro, res, rec, reentrada)



            if erro == "sem_permissao":

                await self._avisar_permissao(guild)



    async def _registrar_entrada(self, guild: discord.Guild, membro: discord.Member, res: dict):

        """Salva/atualiza a entrada no PostgreSQL. Retorna (registro, foi_reentrada)."""

        if self.pool is None:

            raise RuntimeError("bot.pool não está configurado")



        agora = int(time.time())

        conta_ts = int(membro.created_at.timestamp())



        async with self.pool.acquire() as conn:

            async with conn.transaction():

                await conn.execute(SQL_UPSERT_NOME, guild.id, membro.id, membro.display_name)



                if res.get("inviter") is not None and res.get("inviter_nome"):

                    await conn.execute(SQL_UPSERT_NOME, guild.id, res["inviter"], res["inviter_nome"])



                for c in res.get("candidatos", []):

                    if c.get("inviter") is not None and c.get("nome"):

                        await conn.execute(SQL_UPSERT_NOME, guild.id, c["inviter"], c["nome"])



                row = await conn.fetchrow(

                    "SELECT * FROM convite_membros WHERE guild_id=$1 AND user_id=$2 FOR UPDATE",

                    guild.id, membro.id,

                )

                reentrada = row is not None



                if row is None:

                    eh_convite = res["tipo"] == "convite"

                    novo = await conn.fetchrow(

                        """

                        INSERT INTO convite_membros (

                            guild_id, user_id, nome, inviter_id, inviter_nome,

                            codigo, tipo, candidatos, conta_ts, entrou_ts,

                            ultima_entrada_ts, saiu_ts, entradas

                        )

                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$10,NULL,1)

                        RETURNING *

                        """,

                        guild.id,

                        membro.id,

                        membro.display_name,

                        res.get("inviter") if eh_convite else None,

                        res.get("inviter_nome") if eh_convite else None,

                        res.get("codigo"),

                        res["tipo"],

                        json.dumps(res.get("candidatos", []), ensure_ascii=False),

                        conta_ts,

                        agora,

                    )

                    return _row_para_rec(novo), False



                # Reentrada: o crédito fica com o primeiro convite identificado.
                inviter_id = row["inviter_id"]

                inviter_nome = row["inviter_nome"]

                codigo = row["codigo"]

                tipo = row["tipo"]

                candidatos = _cands(row["candidatos"])



                if inviter_id is None and res["tipo"] == "convite":

                    inviter_id = res.get("inviter")

                    inviter_nome = res.get("inviter_nome")

                    codigo = res.get("codigo")

                    tipo = "convite"

                    candidatos = []

                elif tipo in ("ambiguo", "desconhecido") and res["tipo"] == "vanity":

                    tipo = "vanity"

                    codigo = res.get("codigo")

                    candidatos = []



                atualizado = await conn.fetchrow(

                    """

                    UPDATE convite_membros

                    SET nome=$3, entradas=entradas+1, ultima_entrada_ts=$4, saiu_ts=NULL,

                        inviter_id=$5, inviter_nome=$6, codigo=$7, tipo=$8, candidatos=$9::jsonb

                    WHERE guild_id=$1 AND user_id=$2

                    RETURNING *

                    """,

                    guild.id,

                    membro.id,

                    membro.display_name,

                    agora,

                    inviter_id,

                    inviter_nome,

                    codigo,

                    tipo,

                    json.dumps(candidatos, ensure_ascii=False),

                )

                return _row_para_rec(atualizado), True



    # ── Nomes ───────────────────────────────────────────────────
    async def _nomes(self, guild: discord.Guild, ids: list[int]) -> dict[int, str]:

        """display_name atual se o membro estiver no servidor; senão o último nome salvo."""

        ids = [i for i in dict.fromkeys(ids) if i is not None]

        nomes: dict[int, str] = {}

        faltando = []

        for uid in ids:

            m = guild.get_member(uid)

            if m:

                nomes[uid] = m.display_name

            else:

                faltando.append(uid)

        if faltando and self.pool is not None:

            salvos = await db_nomes(self.pool, guild.id, faltando)

            for uid in faltando:

                nomes[uid] = salvos.get(uid) or f"ID {uid}"

        return nomes



    # ── Mensagens (embeds) ──────────────────────────────────────
    async def _canal_log(self, guild: discord.Guild):

        return guild.get_channel(CANAL_CONVITES_ID) if CANAL_CONVITES_ID else None



    async def _enviar_log_entrada(self, guild, membro, res, rec, reentrada):
        """Log V2 seguro: sem imagem de perfil; registro fiel à origem detectada."""
        canal = await self._canal_log(guild)
        if canal is None:
            return
        idade, dias = idade_conta_txt(membro.created_at)
        conta_nova = dias < ALERTA_CONTA_NOVA_DIAS
        tipo = res.get("tipo", "desconhecido")
        credito = rec.get("inviter")  # conservado na reentrada

        if tipo == "bot":
            cor, titulo = COR_NEUTRA, "🤖  BOT ADICIONADO"
        elif reentrada:
            cor, titulo = COR_REENTRADA, "🔁  RETORNO AO REINO"
        elif conta_nova:
            cor, titulo = COR_ALERTA, "⚠️  NOVO INTEGRANTE • CONTA RECENTE"
        elif tipo in ("ambiguo", "desconhecido"):
            cor, titulo = COR_NEUTRA, "❔  NOVO INTEGRANTE • ORIGEM INCERTA"
        else:
            cor, titulo = COR_SUCESSO, "✦  NOVO INTEGRANTE DA ROYAL"

        ids_nomes = [uid for uid in (credito, res.get("inviter")) if uid is not None]
        nomes = await self._nomes(guild, ids_nomes)
        partes = [
            "`👮🏼` **IDENTIFICAÇÃO**\n"
            f"> Membro: {membro.mention}\n"
            f"> ID do usuário: `{membro.id}`",
            "`⏳` **CONTA DO DISCORD**\n"
            f"> Idade da conta: **{idade}**" + (" ⚠️" if conta_nova else "") + "\n"
            f"> Criada em: <t:{int(membro.created_at.timestamp())}:D>",
        ]
        if tipo == "bot":
            origem = "> Integração adicionada como bot; **não gera convite**."
        elif tipo == "convite":
            convidador = res.get("inviter")
            codigo = discord.utils.escape_markdown(str(res.get("codigo") or "indefinido"))
            recrutador = f"<@{convidador}>" if convidador else "Não identificado"
            origem = (
                f"> Recrutador(a): {recrutador}\n"
                f"> Código utilizado: `{codigo}`"
            )
        elif tipo == "vanity":
            codigo = discord.utils.escape_markdown(str(res.get("codigo") or "indefinido"))
            origem = f"> Link personalizado: `discord.gg/{codigo}`"
        elif tipo == "ambiguo":
            candidatos = list(res.get("candidatos", []))
            candidatos_txt = "\n".join(
                "> Possibilidade: "
                + discord.utils.escape_markdown(str(item.get("nome") or item.get("inviter") or "Desconhecido"))
                + f" (`{discord.utils.escape_markdown(str(item.get('codigo') or '?'))}`)"
                for item in candidatos[:5]
            )
            resto = f"\n> Outras possibilidades: {len(candidatos) - 5}" if len(candidatos) > 5 else ""
            origem = (
                "> Entradas simultâneas; não é seguro escolher um recrutador.\n"
                + (candidatos_txt or "> Sem candidatos confiáveis") + resto
                + "\n-# ❕ Sem crédito atribuído."
            )
        else:
            causas = {
                "sem_permissao": "O bot não possui permissão para consultar convites.",
                "falha_api": "A API do Discord não respondeu adequadamente.",
                "sem_base": "O rastreador ainda não tinha uma base de convites.",
                "sem_uso": "Nenhum convite rastreável foi alterado (ou veio por Descoberta).",
            }
            origem = "> " + causas.get(res.get("motivo"), "Não foi possível identificar a origem.") + "\n-# ❕ Sem crédito atribuído."

        partes.append("`💌` **ORIGEM**\n" + origem)
        if reentrada:
            if credito is not None:
                dono_credito = f"<@{credito}>"
                nota = f"> O crédito permanece com {dono_credito} (primeira entrada)."
            else:
                nota = "> A reentrada **não gera um novo convite**."
            partes.append("`♻️` **HISTÓRICO DE ENTRADA**\n" + nota)
        if credito is not None and self.pool is not None:
            resumo = await db_resumo(self.pool, guild.id, credito)
            partes.append(
                "`🏆` **DESEMPENHO DO RECRUTADOR**\n"
                f"> Convites registrados: **{resumo['total']}**\n"
                f"> Ativos: **{resumo['ativos']}** · Saíram: **{resumo['saiu']}**"
            )

        banner = caminho_banner()
        try:
            await enviar_v2(
                canal,
                montar_registro_v2(titulo, cor, partes, com_banner=banner is not None),
                banner,
            )
        except (discord.HTTPException, OSError) as exc:
            print(f"[convites] Falha ao enviar registro V2: {exc}")

    async def _avisar_permissao(self, guild: discord.Guild):

        agora = time.monotonic()

        if agora - self.aviso_perm.get(guild.id, -1e9) < 3600:

            return

        self.aviso_perm[guild.id] = agora

        canal = await self._canal_log(guild)

        if canal:

            embed = embed_base(

                "⚠️ Não consigo rastrear convites",

                "O bot precisa da permissão **Gerenciar Servidor**.\n"

                "Enquanto isso, as entradas ficam como **origem desconhecida**.",

                cor=COR_ERRO,

            )

            try:

                await canal.send(embed=embed)

            except discord.HTTPException:

                pass



    # ── Saída de membros ────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if self.pool is None:
            return
        saiu_ts = int(time.time())
        row = await self.pool.fetchrow(
            """UPDATE convite_membros SET saiu_ts=$3
               WHERE guild_id=$1 AND user_id=$2 RETURNING *""",
            member.guild.id, member.id, saiu_ts,
        )
        if row is None or not LOGAR_SAIDAS:
            return
        canal = await self._canal_log(member.guild)
        if canal is None:
            return
        rec = _row_para_rec(row)
        duracao = duracao_txt(saiu_ts - rec.get("ultima_entrada_ts", saiu_ts))
        partes = [
            f"**👤  INTEGRANTE**\n╰┈ {member.mention} (`{member.id}`)",
            f"**⏳  PERMANÊNCIA**\n╰┈ **{duracao}**",
        ]
        if rec.get("inviter") is not None:
            nomes = await self._nomes(member.guild, [rec["inviter"]])
            responsavel = discord.utils.escape_markdown(nomes.get(rec["inviter"], "Não identificado"))
            partes.append(f"**🔗  RECRUTADOR ORIGINAL**\n╰┈ {responsavel}")
        banner = caminho_banner()
        try:
            await enviar_v2(
                canal,
                montar_registro_v2("🚪  SAÍDA DO REINO", COR_ERRO, partes, com_banner=banner is not None),
                banner,
            )
        except (discord.HTTPException, OSError) as exc:
            print(f"[convites] Falha ao registrar saída: {exc}")

    # ── Construtores de embeds (usados por comandos e botões) ───
    async def embed_resumo(self, guild: discord.Guild, usuario: discord.abc.User) -> discord.Embed:

        r = await db_resumo(self.pool, guild.id, usuario.id)

        rank = await db_ranking(self.pool, guild.id)

        pos = next((i for i, x in enumerate(rank, 1) if x["uid"] == usuario.id), None)

        nomes = await self._nomes(guild, [usuario.id])

        nome = nomes.get(usuario.id, usuario.name)



        embed = embed_base(

            "📊  ✦ MEUS CONVITES · ROYAL",

            f"**{nome}** convidou **{pessoas(r['total'])}**.",

            banner=True,

        )

        

        embed.add_field(name="✅ Ativos", value=f"**{r['ativos']}**", inline=True)

        embed.add_field(name="🚪 Já saíram", value=f"**{r['saiu']}**", inline=True)

        embed.add_field(

            name="⚠️ Contas novas",

            value=f"**{r['novas']}**\n*(menos de {ALERTA_CONTA_NOVA_DIAS} dias)*",

            inline=True,

        )

        embed.add_field(name="📈 Retenção", value=f"**{pct(r['ativos'], r['total'])}**", inline=True)

        embed.add_field(

            name="🏆 Ranking",

            value=f"**#{pos}** de {len(rank)}" if pos else "Sem posição ainda",

            inline=True,

        )

        return embed



    async def embed_ranking(self, guild: discord.Guild, quantidade: int = 10) -> discord.Embed:

        quantidade = max(1, min(quantidade, 30))

        rank = await db_ranking(self.pool, guild.id)

        embed = embed_base("🏆  ✦ RANKING REAL DE CONVITES", banner=True)

        if not rank:

            embed.description = "📭 Ainda não há convites registrados."

            return embed



        nomes = await self._nomes(guild, [x["uid"] for x in rank[:quantidade]])

        linhas = []

        for i, x in enumerate(rank[:quantidade], 1):

            marca = MEDALHAS.get(i, f"`#{i}`")

            linhas.append(

                f"{marca} **{nomes.get(x['uid'])}** — **{pessoas(x['total'])}**\n"

                f"╰ ✅ {x['ativos']} ativos • 🚪 {x['saiu']} saíram"

            )

        embed.description = "\n".join(linhas)



        total_ok = sum(x["total"] for x in rank)

        sem = await db_sem_origem(self.pool, guild.id)

        embed.add_field(name="✅ Identificados", value=f"**{total_ok}**", inline=True)

        embed.add_field(name="❓ Sem origem", value=f"**{sem}**", inline=True)

        return embed



    async def embed_status(self, guild: discord.Guild) -> discord.Embed:

        perm = guild.me.guild_permissions.manage_guild

        cache = self.cache.get(guild.id)

        canal = guild.get_channel(CANAL_CONVITES_ID) if CANAL_CONVITES_ID else None

        totais = await db_totais(self.pool, guild.id)

        sem = await db_sem_origem(self.pool, guild.id)



        saudavel = bool(perm and cache is not None and self.bot.intents.members)

        embed = embed_base(

            "🩺  ✦ STATUS DOS CONVITES",

            "Tudo funcionando." if saudavel else "⚠️ Há algo para ajustar abaixo.",

            cor=COR_SUCESSO if saudavel else COR_ALERTA,

        )

        embed.add_field(

            name="Permissões e intents",

            value=(

                f"Gerenciar Servidor: {'✅' if perm else '❌ FALTANDO'}\n"

                f"Intent Members: {'✅' if self.bot.intents.members else '❌ DESLIGADA'}"

            ),

            inline=True,

        )

        embed.add_field(

            name="Rastreamento",

            value=(

                "Convites em cache: "

                + (f"**{len(cache)}**" if cache is not None else "❌ não iniciado")

                + "\nLink personalizado: "

                + (f"✅ `{guild.vanity_url_code}`" if guild.vanity_url_code else "não tem")

            ),

            inline=True,

        )

        embed.add_field(

            name="Canal de registro",

            value=canal.mention if canal else "⚠️ não configurado (`CANAL_CONVITES_ID`)",

            inline=False,

        )

        embed.add_field(

            name="Banco de dados (PostgreSQL)",

            value=(

                f"Pool: {'✅' if self.pool is not None else '❌'}\n"

                f"Pessoas registradas: **{totais['registrados']}** "

                f"({totais['ativos']} ativas)\n"

                f"Sem origem identificada: **{sem}**"

            ),

            inline=False,

        )

        banner_path = caminho_banner()
        embed.add_field(
            name="🖼️ Banner local",
            value=f"{'✅ `assets/' + NOME_BANNER + '`' if banner_path else '⏳ Aguardando `assets/' + NOME_BANNER + '`'}",
            inline=False,
        )
        return embed



    def embed_ajuda(self, p: str) -> discord.Embed:

        embed = embed_base(

            "📖  ✦ CENTRAL DE AJUDA · CONVITES",

            "Todos os comandos são exclusivos da staff.",

            banner=True,

        )

        embed.add_field(

            name="Consultas",

            value=(

                f"`{p}convites [@membro]` — quantas pessoas o membro convidou\n"

                f"`{p}topconvites [quantidade]` — ranking de convites\n"

                f"`{p}quemconvidou @membro` — quem convidou e idade da conta\n"

                f"`{p}convidados [@membro]` — lista de quem o membro convidou"

            ),

            inline=False,

        )

        embed.add_field(

            name="Administração",

            value=(

                f"`{p}painelconvites` — publica o painel V2 neste canal\n"

                f"`{p}atualizarpainelconvites` — atualiza ao responder ao painel\n"

                f"`{p}previaconvites` — prévia do painel\n"

                f"`{p}testarconvites` — simula um registro sem salvar dados\n"

                f"`{p}statusconvites` — diagnóstico do sistema"

            ),

            inline=False,

        )

        return embed



    def embed_painel(self) -> discord.Embed:
        """Compatibilidade com chamadas antigas; o painel publicado é Components V2."""
        return embed_base(
            "👑  CENTRAL DE CONVITES • FAMÍLIA ROYAL",
            "✦ Acompanhe convites, ranking e situação do rastreamento pelo painel V2.",
        )

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
    @commands.command(name="painelconvites")
    @commands.guild_only()
    @apenas_staff()
    async def painelconvites(self, ctx: commands.Context):
        """Publica o painel de convites V2 com banner opcional neste canal."""
        banner = caminho_banner()
        try:
            await enviar_v2(ctx.channel, PainelConvitesView(self, com_banner=banner is not None), banner)
        except (discord.HTTPException, OSError) as exc:
            return await ctx.reply(f"❌ Não foi possível publicar o painel: {exc}", mention_author=False)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="atualizarpainelconvites", aliases=["atualizarconvites"])
    @commands.guild_only()
    @apenas_staff()
    async def atualizarpainelconvites(self, ctx: commands.Context):
        """Edita o painel ao responder sua mensagem, sem duplicá-lo."""
        referencia = ctx.message.reference
        if referencia is None or referencia.message_id is None:
            return await ctx.reply(
                "❌ Responda à mensagem do painel com `!atualizarpainelconvites`.", mention_author=False
            )
        try:
            mensagem = await ctx.channel.fetch_message(referencia.message_id)
            if self.bot.user is None or mensagem.author.id != self.bot.user.id:
                raise ValueError("A mensagem não foi publicada por este bot.")
            if not getattr(mensagem.flags, "components_v2", False):
                raise ValueError("A mensagem ainda não é um painel Components V2. Publique com `!painelconvites`.")
            anterior = discord.ui.LayoutView.from_message(mensagem, timeout=None)
            textos = [item.content for item in anterior.walk_children()
                      if isinstance(item, discord.ui.TextDisplay)]
            if not any("CENTRAL DE CONVITES" in txt for txt in textos):
                raise ValueError("Esta mensagem não é o painel de convites da Royal.")
            banner = caminho_banner()
            view = PainelConvitesView(self, com_banner=banner is not None)
            if banner is None:
                atualizada = await mensagem.edit(
                    view=view, attachments=[], allowed_mentions=SEM_MENCOES,
                )
            else:
                with banner.open("rb") as arq:
                    atualizada = await mensagem.edit(
                        view=view, attachments=[discord.File(arq, filename=NOME_BANNER)],
                        allowed_mentions=SEM_MENCOES,
                    )
        except (discord.HTTPException, OSError, ValueError) as exc:
            return await ctx.reply(f"❌ Falha ao atualizar painel: {exc}", mention_author=False)
        await ctx.reply(f"✅ Central de convites atualizada: {atualizada.jump_url}", mention_author=False)

    @commands.command(name="previaconvites")
    @commands.guild_only()
    @apenas_staff()
    async def previaconvites(self, ctx: commands.Context):
        """Mostra uma prévia V2 no canal atual, sem alterar dados."""
        banner = caminho_banner()
        try:
            await enviar_v2(ctx.channel, PainelConvitesView(self, com_banner=banner is not None), banner)
        except (discord.HTTPException, OSError) as exc:
            await ctx.reply(f"❌ Falha na prévia: {exc}", mention_author=False)

    @commands.command(name="testarconvites", aliases=["testarregistroconvites"])
    @commands.guild_only()
    @apenas_staff()
    async def testarconvites(self, ctx: commands.Context):
        """Prévia do registro V2 sem adicionar nenhum dado ao PostgreSQL."""
        autor = ctx.author
        idade, _ = idade_conta_txt(autor.created_at)
        partes = [
            "`👮🏼` **IDENTIFICAÇÃO**\n"
            f"> Membro: {autor.mention}\n"
            f"> ID do usuário: `{autor.id}`",
            "`⏳` **CONTA DO DISCORD**\n"
            f"> Idade da conta: **{idade}**\n"
            f"> Criada em: <t:{int(autor.created_at.timestamp())}:D>",
            "`💌` **ORIGEM**\n"
            "> Recrutador(a): **Simulação da Família Royal**\n"
            "> Código utilizado: `EXEMPLO`",
            "-# 🧪 ESTA É UMA SIMULAÇÃO. Nenhum convite foi registrado nem contabilizado.",
        ]
        banner = caminho_banner()
        try:
            await enviar_v2(
                ctx.channel,
                montar_registro_v2(
                    "🧪  PRÉVIA DO REGISTRO DE CONVITES", COR_SUCESSO, partes,
                    com_banner=banner is not None,
                ),
                banner,
            )
        except (discord.HTTPException, OSError) as exc:
            await ctx.reply(f"❌ Falha ao exibir teste de convites: {exc}", mention_author=False)

    @commands.command(name="convites")

    @apenas_staff()

    async def convites(self, ctx: commands.Context, membro: discord.User = None):

        """Quantas pessoas um membro convidou."""

        membro = membro or ctx.author

        embed = await self.embed_resumo(ctx.guild, membro)

        await ctx.send(embed=embed, allowed_mentions=SEM_MENCOES)



    @commands.command(name="topconvites")

    @apenas_staff()

    async def topconvites(self, ctx: commands.Context, quantidade: int = 10):

        """Ranking de quem mais convidou."""

        embed = await self.embed_ranking(ctx.guild, quantidade)

        await ctx.send(embed=embed, allowed_mentions=SEM_MENCOES)



    @commands.command(name="quemconvidou")

    @apenas_staff()

    async def quemconvidou(self, ctx: commands.Context, membro: discord.User):

        """Mostra quem convidou um membro e os dados da entrada."""

        row = await self.pool.fetchrow(

            "SELECT * FROM convite_membros WHERE guild_id=$1 AND user_id=$2",

            ctx.guild.id, membro.id,

        )

        if row is None:

            return await ctx.send(

                embed=embed_base(

                    "📭 Sem registro",

                    "Não tenho registro de entrada desse usuário (ele pode ter entrado "

                    "antes de o bot começar a registrar).",

                    cor=COR_NEUTRA,

                )

            )



        rec = _row_para_rec(row)

        idade, dias = idade_conta_txt(

            datetime.fromtimestamp(rec["conta_ts"], timezone.utc),

            datetime.fromtimestamp(rec["entrou_ts"], timezone.utc),

        )

        tipo = rec.get("tipo")

        nomes = await self._nomes(ctx.guild, [rec["inviter"]] if rec.get("inviter") else [])



        if tipo == "convite" and rec.get("inviter") is not None:

            origem = f"**{nomes.get(rec['inviter'])}**\nCódigo `{rec['codigo']}`"

        elif tipo == "vanity":

            origem = f"Link personalizado\n`discord.gg/{rec.get('codigo')}`"

        elif tipo == "ambiguo":

            origem = "Indeterminado (entrou junto com outras pessoas):\n" + "\n".join(

                f"• {c['nome'] or c['inviter']} (`{c['codigo']}`)" for c in rec.get("candidatos", [])

            )

        elif tipo == "bot":

            origem = "Bot adicionado (OAuth2)"

        else:

            origem = "Desconhecida"



        presente = not rec.get("saiu_ts")

        conta_nova = dias < ALERTA_CONTA_NOVA_DIAS

        embed = embed_base(

            "🔎  ✦ HISTÓRICO DE ENTRADA",

            f"**{rec.get('nome', membro.name)}** • ID `{membro.id}`",

            cor=COR_ALERTA if conta_nova else COR_PRINCIPAL,

        )

        

        embed.add_field(name="🔗 Convidado por", value=origem, inline=False)

        embed.add_field(

            name="🕒 Conta criada",

            value=f"<t:{rec['conta_ts']}:D>\n{idade} na 1ª entrada" + (" ⚠️" if conta_nova else ""),

            inline=True,

        )

        embed.add_field(name="📥 Primeira entrada", value=f"<t:{rec['entrou_ts']}:f>", inline=True)

        embed.add_field(name="🔁 Entradas", value=f"**{rec.get('entradas', 1)}**", inline=True)

        embed.add_field(

            name="📍 Situação",

            value="✅ No servidor" if presente else f"❌ Saiu <t:{rec['saiu_ts']}:R>",

            inline=True,

        )

        await ctx.send(embed=embed, allowed_mentions=SEM_MENCOES)



    @commands.command(name="convidados")

    @apenas_staff()

    async def convidados(self, ctx: commands.Context, membro: discord.User = None):

        """Lista as pessoas que um membro convidou (as mais recentes)."""

        membro = membro or ctx.author

        rows = await self.pool.fetch(

            """

            SELECT user_id, nome, conta_ts, entrou_ts, saiu_ts

            FROM convite_membros

            WHERE guild_id=$1 AND inviter_id=$2

            ORDER BY entrou_ts DESC

            """,

            ctx.guild.id, membro.id,

        )

        if not rows:

            return await ctx.send(

                embed=embed_base(

                    "📭 Nenhum convidado",

                    "Esse membro ainda não convidou ninguém.",

                    cor=COR_NEUTRA,

                )

            )



        nomes = await self._nomes(ctx.guild, [membro.id])

        linhas = []

        for r in rows[:LIMITE_CONVIDADOS]:

            dias = (r["entrou_ts"] - r["conta_ts"]) // 86400

            alerta = " ⚠️" if dias < ALERTA_CONTA_NOVA_DIAS else ""

            status = "❌" if r["saiu_ts"] else "✅"

            linhas.append(

                f"{status} **{r['nome']}** — conta com **{dias}d**{alerta} • "

                f"entrou <t:{r['entrou_ts']}:d>"

            )



        embed = embed_base(

            f"📋  CONVIDADOS DE {nomes.get(membro.id, membro.name)}",

            "\n".join(linhas),

        )

        

        embed.add_field(

            name="Total",

            value=f"**{pessoas(len(rows))}** (mostrando {min(LIMITE_CONVIDADOS, len(rows))} mais recentes)",

            inline=False,

        )

        await ctx.send(embed=embed, allowed_mentions=SEM_MENCOES)



    @commands.command(name="statusconvites")

    @apenas_staff()

    async def statusconvites(self, ctx: commands.Context):

        """Diagnóstico do rastreador de convites."""

        await ctx.send(embed=await self.embed_status(ctx.guild))



    @commands.command(name="conviteajuda")

    @apenas_staff()

    async def conviteajuda(self, ctx: commands.Context):

        """Lista os comandos do rastreador de convites."""

        await ctx.send(embed=self.embed_ajuda(ctx.clean_prefix))





async def setup(bot: commands.Bot):

    await bot.add_cog(ConvitesCog(bot))