"""Portal público da Família Royal; não expõe comandos administrativos."""
from __future__ import annotations

import asyncio
import secrets
import hashlib
import base64
import json
import html
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlsplit

import aiohttp
import logging
import os
from pathlib import Path

import discord
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

LOG = logging.getLogger("royal.site")
BASE = Path(__file__).resolve().parent
GUILD_ID = int(os.getenv("GUILD_ID", "1553803921514963075"))
OFC_ID = 1554367619463913582
INFLUENCER_ID = 1565443626388164790

STAFF = [
    ("Manager", 1553923854877990945, "Direção e organização geral", "♛"),
    ("Administrador", 1562909560430264420, "Gestão e administração", "⚜"),
    ("Coordenador", 1553832097255260260, "Coordenação das equipes", "✦"),
    ("Supervisor", 1562950237117481000, "Acompanhamento operacional", "◆"),
    ("Moderador", 1553832097905377422, "Segurança e convivência", "◇"),
    ("Estagiário", 1553832098404499516, "Formação e apoio à equipe", "✧"),
]
OTHER = [
    ("Analista de Famílias", 1556295901293715486, "Fiscalização independente da hierarquia administrativa", "◎"),
    ("Organizador de Eventos", 1561231585993293864, "Planejamento de eventos e atividades", "✧"),
    ("Organizador de Leilões", 1559771638025691178, "Organização de leilões e premiações", "♢"),
]
BENEFITS = [
    ("Sorteios exclusivos", "Premiações reservadas aos integrantes oficiais.", "🎁"),
    ("Indicações familiares", "Recomende novos candidatos para avaliação.", "📜"),
    ("Perfil Royal", "Trajetória, reconhecimentos e insígnias pessoais.", "👤"),
    ("Eventos privativos", "Atividades e experiências exclusivas.", "🎭"),
    ("Conselho Royal", "Propostas e votações consultivas dos membros.", "⚖️"),
    ("Call privada", "Espaço de voz reservado aos integrantes oficiais.", "🎙️"),
    ("Permissões no E.B", "Vantagens do cargo Família no E.B do ALPHA, conforme regras locais.", "🛡️"),
]

def signing():
    key = os.getenv('ROYAL_SITE_SECRET', '').strip()
    if len(key) < 32:
        raise HTTPException(503, 'A autenticação requer ROYAL_SITE_SECRET (mínimo 32 caracteres).')
    return URLSafeTimedSerializer(key, salt='royal-profile-v2')


def oauth_status():
    client_id = os.getenv('DISCORD_CLIENT_ID', '').strip() or os.getenv('CLIENT_ID', '').strip()
    client_secret = os.getenv('DISCORD_CLIENT_SECRET', '').strip()
    redirect_uri = os.getenv('DISCORD_REDIRECT_URI', '').strip()
    if not redirect_uri:
        public_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
        if public_domain and '/' not in public_domain:
            redirect_uri = f'https://{public_domain}/auth/callback'
    missing = []
    if not client_id: missing.append('DISCORD_CLIENT_ID')
    if not client_secret: missing.append('DISCORD_CLIENT_SECRET')
    if not redirect_uri or not redirect_uri.startswith('https://') or not redirect_uri.endswith('/auth/callback'):
        missing.append('DISCORD_REDIRECT_URI')
    if len(os.getenv('ROYAL_SITE_SECRET', '').strip()) < 32: missing.append('ROYAL_SITE_SECRET')
    return {'ready': not missing, 'missing': missing, 'redirect_uri': redirect_uri}


def oauth_config():
    status = oauth_status()
    if not status['ready']:
        raise HTTPException(503, 'A integração Discord OAuth2 ainda não foi configurada no Railway.')
    return (os.getenv('DISCORD_CLIENT_ID', '').strip() or os.getenv('CLIENT_ID', '').strip(),
            os.getenv('DISCORD_CLIENT_SECRET', '').strip(), status['redirect_uri'])


