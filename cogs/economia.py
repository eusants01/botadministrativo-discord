from __future__ import annotations

from datetime import date
import discord
from discord.ext import commands
from utils import cassino_db

MOEDA = "SC"
NOME_MOEDA = "Sant's Coins"
RECOMPENSA_DIARIA = 950
LIMITE_TRANSFERENCIA_DIARIA = 5000

def fmt(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".") + f" {MOEDA}"

class Economia(commands.Cog):
    """Carteira, recompensa diária, transferências e extrato."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("bot.pool não existe; configure DATABASE_URL no Railway.")
        cassino_db.configurar_pool(pool)
        await cassino_db.inicializar_tabelas(pool)

    @commands.command(name="saldo", aliases=["carteira", "coins"])
    async def saldo(self, ctx: commands.Context, membro: discord.Member = None):
        alvo = membro or ctx.author
        if alvo.id != ctx.author.id and not ctx.author.guild_permissions.manage_guild:
            return await ctx.reply("❌ Você só pode consultar seu próprio saldo.", mention_author=False)
        saldo = await cassino_db.obter_saldo(alvo.id)
        embed = discord.Embed(
            title="🪙 Carteira Sant's Coins",
            description=f"**Titular:** {alvo.mention}\n**Saldo:** {fmt(saldo)}",
            color=0xD9A441
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="diario", aliases=["daily", "coletar"])
    async def diario(self, ctx: commands.Context):
        pool = cassino_db.obter_pool()
        uid = ctx.author.id
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Impede duas coletas simultâneas no mesmo dia pelo mesmo membro.
                await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", uid)
                await cassino_db.garantir_carteira(uid, conn)
                row = await conn.fetchrow(
                    "SELECT ultima_coleta FROM sants_diarios WHERE user_id=$1 FOR UPDATE", uid
                )
                hoje = await conn.fetchval("SELECT CURRENT_DATE")
                if row and row["ultima_coleta"] == hoje:
                    return await ctx.reply("⏳ Você já coletou sua recompensa diária. Volte amanhã.", mention_author=False)
                await conn.execute(
                    "INSERT INTO sants_carteiras(user_id,saldo) VALUES($1,$2) "
                    "ON CONFLICT(user_id) DO UPDATE SET saldo=sants_carteiras.saldo+EXCLUDED.saldo, atualizado_em=NOW()",
                    uid, RECOMPENSA_DIARIA
                )
                await conn.execute(
                    "INSERT INTO sants_diarios(user_id,ultima_coleta) VALUES($1,$2) "
                    "ON CONFLICT(user_id) DO UPDATE SET ultima_coleta=EXCLUDED.ultima_coleta",
                    uid, hoje
                )
                await conn.execute(
                    "INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao) "
                    "VALUES($1,'diario',$2,'Recompensa diária')", uid, RECOMPENSA_DIARIA
                )
                novo_saldo = await conn.fetchval("SELECT saldo FROM sants_carteiras WHERE user_id=$1", uid)
        await ctx.reply(
            f"🎁 Você recebeu **{fmt(RECOMPENSA_DIARIA)}**!\n"
            f"💼 Novo saldo: **{fmt(novo_saldo)}**",
            mention_author=False
        )

    @commands.command(name="transferir", aliases=["pagar", "pix"])
    async def transferir(self, ctx: commands.Context, membro: discord.Member, quantia: int):
        if membro.bot:
            return await ctx.reply("❌ Não é possível transferir moedas para bots.", mention_author=False)
        if quantia <= 0:
            return await ctx.reply("❌ Informe uma quantia maior que zero.", mention_author=False)
        ok, msg = await cassino_db.transferir_moedas(
            ctx.author.id, membro.id, quantia, LIMITE_TRANSFERENCIA_DIARIA
        )
        if not ok:
            return await ctx.reply(f"❌ {msg}", mention_author=False)
        await ctx.reply(
            f"💸 {ctx.author.mention} transferiu **{fmt(quantia)}** para {membro.mention}.\n"
            f"📌 Limite diário: **{fmt(LIMITE_TRANSFERENCIA_DIARIA)}** por remetente.",
            mention_author=False
        )

    @commands.command(name="extrato", aliases=["historico", "transacoes"])
    async def extrato(self, ctx: commands.Context):
        rows = await cassino_db.historico(ctx.author.id, 8)
        if not rows:
            return await ctx.reply("📜 Você ainda não tem movimentações registradas.", mention_author=False)
        linhas = []
        for row in rows:
            sinal = "+" if row["tipo"] in ("credito", "diario", "transferencia_recebida") else "-"
            quando = row["criado_em"].strftime("%d/%m %H:%M")
            linhas.append(f"`{quando}` **{sinal}{fmt(row['quantia'])}** — {row['descricao']}")
        embed = discord.Embed(title="📜 Extrato da carteira", description="\n".join(linhas), color=0x211A1A)
        await ctx.reply(embed=embed, mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Economia(bot))
