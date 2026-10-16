"""Mesa do Diabo — Contratos reformulados e Pacto das Duas Almas / Cuphead.

Extensão aditiva para bot Discord discord.py >= 2.4 com bot.pool (asyncpg).
Preserva o Cassino 2.2, suas carteiras/transações e os resgates do 2.0 anterior.
Não envolve apostas, perdas de SC ou pagamentos reais.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from utils import cassino_db as db
from utils import cassino_extras as extras

LOG = logging.getLogger("sants.contratos")
COR = 0xA71B27
COR_OURO = 0xDDAA54
COR_TREVAS = 0x29212F
BONUS_FINAL = 30
DUO_PREMIO = 75
DUO_BONUS_PERFEITO = 15
DUO_ETAPAS = 4
DUO_MAX_ERROS = 2
DUO_CONVITE_MINUTOS = 2
DUO_JOGO_MINUTOS = 20
BANNER_MESA = ""  # URL https://... opcional, não afeta a lógica

# O limite das missões do Cassino é gerenciado pelo próprio Cassino 2.2.
# Todas as provas abaixo são gratuitas. Não há débito na carteira.
ROTAS = {
    "brasa": {
        "nome": "Pacto das Chamas",
        "emoji": "🔥",
        "titulo": "A Alma Incendiada",
        "descricao": "O Diabo exige coragem. Pode errar duas vezes.",
        "etapas": 2,
        "erros": 2,
        "premio": 60,
        "castigo": 10,
        "falas": [
            "'Ora, ora... mais uma alma querendo desafiar minhas chamas!'",
            "'Se resistir ao calor, talvez eu considere nosso acordo.'",
        ],
    },
    "dados": {
        "nome": "Pacto do King Dice",
        "emoji": "🎲",
        "titulo": "O Jogador Astuto",
        "descricao": "O braço direito do Diabo preparou três enigmas. Um erro permitido.",
        "etapas": 3,
        "erros": 1,
        "premio": 85,
        "castigo": 15,
        "falas": [
            "'Heh-heh! King Dice preparou uma mesa especialmente para você.'",
            "'Cuidado com suas respostas. Nesta casa, cada erro tem seu preço.'",
        ],
    },
    "tridente": {
        "nome": "Pacto do Tridente",
        "emoji": "🔱",
        "titulo": "O Devedor de Almas",
        "descricao": "Quatro provas do próprio Diabo. Nenhum erro permitido.",
        "etapas": 4,
        "erros": 0,
        "premio": 115,
        "castigo": 0,
        "falas": [
            "'ASSINE AQUI! Mas não chore quando o chão começar a tremer!'",
            "'Quatro provas. Uma oportunidade. Surpreenda-me, mortal.'",
        ],
    },
}

CLAUSULAS = (
    ("Cláusula da Lua Rubra", "Uma noite de contratos antigos. Vitórias perfeitas recebem **+10 SC**."),
    ("Cláusula do Tinteiro", "A tinta não perdoa erros. Vitórias perfeitas recebem **+10 SC**."),
    ("Cláusula do Salão", "O Diabo observa cada assinatura. Vitórias perfeitas recebem **+10 SC**."),
    ("Cláusula do Trono", "Quem encara o trono sem hesitar recebe **+10 SC** por vitória perfeita."),
)
BONUS_PERFEITO = 10
BONUS_STREAK_3 = 20
BONUS_STREAK_7 = 50

# Cada resposta está codificada no servidor e nunca no custom_id dos botões.
# Os conjuntos são diferentes para cada rota; uma seleção diária determinística
# dá variedade sem perder o progresso quando o bot reinicia.
QUESTOES = {
    "brasa": [
        ("No universo de Cuphead, o que Mugman é de Cuphead?", ("Irmão", "Professor", "Inimigo", "Tio"), 0),
        ("Qual item é essencial para vencer os chefes de Cuphead?", ("Atenção aos padrões", "Uma senha secreta", "Um mapa de metrô", "Uma armadura invisível"), 0),
        ("Sou devorado pelo fogo, mas também alimento sua chama. O que sou?", ("Água", "Lenha", "Gelo", "Areia"), 1),
        ("O que acontece ao terminar uma fase desafiadora?", ("Uma vitória", "O relógio para", "Tudo desaparece", "O jogo fecha"), 0),
        ("Cuphead e Mugman são conhecidos pelo formato de suas...", ("Botas", "Cabeças", "Luvas", "Capas"), 1),
        ("Qual símbolo costuma representar fogo e determinação?", ("Chama", "Floco de neve", "Âncora", "Livro"), 0),
    ],
    "dados": [
        ("Quem administra o cassino do Diabo em Cuphead?", ("King Dice", "Mugman", "Elder Kettle", "Ms. Chalice"), 0),
        ("Qual destes é um número par?", ("7", "11", "14", "19"), 2),
        ("Se há três cartas e você pega uma, quantas ficam na mesa?", ("Uma", "Duas", "Três", "Quatro"), 1),
        ("O que deve fazer primeiro diante de um pacto suspeito?", ("Assinar sem ler", "Ler as cláusulas", "Fechar os olhos", "Esconder o papel"), 1),
        ("Num conjunto de quatro dados, cada dado tem quantas faces normalmente?", ("4", "5", "6", "8"), 2),
        ("Em Cuphead, quem trabalha diretamente para o Diabo?", ("King Dice", "Sally Stageplay", "Cagney Carnation", "Goopy Le Grande"), 0),
        ("Se 5 fichas valem 10 pontos cada, qual a soma?", ("15", "25", "50", "100"), 2),
        ("Qual é a melhor defesa contra uma charada enganosa?", ("Responder rápido", "Ignorar o enunciado", "Ler com atenção", "Escolher ao acaso"), 2),
    ],
    "tridente": [
        ("Quem é o grande antagonista de Cuphead?", ("King Dice", "O Diabo", "Elder Kettle", "Mugman"), 1),
        ("Qual é o nome do jogo que inspirou este episódio?", ("Cuphead", "Undertale", "Hollow Knight", "Celeste"), 0),
        ("No jogo, Cuphead e Mugman precisam recuperar...", ("Moedas perdidas", "Contratos de almas", "Coroas", "Livros da escola"), 1),
        ("Quem oferece a grande aposta no cassino do jogo?", ("O Diabo", "Uma carta misteriosa", "Uma tempestade", "Um dragão"), 0),
        ("Qual destes números é o resultado de 7 × 8?", ("54", "56", "58", "64"), 1),
        ("Qual opção completa 2, 4, 8, 16, ...?", ("18", "20", "24", "32"), 3),
        ("Se uma regra permite zero erros, quantas respostas erradas podem ser dadas?", ("Nenhuma", "Uma", "Duas", "Três"), 0),
        ("Qual dos dois costuma acompanhar Cuphead nas aventuras originais?", ("Mugman", "King Dice", "O Diabo", "Chef Saltbaker"), 0),
        ("Qual é o próximo número em 1, 1, 2, 3, 5, ...?", ("6", "7", "8", "10"), 2),
    ],
}

SQL = """
-- Tabela preservada da primeira versão. Nenhum DROP/DELETE é executado.
CREATE TABLE IF NOT EXISTS sants_contratos20_diario (
    user_id BIGINT NOT NULL,
    dia DATE NOT NULL,
    selo_resgatado BOOLEAN NOT NULL DEFAULT FALSE,
    final_resgatado BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, dia)
);
-- Progresso do episódio DELUXE, isolado dos dados legados.
CREATE TABLE IF NOT EXISTS sants_contratos20_aventuras (
    user_id BIGINT NOT NULL,
    dia DATE NOT NULL,
    guild_id BIGINT NOT NULL,
    rota TEXT NOT NULL,
    etapa SMALLINT NOT NULL DEFAULT 0,
    tentativa SMALLINT NOT NULL DEFAULT 0,
    erros SMALLINT NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'andamento',
    premio BIGINT NOT NULL DEFAULT 0,
    bonus_serie BIGINT NOT NULL DEFAULT 0,
    serie INTEGER NOT NULL DEFAULT 0,
    iniciado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ,
    PRIMARY KEY (user_id, dia)
);
ALTER TABLE sants_contratos20_aventuras ADD COLUMN IF NOT EXISTS tentativa SMALLINT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_sants_contratos20_aventuras_ranking
 ON sants_contratos20_aventuras (dia DESC, estado);
"""


# Sistema independente das aventuras solo, sem alterar ou apagar dados existentes.
SQL_DUPLAS = """
CREATE TABLE IF NOT EXISTS sants_pactos_dupla (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    dia DATE NOT NULL,
    criador_id BIGINT NOT NULL,
    parceiro_id BIGINT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'convite',
    etapa SMALLINT NOT NULL DEFAULT 0,
    erros SMALLINT NOT NULL DEFAULT 0,
    tentativa INTEGER NOT NULL DEFAULT 0,
    premio_individual INTEGER NOT NULL DEFAULT 0,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    aceito_em TIMESTAMPTZ,
    expira_em TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '2 minutes'),
    finalizado_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pactos_dupla_historico
    ON sants_pactos_dupla (guild_id, dia DESC, estado);