async def authenticated(request: Request, require=True):
    token = request.cookies.get('royal_session')
    if not token:
        if require: raise HTTPException(401, 'Faça login pelo Discord.')
        return None
    try:
        signed = signing().loads(token, max_age=60 * 60 * 24 * 7)
        user_id, secret = signed['id'], signed['secret']
        digest = hashlib.sha256(secret.encode()).hexdigest()
        pool = await profile_db()
        row = await pool.fetchrow('SELECT user_id FROM royal_site_sessions WHERE user_id=$1 AND token_hash=$2 AND expires_at>NOW()',int(user_id), digest)
        if row: return int(user_id)
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError): pass
    if require: raise HTTPException(401, 'Sessão expirada. Entre novamente.')
    return None


_profile_schema_ready = False
_profile_schema_lock = asyncio.Lock()

async def profile_db():
    global _profile_schema_ready
    pool = getattr(_bot, 'pool', None)
    if pool is None:
        raise HTTPException(503, 'PostgreSQL temporariamente indisponível.')
    if not _profile_schema_ready:
        async with _profile_schema_lock:
            if not _profile_schema_ready:
                await pool.execute("""CREATE TABLE IF NOT EXISTS royal_site_profiles (
                    user_id BIGINT PRIMARY KEY,
                    display_name VARCHAR(48) NOT NULL DEFAULT '',
                    bio VARCHAR(420) NOT NULL DEFAULT '',
                    title VARCHAR(50) NOT NULL DEFAULT '',
                    color VARCHAR(16) NOT NULL DEFAULT 'gold',
                    link VARCHAR(240) NOT NULL DEFAULT '',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""")
                for col, length in [('motto', 120),('badge_a',24),('badge_b',24),('signature',80)]:
                    await pool.execute(f"ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS {col} VARCHAR({length}) NOT NULL DEFAULT ''")
                await pool.execute("""CREATE TABLE IF NOT EXISTS royal_site_sessions (
                    user_id BIGINT NOT NULL,
                    token_hash VARCHAR(64) PRIMARY KEY,
                    expires_at TIMESTAMPTZ NOT NULL
                )""")
                _profile_schema_ready = True
    return pool


app = FastAPI(title="Família Royal — Portal Oficial", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/assets", StaticFiles(directory=str(BASE / "assets")), name="assets")


@app.exception_handler(HTTPException)
async def friendly_auth_errors(request: Request, exc: HTTPException):
    if not request.url.path.startswith('/auth/'):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    hint = ''
    if exc.status_code == 503 and request.url.path.startswith('/auth/'):
        status = oauth_status()
        if status['missing']:
            hint = '<p class="tip">Faltam no Railway: <strong>' + html.escape(', '.join(status['missing'])) + '</strong>.</p>'
    body = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Família Royal • Conexão Discord</title>'
            '<style>body{min-height:100vh;margin:0;background:radial-gradient(circle at top,#53331a,#110b09 63%);color:#fff2d9;font:15px/1.8 Arial,sans-serif;display:grid;place-items:center;padding:20px}'
            'main{max-width:610px;background:#1d120dcc;border:1px solid #b58a50;padding:36px;border-radius:16px;box-shadow:0 20px 80px #0008}'
            'h1{font:600 32px Georgia,serif;color:#ffdc9f}h2{font-size:14px;color:#cca373}.tip{padding:15px;background:#3f2b1c;border-left:3px solid #f2ba73}'
            'a{color:#ffe0a9}.button{display:inline-block;background:#e3b36b;color:#21140c;padding:10px 18px;text-decoration:none;font-weight:bold;border-radius:5px}</style>'
            '<main><h2>✦ FAMÍLIA ROYAL • PORTAL OFICIAL</h2><h1>Não foi possível conectar ao Discord</h1>'
            '<p>' + html.escape(str(exc.detail)) + '</p>' + hint
            + '<p>O restante do site continua disponível. Para ativar o editor, confira as variáveis OAuth2 no Railway e o Redirect URI no Discord Developer Portal.</p>'
            '<a class="button" href="/#perfil">Voltar ao meu perfil ↗</a></main></html>')
    return HTMLResponse(body, status_code=exc.status_code)


