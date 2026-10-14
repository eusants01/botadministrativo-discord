from __future__ import annotations

import random
import discord
from discord.ext import commands
from utils import cassino_db

MOEDA = "SC"
APOSTA_MINIMA = 10
APOSTA_MAXIMA = 1000

def fmt(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".") + f" {MOEDA}"

class Cassino(commands.Cog):
    """Jogos simples de cassino usando a carteira compartilhada."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("bot.pool não existe; configure DATABASE_URL no Railway.")
        cassino_db.configurar_pool(pool)
        await cassino_db.inicializar_tabelas(pool)

    async def _validar_aposta(self, ctx, aposta: int) -> bool:
        if aposta < APOSTA_MINIMA:
            await ctx.reply(f"❌ A aposta mínima é **{fmt(APOSTA_MINIMA)}**.", mention_author=False)
            return False
        if aposta > APOSTA_MAXIMA:
            await ctx.reply(f"❌ A aposta máxima é **{fmt(APOSTA_MAXIMA)}** por rodada.", mention_author=False)
            return False
        saldo = await cassino_db.obter_saldo(ctx.author.id)
        if saldo < aposta:
            await ctx.reply(f"❌ Saldo insuficiente. Seu saldo é **{fmt(saldo)}**.", mention_author=False)
            return False
        return True

    async def _apostar(self, ctx, aposta: int, jogo: str) -> bool:
        return await cassino_db.registrar_aposta(ctx.author.id, aposta, f"Aposta: {jogo}")

    async def _resultado(self, ctx, aposta: int, jogo: str, ganhou: bool, multiplicador: int, detalhe: str):
        if ganhou:
            premio = aposta * multiplicador
            await cassino_db.adicionar_moedas(ctx.author.id, premio, f"Prêmio: {jogo}")
            saldo = await cassino_db.obter_saldo(ctx.author.id)
            await ctx.reply(
                f"🎉 **Você venceu!** {detalhe}\n"
                f"🪙 Prêmio: **{fmt(premio)}**\n💼 Saldo atual: **{fmt(saldo)}**",
                mention_author=False
            )
        else:
            saldo = await cassino_db.obter_saldo(ctx.author.id)
            await ctx.reply(
                f"🎭 **Não foi desta vez!** {detalhe}\n"
                f"💸 Você perdeu **{fmt(aposta)}**.\n💼 Saldo atual: **{fmt(saldo)}**",
                mention_author=False
            )

    @commands.command(name="cara", aliases=["coroa"])
    async def cara_coroa(self, ctx: commands.Context, aposta: int, escolha: str = "cara"):
        escolha = escolha.lower()
        if escolha not in ("cara", "coroa"):
            return await ctx.reply("Use `!cara 100 cara` ou `!cara 100 coroa`.", mention_author=False)
        if not await self._validar_aposta(ctx, aposta):
            return
        if not await self._apostar(ctx, aposta, "cara ou coroa"):
            return await ctx.reply("❌ Saldo insuficiente; tente novamente.", mention_author=False)
        resultado = random.choice(("cara", "coroa"))
        ganhou = escolha == resultado
        detalhe = f"Você escolheu **{escolha}** e saiu **{resultado}**."
        await self._resultado(ctx, aposta, "cara ou coroa", ganhou, 2, detalhe)

    @commands.command(name="dados")
    async def dados(self, ctx: commands.Context, aposta: int, palpite: int):
        if not await self._validar_aposta(ctx, aposta):
            return
        if not 1 <= palpite <= 6:
            return await ctx.reply("❌ O palpite precisa ser um número de 1 a 6.", mention_author=False)
        if not await self._apostar(ctx, aposta, "dados"):
            return await ctx.reply("❌ Saldo insuficiente; tente novamente.", mention_author=False)
        resultado = random.randint(1, 6)
        ganhou = palpite == resultado
        detalhe = f"Você apostou no **{palpite}** e o dado caiu em **{resultado}**."
        await self._resultado(ctx, aposta, "dados", ganhou, 5, detalhe)

    @commands.command(name="roleta")
    async def roleta(self, ctx: commands.Context, aposta: int, escolha: str = "vermelho"):
        escolha = escolha.lower()
        if escolha not in ("vermelho", "preto", "verde"):
            return await ctx.reply("Use `!roleta 100 vermelho`, `preto` ou `verde`.", mention_author=False)
        if not await self._validar_aposta(ctx, aposta):
            return
        if not await self._apostar(ctx, aposta, "roleta"):
            return await ctx.reply("❌ Saldo insuficiente; tente novamente.", mention_author=False)
        # Roleta simplificada: 18 vermelhos, 18 pretos e 1 verde.
        resultado = random.choices(
            ["vermelho", "preto", "verde"], weights=[18, 18, 1], k=1
        )[0]
        ganhou = escolha == resultado
        multiplicador = 14 if escolha == "verde" else 2
        detalhe = f"A roleta parou em **{resultado}**."
        await self._resultado(ctx, aposta, "roleta", ganhou, multiplicador, detalhe)

async def setup(bot: commands.Bot):
    await bot.add_cog(Cassino(bot))