CREATE INDEX IF NOT EXISTS idx_pactos_dupla_convites
    ON sants_pactos_dupla (criador_id, parceiro_id, estado, expira_em);
CREATE TABLE IF NOT EXISTS sants_pactos_dupla_participantes (
    user_id BIGINT NOT NULL,
    dia DATE NOT NULL,
    pacto_id BIGINT NOT NULL REFERENCES sants_pactos_dupla(id),
    PRIMARY KEY (user_id, dia)
);
CREATE INDEX IF NOT EXISTS idx_pactos_dupla_participante_pacto
    ON sants_pactos_dupla_participantes(pacto_id);
"""

ETAPAS_DUPLA = (
    ("🕯️ O Tinteiro", "O Diabo exige que uma alma dê o primeiro passo."),
    ("🎲 A Mesa de King Dice", "A segunda alma encara o mestre dos dados."),
    ("🔥 A Fornalha", "O fogo volta a testar quem fez o convite."),
    ("🔱 A Última Assinatura", "Só o convidado pode selar este acordo."),
)

# Banco de perguntas por etapa, com as respostas somente no servidor.
PROVAS_DUPLA = (
    (
        ("O que torna um contrato válido nesta mesa?", ("Uma única assinatura", "O aceite das duas almas", "Uma aposta em SC", "Uma mensagem vazia"), 1),
        ("Quem comanda o cassino da história de Cuphead?", ("King Dice", "Elder Kettle", "Mugman", "Sally Stageplay"), 0),
        ("O que o Diabo guarda em seus contratos?", ("Receitas", "Mapas", "Almas", "Troféus esportivos"), 2),
        ("O que uma boa dupla deve fazer primeiro?", ("Ignorar o parceiro", "Ler as regras", "Fechar a janela", "Sair do canal"), 1),
    ),
    (
        ("Quem é o braço direito do Diabo?", ("Goopy", "King Dice", "Beppi", "Mugman"), 1),
        ("Dois dados comuns têm quantas faces no total?", ("10", "12", "16", "20"), 1),
        ("Qual é o próximo número: 3, 6, 12, 24...?", ("27", "30", "48", "72"), 2),
        ("Se o contrato tem quatro etapas e duas foram cumpridas, faltam...", ("Uma", "Três", "Quatro", "Duas"), 3),
    ),
    (
        ("O fogo exige combustível: qual opção é combustível?", ("Gelo", "Lenha", "Água", "Pedra"), 1),
        ("No universo de Cuphead, Mugman é o quê de Cuphead?", ("Irmão", "Chefe", "Inimigo", "Vizinho"), 0),
        ("Qual atitude evita uma armadilha numa negociação?", ("Não ler", "Assinar no escuro", "Examinar cláusulas", "Ignorar o acordo"), 2),
        ("Qual é o dobro de 17?", ("30", "32", "34", "36"), 2),
    ),
    (
        ("Quem deve concordar para que a dupla ganhe a recompensa?", ("Só o criador", "Só o Diabo", "Ambos os jogadores", "Qualquer espectador"), 2),
        ("Quantos jogadores formam uma dupla?", ("Um", "Dois", "Três", "Quatro"), 1),
        ("No jogo Cuphead, o Diabo quer recuperar...", ("Contratos de almas", "Instrumentos", "Trilhos", "Bandeiras"), 0),
        ("Se a última cláusula depende do parceiro, o correto é...", ("Esperar sua vez", "Tentar agir por ele", "Enviar spam", "Reiniciar a partida"), 0),
    ),
)


def prova_dupla(pacto_id: int, etapa: int, tentativa: int):
    """Seleção e embaralhamento determinísticos, restauráveis após reiniciar."""
    perguntas = PROVAS_DUPLA[etapa]
    pos = numero_estavel("dupla", pacto_id, etapa, tentativa) % len(perguntas)
    pergunta, opcoes, correta = perguntas[pos]
    ordem = sorted(range(4), key=lambda i: numero_estavel("dup-opt", pacto_id, etapa, tentativa, i))
    return pergunta, tuple(opcoes[i] for i in ordem), ordem.index(correta)


def responsavel_dupla(pacto, etapa: int) -> int:
    return pacto["criador_id"] if etapa % 2 == 0 else pacto["parceiro_id"]


class ErroPacto(Exception):
    """Violação amigável das regras; transação é revertida automaticamente."""



def hoje() -> datetime.date:
    return datetime.now(timezone.utc).date()


def numero_estavel(*partes: object) -> int:
    s = "|".join(map(str, partes)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(s).digest()[:8], "big")


def clausula_do_dia(dia) -> tuple[str, str]:
    return CLAUSULAS[numero_estavel("clausula", dia.isoformat()) % len(CLAUSULAS)]


def questao_da_vez(rota: str, uid: int, dia, etapa: int):
    perguntas = QUESTOES[rota]
    # Permutação de perguntas estável por usuário/dia/rota, sem repetição.
    indices = sorted(range(len(perguntas)), key=lambda i: numero_estavel("prova", uid, dia, rota, i))
    pergunta, opcoes, correta = perguntas[indices[etapa]]
    # Rotação estável da posição das respostas, evitando sempre letra A.
    ordem = sorted(range(4), key=lambda i: numero_estavel("alternativa", uid, dia, rota, etapa, i))
    return pergunta, tuple(opcoes[i] for i in ordem), ordem.index(correta)


def moeda(quantia: int) -> str:
    return f"{int(quantia):,}".replace(",", ".")


def narracao(rota: str, momento: str) -> str:
    dic = {
        "brasa": {
            "inicio": "*'Heh-heh! Quero ver sua coragem quando as chamas subirem!'*",
            "acerto": "*'Grrr... escapou dessa. Mas ainda não acabou!'*",
            "erro": "*'HA! Senti cheiro de medo! Ainda tem alguma chance?'*",
            "falha": "*'Sua coragem derreteu. Volte quando meu relógio zerar!'*",
            "vitoria": "*'COMO?! As minhas chamas não foram suficientes?!'*",
        },
        "dados": {
            "inicio": "*'King Dice! Traga o nosso convidado à mesa!'*",
            "acerto": "*'Nada mal, espertinho. A próxima prova vai ser melhor.'*",
            "erro": "*'King Dice, está vendo? Mais um que tropeça nas próprias cartas!'*",
            "falha": "*'O cassino agradece a visita. O pacto foi rasgado!'*",
            "vitoria": "*'King Dice... você deixou esse mortal vencer?!'*",
        },
        "tridente": {
            "inicio": "*'ASSINE, MORTAL! Nenhum erro. Nenhuma desculpa.'*",
            "acerto": "*'IMPOSSÍVEL! Meu tridente ainda não disse a última palavra!'*",
            "erro": "*'BAHAHA! Uma única falha era tudo de que eu precisava!'*",
            "falha": "*'SEU CONTRATO É MEU! ...até amanhã, é claro.'*",
            "vitoria": "*'NÃO! Um mero mortal venceu o próprio Diabo?!'*",
        },
    }
    return dic[rota][momento]


def base_embed(titulo: str, descricao: str, *, cor: int = COR) -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao[:4096], color=cor)
    e.set_footer(text="Família Sant's • Mesa do Diabo • Reinício diário às 00:00 UTC")
    return e


class PainelMesa(discord.ui.View):
    """Nova mesa limpa, permanente e distinta dos IDs da versão Deluxe."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Pacto solo", emoji="📜", style=discord.ButtonStyle.primary,
                       custom_id="sants:mesa:solo", row=0)
    async def solo(self, it, _):
        await self.cog.abrir_escolha(it)

    @discord.ui.button(label="Pacto em dupla", emoji="🤝", style=discord.ButtonStyle.danger,
                       custom_id="sants:mesa:dupla", row=0)
    async def dupla(self, it, _):
        await self.cog.escolher_parceiro(it)

    @discord.ui.button(label="Retomar", emoji="🎭", style=discord.ButtonStyle.secondary,
                       custom_id="sants:mesa:retomar", row=0)
    async def retomar(self, it, _):
        await self.cog.retomar_mesa(it)

    @discord.ui.button(label="Grimório", emoji="📖", style=discord.ButtonStyle.secondary,
                       custom_id="sants:mesa:grimorio", row=1)
    async def grimorio(self, it, _):
        await self.cog.meu_grimorio(it)

    @discord.ui.button(label="Recompensas", emoji="💰", style=discord.ButtonStyle.secondary,
                       custom_id="sants:mesa:recompensas", row=1)
    async def recompensas(self, it, _):
        await self.cog.menu_recompensas(it)

    @discord.ui.button(label="Regras", emoji="👁️", style=discord.ButtonStyle.secondary,
                       custom_id="sants:mesa:regras", row=1)
    async def regras(self, it, _):
        await self.cog.regras_mesa(it)


