"""Extensão transacional do cassino. Não substitui cassino_db.py."""
from utils import cassino_db

class SaldoInsuficiente(Exception):
    pass

async def inicializar_cassino(pool=None):
    p = pool or cassino_db.obter_pool()
    await p.execute('''
        CREATE TABLE IF NOT EXISTS sants_partidas (
            id UUID PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            jogo TEXT NOT NULL,
            escolha TEXT NOT NULL,
            resultado TEXT NOT NULL,
            aposta BIGINT NOT NULL CHECK (aposta > 0),
            premio BIGINT NOT NULL CHECK (premio >= 0),
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_sants_partidas_usuario ON sants_partidas(user_id, criado_em DESC);
        CREATE INDEX IF NOT EXISTS idx_sants_partidas_semana ON sants_partidas(criado_em DESC);
    ''')

async def finalizar_partida_cassino(user_id, guild_id, partida_id, jogo, escolha, resultado, aposta, premio):
    """Liquidação indivisível e idempotente; a carteira e o extrato ficam consistentes."""
    from uuid import UUID
    uid, aposta, premio = int(user_id), int(aposta), int(premio)
    if aposta <= 0 or premio < 0:
        raise ValueError('Quantias inválidas')
    pool = cassino_db.obter_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await cassino_db.garantir_carteira(uid, conn)
            await conn.fetchrow('SELECT saldo FROM sants_carteiras WHERE user_id=$1 FOR UPDATE', uid)
            existente = await conn.fetchrow('SELECT user_id FROM sants_partidas WHERE id=$1', UUID(partida_id))
            if existente:
                if existente['user_id'] != uid:
                    raise ValueError('ID de partida utilizado por outro usuário')
                return int(await conn.fetchval('SELECT saldo FROM sants_carteiras WHERE user_id=$1', uid))
            saldo = await conn.fetchval('''
                UPDATE sants_carteiras SET saldo=saldo-$2+$3, atualizado_em=NOW()
                WHERE user_id=$1 AND saldo >= $2 RETURNING saldo
            ''', uid, aposta, premio)
            if saldo is None:
                raise SaldoInsuficiente()
            await conn.execute('''
                INSERT INTO sants_partidas(id,user_id,guild_id,jogo,escolha,resultado,aposta,premio)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ''', UUID(partida_id), uid, int(guild_id), jogo, escolha, resultado, aposta, premio)
            await conn.execute('''
                INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
                VALUES($1,'debito',$2,$3)
            ''', uid, aposta, f'Cassino {jogo} • aposta {partida_id[:8]}')
            if premio:
                await conn.execute('''
                    INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
                    VALUES($1,'credito',$2,$3)
                ''', uid, premio, f'Cassino {jogo} • prêmio {partida_id[:8]}')
            return int(saldo)

async def estatisticas_cassino(user_id):
    pool = cassino_db.obter_pool()
    r = await pool.fetchrow('''
        SELECT COUNT(*)::int AS partidas,
               COUNT(*) FILTER (WHERE premio > 0)::int AS vitorias,
               COUNT(*) FILTER (WHERE premio = 0)::int AS derrotas,
               COALESCE(SUM(premio-aposta),0)::bigint AS lucro
        FROM sants_partidas WHERE user_id=$1
    ''', int(user_id))
    return dict(r)

async def ranking_cassino(limite=10):
    pool = cassino_db.obter_pool()
    return await pool.fetch('''
        SELECT user_id, SUM(premio-aposta)::bigint AS lucro
        FROM sants_partidas
        WHERE criado_em >= date_trunc('week', NOW())
        GROUP BY user_id ORDER BY lucro DESC, user_id ASC LIMIT $1
    ''', max(1,min(int(limite),25)))
