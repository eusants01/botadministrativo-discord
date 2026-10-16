"""Portal Sant's 3 — recursos públicos e edição segura de perfis.

Não concede cargos do Discord nem modifica tabelas do cassino.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

import asyncpg
import discord
from fastapi import HTTPException, Request

DEFAULT_INVITE = 'https://discord.gg/EfRaFAXgHb'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS portal_profiles (
 user_id BIGINT PRIMARY KEY,
 bio TEXT NOT NULL DEFAULT '',
 frase TEXT NOT NULL DEFAULT '',
 banner TEXT NOT NULL DEFAULT '',
 accent TEXT NOT NULL DEFAULT '#69b7ff',
 socials JSONB NOT NULL DEFAULT '{}'::jsonb,
 is_public BOOLEAN NOT NULL DEFAULT TRUE,
 admin_hidden BOOLEAN NOT NULL DEFAULT FALSE,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE portal_profiles ADD COLUMN IF NOT EXISTS admin_hidden BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS portal_role_catalog (
 role_id BIGINT PRIMARY KEY,
 categoria TEXT NOT NULL DEFAULT 'exclusivo',
 descricao TEXT NOT NULL DEFAULT '',
 simbolo TEXT NOT NULL DEFAULT '✦',
 ordem INTEGER NOT NULL DEFAULT 100,
 visivel BOOLEAN NOT NULL DEFAULT TRUE,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

# Descrições de referência do material disponibilizado pelo usuário.
ROLE_REFERENCE = {
 'criador': ('administrativo', 'Criadores da Família.', '⚔️', 0),
 'diretor': ('administrativo', 'Lidera a administração, define estratégias e supervisiona os setores.', '♜', 10),
 'diretor geral': ('administrativo', 'Lidera a administração, define estratégias e supervisiona os setores.', '♜', 10),
 'administrador': ('administrativo', 'Gerencia recursos, sistemas e processos internos.', '✧', 20),
 'moderador': ('administrativo', 'Mantém a ordem, a segurança e o bem-estar da comunidade.', '🛡️', 30),
 'estagiario': ('administrativo', 'Membro em treinamento para integrar a moderação.', '✦', 40),
 'amigos da bruna': ('exclusivo', 'Cargo concedido exclusivamente pela Bruna.', '🦊', 10),
 'kitsune': ('exclusivo', 'A raposa observa aqueles que prestam atenção.', '🦊', 20),
 'ancestral': ('exclusivo', '7 dias de participação, atividade mínima e nenhuma punição grave.', '⛩️', 30),
 'crystal': ('exclusivo', 'Vença três eventos oficiais do servidor.', '💎', 40),
 'pesquisador': ('exclusivo', 'Explore o servidor e encontre informações escondidas nos canais.', '🔎', 50),
 'sakura': ('exclusivo', 'Conquistada por vencedores de um evento específico.', '🌸', 60),
 'designer': ('exclusivo', 'Reconhecimento por uma criação artística para a Família.', '🎨', 70),
 'medalha da bruna': ('heroina', 'Homenagem especial à Bruna.', '💝', 10),
 'medalha da tatah': ('heroina', 'Homenagem especial à Tatah.', '💝', 20),
 'medalha da pietra': ('heroina', 'Homenagem especial à Pietra.', '💝', 30),
 'medalha da kananda': ('heroina', 'Homenagem especial à Kananda.', '💝', 40),
 'medalha do sants': ('campeao', 'Medalha dos campeões da Família.', '🏆', 10),
 'medalha do ruan': ('campeao', 'Medalha dos campeões da Família.', '🏆', 20),
 'medalha do golgos': ('campeao', 'Medalha dos campeões da Família.', '🏆', 30),
 'medalha do kael': ('campeao', 'Medalha dos campeões da Família.', '🏆', 40),
 'medalha do pato': ('campeao', 'Medalha dos campeões da Família.', '🏆', 50),
 'medalha do diniz': ('campeao', 'Medalha dos campeões da Família.', '🏆', 60),
 'medalha cerebro': ('medalha', 'Faça um total de 10 abates em evento organizado pelo servidor.', '🧠', 10),
 'medalha coradouro': ('medalha', 'Reconhecimento a quem contribui ajudando membros no servidor.', '❤️', 20),
 'medalha contribuidor': ('medalha', 'Membro booster do servidor.', '💛', 30),
 'medalha meme': ('medalha', 'Medalha de significado especial, definida pela administração.', '🎭', 40),
 'medalha angel': ('medalha', 'Reconhecimento a membros antigos da comunidade.', '👼', 50),
 'medalha esfera': ('medalha', 'Medalha de significado especial, definida pela administração.', '🐉', 60),
}
CATEGORIAS = {'administrativo', 'exclusivo', 'heroina', 'campeao', 'medalha', 'outro'}
BRAND_KEYS = {
 'hero_banner', 'membros_banner', 'hierarquia_banner', 'evento_banner',
 'evento_titulo', 'evento_subtitulo', 'evento_promotor', 'spoiler_ativo',
 'spoiler_texto', 'home_recado'
}
IMAGE_KEYS = {'hero_banner', 'membros_banner', 'hierarquia_banner', 'evento_banner'}
RE_URL = re.compile(r'^https://[^\s<>"\']{1,490}$')
RE_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def normalize(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return s.strip()


def valid_url(value, *, allow_asset=False):
    if not value:
        return ''
    if allow_asset and re.fullmatch(r'/assets/[a-zA-Z0-9_.\-/]+', value) and '..' not in value:
        return value
    if not RE_URL.fullmatch(value):
        raise HTTPException(400, 'Use um endereço HTTPS válido (ou /assets/arquivo).')
    u = urlparse(value)
    try:
        forbidden = u.username or u.password or not u.netloc or (u.port is not None and u.port != 443)
    except ValueError:
        forbidden = True
    if forbidden:
        raise HTTPException(400, 'Endereço inválido.')
    return value


def installed_on(app, *, get_bot, get_pool, guild_id, get_admin, audit_fn, guard_write,
                 creator_role_id, staff_ids=()):
    """Injeta rotas no FastAPI atual, sem modificar o main.py."""
    cache_lock = asyncio.Lock()
    last_chunk = 0.0

    def bot_guild():
        b = get_bot()
        return b.get_guild(guild_id) if b else None

    def db():
        p = get_pool()
        if p is None:
            raise HTTPException(503, 'Banco de dados temporariamente indisponível.')
        return p

    def guild_or_503():
        g = bot_guild()
        if not g:
            raise HTTPException(503, 'Discord em sincronização. Aguarde alguns instantes.')
        return g

    async def sync_members_once(force=False):
        nonlocal last_chunk
        g = bot_guild()
        if not g or not get_bot().is_ready():
            return
        total = g.member_count or 0
        if not force and (time.monotonic() - last_chunk < 900 or len(g.members) >= total > 0):
            return
        if cache_lock.locked():
            return
        async with cache_lock:
            last_chunk = time.monotonic()
            try:
                await asyncio.wait_for(g.chunk(cache=True), timeout=65)
            except (asyncio.TimeoutError, discord.HTTPException, discord.ClientException) as exc:
                print('[portal] Não foi possível sincronizar todos os membros:', type(exc).__name__)

    async def initialize():
        await db().execute(SCHEMA)
        b = get_bot()
        await b.wait_until_ready()
        await sync_members_once(force=True)
        await seed_roles()
        print('[portal] Perfis públicos, hierarquia e membros preparados.')

    async def seed_roles():
        g = bot_guild()
        if g is None:
            return
        existing = await db().fetch('SELECT role_id FROM portal_role_catalog')
        indexed = {int(r['role_id']) for r in existing}
        for role in g.roles:
            if role.is_default() or role.managed or role.id in indexed:
                continue
            name = normalize(role.name.replace('@', ''))
            data = ROLE_REFERENCE.get(name)
            if role.id == creator_role_id:
                data = ROLE_REFERENCE['criador']
            if role.id in staff_ids and data is None:
                data = ('administrativo', 'Cargo de administração da comunidade.', '🛡️', 60)
            if data:
                await db().execute('''INSERT INTO portal_role_catalog(role_id,categoria,descricao,simbolo,ordem)
                      VALUES($1,$2,$3,$4,$5) ON CONFLICT(role_id) DO NOTHING''', role.id, *data)

    def role_summary(role, meta):
        return {'id': str(role.id), 'nome': role.name, 'cor': f'#{role.color.value:06x}' if role.color.value else '#78b6f4',
                'categoria': meta['categoria'], 'descricao': meta['descricao'], 'simbolo': meta['simbolo'],
                'ordem': meta['ordem'], 'visivel': meta['visivel']}

    async def role_records(include_hidden=False):
        g = guild_or_503()
        rows = await db().fetch('SELECT * FROM portal_role_catalog ORDER BY ordem, role_id')
        out = []
        for r in rows:
            role = g.get_role(int(r['role_id']))
            if role is None or (not include_hidden and not r['visivel']):
                continue
            out.append(role_summary(role, r))
        return out

    def brief_member(m, *, rich=False):
        o = {'id': str(m.id), 'nome': m.display_name[:100], 'usuario': m.name[:100],
             'avatar': m.display_avatar.replace(size=128).url}
        if rich:
            o['entrou'] = m.joined_at.isoformat() if m.joined_at else None
        return o

    async def get_profile(uid):
        r = await db().fetchrow('SELECT * FROM portal_profiles WHERE user_id=$1', uid)
        if not r:
            return {'bio': '', 'frase': '', 'banner': '', 'accent': '#69b7ff', 'socials': {}, 'public': True}
        socials = r['socials']
        if isinstance(socials, str):
            socials = json.loads(socials)
        return {'bio': r['bio'], 'frase': r['frase'], 'banner': r['banner'],
                'accent': r['accent'], 'socials': socials or {}, 'public': r['is_public'] and not r['admin_hidden']}

    async def login_member(req):
        uid = req.session.get('uid')
        if not uid:
            raise HTTPException(401, 'Entre com sua conta Discord para editar seu perfil.')
        g = guild_or_503()
        try:
            return await g.fetch_member(int(uid))
        except (discord.NotFound, ValueError, TypeError):
            raise HTTPException(403, 'Você precisa participar do Discord da Família.')
        except discord.HTTPException:
            raise HTTPException(503, 'Não foi possível confirmar sua participação agora.')

    async def member_page(m, roles_index=None):
        prof = await get_profile(m.id)
        if not prof['public']:
            raise HTTPException(404, 'Este membro não disponibiliza perfil público.')
        if roles_index is None:
            roles_index = {int(r['id']): r for r in await role_records()}
        roles = [roles_index[r.id] for r in m.roles if r.id in roles_index]
        roles.sort(key=lambda r: (r['categoria'], r['ordem']))
        return {**brief_member(m, rich=True), 'perfil': prof, 'cargos': roles,
                'medalhas': [r for r in roles if r['categoria'] in ('heroina', 'campeao', 'medalha')],
                'criador': any(r.id == creator_role_id for r in m.roles)}

    @app.get('/api/portal/status')
    async def portal_status(req: Request):
        uid = req.session.get('uid')
        if not uid:
            return {'logado': False, 'convite': DEFAULT_INVITE}
        try:
            member = await login_member(req)
        except HTTPException:
            return {'logado': False, 'convite': DEFAULT_INVITE}
        return {'logado': True, 'id': str(member.id), 'nome': member.display_name,
                'avatar': member.display_avatar.replace(size=128).url,
                'admin': member.guild_permissions.administrator or bool({r.id for r in member.roles} & set(staff_ids))}

    @app.get('/api/portal/membros')
    async def portal_members(q: str = '', grupo: str = 'todos', pagina: int = 1):
        if len(q) > 80 or pagina < 1 or pagina > 500:
            raise HTTPException(400, 'Parâmetros inválidos.')
        g = guild_or_503()
        all_roles = {int(r['id']): r for r in await role_records()}
        entries = []
        for m in g.members:
            if m.bot:
                continue
            if q and normalize(q) not in normalize(f'{m.name} {m.display_name}'):
                continue
            rlist = [all_roles[r.id] for r in m.roles if r.id in all_roles]
            if grupo != 'todos' and not any(r['categoria'] == grupo for r in rlist):
                continue
            o = brief_member(m)
            o['cargos'] = sorted(rlist, key=lambda r: r['ordem'])[:4]
            entries.append(o)
        entries.sort(key=lambda m: (not any(r['categoria']=='administrativo' for r in m['cargos']), m['nome'].casefold()))
        # Opt-out: remove da listagem pública os perfis definidos como privados.
        if entries:
            rows = await db().fetch('SELECT user_id FROM portal_profiles WHERE is_public=FALSE OR admin_hidden=TRUE')
            hidden = {str(r['user_id']) for r in rows}
            entries = [x for x in entries if x['id'] not in hidden]
        page_size = 24
        start = (pagina - 1) * page_size
        return {'total': len(entries), 'pagina': pagina, 'paginas': max(1, (len(entries)+page_size-1)//page_size),
                'membros': entries[start:start+page_size], 'sincronizados': len(g.members),
                'estimado': g.member_count or len(g.members)}

    @app.get('/api/portal/perfil/{uid}')
    async def portal_public_profile(uid: int):
        g = guild_or_503()
        m = g.get_member(uid)
        if m is None:
            raise HTTPException(404, 'Membro não localizado na listagem. Aguarde a sincronização.')
        return await member_page(m)

    @app.get('/api/portal/meu-perfil')
    async def own_profile(req: Request):
        m = await login_member(req)
        return {**brief_member(m), 'perfil': await get_profile(m.id)}

    @app.post('/api/portal/meu-perfil')
    async def save_own_profile(req: Request):
        guard_write(req)
        m = await login_member(req)
        d = await req.json()
        if not isinstance(d, dict):
            raise HTTPException(400, 'Dados inválidos.')
        bio = str(d.get('bio') or '').strip()[:600]
        frase = str(d.get('frase') or '').strip()[:110]
        banner = valid_url(str(d.get('banner') or '').strip()[:500], allow_asset=True)
        accent = str(d.get('accent') or '#69b7ff')
        if not RE_COLOR.fullmatch(accent):
            raise HTTPException(400, 'Cor inválida.')
        links = d.get('socials') or {}
        if not isinstance(links, dict):
            raise HTTPException(400, 'Links inválidos.')
        socials = {key: valid_url(str(links.get(key) or '').strip()[:490])
                   for key in ('site', 'github', 'youtube') if links.get(key)}
        public = bool(d.get('public', True))
        await db().execute('''INSERT INTO portal_profiles(user_id,bio,frase,banner,accent,socials,is_public)
            VALUES($1,$2,$3,$4,$5,$6::jsonb,$7)
            ON CONFLICT(user_id) DO UPDATE SET bio=$2,frase=$3,banner=$4,accent=$5,socials=$6::jsonb,
            is_public=$7,updated_at=now()''', m.id, bio, frase, banner, accent, json.dumps(socials), public)
        return {'ok': 'Seu perfil foi atualizado.', 'id': str(m.id)}

    @app.get('/api/portal/hierarquia')
    async def portal_hierarchy():
        return {'cargos': await role_records(), 'origem': 'Cargos atuais do Discord e descrições aprovadas pelo painel'}

    @app.get('/api/portal/brand')
    async def brand():
        rows = await db().fetch('SELECT chave,valor FROM config WHERE chave=ANY($1::text[])', list(BRAND_KEYS))
        values = {r['chave']: r['valor'] for r in rows}
        return {'hero_banner': values.get('hero_banner') or '/assets/banner.jpg',
                'membros_banner': values.get('membros_banner') or '/assets/banner.jpg',
                'hierarquia_banner': values.get('hierarquia_banner') or '/assets/banner.jpg',
                'evento_banner': values.get('evento_banner') or '/assets/evento-teaser.webp',
                'evento_titulo': values.get('evento_titulo') or 'Uma nova energia se aproxima.',
                'evento_subtitulo': values.get('evento_subtitulo') or 'Um novo evento está sendo preparado.',
                'evento_promotor': values.get('evento_promotor') or 'Kael',
                'spoiler_ativo': values.get('spoiler_ativo', 'true') == 'true',
                'spoiler_texto': values.get('spoiler_texto') or 'Sete sinais. Uma única surpresa. Fique atento à próxima saga.',
                'home_recado': values.get('home_recado') or 'Uma comunidade. Infinitas histórias.'}

    @app.get('/api/portal/admin/roles')
    async def admin_roles(req: Request):
        await get_admin(req)
        await seed_roles()
        g = guild_or_503()
        return {'cargos': await role_records(include_hidden=True),
                'disponiveis': [{'id': str(r.id), 'nome': r.name} for r in sorted(g.roles, key=lambda r:r.position, reverse=True)
                                if not r.is_default() and not r.managed]}

    @app.post('/api/portal/admin/role')
    async def update_role(req: Request):
        guard_write(req)
        m, level = await get_admin(req)
        if level < 5:
            raise HTTPException(403, 'Somente a direção pode editar a hierarquia.')
        data = await req.json()
        g = guild_or_503()
        try:
            rid = int(data.get('id'))
        except (ValueError, TypeError):
            raise HTTPException(400, 'Cargo inválido.')
        role = g.get_role(rid)
        if not role or role.is_default() or role.managed:
            raise HTTPException(404, 'Cargo não encontrado no servidor.')
        cat = str(data.get('categoria') or 'outro')
        if cat not in CATEGORIAS:
            raise HTTPException(400, 'Categoria inválida.')
        desc = str(data.get('descricao') or '').strip()[:300]
        symbol = str(data.get('simbolo') or '✦').strip()[:10]
        try:
            order = max(0, min(9999, int(data.get('ordem', 100))))
        except (TypeError, ValueError):
            raise HTTPException(400, 'Ordem inválida.')
        visible = bool(data.get('visivel', True))
        await db().execute('''INSERT INTO portal_role_catalog(role_id,categoria,descricao,simbolo,ordem,visivel)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT(role_id) DO UPDATE SET categoria=$2,descricao=$3,simbolo=$4,ordem=$5,visivel=$6,updated_at=now()''',
            rid, cat, desc, symbol, order, visible)
        await audit_fn(m, 'hierarquia_editar', None, f'{role.name}: {cat}')
        return {'ok': 'Cargo atualizado no catálogo do site (sem alterar permissões do Discord).'}

    @app.post('/api/portal/admin/brand')
    async def save_brand(req: Request):
        guard_write(req)
        m, level = await get_admin(req)
        if level < 5:
            raise HTTPException(403, 'Somente a direção pode alterar a identidade visual.')
        data = await req.json()
        if not isinstance(data, dict):
            raise HTTPException(400, 'Dados inválidos.')
        changes = {}
        for k, v in data.items():
            if k not in BRAND_KEYS:
                continue
            value = str(v or '').strip()
            if k in IMAGE_KEYS:
                value = valid_url(value[:500], allow_asset=True)
            elif k == 'spoiler_ativo':
                value = 'true' if str(v).lower() in ('true', '1', 'sim') else 'false'
            else:
                value = value[:300]
            changes[k] = value
        async with db().acquire() as conn:
            async with conn.transaction():
                for k, v in changes.items():
                    await conn.execute('''INSERT INTO config(chave,valor) VALUES($1,$2)
                         ON CONFLICT(chave) DO UPDATE SET valor=$2''', k, v)
        await audit_fn(m, 'identidade_visual', None, ', '.join(changes.keys())[:250])
        return {'ok': 'Identidade visual atualizada.'}

    @app.post('/api/portal/admin/profile')
    async def moderate_profile(req: Request):
        guard_write(req)
        m, level = await get_admin(req)
        if level < 4:
            raise HTTPException(403, 'Apenas administradores podem moderar perfis.')
        data = await req.json()
        try:
            uid = int(data.get('id'))
        except (ValueError, TypeError):
            raise HTTPException(400, 'ID inválido.')
        target = guild_or_503().get_member(uid)
        if not target:
            raise HTTPException(404, 'Membro não encontrado.')
        hidden = bool(data.get('ocultar', True))
        await db().execute('''INSERT INTO portal_profiles(user_id,admin_hidden) VALUES($1,$2)
            ON CONFLICT(user_id) DO UPDATE SET admin_hidden=$2,updated_at=now()''', uid, hidden)
        await audit_fn(m, 'perfil_moderar', target, 'Oculto' if hidden else 'Público')
        return {'ok': 'Visibilidade do perfil atualizada.'}

    return initialize, sync_members_once