class MenuRecompensas(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label="Visitar o salão", emoji="🚪", style=discord.ButtonStyle.primary)
    async def visita(self, it, _):
        await self.cog.visitar(it)

    @discord.ui.button(label="Cobrar dívida", emoji="💰", style=discord.ButtonStyle.success)
    async def cobrar(self, it, _):
        await self.cog.cobrar_final(it)


class EscolherParceiro(discord.ui.View):
    """UserSelect devolve usuário; confirmação dos dois acontece pelo convite público."""
    def __init__(self, cog, criador_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.criador_id = criador_id
        menu = discord.ui.UserSelect(placeholder="Selecione quem vai assinar com você...", min_values=1, max_values=1)

        async def escolhido(it: discord.Interaction):
            if it.user.id != self.criador_id:
                return await it.response.send_message("🔒 Esta seleção não é sua.", ephemeral=True)
            await it.response.defer(ephemeral=True, thinking=True)
            await self.cog.criar_convite_dupla(it, menu.values[0].id)
        menu.callback = escolhido
        self.add_item(menu)


class BotaoDupla(discord.ui.DynamicItem[discord.ui.Button],
                 template=r"sants:dupla:(?P<acao>aceitar|recusar|jogar|status|cancelar|resp):(?P<id>\d+)(?::(?P<etapa>\d+))?(?::(?P<tentativa>\d+))?(?::(?P<resposta>\d+))?"):
    """Botão reconstituído por custom_id após reinício do bot."""
    INFO = {
        "aceitar": ("Aceitar pacto", "✍️", discord.ButtonStyle.success),
        "recusar": ("Recusar", "❌", discord.ButtonStyle.danger),
        "jogar": ("Responder prova", "🎲", discord.ButtonStyle.primary),
        "status": ("Ver andamento", "📜", discord.ButtonStyle.secondary),
        "cancelar": ("Romper pacto", "💀", discord.ButtonStyle.danger),
        "resp": ("Escolher", None, discord.ButtonStyle.secondary),
    }

    def __init__(self, acao: str, id_: int, etapa=None, tentativa=None, resposta=None, rotulo=None):
        titulo, emoji, estilo = self.INFO[acao]
        cid = f"sants:dupla:{acao}:{id_}"
        for valor in (etapa, tentativa, resposta):
            if valor is not None:
                cid += f":{int(valor)}"
        super().__init__(discord.ui.Button(label=rotulo or titulo, emoji=emoji,
                                           style=estilo, custom_id=cid))
        self.acao, self.id_ = acao, int(id_)
        self.etapa, self.tentativa, self.resposta = etapa, tentativa, resposta

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        conv = lambda k: int(match[k]) if match[k] is not None else None
        return cls(match["acao"], int(match["id"]), conv("etapa"), conv("tentativa"), conv("resposta"))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ContratosDiabo20")
        if cog is None:
            return await interaction.response.send_message("❌ A mesa está fechada no momento.", ephemeral=True)
        await cog.acao_dupla(interaction, self.acao, self.id_, self.etapa, self.tentativa, self.resposta)


def view_dupla(id_: int, estado: str) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    if estado == "convite":
        v.add_item(BotaoDupla("aceitar", id_))
        v.add_item(BotaoDupla("recusar", id_))
    elif estado == "ativo":
        v.add_item(BotaoDupla("jogar", id_))
        v.add_item(BotaoDupla("cancelar", id_))
    v.add_item(BotaoDupla("status", id_))
    return v

class PainelContratos(discord.ui.View):
    """Persistente, válido após reinício; nenhum progresso guardado na View."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Assinar pacto", emoji="📜", style=discord.ButtonStyle.danger,
                       custom_id="sants:contratos:assinar", row=0)
    async def assinar(self, it, _):
        await self.cog.abrir_escolha(it)

    @discord.ui.button(label="Continuar prova", emoji="🔱", style=discord.ButtonStyle.primary,
                       custom_id="sants:contratos:continuar", row=0)
    async def continuar(self, it, _):
        await self.cog.continuar(it)

    @discord.ui.button(label="Meu grimório", emoji="📖", style=discord.ButtonStyle.secondary,
                       custom_id="sants:contratos:grimorio", row=0)
    async def grimorio(self, it, _):
        await self.cog.meu_grimorio(it)

    @discord.ui.button(label="Visitar o salão", emoji="🚪", style=discord.ButtonStyle.secondary,
                       custom_id="sants:contratos:visita", row=1)
    async def visita(self, it, _):
        await self.cog.visitar(it)

    @discord.ui.button(label="Cobrar a dívida", emoji="💰", style=discord.ButtonStyle.success,
                       custom_id="sants:contratos:cobrar", row=1)
    async def cobrar(self, it, _):
        await self.cog.cobrar_final(it)

    @discord.ui.button(label="Cláusulas", emoji="👁️", style=discord.ButtonStyle.secondary,
                       custom_id="sants:contratos:clausulas", row=1)
    async def clausulas(self, it, _):
        await self.cog.ver_clausulas(it)


class PainelLegado(discord.ui.View):
    """Mantém vivos os botões dos painéis publicados na primeira versão."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Visitar o Salão", emoji="🚪", style=discord.ButtonStyle.primary,
                       custom_id="sants:contratos20:visita")
    async def visita(self, it, _):
        await self.cog.visitar(it)

    @discord.ui.button(label="Aceitar Selo", emoji="📜", style=discord.ButtonStyle.primary,
                       custom_id="sants:contratos20:selo")
    async def selo(self, it, _):
        await self.cog.abrir_escolha(it)

    @discord.ui.button(label="Recompensa Final", emoji="🎁", style=discord.ButtonStyle.success,
                       custom_id="sants:contratos20:final")
    async def final(self, it, _):
        await self.cog.cobrar_final(it)

    @discord.ui.button(label="Meu Progresso", emoji="📊", style=discord.ButtonStyle.secondary,
                       custom_id="sants:contratos20:status")
    async def status(self, it, _):
        await self.cog.meu_grimorio(it)


class EscolhaRotas(discord.ui.View):
    def __init__(self, cog, uid: int):
        super().__init__(timeout=180)
        self.cog, self.uid = cog, uid
        for rota, config in ROTAS.items():
            b = discord.ui.Button(label=config["nome"], emoji=config["emoji"],
                                  style=discord.ButtonStyle.danger if rota == "tridente" else discord.ButtonStyle.primary)
            async def callback(it: discord.Interaction, r=rota):
                if it.user.id != self.uid:
                    return await it.response.send_message("🔒 Este pacto não é seu.", ephemeral=True)
                await self.cog.assinar(it, r)
            b.callback = callback
            self.add_item(b)