@app.get('/api/royal/oauth-status')
async def public_auth_status():
    status = oauth_status()
    return {'ready': status['ready'], 'missing': status['missing']}

_bot: discord.Client | None = None


def guild():
    return _bot.get_guild(GUILD_ID) if _bot and _bot.is_ready() else None


def member_data(m: discord.Member):
    return {"id": str(m.id), "nome": m.display_name,
            "usuario": m.name, "avatar": str(m.display_avatar.replace(size=128).url),
            "roles": [str(r.id) for r in m.roles],
            "ingresso_servidor": m.joined_at.isoformat() if m.joined_at else None}


def members_of(g, role_id):
    role = g.get_role(role_id)
    if not role:
        return []
    return sorted([member_data(m) for m in role.members if not m.bot], key=lambda m: m["nome"].casefold())


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse((BASE / "royal_site.html").read_text(encoding="utf-8"),headers={'Cache-Control':'no-store'})


@app.get("/api/royal")
async def royal_data():
    g = guild()
    if g is None:
        return {"online": False, "membros": [], "influencers": [], "staff": [], "apoio": [],
                "beneficios": [{"nome": n, "descricao": d, "emoji": e} for n,d,e in BENEFITS],
                "insignias": insignias(), "error": "Sincronização com o Discord indisponível."}
    def group(entry):
        name, rid, desc, symbol = entry
        return {"nome": name, "id": str(rid), "descricao": desc, "simbolo": symbol,
                "pessoas": members_of(g, rid)}
    members = members_of(g, OFC_ID)
    influencers = members_of(g, INFLUENCER_ID)
    try:
        pool = await profile_db()
        ids = list({int(m['id']) for m in members + influencers})
        if ids:
            profiles = await pool.fetch('SELECT user_id,display_name,bio,title,motto,color,link,badge_a,badge_b,signature FROM royal_site_profiles WHERE user_id=ANY($1::bigint[])',ids)
            indexed = {str(p['user_id']): {k:p[k] for k in ('display_name','bio','title','motto','color','link','badge_a','badge_b','signature')} for p in profiles}
            for m in members + influencers:
                m['perfil'] = indexed.get(m['id'])
    except Exception:
        LOG.warning('Perfis públicos temporariamente indisponíveis',exc_info=True)
    return {"online": True, "guild": g.name,
            "membros": members, "influencers": influencers,
            "staff": [group(r) for r in STAFF], "apoio": [group(r) for r in OTHER],
            "beneficios": [{"nome": n, "descricao": d, "emoji": e} for n,d,e in BENEFITS],
            "insignias": insignias()}


def insignias():
    # A configuração oficial é importada do cog, sem duplicar IDs ou descrições.
    try:
        from cogs.insignias_royal import INSIGNIAS
        return [{"nome": i["nome"], "cargo_id": str(i["cargo_id"]),
                 "emoji": i["emoji"], "descricao": i["descricao_curta"],
                 "destaque": i["nome"] in {"Bruna", "Pietra", "Kananda", "Tatah", "Lívia", "Livia", "Nathy"}}
                for i in INSIGNIAS]
    except Exception:
        LOG.exception("Não foi possível carregar as insígnias do cog")
        return []


