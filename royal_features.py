"""Família Royal · recursos persistentes do portal.

Não concede cargos do Discord: insígnias web são reconhecimentos internos, separados
em banco. A autenticação continua sendo a sessão OAuth2 do painel.py.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

LOG = logging.getLogger('royal.features')
_LOCK = asyncio.Lock()
_READY = False
_ACCENTS = {'gold', 'crimson', 'amethyst', 'ice', 'emerald'}
_FRAMES = {'gold', 'silver', 'phoenix', 'neon'}
_FX = {'sparks', 'glow', 'flames', 'none'}
_REACTIONS = {'👑', '🔥', '⚔️'}
_SOCIALS = ('instagram', 'youtube', 'tiktok', 'twitch', 'github', 'roblox', 'site')

SCHEMA = '''
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS slug VARCHAR(64);
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS frame VARCHAR(16) NOT NULL DEFAULT 'gold';
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS fx VARCHAR(16) NOT NULL DEFAULT 'sparks';
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS banner_id BIGINT;
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS socials JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS games TEXT NOT NULL DEFAULT '';
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS birthday VARCHAR(5) NOT NULL DEFAULT '';
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS badge_slots JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE royal_site_profiles ADD COLUMN IF NOT EXISTS suspended BOOLEAN NOT NULL DEFAULT FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS royal_site_profiles_slug_idx ON royal_site_profiles(slug);
CREATE TABLE IF NOT EXISTS royal_media (
 id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, kind TEXT NOT NULL,
 mime TEXT NOT NULL, bytes BYTEA NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_badges (
 id BIGSERIAL PRIMARY KEY, name VARCHAR(60) NOT NULL, icon VARCHAR(12) NOT NULL DEFAULT '✦',
 description VARCHAR(300) NOT NULL DEFAULT '', rarity VARCHAR(24) NOT NULL DEFAULT 'Rara',
 secret BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_badge_awards (
 badge_id BIGINT NOT NULL REFERENCES royal_badges(id) ON DELETE CASCADE,
 user_id BIGINT NOT NULL, granted_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(badge_id,user_id)
);
CREATE TABLE IF NOT EXISTS royal_xp (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, points INTEGER NOT NULL,
 reason VARCHAR(28) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS royal_xp_rank_idx ON royal_xp(user_id,created_at);
CREATE TABLE IF NOT EXISTS royal_events (
 id BIGSERIAL PRIMARY KEY, title VARCHAR(90) NOT NULL, description VARCHAR(700) NOT NULL DEFAULT '',
 starts_at TIMESTAMPTZ NOT NULL, image_id BIGINT, created_by BIGINT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_rsvps (
 event_id BIGINT NOT NULL REFERENCES royal_events(id) ON DELETE CASCADE,
 user_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(event_id,user_id)
);
CREATE TABLE IF NOT EXISTS royal_posts (
 id BIGSERIAL PRIMARY KEY, kind VARCHAR(20) NOT NULL DEFAULT 'noticia',
 title VARCHAR(95) NOT NULL, body VARCHAR(1800) NOT NULL,
 created_by BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_talents (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, title VARCHAR(90) NOT NULL,
 category VARCHAR(28) NOT NULL, image_id BIGINT, url VARCHAR(350),
 likes INTEGER NOT NULL DEFAULT 0, approved BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_talent_likes (
 talent_id BIGINT NOT NULL REFERENCES royal_talents(id) ON DELETE CASCADE,
 user_id BIGINT NOT NULL, PRIMARY KEY(talent_id,user_id)
);
CREATE TABLE IF NOT EXISTS royal_profile_reactions (
 target_id BIGINT NOT NULL, user_id BIGINT NOT NULL, emoji VARCHAR(8) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(target_id,user_id)
);
CREATE TABLE IF NOT EXISTS royal_follows (
 target_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(target_id,user_id)
);
CREATE TABLE IF NOT EXISTS royal_guestbook (
 id BIGSERIAL PRIMARY KEY, target_id BIGINT NOT NULL, author_id BIGINT NOT NULL,
 body VARCHAR(300) NOT NULL, approved BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_notifications (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, message VARCHAR(250) NOT NULL,
 seen BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royal_growth_snapshots (
 day DATE PRIMARY KEY, members INTEGER NOT NULL, staff INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS royal_visits (
 target_id BIGINT NOT NULL, visitor_id BIGINT NOT NULL, date DATE NOT NULL DEFAULT CURRENT_DATE,
 PRIMARY KEY(target_id,visitor_id,date)
);
CREATE TABLE IF NOT EXISTS royal_admin_audit (
 id BIGSERIAL PRIMARY KEY, actor_id BIGINT NOT NULL, action VARCHAR(48) NOT NULL,
 detail VARCHAR(450) NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

async def initialize(pool):
    global _READY
    if _READY: return
    async with _LOCK:
        if not _READY:
            # profile_db() must create the original profiles table before this migration.
            await pool.execute(SCHEMA)
            await pool.execute("""INSERT INTO royal_badges(name,icon,description,rarity,secret)
                SELECT 'Chama Oculta','🔥','Descobriu o segredo da Fênix Real.','Épica',TRUE
                WHERE NOT EXISTS(SELECT 1 FROM royal_badges WHERE name='Chama Oculta' AND secret=TRUE)""")
            _READY = True


def clean(data, name, limit, *, optional=True):
    value = data.get(name, '')
    if not isinstance(value, str) or len(value) > limit or (not optional and not value.strip()):
        raise HTTPException(422, f'Campo {name} inválido (máximo {limit} caracteres).')
    return ''.join(c for c in value.strip() if c.isprintable() or c in '\n\t')


def safe_https(url):
    if not url: return ''
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None,443):
            raise ValueError
    except ValueError:
        raise HTTPException(422, 'Use um endereço HTTPS válido.')
    return url


def slugify(value):
    import unicodedata
    s = unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()
    return re.sub(r'-+', '-', re.sub('[^a-z0-9-]', '-', s)).strip('-')[:42]


def iso(value):
    return value.isoformat() if value else None


def asdict(row):
    return dict(row) if row else None


def profile_fields(row):
    if not row: return {}
    o=dict(row)
    for k in ('socials','badge_slots'):
        if isinstance(o.get(k),str): o[k]=json.loads(o[k])
    o.pop('user_id',None)
    for k in ('created_at','updated_at'):
        if k in o: o[k]=iso(o[k])
    return o


def level_for(xp):
    level=max(1,int((max(0,xp)/110)**.5)+1)
    tiers=[(25000,'Rei / Rainha'),(10000,'Duque'),(5000,'Conde'),(2000,'Barão'),(500,'Cavaleiro')]
    return {'xp':xp,'level':level,'tier':next((t for minimum,t in tiers if xp>=minimum),'Plebeu'),
            'next_xp':110*level*level,'prev_xp':110*(level-1)*(level-1)}


def install(app, *, get_pool, authenticated, guild, member_data, insignias, staff_ids, public_redirect):
    async def pool():
        p=await get_pool()
        await initialize(p)
        return p

    async def current(req, required=True):
        uid=await authenticated(req, require=required)
        if not uid: return None
        g=guild()
        if not g: raise HTTPException(503,'Discord indisponível.')
        m=g.get_member(uid)
        if not m:
            try: m=await g.fetch_member(uid)
            except Exception: raise HTTPException(403,'É necessário estar no servidor Royal.')
        return m

    def is_staff(m):
        g=guild()
        return bool(m and ((g and g.owner_id == m.id) or any(r.id in staff_ids for r in m.roles)))

    async def staff(req):
        m=await current(req)
        if not is_staff(m): raise HTTPException(403,'Acesso exclusivo à equipe Royal.')
        return m

    def write_origin(req):
        # CSRF: browser form/fetch must send exact Origin and custom content type.
        origin=req.headers.get('origin','').rstrip('/')
        url=public_redirect()
        redirect=urlsplit(url)
        allowed=f'{redirect.scheme}://{redirect.netloc}' if redirect.scheme=='https' else ''
        if not origin or not allowed or origin!=allowed:
            raise HTTPException(403,'Origem não autorizada. Verifique DISCORD_REDIRECT_URI.')

    async def body(req):
        write_origin(req)
        try: data=await req.json()
        except Exception: raise HTTPException(400,'JSON inválido.')
        if not isinstance(data,dict): raise HTTPException(400,'Formato inválido.')
        return data

    async def notify(p, uid, message):
        await p.execute('INSERT INTO royal_notifications(user_id,message) VALUES($1,$2)',uid,message[:250])

    async def audit(p, m, action, detail=''):
        await p.execute('INSERT INTO royal_admin_audit(actor_id,action,detail) VALUES($1,$2,$3)',m.id,action,detail[:450])

    async def add_xp(p, uid, n, reason, *, cooldown=None):
        if cooldown:
            # Last activity is checked from DB, so it works across bot restarts.
            result=await p.fetchval("""INSERT INTO royal_xp(user_id,points,reason)
                SELECT $1,$2,$3 WHERE NOT EXISTS(
                SELECT 1 FROM royal_xp WHERE user_id=$1 AND reason=$3
                AND created_at > now()-($4::int * interval '1 second')) RETURNING id""",uid,n,reason,cooldown)
        else:
            result=await p.fetchval('INSERT INTO royal_xp(user_id,points,reason) VALUES($1,$2,$3) RETURNING id',uid,n,reason)
        return bool(result)

    async def profile(p,uid):
        return await p.fetchrow('SELECT * FROM royal_site_profiles WHERE user_id=$1',uid)

    async def stats(p,uid):
        xp=await p.fetchval('SELECT COALESCE(SUM(points),0) FROM royal_xp WHERE user_id=$1',uid)
        rank=await p.fetchval('''SELECT COUNT(*)+1 FROM (SELECT user_id,SUM(points) score FROM royal_xp GROUP BY user_id
            HAVING SUM(points)>$1) q''',xp)
        return {**level_for(xp),'rank':rank}

    async def badges(p,uid,roles):
        role_ids={str(r.id) for r in roles}
        official=[{'id':f'role:{b["cargo_id"]}','name':b['nome'],'icon':b['emoji'],
                   'rarity':'Oficial','description':b['descricao'],'official':True}
                  for b in insignias() if b['cargo_id'] in role_ids]
        rows=await p.fetch('''SELECT b.id,b.name,b.icon,b.description,b.rarity FROM royal_badges b JOIN royal_badge_awards a
            ON a.badge_id=b.id WHERE a.user_id=$1 ORDER BY a.created_at DESC''',uid)
        return official+[{'id':f'web:{r["id"]}','name':r['name'],'icon':r['icon'],
                'rarity':r['rarity'],'description':r['description'],'official':False} for r in rows]

    async def public_record(p, m, viewer=None):
        r=await profile(p,m.id)
        if r and (not r['is_public'] or r['suspended']) and (not viewer or (viewer.id!=m.id and not is_staff(viewer))):
            raise HTTPException(404,'Este perfil não está público.')
        info=member_data(m)
        earned=await badges(p,m.id,m.roles)
        o=profile_fields(r)
        # Staff suspension is not leaked to normal visitors.
        o.pop('suspended',None)
        counts=await p.fetchrow('''SELECT (SELECT COUNT(*) FROM royal_follows WHERE target_id=$1) followers,
            (SELECT COUNT(*) FROM royal_visits WHERE target_id=$1) visits''',m.id)
        reacts=await p.fetch('SELECT emoji,COUNT(*) total FROM royal_profile_reactions WHERE target_id=$1 GROUP BY emoji',m.id)
        o['badges']=earned; o['stats']=await stats(p,m.id);o['followers']=counts['followers'];o['visits']=counts['visits']
        o['reactions']={r['emoji']:r['total'] for r in reacts};o['joined_at']=info.get('ingresso_servidor')
        return {**info,'oficial':any(r.id==1554367619463913582 for r in m.roles),'perfil':o}

    @app.get('/api/kingdom/me')
    async def get_me(req:Request):
        m=await current(req,False)
        if not m: return {'authenticated':False}
        p=await pool()
        obj=await public_record(p,m,m)
        obj['perfil']['suspended']=bool(dict(await profile(p,m.id) or {}).get('suspended',False))
        obj['authenticated']=True;obj['staff']=is_staff(m)
        obj['notifications']=[dict(r) for r in await p.fetch('SELECT id,message,seen,created_at FROM royal_notifications WHERE user_id=$1 ORDER BY id DESC LIMIT 12',m.id)]
        for note in obj['notifications']: note['created_at']=iso(note['created_at'])
        return obj

    @app.put('/api/kingdom/me')
    async def save_me(req:Request):
        m=await current(req); d=await body(req);p=await pool()
        old=await profile(p,m.id)
        if old and old['suspended']: raise HTTPException(403,'A edição deste perfil está suspensa.')
        name=clean(d,'display_name',48);title=clean(d,'title',50);bio=clean(d,'bio',420)
        motto=clean(d,'motto',120);games=clean(d,'games',220);signature=clean(d,'signature',80)
        link=safe_https(clean(d,'link',240));birthday=clean(d,'birthday',5)
        if birthday and not re.fullmatch(r'(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])',birthday):
            raise HTTPException(422,'Aniversário deve ser MM-DD.')
        accent=clean(d,'color',16) or 'gold';frame=clean(d,'frame',16) or 'gold';fx=clean(d,'fx',16) or 'sparks'
        if accent not in _ACCENTS or frame not in _FRAMES or fx not in _FX: raise HTTPException(422,'Personalização inválida.')
        socials=d.get('socials',{});slots=d.get('badge_slots',[])
        if not isinstance(socials,dict) or set(socials)-set(_SOCIALS):raise HTTPException(422,'Redes sociais inválidas.')
        socials={k:safe_https(clean({'url':v},'url',240)) for k,v in socials.items() if v}
        if not isinstance(slots,list) or len(slots)>3 or len(set(slots))!=len(slots):raise HTTPException(422,'Escolha até três insígnias diferentes.')
        earned={b['id'] for b in await badges(p,m.id,m.roles)}
        if any(not isinstance(s,str) or s not in earned for s in slots):raise HTTPException(422,'Insígnia não conquistada.')
        if not isinstance(d.get('is_public',True),bool):raise HTTPException(422,'Visibilidade inválida.')
        banner=d.get('banner_id')
        if banner is not None and not isinstance(banner,int):raise HTTPException(422,'Banner inválido.')
        if banner and not await p.fetchval('SELECT 1 FROM royal_media WHERE id=$1 AND owner_id=$2 AND kind=$3',banner,m.id,'banner'):
            raise HTTPException(422,'Banner não pertence a este perfil.')
        slug=(old and old['slug']) or (slugify(name or m.display_name)+'-'+str(m.id)[-6:])
        await p.execute('''INSERT INTO royal_site_profiles(user_id,display_name,title,bio,motto,games,signature,link,
            color,frame,fx,socials,birthday,badge_slots,is_public,banner_id,slug)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14::jsonb,$15,$16,$17)
            ON CONFLICT(user_id) DO UPDATE SET display_name=$2,title=$3,bio=$4,motto=$5,games=$6,signature=$7,
            link=$8,color=$9,frame=$10,fx=$11,socials=$12::jsonb,birthday=$13,badge_slots=$14::jsonb,
            is_public=$15,banner_id=$16,updated_at=now()''',m.id,name,title,bio,motto,games,signature,link,
            accent,frame,fx,json.dumps(socials),birthday,json.dumps(slots),d['is_public'],banner,slug)
        await add_xp(p,m.id,25,'perfil',cooldown=86400)
        return {'ok':True,'slug':slug}

    @app.get('/api/kingdom/membro/{slug}')
    async def get_member(slug:str,req:Request):
        p=await pool();g=guild()
        if not g:raise HTTPException(503,'Discord indisponível.')
        if slug.isdecimal(): uid=int(slug)
        else: uid=await p.fetchval('SELECT user_id FROM royal_site_profiles WHERE slug=$1',slug)
        if not uid:raise HTTPException(404,'Membro não encontrado.')
        m=g.get_member(uid)
        if not m:
            try:m=await g.fetch_member(uid)
            except Exception: raise HTTPException(404,'Membro não encontrado.')
        viewer=await current(req,False)
        result=await public_record(p,m,viewer)
        if viewer and viewer.id!=uid:
            await p.execute('INSERT INTO royal_visits(target_id,visitor_id) VALUES($1,$2) ON CONFLICT DO NOTHING',uid,viewer.id)
        msgs=await p.fetch('''SELECT id,author_id,body,created_at FROM royal_guestbook
            WHERE target_id=$1 AND approved=TRUE ORDER BY id DESC LIMIT 20''',uid)
        result['recados']=[{'id':r['id'],'author_id':str(r['author_id']),'body':r['body'],'created_at':iso(r['created_at'])} for r in msgs]
        result['following']=bool(viewer and await p.fetchval('SELECT 1 FROM royal_follows WHERE target_id=$1 AND user_id=$2',uid,viewer.id))
        return result

    @app.post('/api/kingdom/media')
    async def upload_media(req:Request,kind:str='banner'):
        m=await current(req);write_origin(req)
        if kind not in ('banner','talent','event'):raise HTTPException(422,'Tipo de imagem inválido.')
        p=await pool()
        if (await p.fetchval('SELECT COUNT(*) FROM royal_media WHERE owner_id=$1',m.id))>=35:
            raise HTTPException(429,'Limite de imagens atingido. Peça ajuda à equipe.')
        if req.headers.get('content-type','').split(';')[0] not in ('image/jpeg','image/png','image/webp'):
            raise HTTPException(415,'Envie JPG, PNG ou WebP.')
        if int(req.headers.get('content-length','0') or '0')>4_000_000:raise HTTPException(413,'Imagem muito grande (máximo 4 MB).')
        raw=await req.body()
        if len(raw)>4_000_000:raise HTTPException(413,'Imagem muito grande.')
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width*im.height>30_000_000:raise ValueError('dimensions')
                im=ImageOps.exif_transpose(im).convert('RGB')
                if kind=='banner':
                    im=ImageOps.fit(im,(1400,480),centering=(.5,.5))
                else:
                    im.thumbnail((1500,1000))
                out=io.BytesIO();im.save(out,'WEBP',quality=83,method=5)
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            raise HTTPException(422,'Imagem corrompida ou inválida.')
        ident=await p.fetchval('INSERT INTO royal_media(owner_id,kind,mime,bytes) VALUES($1,$2,$3,$4) RETURNING id',m.id,kind,'image/webp',out.getvalue())
        return {'id':ident,'url':f'/api/kingdom/media/{ident}'}

    @app.get('/api/kingdom/media/{image_id}')
    async def read_media(image_id:int):
        p=await pool();r=await p.fetchrow('SELECT mime,bytes FROM royal_media WHERE id=$1',image_id)
        if not r:raise HTTPException(404,'Imagem não encontrada.')
        return Response(content=bytes(r['bytes']),media_type=r['mime'],headers={'Cache-Control':'public, max-age=604800','X-Content-Type-Options':'nosniff'})

    @app.get('/api/kingdom/ranking')
    async def rankings(period:str='geral'):
        p=await pool()
        if period not in ('geral','semanal','mensal'):raise HTTPException(422,'Período inválido.')
        window={'geral':'','semanal':"AND created_at>=now()-interval '7 days'",'mensal':"AND created_at>=now()-interval '30 days'"}[period]
        rows=await p.fetch(f'SELECT user_id,SUM(points)::int xp FROM royal_xp WHERE TRUE {window} GROUP BY user_id ORDER BY xp DESC,user_id LIMIT 40')
        g=guild();out=[]
        for r in rows:
            m=g.get_member(r['user_id']) if g else None
            if m and not m.bot:out.append({'member':member_data(m),'xp':r['xp'],**level_for(r['xp'])})
        return {'period':period,'ranking':out,'tiers':['Plebeu','Cavaleiro','Barão','Conde','Duque','Rei / Rainha']}

    @app.get('/api/kingdom/badges')
    async def catalog():
        p=await pool();rows=await p.fetch('''SELECT b.id,b.name,b.icon,b.description,b.rarity,COUNT(a.user_id)::int holders
          FROM royal_badges b LEFT JOIN royal_badge_awards a ON a.badge_id=b.id WHERE b.secret=FALSE
          GROUP BY b.id ORDER BY b.id DESC''')
        g=guild(); official=[]
        for item in insignias():
            entry=dict(item)
            role=g.get_role(int(entry['cargo_id'])) if g else None
            entry['holders']=len([m for m in role.members if not m.bot]) if role else 0
            official.append(entry)
        return {'badges':[dict(r) for r in rows], 'official':official}

    @app.get('/api/kingdom/events')
    async def events(req:Request):
        p=await pool();me=await current(req,False)
        rows=await p.fetch('''SELECT e.*,COUNT(r.user_id)::int attendees FROM royal_events e LEFT JOIN royal_rsvps r
         ON r.event_id=e.id GROUP BY e.id ORDER BY e.starts_at DESC LIMIT 50''')
        names_by_event={}
        g=guild()
        if rows and g:
            records=await p.fetch('SELECT event_id,user_id FROM royal_rsvps WHERE event_id=ANY($1::bigint[]) ORDER BY created_at LIMIT 700',[r['id'] for r in rows])
            for record in records:
                arr=names_by_event.setdefault(record['event_id'],[])
                if len(arr)>=12:continue
                member=g.get_member(record['user_id'])
                if member:arr.append({'id':str(member.id),'nome':member.display_name,'avatar':str(member.display_avatar.replace(size=64).url)})
        return {'events':[{'id':r['id'],'title':r['title'],'description':r['description'],'starts_at':iso(r['starts_at']),
              'image_id':r['image_id'],'attendees':r['attendees'],'attendee_list':names_by_event.get(r['id'],[])} for r in rows],
                'joined':[r['event_id'] for r in await p.fetch('SELECT event_id FROM royal_rsvps WHERE user_id=$1',me.id)] if me else []}

    @app.post('/api/kingdom/events/{event_id}/rsvp')
    async def rsvp(event_id:int,req:Request):
        m=await current(req);d=await body(req);p=await pool()
        if not await p.fetchval('SELECT 1 FROM royal_events WHERE id=$1',event_id):raise HTTPException(404,'Evento não encontrado.')
        if d.get('join',True):
            created=await p.fetchval('INSERT INTO royal_rsvps(event_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING user_id',event_id,m.id)
            if created: await add_xp(p,m.id,15,'evento',cooldown=3600)
        else:await p.execute('DELETE FROM royal_rsvps WHERE event_id=$1 AND user_id=$2',event_id,m.id)
        return {'ok':True}

    @app.get('/api/kingdom/posts')
    async def posts():
        p=await pool();rows=await p.fetch('SELECT id,kind,title,body,created_at FROM royal_posts ORDER BY id DESC LIMIT 30')
        return {'posts':[dict(r,created_at=iso(r['created_at'])) for r in rows]}

    @app.get('/api/kingdom/birthdays')
    async def birthdays():
        p=await pool();month=datetime.now(timezone.utc).month
        rows=await p.fetch("SELECT user_id,display_name,birthday FROM royal_site_profiles WHERE birthday LIKE $1 AND is_public=TRUE AND suspended=FALSE ORDER BY birthday",f'{month:02d}-%')
        return {'birthdays':[{'id':str(r['user_id']),'name':r['display_name'],'day':r['birthday'][3:]} for r in rows]}

    @app.get('/api/kingdom/talents')
    async def talents(req:Request):
        p=await pool();me=await current(req,False)
        rows=await p.fetch('''SELECT t.*, (SELECT COUNT(*) FROM royal_talent_likes WHERE talent_id=t.id)::int likes
           FROM royal_talents t WHERE approved=TRUE ORDER BY t.id DESC LIMIT 40''')
        return {'talents':[{'id':r['id'],'user_id':str(r['user_id']),'title':r['title'],'category':r['category'],
          'image_id':r['image_id'],'url':r['url'],'likes':r['likes']} for r in rows],
          'liked':[r['talent_id'] for r in await p.fetch('SELECT talent_id FROM royal_talent_likes WHERE user_id=$1',me.id)] if me else []}

    @app.post('/api/kingdom/talents')
    async def submit_talent(req:Request):
        m=await current(req);d=await body(req);p=await pool()
        title=clean(d,'title',90,optional=False);cat=clean(d,'category',28)
        if cat not in ('arte','gameplay','video','montagem','outro'):raise HTTPException(422,'Categoria inválida.')
        url=safe_https(clean(d,'url',350));image_id=d.get('image_id')
        if not url and not image_id:raise HTTPException(422,'Informe uma imagem ou um link.')
        if image_id and not await p.fetchval("SELECT 1 FROM royal_media WHERE id=$1 AND owner_id=$2 AND kind='talent'",image_id,m.id):
            raise HTTPException(422,'Imagem não autorizada.')
        await p.execute('INSERT INTO royal_talents(user_id,title,category,image_id,url) VALUES($1,$2,$3,$4,$5)',m.id,title,cat,image_id,url or None)
        return {'ok':True,'message':'Enviado para avaliação da equipe.'}

    @app.post('/api/kingdom/talents/{tid}/like')
    async def like_talent(tid:int,req:Request):
        m=await current(req);await body(req);p=await pool()
        if not await p.fetchval('SELECT 1 FROM royal_talents WHERE id=$1 AND approved=TRUE',tid):raise HTTPException(404,'Publicação não encontrada.')
        created=await p.fetchval('INSERT INTO royal_talent_likes(talent_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING user_id',tid,m.id)
        if created:await add_xp(p,m.id,2,'talento',cooldown=3600)
        return {'liked':True}

    @app.post('/api/kingdom/member/{uid}/react')
    async def react(uid:int,req:Request):
        m=await current(req);d=await body(req);emoji=d.get('emoji');p=await pool()
        if emoji not in _REACTIONS:raise HTTPException(422,'Reação inválida.')
        await p.execute('''INSERT INTO royal_profile_reactions(target_id,user_id,emoji) VALUES($1,$2,$3)
             ON CONFLICT(target_id,user_id) DO UPDATE SET emoji=EXCLUDED.emoji''',uid,m.id,emoji)
        return {'ok':True}

    @app.post('/api/kingdom/member/{uid}/follow')
    async def follow(uid:int,req:Request):
        m=await current(req);d=await body(req);p=await pool()
        if m.id==uid:raise HTTPException(422,'Não é possível seguir a si mesmo.')
        if d.get('follow',True):
            created=await p.fetchval('INSERT INTO royal_follows(target_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING user_id',uid,m.id)
            if created:await notify(p,uid,'Um integrante começou a seguir seu perfil Royal.')
        else:await p.execute('DELETE FROM royal_follows WHERE target_id=$1 AND user_id=$2',uid,m.id)
        return {'ok':True}

    @app.post('/api/kingdom/member/{uid}/recado')
    async def guestbook(uid:int,req:Request):
        m=await current(req);d=await body(req);p=await pool();s=clean(d,'body',300,optional=False)
        if m.id==uid:raise HTTPException(422,'Não é possível enviar recados ao próprio perfil.')
        if await p.fetchval("SELECT COUNT(*) FROM royal_guestbook WHERE author_id=$1 AND created_at>now()-interval '1 day'",m.id)>=5:
            raise HTTPException(429,'Limite diário de recados atingido.')
        await p.execute('INSERT INTO royal_guestbook(target_id,author_id,body) VALUES($1,$2,$3)',uid,m.id,s)
        await notify(p,uid,'Você recebeu um novo recado para aprovar no perfil.')
        return {'ok':True,'message':'Recado enviado para aprovação.'}

    @app.get('/api/kingdom/recados-pendentes')
    async def pending_messages(req:Request):
        m=await current(req);p=await pool()
        rows=await p.fetch('SELECT id,author_id,body,created_at FROM royal_guestbook WHERE target_id=$1 AND approved=FALSE ORDER BY id DESC LIMIT 30',m.id)
        return {'messages':[{'id':r['id'],'author_id':str(r['author_id']),'body':r['body'],'created_at':iso(r['created_at'])} for r in rows]}

    @app.post('/api/kingdom/recados/{rid}')
    async def approve_recado(rid:int,req:Request):
        m=await current(req);d=await body(req);p=await pool()
        rec=await p.fetchrow('SELECT target_id,author_id FROM royal_guestbook WHERE id=$1',rid)
        if not rec:raise HTTPException(404,'Recado não encontrado.')
        if rec['target_id'] != m.id and not is_staff(m):raise HTTPException(403,'Sem permissão.')
        if d.get('approve',False):
            await p.execute('UPDATE royal_guestbook SET approved=TRUE WHERE id=$1',rid)
            await notify(p,rec['author_id'],'Seu recado foi aprovado no perfil Royal.')
        else: await p.execute('DELETE FROM royal_guestbook WHERE id=$1',rid)
        return {'ok':True}

    @app.get('/api/kingdom/admin')
    async def dashboard(req:Request):
        await staff(req);p=await pool()
        cnt=await p.fetchrow('''SELECT
         (SELECT COUNT(*) FROM royal_site_profiles)::int profiles,
         (SELECT COUNT(*) FROM royal_talents WHERE approved=FALSE)::int pending_talents,
         (SELECT COUNT(*) FROM royal_visits)::int visits,
         (SELECT COUNT(*) FROM royal_events)::int events''')
        recent=await p.fetch('SELECT id,user_id,title,category,image_id FROM royal_talents WHERE approved=FALSE ORDER BY id DESC LIMIT 25')
        activity=await p.fetch("SELECT created_at::date day,COUNT(*)::int total FROM royal_xp WHERE created_at>now()-interval '14 days' GROUP BY day ORDER BY day")
        most=await p.fetch('SELECT target_id,COUNT(*)::int total FROM royal_visits GROUP BY target_id ORDER BY total DESC LIMIT 8')
        logs=await p.fetch('SELECT actor_id,action,detail,created_at FROM royal_admin_audit ORDER BY id DESC LIMIT 20')
        growth=await p.fetch('SELECT day,members,staff FROM royal_growth_snapshots ORDER BY day DESC LIMIT 30')
        return {'stats':dict(cnt),'pending_talents':[dict(r,user_id=str(r['user_id'])) for r in recent],
           'activity':[{'day':iso(r['day']),'total':r['total']} for r in activity],
           'growth':[{'day':iso(r['day']),'members':r['members'],'staff':r['staff']} for r in reversed(growth)],
           'popular':[{'user_id':str(r['target_id']),'visits':r['total']} for r in most],
           'audit':[{'actor_id':str(r['actor_id']),'action':r['action'],'detail':r['detail'],'created_at':iso(r['created_at'])} for r in logs]}

    @app.post('/api/kingdom/admin/talent/{tid}')
    async def approve_talent(tid:int,req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        r=await p.fetchrow('SELECT user_id FROM royal_talents WHERE id=$1',tid)
        if not r:raise HTTPException(404,'Publicação não encontrada.')
        if d.get('approve',False):
            await p.execute('UPDATE royal_talents SET approved=TRUE WHERE id=$1',tid)
            await notify(p,r['user_id'],'Sua publicação foi aprovada em Talentos Royal.')
            await add_xp(p,r['user_id'],70,'publicacao')
        else: await p.execute('DELETE FROM royal_talents WHERE id=$1',tid)
        await audit(p,m,'talento_moderação',str(tid))
        return {'ok':True}

    @app.post('/api/kingdom/admin/event')
    async def create_event(req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        title=clean(d,'title',90,optional=False);desc=clean(d,'description',700)
        try: dt=datetime.fromisoformat(d.get('starts_at','').replace('Z','+00:00'))
        except (ValueError,AttributeError): raise HTTPException(422,'Data do evento inválida.')
        if dt.tzinfo is None:raise HTTPException(422,'Informe data com fuso horário.')
        image_id=d.get('image_id')
        if image_id is not None and (not isinstance(image_id,int) or not await p.fetchval(
             "SELECT 1 FROM royal_media WHERE id=$1 AND owner_id=$2 AND kind='event'",image_id,m.id)):
            raise HTTPException(422,'Imagem do evento não autorizada.')
        eid=d.get('id')
        if eid:
            await p.execute('UPDATE royal_events SET title=$1,description=$2,starts_at=$3,image_id=COALESCE($5,image_id) WHERE id=$4',title,desc,dt,int(eid),image_id)
        else:
            eid=await p.fetchval('INSERT INTO royal_events(title,description,starts_at,created_by,image_id) VALUES($1,$2,$3,$4,$5) RETURNING id',title,desc,dt,m.id,image_id)
        await audit(p,m,'evento',str(eid))
        return {'ok':True,'id':eid}

    @app.post('/api/kingdom/admin/post')
    async def publish(req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        kind=clean(d,'kind',20)
        if kind not in ('aviso','noticia','destaque'):raise HTTPException(422,'Tipo inválido.')
        title=clean(d,'title',95,optional=False);text=clean(d,'body',1800,optional=False)
        pid=d.get('id')
        if pid:await p.execute('UPDATE royal_posts SET kind=$1,title=$2,body=$3 WHERE id=$4',kind,title,text,int(pid))
        else:pid=await p.fetchval('INSERT INTO royal_posts(kind,title,body,created_by) VALUES($1,$2,$3,$4) RETURNING id',kind,title,text,m.id)
        await audit(p,m,'publicação',str(pid))
        return {'ok':True,'id':pid}

    @app.delete('/api/kingdom/admin/event/{event_id}')
    async def delete_event(event_id:int,req:Request):
        m=await staff(req);write_origin(req);p=await pool()
        await p.execute('DELETE FROM royal_events WHERE id=$1',event_id)
        await audit(p,m,'evento_removido',str(event_id))
        return {'ok':True}

    @app.delete('/api/kingdom/admin/post/{post_id}')
    async def delete_post(post_id:int,req:Request):
        m=await staff(req);write_origin(req);p=await pool()
        await p.execute('DELETE FROM royal_posts WHERE id=$1',post_id)
        await audit(p,m,'publicação_removida',str(post_id))
        return {'ok':True}

    @app.post('/api/kingdom/admin/badge')
    async def create_badge(req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        name=clean(d,'name',60,optional=False);icon=clean(d,'icon',12) or '✦'
        desc=clean(d,'description',300);rarity=clean(d,'rarity',24)
        if rarity not in ('Comum','Rara','Épica','Lendária'):raise HTTPException(422,'Raridade inválida.')
        bid=d.get('id')
        if bid:await p.execute('UPDATE royal_badges SET name=$1,icon=$2,description=$3,rarity=$4 WHERE id=$5 AND secret=FALSE',name,icon,desc,rarity,int(bid))
        else:bid=await p.fetchval('INSERT INTO royal_badges(name,icon,description,rarity) VALUES($1,$2,$3,$4) RETURNING id',name,icon,desc,rarity)
        await audit(p,m,'insígnia_criada',str(bid));return {'ok':True,'id':bid}

    @app.post('/api/kingdom/admin/award')
    async def grant_badge(req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        try:bid=int(d['badge_id']);uid=int(d['user_id'])
        except (KeyError,ValueError,TypeError):raise HTTPException(422,'Selecione insígnia e usuário.')
        if not await p.fetchval('SELECT 1 FROM royal_badges WHERE id=$1 AND secret=FALSE',bid):raise HTTPException(404,'Insígnia não encontrada.')
        g=guild()
        if not g or not (g.get_member(uid)):
            try:
                if not g: raise RuntimeError
                await g.fetch_member(uid)
            except Exception: raise HTTPException(422,'Usuário não pertence à comunidade Royal.')
        if d.get('grant',True):
            await p.execute('INSERT INTO royal_badge_awards(badge_id,user_id,granted_by) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',bid,uid,m.id)
            await notify(p,uid,'Você recebeu uma nova insígnia Royal!')
        else: await p.execute('DELETE FROM royal_badge_awards WHERE badge_id=$1 AND user_id=$2',bid,uid)
        await audit(p,m,'insígnia_entregue',f'{bid}:{uid}');return {'ok':True}

    @app.post('/api/kingdom/admin/profile/{uid}')
    async def moderate_profile(uid:int,req:Request):
        m=await staff(req);d=await body(req);p=await pool()
        if uid==m.id:raise HTTPException(422,'Não é possível moderar o próprio perfil.')
        action=d.get('action')
        if action not in ('suspend','release','clear_banner','clear_bio'):
            raise HTTPException(422,'Ação de moderação inválida.')
        if action in ('suspend','release'):
            await p.execute('INSERT INTO royal_site_profiles(user_id,suspended) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET suspended=$2',uid,action=='suspend')
        elif action=='clear_banner':
            await p.execute('UPDATE royal_site_profiles SET banner_id=NULL,updated_at=now() WHERE user_id=$1',uid)
        elif action=='clear_bio':
            await p.execute("UPDATE royal_site_profiles SET bio='',updated_at=now() WHERE user_id=$1",uid)
        await audit(p,m,'perfil_moderado',f'{uid}:{action}')
        await notify(p,uid,'A equipe atualizou a moderação do seu perfil Royal.')
        return {'ok':True}

    @app.post('/api/kingdom/notifications/read')
    async def mark_notifications(req:Request):
        m=await current(req);await body(req);p=await pool()
        await p.execute('UPDATE royal_notifications SET seen=TRUE WHERE user_id=$1',m.id)
        return {'ok':True}

    @app.post('/api/kingdom/easter-egg')
    async def easter(req:Request):
        m=await current(req);await body(req);p=await pool()
        badge=await p.fetchval("SELECT id FROM royal_badges WHERE name='Chama Oculta' AND secret=TRUE")
        first=await p.fetchval('INSERT INTO royal_badge_awards(badge_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING badge_id',badge,m.id)
        if first:await notify(p,m.id,'Você despertou a Chama Oculta da Fênix!')
        return {'ok':True,'new':bool(first)}

    return initialize


async def award_message(bot, message):
    """Listener opcional, limitado para impedir farm por mensagens curtas."""
    if message.author.bot or not message.guild or len((message.content or '').strip())<12:
        return
    from painel import GUILD_ID, profile_db
    if message.guild.id!=GUILD_ID: return
    p=await profile_db();await initialize(p)
    try:
        await p.execute("""INSERT INTO royal_xp(user_id,points,reason)
             SELECT $1,5,'discord' WHERE NOT EXISTS(SELECT 1 FROM royal_xp
             WHERE user_id=$1 AND reason='discord' AND created_at>now()-interval '5 minutes')""",message.author.id)
    except Exception:
        LOG.exception('Falha ao contabilizar XP do Discord')