class Respostas(discord.ui.View):
    def __init__(self, cog, uid: int, dia, rota: str, etapa: int, tentativa: int, opcoes: tuple[str, ...]):
        super().__init__(timeout=600)
        self.cog, self.uid, self.dia, self.rota, self.etapa, self.tentativa = cog, uid, dia, rota, etapa, tentativa
        for i, nome in enumerate(opcoes):
            b = discord.ui.Button(label=f"{chr(65+i)} • {nome}"[:80], style=discord.ButtonStyle.secondary,
                                  row=i // 2)
            async def callback(it: discord.Interaction, resposta=i):
                if it.user.id != self.uid:
                    return await it.response.send_message("🔒 Esta prova não é sua.", ephemeral=True)
                await self.cog.responder(it, self.dia, self.rota, self.etapa, self.tentativa, resposta)
            b.callback = callback
            self.add_item(b)


class ContratosDiabo20(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def pool(self):
        return getattr(self.bot, "pool", None)

    async def cog_load(self):
        if self.pool is None:
            raise RuntimeError("Contratos 2.0 DELUXE: bot.pool não configurado no main.py")
        db.configurar_pool(self.pool)
        await db.inicializar_tabelas(self.pool)
        await extras.inicializar_extras(self.pool)
        await self.pool.execute(SQL)
        await self.pool.execute(SQL_DUPLAS)
        self.bot.add_dynamic_items(BotaoDupla)
        self.bot.add_view(PainelMesa(self))
        self.bot.add_view(PainelContratos(self))
        self.bot.add_view(PainelLegado(self))
        LOG.info("Mesa do Diabo reformulada / duplas carregada; dados anteriores preservados")

    async def _garantir_legado(self, conn, uid, dia):
        await conn.execute("""
            INSERT INTO sants_contratos20_diario(user_id, dia) VALUES($1, $2)
            ON CONFLICT(user_id, dia) DO NOTHING
        """, uid, dia)

    async def _aventura(self, conn, uid, dia, *, lock=False):
        sql = "SELECT * FROM sants_contratos20_aventuras WHERE user_id=$1 AND dia=$2"
        if lock:
            sql += " FOR UPDATE"
        return await conn.fetchrow(sql, uid, dia)

    async def _creditar(self, conn, uid, quantia: int, motivo: str):
        if quantia <= 0:
            return
        await db.garantir_carteira(uid, conn)
        await conn.execute("""
            UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW() WHERE user_id=$1
        """, uid, quantia)
        await conn.execute("""
            INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
            VALUES($1,'credito',$2,$3)
        """, uid, quantia, motivo[:200])

    async def _estado(self, uid):
        dia = hoje()
        async with self.pool.acquire() as conn:
            aventura = await self._aventura(conn, uid, dia)
            lado = await conn.fetchrow("""
                SELECT visita, carta, premio_carta FROM sants_cassino_extras_diario
                WHERE user_id=$1 AND dia=$2
            """, uid, dia)
            legado = await conn.fetchrow("""
                SELECT selo_resgatado, final_resgatado FROM sants_contratos20_diario
                WHERE user_id=$1 AND dia=$2
            """, uid, dia)
        return dia, aventura, lado, legado

    def _painel_publico(self):
        e = base_embed(
            "😈 A MESA DO DIABO",
            "*'Heh-heh... um nome ou duas almas? Escolha o seu acordo.'*\n\n"
            "📜 **Pacto solo** — enfrente os desafios do Diabo.\n"
            "🤝 **Pacto em dupla** — convide alguém e enfrentem quatro provas juntos.\n"
            "📖 **Grimório** — consulte seu progresso, vitórias e recompensas.\n\n"
            "*Assine por sua conta e risco... mas suas moedas estão seguras.*",
            cor=COR,
        )
        if BANNER_MESA.startswith("https://"):
            e.set_image(url=BANNER_MESA)
        return e

    async def _enviar(self, it, *, embed=None, texto=None, view=None):
        # O followup permite tratar cliques demorados após defer, evita interação expirada.
        await it.followup.send(content=texto, embed=embed, view=view, ephemeral=True,
                               allowed_mentions=discord.AllowedMentions.none())

    async def abrir_escolha(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        dia, aventura, _, _ = await self._estado(it.user.id)
        if aventura:
            return await self._mostrar_aventura(it, aventura, dia)
        desc = "**'Heh-heh... assine um deles, se tiver coragem!'**\n\n"
        for _, r in ROTAS.items():
            desc += (f"**{r['emoji']} {r['nome']}**\n"
                     f"> {r['descricao']}\n"
                     f"> Vitória: **{r['premio']} SC** + **{BONUS_PERFEITO} SC** se não errar.\n\n")
        desc += ("**ATENÇÃO:** somente **um pacto por dia**. Se ultrapassar o limite de erros, "
                 "o pacto se encerra até amanhã. Não há cobrança nem perda de moedas.")
        await self._enviar(it, embed=base_embed("📜 ESCOLHA SEU PACTO", desc),
                           view=EscolhaRotas(self, it.user.id))

    async def assinar(self, it, rota):
        await it.response.defer(ephemeral=True, thinking=True)
        if rota not in ROTAS:
            return await self._enviar(it, texto="❌ Contrato desconhecido.")
        dia = hoje()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # A PK(user_id,dia) impede dois contratos simultâneos.
                await conn.execute("""
                    INSERT INTO sants_contratos20_aventuras(user_id,dia,guild_id,rota)
                    VALUES($1,$2,$3,$4) ON CONFLICT(user_id,dia) DO NOTHING
                """, it.user.id, dia, it.guild_id or 0, rota)
                aventura = await self._aventura(conn, it.user.id, dia, lock=True)
        if aventura["rota"] != rota:
            return await self._enviar(it, texto="📜 Você já assinou outro contrato hoje. O Diabo não aceita duas assinaturas!")
        await self._mostrar_aventura(it, aventura, dia)

    async def continuar(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        dia, aventura, _, _ = await self._estado(it.user.id)
        if not aventura:
            return await self._enviar(it, texto="📜 Você ainda não assinou um pacto. Clique em **Assinar pacto**.")
        await self._mostrar_aventura(it, aventura, dia)

    async def _mostrar_aventura(self, it, aventura, dia, aviso=""):
        rota = aventura["rota"]
        r = ROTAS[rota]
        etapa = int(aventura["etapa"])
        erros = int(aventura["erros"])
        tentativa = int(aventura["tentativa"])
        status = aventura["estado"]
        pref = f"{aviso}\n\n" if aviso else ""
        if status == "vencido":
            desc = (f"{pref}{narracao(rota, 'vitoria')}\n\n"
                    f"**{r['titulo']}** • CONTRATO CUMPRIDO ✅\n"
                    f"💰 Prêmio recebido: **{moeda(aventura['premio'])} SC**\n"
                    f"🔥 Sequência: **{aventura['serie']} dia(s)**\n"
                    "*Agora visite o salão, revele sua Carta do Destino e cobre a dívida final!*")
            return await self._enviar(it, embed=base_embed("🏆 ALMA RESGATADA!", desc, cor=COR_OURO))
        if status == "fracassado":
            desc = (f"{pref}{narracao(rota, 'falha')}\n\n"
                    "🩸 Seu contrato de hoje foi rasgado. **Nenhuma SC foi retirada.**\n"
                    "📜 Novo pacto disponível após o reinício diário (00:00 UTC).")
            return await self._enviar(it, embed=base_embed("💀 CONTRATO RASGADO", desc, cor=COR_TREVAS))
        if etapa >= r["etapas"]:
            LOG.error("Etapa inválida em aventura id=%s", aventura["user_id"])
            return await self._enviar(it, texto="❌ Ocorreu um erro de progresso. Avise a staff.")
        enunciado, opcoes, _ = questao_da_vez(rota, it.user.id, dia, tentativa)
        caixas = "▰" * etapa + "▱" * (r["etapas"] - etapa)
        e = base_embed(f"{r['emoji']} {r['nome'].upper()} | PROVA {etapa + 1}/{r['etapas']}",
            f"{pref}{narracao(rota, 'inicio') if etapa == 0 else r['falas'][1]}\n\n"
            f"**🕯️ {enunciado}**\n\n"
            "*O Diabo observa a sua escolha...*\n\n"
            f"📜 `{caixas}` • **{etapa}/{r['etapas']}** provadas\n"
            f"💀 Erros: **{erros}/{r['erros'] + 1}** (falha ao ultrapassar o limite)\n"
            f"💰 Recompensa-base: **{r['premio']} SC**",
            cor=COR)
        await self._enviar(it, embed=e, view=Respostas(self, it.user.id, dia, rota, etapa, tentativa, opcoes))

    async def responder(self, it, dia, rota: str, etapa: int, tentativa: int, resposta: int):
        await it.response.defer(ephemeral=True, thinking=True)
        uid = it.user.id
        if dia != hoje():
            return await self._enviar(it, texto="⌛ O dia mudou. O Diabo já renovou os contratos! Abra o painel novamente.")
        if rota not in ROTAS or resposta not in (0, 1, 2, 3):
            return await self._enviar(it, texto="❌ Resposta inválida.")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                aventura = await self._aventura(conn, uid, dia, lock=True)
                if not aventura:
                    return await self._enviar(it, texto="📜 Assine um contrato antes de iniciar a prova.")
                if (aventura["rota"] != rota or int(aventura["etapa"]) != etapa
                        or int(aventura["tentativa"]) != tentativa
                        or aventura["estado"] != "andamento"):
                    return await self._enviar(it, texto="⌛ Essa pergunta já foi respondida. Clique em **Continuar prova** no painel.")
                _, opcoes, correta = questao_da_vez(rota, uid, dia, tentativa)
                acertou = resposta == correta
                r = ROTAS[rota]
                erros = int(aventura["erros"]) + (0 if acertou else 1)
                avancou = etapa + 1 if acertou else etapa
                fracassou = erros > r["erros"]
                venceu = acertou and avancou >= r["etapas"]
                novo_status = "fracassado" if fracassou else "vencido" if venceu else "andamento"
                premio = 0
                bonus_serie = 0
                serie = 0
                if venceu:
                    premio = max(0, r["premio"] - erros * r["castigo"])
                    if erros == 0:
                        premio += BONUS_PERFEITO
                    # A linha de ontem é imutável após o fechamento do dia.
                    anterior = await conn.fetchval("""
                        SELECT serie FROM sants_contratos20_aventuras
                        WHERE user_id=$1 AND dia=$2 AND estado='vencido'
                    """, uid, dia - timedelta(days=1))
                    serie = int(anterior or 0) + 1
                    if serie % 7 == 0:
                        bonus_serie = BONUS_STREAK_7
                    elif serie % 3 == 0:
                        bonus_serie = BONUS_STREAK_3
                    premio += bonus_serie
                    # Um só caminho de crédito, atomicamente com a mudança de estado.
                    await self._creditar(conn, uid, premio, f"Contratos Diabo 2.0 DELUXE • {rota} • {dia}")
                    await self._garantir_legado(conn, uid, dia)
                    # Marcação do selo antigo, SEM pagar novamente +20 SC.
                    await conn.execute("""
                        UPDATE sants_contratos20_diario SET selo_resgatado=TRUE
                        WHERE user_id=$1 AND dia=$2
                    """, uid, dia)
                await conn.execute("""
                    UPDATE sants_contratos20_aventuras
                    SET etapa=$3, erros=$4, estado=$5, premio=$6,
                        bonus_serie=$7, serie=$8, tentativa=tentativa+1,
                        finalizado_em=CASE WHEN $5='andamento' THEN NULL ELSE NOW() END
                    WHERE user_id=$1 AND dia=$2
                """, uid, dia, avancou, erros, novo_status, premio, bonus_serie, serie)
                resultado = await self._aventura(conn, uid, dia)
        if venceu:
            info = f"✅ Prova correta! **+{moeda(premio)} SC** creditadas no saldo compartilhado."
            if bonus_serie:
                info += f" Bônus de sequência: **+{bonus_serie} SC**."
        elif fracassou:
            info = f"❌ Resposta errada! A resposta correta era **{opcoes[correta]}**. Seu pacto foi rasgado."
        elif acertou:
            info = "✅ Resposta correta! O Diabo range os dentes... Próxima prova liberada."
        else:
            info = (f"❌ Resposta incorreta! A resposta certa era **{opcoes[correta]}**. "
                    f"Você ainda possui **{max(0, r['erros'] + 1 - erros)} tentativa(s)** antes de perder o pacto.")
        await self._mostrar_aventura(it, resultado, dia, aviso=info)

    async def visitar(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        try:
            ganhou, saldo = await extras.coletar_visita(it.user.id)
            fala = ("'Olhe quem voltou ao salão! Meu tapete vermelho não é de graça... "
                    "Brincadeirinha. Hoje é por conta da casa!'" if ganhou else
                    "'Você já visitou meu salão hoje. Não seja ganancioso!'")
            await self._enviar(it, embed=base_embed("🚪 VISITA AO SALÃO DO DIABO",
                f"*{fala}*\n\n" + ("✅ **+40 SC** recebidas.\n" if ganhou else "⌛ Recompensa já resgatada.\n")
                + f"💰 Saldo atual: **{moeda(saldo)} SC**"))
        except Exception:
            LOG.exception("Erro ao visitar o salão")
            await self._enviar(it, texto="❌ Não consegui registrar sua visita. Verifique o extrato antes de tentar de novo.")

    async def cobrar_final(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        dia = hoje()
        uid = it.user.id
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._garantir_legado(conn, uid, dia)
                legado = await conn.fetchrow("""
                    SELECT final_resgatado FROM sants_contratos20_diario
                    WHERE user_id=$1 AND dia=$2 FOR UPDATE
                """, uid, dia)
                aventura = await self._aventura(conn, uid, dia)
                lado = await conn.fetchrow("""
                    SELECT visita, carta FROM sants_cassino_extras_diario
                    WHERE user_id=$1 AND dia=$2
                """, uid, dia)
                requisitos = {
                    "📜 Vencer o pacto": bool(aventura and aventura["estado"] == "vencido"),
                    "🚪 Visitar o salão": bool(lado and lado["visita"]),
                    "🃏 Revelar Carta do Destino no cassino": bool(lado and lado["carta"]),
                }
                if legado["final_resgatado"]:
                    mensagem = "⌛ Você já recebeu a recompensa final de hoje, inclusive se a resgatou na versão anterior."
                elif not all(requisitos.values()):
                    mensagem = "🔒 **Você ainda deve cláusulas ao Diabo:**\n\n" + "\n".join(
                        ("✅" if feito else "⬜") + f" {nome}" for nome, feito in requisitos.items())
                else:
                    await conn.execute("""
                        UPDATE sants_contratos20_diario SET final_resgatado=TRUE
                        WHERE user_id=$1 AND dia=$2
                    """, uid, dia)
                    await self._creditar(conn, uid, BONUS_FINAL, f"Contratos Diabo 2.0 • dívida final • {dia}")
                    mensagem = ("😈 *'NÃO! Você cumpriu todas as cláusulas! "
                                "King Dice, pague o que devo...'*\n\n"
                                f"💰 **+{BONUS_FINAL} SC** creditadas. Você está livre... por hoje.")
        await self._enviar(it, embed=base_embed("💰 COBRANÇA DA DÍVIDA", mensagem, cor=COR_OURO))

    async def ver_clausulas(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        nome, efeito = clausula_do_dia(hoje())
        desc = (f"**👁️ {nome}**\n> {efeito}\n\n"
                "**I. Uma assinatura por dia.** Depois de assinar, a rota não pode ser trocada.\n"
                "**II. Responda às provas.** Acertos avançam; erros consomem a tolerância do pacto.\n"
                "**III. Uma falha encerra o contrato até amanhã.** Sem perda de moedas ou punição real.\n"
                "**IV. Vitória libera recompensa.** Acertos perfeitos dão **+10 SC**; erros reduzem "
                "a recompensa apenas nas rotas que aceitam falhas.\n"
                "**V. A sequência de vitórias conta.** Bônus de **+20 SC** a cada 3 vitórias consecutivas, "
                "e **+50 SC** a cada 7.\n"
                "**VI. Dívida final.** Visita + Carta do Destino + pacto vencido = **+30 SC**.\n"
                "**VII. Resgate diário.** Reinício às **00:00 UTC**; nenhuma aposta ou SC em risco.")
        await self._enviar(it, embed=base_embed("📜 AS SETE CLÁUSULAS DO DIABO", desc, cor=COR_OURO))

    async def _embed_grimorio(self, uid):
        dia, aventura, lado, legado = await self._estado(uid)
        async with self.pool.acquire() as conn:
            passado = await conn.fetch("""
                SELECT dia, rota, estado, premio FROM sants_contratos20_aventuras
                WHERE user_id=$1 ORDER BY dia DESC LIMIT 7
            """, uid)
            vitorias = await conn.fetchval("""
                SELECT COUNT(*) FROM sants_contratos20_aventuras
                WHERE user_id=$1 AND estado='vencido'
            """, uid)
        async with self.pool.acquire() as conn:
            dupla_hoje = await conn.fetchrow("""
                SELECT p.* FROM sants_pactos_dupla p
                WHERE p.dia=$1 AND (p.criador_id=$2 OR p.parceiro_id=$2)
                AND p.estado != 'convite'
                ORDER BY p.id DESC LIMIT 1
            """, dia, uid)
            duplas_vencidas = await conn.fetchval("""
                SELECT COUNT(*) FROM sants_pactos_dupla
                WHERE estado='vencido' AND (criador_id=$1 OR parceiro_id=$1)
            """, uid)
        saldo = await db.obter_saldo(uid)
        atual = (f"**{ROTAS[aventura['rota']]['emoji']} {ROTAS[aventura['rota']]['nome']}**\n"
                 f"Etapa: **{aventura['etapa']}/{ROTAS[aventura['rota']]['etapas']}** • "
                 f"Erros: **{aventura['erros']}** • Estado: **{aventura['estado']}**") if aventura else "📜 Nenhum pacto assinado hoje."
        diario = (f"{'✅' if aventura and aventura['estado']=='vencido' else '⬜'} Pacto vencido\n"
                  f"{'✅' if lado and lado['visita'] else '⬜'} Visita ao salão\n"
                  f"{'✅' if lado and lado['carta'] else '⬜'} Carta do Destino\n"
                  f"{'✅' if legado and legado['final_resgatado'] else '⬜'} Recompensa final")
        historico = "\n".join(
            f"{'🏆' if r['estado']=='vencido' else '💀' if r['estado']=='fracassado' else '📜'} "
            f"`{r['dia'].strftime('%d/%m')}` {ROTAS[r['rota']]['nome']} — {r['estado']} "
            f"(**{moeda(r['premio'])} SC**)" for r in passado
        ) or "*O livro de almas ainda está em branco...*"
        rank = "🎩 Novato do Salão" if vitorias < 3 else "🎲 Cúmplice do King Dice" if vitorias < 10 else "😈 Pesadelo do Diabo"
        e = base_embed("📖 SEU GRIMÓRIO DE ALMAS",
            f"*'Ah, então quer espiar seus pecados? Muito bem!'*\n\n"
            f"💰 **Carteira:** {moeda(saldo)} SC\n"
            f"🏅 **Título:** {rank}\n"
            f"🏆 **Vitórias totais:** {vitorias}\n\n"
            f"**📜 Pacto de hoje**\n{atual}\n\n"
            f"**🕯️ Cláusulas de hoje**\n{diario}\n\n"
            f"**🤝 Pactos em dupla**\n"
            + (f"<@{dupla_hoje['parceiro_id'] if dupla_hoje['criador_id']==uid else dupla_hoje['criador_id']}> "
               f"• **{dupla_hoje['estado']}** • etapa {dupla_hoje['etapa']}/{DUO_ETAPAS}\n"
               if dupla_hoje else "Nenhum pacto em dupla firmado hoje.\n")
            + f"🏆 **Vitórias em dupla:** {int(duplas_vencidas or 0)}\n\n"
            + f"**📚 Últimos registros solo**\n{historico}", cor=COR_OURO)
        return e

    async def meu_grimorio(self, it):
        await it.response.defer(ephemeral=True, thinking=True)
        await self._enviar(it, embed=await self._embed_grimorio(it.user.id))

    async def _ranking(self, guild_id: int):
        # Leitura apenas: não concede prêmios nem adiciona cargos.
        async with self.pool.acquire() as conn:
            linhas = await conn.fetch("""
                SELECT user_id, COUNT(*) AS vitorias, SUM(premio) AS premios
                FROM sants_contratos20_aventuras
                WHERE guild_id=$1 AND estado='vencido' AND dia >= $2
                GROUP BY user_id ORDER BY vitorias DESC, premios DESC, user_id ASC LIMIT 10
            """, guild_id, hoje() - timedelta(days=6))
        desc = "\n".join(
            f"**{i}.** <@{r['user_id']}> — **{r['vitorias']}** vitória(s) • **{moeda(r['premios'])} SC**"
            for i, r in enumerate(linhas, 1)) or "*Nenhum mortal venceu o Diabo nos últimos sete dias.*"
        return base_embed("🏆 QUEM O DIABO MAIS TEME?", "**Ranking dos últimos 7 dias**\n\n" + desc, cor=COR_OURO)

    # ═══════════════════════════════════════════════════════════════════
    # PACTO DAS DUAS ALMAS — acerto cooperativo, sem apostas nem transferências
    # ═══════════════════════════════════════════════════════════════════

    async def menu_recompensas(self, it: discord.Interaction):
        await it.response.send_message(embed=base_embed("💰 CONTAS DO DIABO",
            "🚪 **Visita ao Salão:** 40 SC uma vez ao dia.\n"
            "🃏 **Carta do Destino:** resgate pelo painel do cassino.\n"
            f"💰 **Dívida final:** {BONUS_FINAL} SC se vencer o pacto solo, visitar o salão e revelar a carta.\n\n"
            "*O pacto em dupla paga automaticamente quando as quatro provas são vencidas.*"),
            view=MenuRecompensas(self), ephemeral=True)

    async def escolher_parceiro(self, it: discord.Interaction):
        if it.guild is None:
            return await it.response.send_message("❌ Este recurso é exclusivo de servidores.", ephemeral=True)
        await it.response.send_message(
            embed=base_embed("🤝 PACTO DAS DUAS ALMAS",
                "*'Duas almas, uma assinatura... e quatro oportunidades de me decepcionar!'*\n\n"
                "Selecione um membro. Ele deverá aceitar em **2 minutos**.\n"
                "Vocês terão **20 minutos** para cumprir **4 provas alternadas**.\n\n"
                f"💰 **{DUO_PREMIO} SC por jogador**, com **+{DUO_BONUS_PERFEITO} SC** por vitória sem erros.\n"
                "💀 **Até 2 erros por dupla.** Um pacto em dupla aceito por pessoa/dia.\n"
                "*Sem apostas ou descontos da carteira.*"),
            view=EscolherParceiro(self, it.user.id), ephemeral=True)

    async def criar_convite_dupla(self, it: discord.Interaction, parceiro_id: int):
        """Chamado após o defer do UserSelect; valida membro real e grava convite."""
        if it.guild is None or it.channel is None:
            return await self._enviar(it, texto="❌ O convite precisa ser criado em um canal do servidor.")
        if parceiro_id == it.user.id:
            return await self._enviar(it, texto="😈 *'Você não pode assinar com o próprio reflexo!'*")
        try:
            membro = it.guild.get_member(parceiro_id) or await it.guild.fetch_member(parceiro_id)
        except discord.HTTPException:
            return await self._enviar(it, texto="❌ Não encontrei esse membro no servidor.")
        if membro.bot:
            return await self._enviar(it, texto="❌ O Diabo não aceita bots como parceiros.")
        try:
            pacto_id = await self._registrar_convite(it.guild.id, it.channel.id, it.user.id, membro.id)
        except ErroPacto as e:
            return await self._enviar(it, texto=f"❌ {e}")
        try:
            convite = await it.channel.send(
                content=f"<@{membro.id}>, você recebeu um convite!",
                embed=self._embed_dupla({"id": pacto_id, "estado": "convite", "criador_id": it.user.id,
                                         "parceiro_id": membro.id, "etapa": 0, "erros": 0,
                                         "expira_em": datetime.now(timezone.utc) + timedelta(minutes=DUO_CONVITE_MINUTOS)}),
                view=view_dupla(pacto_id, "convite"),
                allowed_mentions=discord.AllowedMentions(users=[membro]))
            await self.pool.execute("UPDATE sants_pactos_dupla SET message_id=$2 WHERE id=$1", pacto_id, convite.id)
        except discord.HTTPException:
            await self.pool.execute("UPDATE sants_pactos_dupla SET estado='cancelado', finalizado_em=NOW() WHERE id=$1 AND estado='convite'", pacto_id)
            LOG.exception("Falha ao enviar convite de pacto %s", pacto_id)
            return await self._enviar(it, texto="❌ Não consegui publicar o convite. Verifique as permissões do bot.")
        await self._enviar(it, texto=f"📜 Convite publicado: {convite.jump_url}\nO pacto só começa quando o outro jogador aceitar.")

    async def _registrar_convite(self, guild_id: int, channel_id: int, criador_id: int, parceiro_id: int) -> int:
        hoje_utc = hoje()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Serializa a criação de convites feitos pelo mesmo remetente.
                await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", int(criador_id))
                participante = await conn.fetchval("""
                    SELECT user_id FROM sants_pactos_dupla_participantes
                    WHERE dia=$1 AND user_id = ANY($2::bigint[]) LIMIT 1
                """, hoje_utc, [criador_id, parceiro_id])
                if participante:
                    raise ErroPacto("Um dos dois já firmou um pacto em dupla hoje.")
                pendente = await conn.fetchval("""
                    SELECT id FROM sants_pactos_dupla
                    WHERE guild_id=$1 AND estado='convite' AND expira_em > NOW()
                    AND (criador_id=$2 OR parceiro_id=$2 OR criador_id=$3 OR parceiro_id=$3)
                    LIMIT 1
                """, guild_id, criador_id, parceiro_id)
                if pendente:
                    raise ErroPacto("Um dos jogadores já tem um convite pendente. Aguarde sua expiração.")
                muito_recente = await conn.fetchval("""
                    SELECT id FROM sants_pactos_dupla WHERE criador_id=$1
                    AND criado_em > NOW() - INTERVAL '60 seconds' LIMIT 1
                """, criador_id)
                if muito_recente:
                    raise ErroPacto("Aguarde um minuto antes de fazer outro convite.")
                pacto_id = await conn.fetchval("""
                    INSERT INTO sants_pactos_dupla(guild_id, channel_id, dia, criador_id, parceiro_id, expira_em)
                    VALUES($1,$2,$3,$4,$5,NOW() + INTERVAL '2 minutes') RETURNING id
                """, guild_id, channel_id, hoje_utc, criador_id, parceiro_id)
                return int(pacto_id)

    def _embed_dupla(self, pacto, aviso: str = "") -> discord.Embed:
        estado = pacto["estado"]
        criador, convidado = pacto["criador_id"], pacto["parceiro_id"]
        par = f"<@{criador}>  ×  <@{convidado}>"
        pre = f"{aviso}\n\n" if aviso else ""
        if estado == "convite":
            expira = int(pacto["expira_em"].timestamp())
            desc = (f"{pre}*'Ora, ora! Dois nomes na mesma folha? Que delícia!'*\n\n"
                    f"{par}\n\n**4 provas • até 2 erros**\n"
                    f"💰 **{DUO_PREMIO} SC para cada alma** • +{DUO_BONUS_PERFEITO} SC sem erros\n"
                    f"⏳ Aceite até <t:{expira}:R>.\n\n"
                    "*Só o convidado pode aceitar. O criador já confirmou ao enviar o convite.*")
            titulo, cor = "📜 CONVITE: PACTO DAS DUAS ALMAS", COR
        elif estado == "ativo":
            etapa = int(pacto["etapa"])
            responsavel = responsavel_dupla(pacto, etapa)
            caixas = "▰" * etapa + "▱" * (DUO_ETAPAS - etapa)
            expira = int(pacto["expira_em"].timestamp())
            nome, lore = ETAPAS_DUPLA[etapa]
            desc = (f"{pre}{par}\n\n**{nome}**\n*{lore}*\n\n"
                    f"🎭 Vez de: <@{responsavel}>\n"
                    f"📜 `{caixas}` • **{etapa}/{DUO_ETAPAS}**\n"
                    f"💀 Erros: **{pacto['erros']}/{DUO_MAX_ERROS + 1}** (a 3ª falha rompe o pacto)\n"
                    f"⏳ Termina <t:{expira}:R>.")
            titulo, cor = "🎲 O DIABO ESTÁ ASSISTINDO", COR
        elif estado == "vencido":
            desc = (f"{pre}{par}\n\n*'NÃO! Vocês dois me derrotaram?! KING DICE!'*\n\n"
                    f"🏆 Contrato cumprido • **{pacto['premio_individual']} SC para cada jogador**\n"
                    "✅ Prêmios creditados automaticamente na carteira compartilhada.")
            titulo, cor = "🏆 O PACTO FOI HONRADO", COR_OURO
        else:
            desc = (f"{pre}{par}\n\n*'Heh-heh... nossa negociação chegou ao fim.'*\n\n"
                    "💀 Pacto encerrado sem recompensa. **Nenhuma SC foi retirada.**")
            titulo, cor = "💀 CONTRATO RASGADO", COR_TREVAS
        e = base_embed(titulo, desc, cor=cor)
        return e

    async def _atualizar_convite_publico(self, pacto, aviso: str = ""):
        if not pacto["message_id"]:
            return
        canal = self.bot.get_channel(pacto["channel_id"])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(pacto["channel_id"])
            except discord.HTTPException:
                return
        try:
            await canal.get_partial_message(pacto["message_id"]).edit(
                content=None, embed=self._embed_dupla(pacto, aviso),
                view=view_dupla(pacto["id"], pacto["estado"]),
                allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOG.warning("Não foi possível atualizar a mensagem do pacto %s", pacto["id"])

    async def _dupla_por_id(self, id_: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)

    async def acao_dupla(self, it: discord.Interaction, acao: str, pacto_id: int,
                         etapa=None, tentativa=None, resposta=None):
        await it.response.defer(ephemeral=True, thinking=True)
        if it.guild is None:
            return await self._enviar(it, texto="❌ Os pactos funcionam somente no servidor.")
        try:
            if acao == "aceitar":
                pacto, aviso = await self._aceitar_dupla(it.user.id, it.guild.id, pacto_id)
            elif acao == "recusar":
                pacto, aviso = await self._encerrar_dupla(it.user.id, it.guild.id, pacto_id, convite=True)
            elif acao == "cancelar":
                pacto, aviso = await self._encerrar_dupla(it.user.id, it.guild.id, pacto_id)
            elif acao == "resp":
                pacto, aviso = await self._responder_dupla(it.user.id, it.guild.id,
                                                           pacto_id, etapa, tentativa, resposta)
            else:
                pacto = await self._dupla_por_id(pacto_id)
                if not pacto or pacto["guild_id"] != it.guild.id or it.user.id not in (pacto["criador_id"], pacto["parceiro_id"]):
                    raise ErroPacto("Este contrato não é seu ou não pertence a este servidor.")
                aviso = ""
            if pacto["estado"] in ("convite", "ativo") and pacto["expira_em"] <= datetime.now(timezone.utc):
                pacto = await self._expirar_dupla(pacto_id)
                aviso = "⌛ O tempo do contrato acabou."
                await self._atualizar_convite_publico(pacto, aviso)
            if acao in ("aceitar", "recusar", "cancelar", "resp"):
                await self._atualizar_convite_publico(pacto, aviso)
            if acao in ("jogar", "resp") and pacto["estado"] == "ativo":
                return await self._mostrar_prova_dupla(it, pacto, aviso)
            await self._enviar(it, embed=self._embed_dupla(pacto, aviso))
        except ErroPacto as e:
            await self._enviar(it, texto=f"❌ {e}")
        except Exception:
            LOG.exception("Erro no Pacto das Duas Almas id=%s, acao=%s", pacto_id, acao)
            await self._enviar(it, texto="❌ Falha ao processar o pacto. Confira o progresso antes de tentar novamente.")

    async def _expirar_dupla(self, id_: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE sants_pactos_dupla SET estado='expirado', finalizado_em=NOW()
                    WHERE id=$1 AND estado IN ('convite','ativo') AND expira_em<=NOW()
                """, id_)
                return await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)

    async def _aceitar_dupla(self, uid: int, gid: int, id_: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1 FOR UPDATE", id_)
                if not p or p["guild_id"] != gid or p["parceiro_id"] != uid:
                    raise ErroPacto("Somente o jogador convidado pode aceitar este pacto.")
                if p["estado"] != "convite":
                    raise ErroPacto("Este convite não está mais disponível.")
                if p["expira_em"] <= datetime.now(timezone.utc) or p["dia"] != hoje():
                    await conn.execute("UPDATE sants_pactos_dupla SET estado='expirado',finalizado_em=NOW() WHERE id=$1", id_)
                    p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)
                    return p, "⌛ Convite expirado."
                # A chave única (user_id,dia) limita o jogador a um pacto aceito por dia.
                for membro_id in sorted((p["criador_id"], p["parceiro_id"])):
                    inserido = await conn.fetchval("""
                        INSERT INTO sants_pactos_dupla_participantes(user_id,dia,pacto_id)
                        VALUES($1,$2,$3) ON CONFLICT(user_id,dia) DO NOTHING RETURNING user_id
                    """, membro_id, p["dia"], id_)
                    if inserido is None:
                        raise ErroPacto("Um dos participantes já assinou outro pacto em dupla hoje.")
                virada = datetime.combine(p["dia"] + timedelta(days=1),
                                           datetime.min.time(), tzinfo=timezone.utc)
                ate = min(datetime.now(timezone.utc) + timedelta(minutes=DUO_JOGO_MINUTOS), virada)
                await conn.execute("""
                    UPDATE sants_pactos_dupla
                    SET estado='ativo', aceito_em=NOW(), expira_em=$2
                    WHERE id=$1
                """, id_, ate)
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)
                return p, "✍️ **Assinaturas confirmadas!** O Diabo abriu o primeiro selo."

    async def _encerrar_dupla(self, uid: int, gid: int, id_: int, convite: bool = False):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1 FOR UPDATE", id_)
                if not p or p["guild_id"] != gid or uid not in (p["criador_id"], p["parceiro_id"]):
                    raise ErroPacto("Você não participa deste pacto.")
                if convite and p["estado"] != "convite":
                    raise ErroPacto("O convite já foi aceito ou encerrado.")
                if not convite and p["estado"] != "ativo":
                    raise ErroPacto("Este pacto não está ativo.")
                await conn.execute("UPDATE sants_pactos_dupla SET estado='cancelado', finalizado_em=NOW() WHERE id=$1", id_)
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)
                return p, "📜 O pacto foi rompido por um dos participantes."

    async def _mostrar_prova_dupla(self, it: discord.Interaction, p, aviso: str = ""):
        etapa = int(p["etapa"])
        if p["estado"] != "ativo" or etapa >= DUO_ETAPAS:
            return await self._enviar(it, embed=self._embed_dupla(p, aviso))
        responsavel = responsavel_dupla(p, etapa)
        if it.user.id != responsavel:
            return await self._enviar(it, embed=self._embed_dupla(p, "🎭 Agora é a vez do seu parceiro. Aguarde a resposta dele."))
        enunciado, opcoes, correta = prova_dupla(p["id"], etapa, p["tentativa"])
        nome, lore = ETAPAS_DUPLA[etapa]
        prefacio = f"**{aviso}**" if aviso else "*'Não faça o Diabo esperar...'*"
        desc = (f"{prefacio}\n\n"
                f"**{nome} • Etapa {etapa+1}/{DUO_ETAPAS}**\n{lore}\n\n"
                f"**❓ {enunciado}**\n\n"
                f"💀 Erros: **{p['erros']}/{DUO_MAX_ERROS + 1}**\n"
                f"*A resposta é definitiva. Uma escolha por etapa.*")
        v = discord.ui.View(timeout=None)
        for i, opcao in enumerate(opcoes):
            v.add_item(BotaoDupla("resp", p["id"], etapa, p["tentativa"], i,
                                 rotulo=f"{chr(65+i)} · {opcao}"[:80]))
        await self._enviar(it, embed=base_embed("😈 O DIABO EXIGE UMA RESPOSTA", desc), view=v)

    async def _responder_dupla(self, uid: int, gid: int, id_: int, etapa, tentativa, resposta):
        if etapa is None or tentativa is None or resposta not in range(4) or etapa not in range(DUO_ETAPAS):
            raise ErroPacto("Resposta de pacto inválida.")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1 FOR UPDATE", id_)
                if not p or p["guild_id"] != gid or uid not in (p["criador_id"], p["parceiro_id"]):
                    raise ErroPacto("Este contrato não é seu.")
                if p["estado"] != "ativo":
                    raise ErroPacto("Este contrato não está mais ativo.")
                if p["expira_em"] <= datetime.now(timezone.utc) or p["dia"] != hoje():
                    await conn.execute("UPDATE sants_pactos_dupla SET estado='expirado',finalizado_em=NOW() WHERE id=$1", id_)
                    return await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1"), "⌛ Tempo encerrado."
                if responsavel_dupla(p, p["etapa"]) != uid:
                    raise ErroPacto("É a vez da outra alma responder.")
                if int(p["etapa"]) != etapa or int(p["tentativa"]) != tentativa:
                    raise ErroPacto("Esta prova já foi respondida. Clique em **Responder prova** para continuar.")
                pergunta, opcoes, correta = prova_dupla(id_, etapa, tentativa)
                acertou = resposta == correta
                erros = int(p["erros"]) + (0 if acertou else 1)
                nova_etapa = etapa + (1 if acertou else 0)
                fracassou = erros > DUO_MAX_ERROS
                venceu = acertou and nova_etapa >= DUO_ETAPAS
                estado = "fracassado" if fracassou else "vencido" if venceu else "ativo"
                premio = DUO_PREMIO + (DUO_BONUS_PERFEITO if erros == 0 else 0) if venceu else 0
                if venceu:
                    for membro_id in sorted((p["criador_id"], p["parceiro_id"])):
                        await self._creditar(conn, membro_id, premio,
                                            f"Pacto das Duas Almas #{id_} • {p['dia']}")
                await conn.execute("""
                    UPDATE sants_pactos_dupla SET estado=$2, etapa=$3, erros=$4,
                        tentativa=tentativa+1, premio_individual=$5,
                        finalizado_em=CASE WHEN $2='ativo' THEN NULL ELSE NOW() END
                    WHERE id=$1
                """, id_, estado, nova_etapa, erros, premio)
                p = await conn.fetchrow("SELECT * FROM sants_pactos_dupla WHERE id=$1", id_)
        if venceu:
            aviso = f"🏆 **Vitória em dupla! +{premio} SC para cada jogador.**"
        elif fracassou:
            aviso = f"💀 Erro! A resposta era **{opcoes[correta]}**. O Diabo rasgou o contrato."
        elif acertou:
            aviso = f"✅ Acertou! O Diabo exige a próxima assinatura de <@{responsavel_dupla(p,nova_etapa)}>!"
        else:
            aviso = f"❌ A resposta era **{opcoes[correta]}**. A dupla acumulou **{erros} erro(s)**."
        return p, aviso

    async def retomar_mesa(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True, thinking=True)
        async with self.pool.acquire() as conn:
            p = await conn.fetchrow("""
                SELECT p.* FROM sants_pactos_dupla p
                WHERE p.guild_id=$1 AND (p.criador_id=$2 OR p.parceiro_id=$2)
                AND p.estado IN ('convite','ativo')
                ORDER BY p.id DESC LIMIT 1
            """, it.guild_id, it.user.id)
        if p:
            if p["expira_em"] <= datetime.now(timezone.utc):
                p = await self._expirar_dupla(p["id"])
                return await self._enviar(it, texto="⌛ Seu último pacto em dupla expirou. Você pode consultar o Grimório.")
            if p["estado"] == "ativo":
                return await self._mostrar_prova_dupla(it, p)
            return await self._enviar(it, embed=self._embed_dupla(p), view=view_dupla(p["id"], p["estado"]))
        dia, aventura, _, _ = await self._estado(it.user.id)
        if aventura:
            return await self._mostrar_aventura(it, aventura, dia)
        await self._enviar(it, texto="📜 Você não possui pacto em andamento. Escolha **Pacto solo** ou **Pacto em dupla**.")

    async def regras_mesa(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True, thinking=True)
        nome, efeito = clausula_do_dia(hoje())
        await self._enviar(it, embed=base_embed("👁️ AS REGRAS DA MESA",
            "**📜 Solo**\nUma rota por dia, com provas e recompensas conforme a dificuldade.\n\n"
            "**🤝 Dupla**\nO convite dura **2 minutos**; depois de aceito, a dupla tem **20 minutos**. "
            "As quatro provas alternam entre os dois participantes. O terceiro erro encerra o pacto. "
            "Cada jogador pode aceitar **um pacto em dupla por dia**.\n\n"
            f"**💰 Prêmio cooperativo:** {DUO_PREMIO} SC por pessoa (+{DUO_BONUS_PERFEITO} SC sem erros).\n"
            "**🔒 Segurança:** sem apostas, transferências ou punições na carteira.\n\n"
            f"**🕯️ {nome}**\n{efeito}\n\n"
            "*O pacto encerra no máximo à virada de 00:00 UTC. As recompensas são automáticas e únicas.*"))

    @commands.command(name="pacto", aliases=["pactodupla"])
    @commands.guild_only()
    async def cmd_pacto(self, ctx, membro: discord.Member | None = None):
        """!pacto @membro — atalho alternativo ao seletor do painel."""
        if membro is None:
            return await ctx.reply("📜 Use `!pacto @membro` ou o botão **Pacto em dupla** no painel.", mention_author=False)
        if membro.id == ctx.author.id or membro.bot:
            return await ctx.reply("❌ Convide outro membro humano.", mention_author=False)
        try:
            pacto_id = await self._registrar_convite(ctx.guild.id, ctx.channel.id, ctx.author.id, membro.id)
        except ErroPacto as e:
            return await ctx.reply(f"❌ {e}", mention_author=False)
        try:
            mensagem = await ctx.send(
                content=f"<@{membro.id}>, você recebeu um convite!",
                embed=self._embed_dupla({"id": pacto_id, "estado": "convite", "criador_id": ctx.author.id,
                                         "parceiro_id": membro.id, "etapa": 0, "erros": 0,
                                         "expira_em": datetime.now(timezone.utc) + timedelta(minutes=DUO_CONVITE_MINUTOS)}),
                view=view_dupla(pacto_id, "convite"),
                allowed_mentions=discord.AllowedMentions(users=[membro]))
            await self.pool.execute("UPDATE sants_pactos_dupla SET message_id=$2 WHERE id=$1", pacto_id, mensagem.id)
        except discord.HTTPException:
            await self.pool.execute("UPDATE sants_pactos_dupla SET estado='cancelado',finalizado_em=NOW() WHERE id=$1 AND estado='convite'", pacto_id)
            return await ctx.reply("❌ Não consegui publicar o convite.", mention_author=False)

    @commands.command(name="retomarpacto")
    @commands.guild_only()
    async def cmd_retomar(self, ctx):
        """Orientação de como retomar após reinicialização."""
        await ctx.reply("🎭 Abra o painel `!painelcontratos` e clique em **Retomar**. "
                        "Se o pacto em dupla já foi aceito, também é possível usar **Responder prova** na mensagem dele.",
                        mention_author=False)

    @commands.command(name="rankingduplas")
    @commands.guild_only()
    async def cmd_ranking_duplas(self, ctx):
        async with self.pool.acquire() as conn:
            linhas = await conn.fetch("""
                SELECT criador_id, parceiro_id, COUNT(*) AS vitorias
                FROM sants_pactos_dupla
                WHERE guild_id=$1 AND estado='vencido' AND dia >= $2
                GROUP BY criador_id, parceiro_id
                ORDER BY vitorias DESC, criador_id, parceiro_id LIMIT 10
            """, ctx.guild.id, hoje() - timedelta(days=6))
        desc = "\n".join(f"**{i}.** <@{r['criador_id']}> × <@{r['parceiro_id']}> — **{r['vitorias']}** vitória(s)"
                         for i, r in enumerate(linhas, 1)) or "*O livro de pactos ainda está vazio...*"
        await ctx.send(embed=base_embed("🏆 AS DUPLAS QUE DESAFIARAM O DIABO",
                                        "**Últimos 7 dias**\n\n" + desc, cor=COR_OURO),
                       allowed_mentions=discord.AllowedMentions.none())


    @commands.command(name="painelcontratos", aliases=["contratos2"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def cmd_painel(self, ctx):
        """Publica o painel interativo permanente (staff)."""
        await ctx.send(embed=self._painel_publico(), view=PainelMesa(self),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="meuscontratos", aliases=["grimorio"])
    @commands.guild_only()
    async def cmd_grimorio(self, ctx):
        """Consulta pessoal; por texto é uma mensagem no canal atual."""
        e = await self._embed_grimorio(ctx.author.id)
        # Evita divulgar saldo e histórico em público: envia por DM.
        try:
            await ctx.author.send(embed=e)
            await ctx.reply("📖 Enviei seu grimório por mensagem privada!", mention_author=False,
                            delete_after=15)
        except discord.Forbidden:
            await ctx.reply("❌ Sua DM está fechada. Use o botão **Meu grimório** do painel para consultar em privado.",
                            mention_author=False)

    @commands.command(name="rankingcontratos")
    @commands.guild_only()
    async def cmd_ranking(self, ctx):
        await ctx.send(embed=await self._ranking(ctx.guild.id),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="contratosajuda")
    @commands.guild_only()
    async def cmd_ajuda(self, ctx):
        await ctx.reply(embed=base_embed("😈 COMANDOS DO DIABO",
            "`!painelcontratos` — publica o painel (staff).\n"
            "`!meuscontratos` — histórico por DM.\n"
            "`!rankingcontratos` — ranking semanal.\n"
            "`!pacto @membro` — enviar convite de pacto em dupla.\n"
            "`!rankingduplas` — ranking cooperativo.\n"
            "`!retomarpacto` — instruções para retomar.\n"
            "`!contratosajuda` — esta ajuda.\n\n"
            "**No painel:** Pacto solo, Pacto em dupla, Retomar, Grimório e Regras.\n"
            "**Cartas do Destino:** continuam no `!painelcassino`."), mention_author=False)


async def setup(bot):
    await bot.add_cog(ContratosDiabo20(bot))