@app.get("/api/royal/membro/{user_id}")
async def royal_member(user_id: int):
    g = guild()
    if g is None:
        raise HTTPException(503, "Discord indisponível")
    m = g.get_member(user_id)
    if m is None:
        try:
            m = await g.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden):
            raise HTTPException(404, "Membro não encontrado")
        except discord.HTTPException:
            raise HTTPException(503, "Discord temporariamente indisponível")
    data = member_data(m)
    try:
        pool = await profile_db()
        profile = await pool.fetchrow('SELECT display_name, bio, title, motto, color, link, badge_a, badge_b, signature FROM royal_site_profiles WHERE user_id=$1', user_id)
        data['perfil'] = dict(profile) if profile else None
    except Exception:
        LOG.warning('Perfil indisponível na consulta', exc_info=True)
        data['perfil'] = None
    data["oficial"] = any(r.id == OFC_ID for r in m.roles)
    data["influencer"] = any(r.id == INFLUENCER_ID for r in m.roles)
    data["insignias"] = [i for i in insignias() if int(i["cargo_id"]) in {r.id for r in m.roles}]
    return data


# Discord OAuth2: conta verificada, sem credenciais administrativas no navegador.
@app.get('/auth/discord')
async def oauth_start():
    client_id, _, redirect_uri = oauth_config()
    state = secrets.token_urlsafe(32)
    signed = signing().dumps(state)
    query = urlencode({'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code', 'scope':'identify', 'state':state, 'prompt':'consent'})
    result = RedirectResponse('https://discord.com/oauth2/authorize?' + query)
    result.set_cookie('royal_oauth_state', signed, httponly=True, secure=True, samesite='lax', max_age=600, path='/')
    return result


