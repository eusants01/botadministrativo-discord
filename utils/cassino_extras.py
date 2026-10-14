"""Recompensas gratuitas do Cassino 2.2. Não altera tabelas antigas."""
from __future__ import annotations
import secrets
from utils import cassino_db

VISITA = 40
CONTRATO_CARTA = 60

async def inicializar_extras(pool=None):
    p = pool or cassino_db.obter_pool()
    await p.execute("""
        CREATE TABLE IF NOT EXISTS sants_cassino_extras_diario (
            user_id BIGINT NOT NULL,
            dia DATE NOT NULL,
            visita BOOLEAN NOT NULL DEFAULT FALSE,
            carta BOOLEAN NOT NULL DEFAULT FALSE,
            carta_num SMALLINT,
            premio_carta BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, dia)
        );
    """)

async def _linha(conn, uid):
    await conn.execute("""
        INSERT INTO sants_cassino_extras_diario(user_id, dia)
        VALUES($1, (NOW() AT TIME ZONE 'UTC')::date)
        ON CONFLICT (user_id, dia) DO NOTHING
    """, uid)
    return await conn.fetchrow("""
        SELECT visita, carta, carta_num, premio_carta
        FROM sants_cassino_extras_diario
        WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
        FOR UPDATE
    """, uid)

async def estado_contratos(user_id):
    p = cassino_db.obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            linha = await _linha(conn, int(user_id))
            return dict(linha)

async def _creditar(conn, uid, valor, descricao):
    if valor <= 0:
        return
    await conn.execute("""
        UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW()
        WHERE user_id=$1
    """, uid, valor)
    await conn.execute("""
        INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
        VALUES($1,'credito',$2,$3)
    """, uid, valor, descricao)

async def coletar_visita(user_id):
    uid = int(user_id)
    p = cassino_db.obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await cassino_db.garantir_carteira(uid, conn)
            linha = await _linha(conn, uid)
            if linha['visita']:
                saldo = await conn.fetchval('SELECT saldo FROM sants_carteiras WHERE user_id=$1', uid)
                return False, int(saldo)
            await conn.execute("""
                UPDATE sants_cassino_extras_diario SET visita=TRUE
                WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
            """, uid)
            await _creditar(conn, uid, VISITA, 'Cassino 2.2 • contrato de visita')
            saldo = await conn.fetchval('SELECT saldo FROM sants_carteiras WHERE user_id=$1', uid)
            return True, int(saldo)

async def revelar_carta(user_id, carta):
    uid = int(user_id)
    carta = int(carta)
    if carta not in (1, 2, 3):
        raise ValueError('Carta inválida')
    p = cassino_db.obter_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await cassino_db.garantir_carteira(uid, conn)
            linha = await _linha(conn, uid)
            if linha['carta']:
                return {'novo': False}
            # Um número aleatório uniforme de 0 a 99; escolha visual não altera chances.
            sorteio = secrets.randbelow(100)
            premio = 0 if sorteio < 40 else 25 if sorteio < 75 else 50 if sorteio < 95 else 100
            await conn.execute("""
                UPDATE sants_cassino_extras_diario
                SET carta=TRUE, carta_num=$2, premio_carta=$3
                WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
            """, uid, carta, premio)
            await _creditar(conn, uid, CONTRATO_CARTA, 'Cassino 2.2 • contrato da carta')
            await _creditar(conn, uid, premio, f'Cassino 2.2 • carta {carta}')
            saldo = await conn.fetchval('SELECT saldo FROM sants_carteiras WHERE user_id=$1', uid)
            return {'novo': True, 'premio': premio, 'saldo': int(saldo)}
