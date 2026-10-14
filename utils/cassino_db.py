"""Camada compartilhada de carteira Sant's Coins (PostgreSQL/asyncpg).

Compatível com o cog de leilões que importa:
    adicionar_moedas(user_id, quantia)
    obter_saldo(user_id)
    remover_moedas(user_id, quantia)

O pool é configurado pelo setup dos cogs. As operações críticas usam SQL atômico.
"""
from __future__ import annotations

from typing import Optional

_pool = None

def configurar_pool(pool) -> None:
    global _pool
    _pool = pool

def obter_pool():
    if _pool is None:
        raise RuntimeError(
            "Pool PostgreSQL não configurado. Verifique DATABASE_URL e o carregamento dos cogs."
        )
    return _pool

async def inicializar_tabelas(pool=None) -> None:
    p = pool or obter_pool()
    await p.execute("""
        CREATE TABLE IF NOT EXISTS sants_carteiras (
            user_id BIGINT PRIMARY KEY,
            saldo BIGINT NOT NULL DEFAULT 0 CHECK (saldo >= 0),
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS sants_transacoes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            tipo TEXT NOT NULL,
            quantia BIGINT NOT NULL CHECK (quantia > 0),
            descricao TEXT NOT NULL DEFAULT '',
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_sants_transacoes_user
            ON sants_transacoes(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS sants_diarios (
            user_id BIGINT PRIMARY KEY,
            ultima_coleta DATE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sants_transferencias_diarias (
            user_id BIGINT NOT NULL,
            dia DATE NOT NULL DEFAULT CURRENT_DATE,
            total BIGINT NOT NULL DEFAULT 0 CHECK (total >= 0),
            PRIMARY KEY(user_id, dia)
        );
    """)

async def garantir_carteira(user_id: int, conn=None) -> None:
    p = conn or obter_pool()
    await p.execute(
        "INSERT INTO sants_carteiras(user_id, saldo) VALUES($1, 0) "
        "ON CONFLICT(user_id) DO NOTHING",
        int(user_id),
    )

async def obter_saldo(user_id: int) -> int:
    p = obter_pool()
    await garantir_carteira(user_id, p)
    value = await p.fetchval(
        "SELECT saldo FROM sants_carteiras WHERE user_id=$1", int(user_id)
    )
    return int(value or 0)

async def adicionar_moedas(user_id: int, quantia: int, descricao: str = "Crédito") -> int:
    quantia = int(quantia)
    if quantia <= 0:
        raise ValueError("A quantia precisa ser maior que zero.")
    p = obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await garantir_carteira(user_id, conn)
            saldo = await conn.fetchval(
                "UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW() "
                "WHERE user_id=$1 RETURNING saldo",
                int(user_id), quantia,
            )
            await conn.execute(
                "INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao) "
                "VALUES($1,'credito',$2,$3)",
                int(user_id), quantia, str(descricao)[:200],
            )
            return int(saldo)

async def remover_moedas(user_id: int, quantia: int, descricao: str = "Débito") -> bool:
    """Debita de forma atômica; retorna False se o saldo for insuficiente."""
    quantia = int(quantia)
    if quantia <= 0:
        raise ValueError("A quantia precisa ser maior que zero.")
    p = obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await garantir_carteira(user_id, conn)
            saldo = await conn.fetchval(
                "UPDATE sants_carteiras SET saldo=saldo-$2, atualizado_em=NOW() "
                "WHERE user_id=$1 AND saldo >= $2 RETURNING saldo",
                int(user_id), quantia,
            )
            if saldo is None:
                return False
            await conn.execute(
                "INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao) "
                "VALUES($1,'debito',$2,$3)",
                int(user_id), quantia, str(descricao)[:200],
            )
            return True

async def transferir_moedas(origem_id: int, destino_id: int, quantia: int,
                            limite_diario: int = 5000) -> tuple[bool, str]:
    """Transfere moedas atomicamente, com teto diário por remetente."""
    origem_id, destino_id, quantia = int(origem_id), int(destino_id), int(quantia)
    if origem_id == destino_id:
        return False, "Você não pode transferir moedas para si mesmo."
    if quantia <= 0:
        return False, "A quantia precisa ser maior que zero."
    if quantia > limite_diario:
        return False, f"O limite por transferência é {limite_diario:,} SC.".replace(",", ".")
    p = obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await garantir_carteira(origem_id, conn)
            await garantir_carteira(destino_id, conn)
            # Lock por usuário, em ordem estável para evitar deadlocks.
            ids = sorted((origem_id, destino_id))
            await conn.fetch(
                "SELECT user_id FROM sants_carteiras WHERE user_id = ANY($1::bigint[]) "
                "ORDER BY user_id FOR UPDATE", ids
            )
            # Serializa transferências do mesmo remetente para respeitar o limite diário.
            await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", origem_id)
            dia_total = await conn.fetchval(
                "SELECT total FROM sants_transferencias_diarias "
                "WHERE user_id=$1 AND dia=CURRENT_DATE",
                origem_id,
            )
            dia_total = int(dia_total or 0)
            if dia_total + quantia > limite_diario:
                restante = max(0, limite_diario - dia_total)
                return False, (
                    f"Você já transferiu {dia_total:,} SC hoje. "
                    f"Ainda pode transferir {restante:,} SC hoje."
                ).replace(",", ".")
            debitado = await conn.fetchval(
                "UPDATE sants_carteiras SET saldo=saldo-$2, atualizado_em=NOW() "
                "WHERE user_id=$1 AND saldo >= $2 RETURNING saldo",
                origem_id, quantia,
            )
            if debitado is None:
                return False, "Saldo insuficiente para realizar essa transferência."
            await conn.execute(
                "UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW() WHERE user_id=$1",
                destino_id, quantia,
            )
            await conn.execute(
                "INSERT INTO sants_transferencias_diarias(user_id,dia,total) "
                "VALUES($1,CURRENT_DATE,$2) "
                "ON CONFLICT(user_id,dia) DO UPDATE SET total=sants_transferencias_diarias.total+EXCLUDED.total",
                origem_id, quantia,
            )
            await conn.execute(
                "INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao) "
                "VALUES($1,'transferencia_enviada',$2,$3),($4,'transferencia_recebida',$2,$5)",
                origem_id, quantia, f"Transferência para {destino_id}",
                destino_id, f"Transferência recebida de {origem_id}",
            )
    return True, "Transferência realizada com sucesso."

async def registrar_aposta(user_id: int, quantia: int, descricao: str) -> bool:
    return await remover_moedas(user_id, quantia, descricao)

async def historico(user_id: int, limite: int = 8):
    p = obter_pool()
    return await p.fetch(
        "SELECT tipo, quantia, descricao, criado_em FROM sants_transacoes "
        "WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
        int(user_id), max(1, min(int(limite), 20)),
    )