@app.get('/auth/callback')
async def oauth_callback(request: Request, code: str = '', state: str = ''):
    client_id, client_secret, redirect_uri = oauth_config()
    try:
        expected = signing().loads(request.cookies.get('royal_oauth_state',''), max_age=600)
        if not secrets.compare_digest(state, expected): raise ValueError('state mismatch')
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        raise HTTPException(400, 'Autenticação expirada ou inválida.')
    if not code: raise HTTPException(400, 'Código OAuth ausente.')
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
        async with session.post('https://discord.com/api/v10/oauth2/token', data={'client_id':client_id,'client_secret':client_secret,'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri}) as res:
            if res.status != 200: raise HTTPException(401,'Autorização Discord recusada.')
            token = (await res.json()).get('access_token')
        async with session.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {token}'}) as res:
            if res.status != 200: raise HTTPException(401,'Não foi possível identificar a conta.')
            account = await res.json()
    uid = int(account['id'])
    g = guild()
    if g is None: raise HTTPException(503,'Servidor Discord indisponível.')
    try:
        member = g.get_member(uid) or await g.fetch_member(uid)
    except (discord.HTTPException, discord.NotFound, discord.Forbidden):
        raise HTTPException(403, 'Entre no servidor da Família Royal para editar seu perfil.')
    pool = await profile_db()
    raw = secrets.token_urlsafe(48)
    await pool.execute("INSERT INTO royal_site_sessions (user_id, token_hash, expires_at) VALUES ($1,$2,NOW()+INTERVAL '7 days')", uid, hashlib.sha256(raw.encode()).hexdigest())
    cookie = signing().dumps({'id':str(uid),'secret':raw})
    result = RedirectResponse('/#meu-perfil',status_code=303)
    result.set_cookie('royal_session', cookie, httponly=True, secure=True, samesite='lax', max_age=604800, path='/')
    result.delete_cookie('royal_oauth_state',path='/')
    return result


@app.get('/api/royal/me')
async def my_profile(request: Request):
    uid=await authenticated(request, require=False)
    if not uid: return {'authenticated':False}
    g=guild()
    if not g: raise HTTPException(503,'Servidor Discord indisponível.')
    try: member=g.get_member(uid) or await g.fetch_member(uid)
    except discord.HTTPException: raise HTTPException(403,'Membro não encontrado no servidor.')
    pool=await profile_db()
    row=await pool.fetchrow('SELECT display_name,bio,title,motto,color,link,badge_a,badge_b,signature FROM royal_site_profiles WHERE user_id=$1',uid)
    return {'authenticated':True,'member':member_data(member),'profile':dict(row) if row else {'display_name':'','bio':'','title':'','motto':'','color':'gold','link':'','badge_a':'','badge_b':'','signature':''}}


@app.put('/api/royal/me')
async def update_profile(request: Request):
    uid=await authenticated(request)
    origin=request.headers.get('origin','').rstrip('/')
    config_origin = ''
    redirect_uri = oauth_status()['redirect_uri']
    if redirect_uri.startswith('https://'):
        u = urlsplit(redirect_uri)
        config_origin = f'{u.scheme}://{u.netloc}'
    # O Railway publica o serviço sob HTTPS, mas internamente usa host/proxy diferentes.
    # A origem permitida é sempre o domínio de retorno cadastrado no Discord.
    if not origin or not config_origin or origin != config_origin:
        raise HTTPException(403,'Origem não autorizada. Confira DISCORD_REDIRECT_URI e o domínio do site.')
    try: data=await request.json()
    except Exception: raise HTTPException(400,'JSON inválido.')
    if not isinstance(data, dict): raise HTTPException(400,'Formato inválido.')
    def clean(key, length):
        value=data.get(key, '')
        if not isinstance(value, str) or len(value)>length: raise HTTPException(422,f'Campo {key} inválido (limite: {length}).')
        return ''.join(ch for ch in value.strip() if ch.isprintable() and ch not in '<>')
    name=clean('display_name',48); bio=clean('bio',420); title=clean('title',50); motto=clean('motto',120); color=clean('color',16); link=clean('link',240); badge_a=clean('badge_a',24); badge_b=clean('badge_b',24); signature=clean('signature',80)
    if color not in ('gold','ivory','rose','onyx'): raise HTTPException(422,'Tema inválido.')
    if link:
        try:
            parsed = urlsplit(link)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(ch.isspace() for ch in link):
                raise ValueError('invalid URL')
        except (ValueError, TypeError):
            raise HTTPException(422,'Utilize um link HTTPS válido.')
    pool=await profile_db()
    await pool.execute("""INSERT INTO royal_site_profiles (user_id,display_name,bio,title,motto,color,link,badge_a,badge_b,signature)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
       ON CONFLICT(user_id) DO UPDATE SET display_name=$2,bio=$3,title=$4,motto=$5,color=$6,link=$7,
       badge_a=$8,badge_b=$9,signature=$10,updated_at=NOW()""",
       uid,name,bio,title,motto,color,link,badge_a,badge_b,signature)
    return {'ok':True}


@app.post('/auth/logout')
async def logout(request:Request):
    uid=await authenticated(request,require=False)
    if uid:
        try:
            token=signing().loads(request.cookies.get('royal_session',''))
            pool=await profile_db()
            await pool.execute('DELETE FROM royal_site_sessions WHERE token_hash=$1',hashlib.sha256(token['secret'].encode()).hexdigest())
        except (BadSignature, KeyError, HTTPException): pass
    resp=JSONResponse({'ok':True})
    resp.delete_cookie('royal_session',path='/')
    return resp


# Endereços legados: sem autenticação administrativa, apenas redirecionamento público.
for legacy, target in [('/membros', '/#membros'), ('/hierarquia', '/#equipe'),
                       ('/perfil', '/#meu-perfil'), ('/conta', '/#meu-perfil'),
                       ('/painel', '/'), ('/login', '/'), ('/logout', '/')]:
    async def redirect(destination=target):
        return RedirectResponse(destination, status_code=302)
    app.add_api_route(legacy, redirect, methods=['GET'], include_in_schema=False)


async def start_painel(client: discord.Client):
    global _bot
    _bot = client
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")),
                            log_level="warning", proxy_headers=True, forwarded_allow_ips="*")
    asyncio.create_task(uvicorn.Server(config).serve(), name="royal_public_portal")
    LOG.info("Portal público Royal iniciado, sem painel administrativo")
