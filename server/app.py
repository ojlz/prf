import flask
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import json
import os
import re
import time
import uuid
import random
import math
from datetime import datetime, timezone, timedelta
from functools import wraps

app = Flask(__name__, static_folder='../')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'prf-simulator-change-in-production')
CORS(app, supports_credentials=True)
limiter = Limiter(app=app, key_func=lambda: request.remote_addr)

DADOS = os.environ.get("PRF_DATA_DIR", os.path.join(os.path.dirname(__file__), 'dados'))
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
# No Vercel os estaticos vao para public/ (CDN); localmente continua igual.
# Fallback para a raiz mantem compatibilidade com checkouts antigos.
_PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
STATIC_DIR = os.environ.get("PRF_STATIC_DIR",
             _PUBLIC_DIR if os.path.isdir(_PUBLIC_DIR) else BASE_DIR)
USUARIOS = os.path.join(DADOS, 'usuarios.json')
BLACKLIST = os.path.join(DADOS, 'tokens_blacklist.json')
try:
    os.makedirs(DADOS, exist_ok=True)
except OSError:
    pass  # disco somente-leitura (ex.: serverless): dados vão para /tmp via PRF_DATA_DIR

ACCESS_EXP = 3600
REFRESH_EXP = 2592000

PATENTES = [
    (0, "Agente de 1ª Classe"), (500, "Agente de 2ª Classe"),
    (1500, "Agente de 3ª Classe"), (3000, "Agente Especial"),
    (6000, "Agente Tático"), (10000, "Agente de Elite"),
    (16000, "Supervisor"), (24000, "Inspetor"),
    (34000, "Coordenador"), (46000, "Comandante Regional"),
    (60000, "Comandante Nacional"), (80000, "Diretor-Geral"),
]

CONQUISTAS_DEF = [
    {"id": "c1_primeira", "nome": "Primeiro Passo", "descricao": "Complete sua primeira patrulha"},
    {"id": "c10_patrulhas", "nome": "Veterano", "descricao": "Complete 10 patrulhas"},
    {"id": "c50_patrulhas", "nome": "Mestre das Rodovias", "descricao": "Complete 50 patrulhas"},
    {"id": "c1000_km", "nome": "Milha Extra", "descricao": "Percorra 1000 km no total"},
    {"id": "c5000_km", "nome": "O Incansável", "descricao": "Percorra 5000 km no total"},
    {"id": "c100_abordagens", "nome": "Fiscal Experiente", "descricao": "Realize 100 fiscalizações"},
    {"id": "c500_abordagens", "nome": "O Incansável", "descricao": "Realize 500 fiscalizações"},
    {"id": "c100_art230", "nome": "Guardião do CTB", "descricao": "Acuse 100 infrações do Art. 230"},
    {"id": "c50_prisoes", "nome": "Caçador de Bandidos", "descricao": "Efetue 50 prisões"},
    {"id": "c10km_patrulha", "nome": "Viagem Longa", "descricao": "Percorra 10 km em uma patrulha"},
    {"id": "c100km_patrulha", "nome": "Maratona", "descricao": "Percorra 100 km em uma patrulha"},
    {"id": "c10min_tempo", "nome": "Plantão Extra", "descricao": "Fique 10 minutos em uma patrulha"},
    {"id": "c30min_tempo", "nome": "Jornada Dupla", "descricao": "Fique 30 minutos em patrulha"},
    {"id": "c1000_pontos", "nome": "Colecionador de Pontos", "descricao": "Some 1000 pontos em patrulhas"},
    {"id": "c10000_pontos", "nome": "Lenda Viva", "descricao": "Some 10000 pontos em patrulhas"},
    {"id": "c1000_pontos_patr", "nome": "Patrulha Nota Mil", "descricao": "Faça 1000 pontos em UMA patrulha"},
]


def ler_json(path, padrao=None):
    if padrao is None: padrao = {}
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return padrao

def salvar_json(path, dados):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

def token_obrigatorio(fn):
    @wraps(fn)
    def decorada(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token = auth.replace('Bearer ', '').strip()
        if not token:
            return jsonify({"erro": "Token de acesso obrigatório"}), 401
        blacklist = ler_json(BLACKLIST, [])
        if token in blacklist:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        except:
            return jsonify({"erro": "Token inválido."}), 401
        usuarios = ler_json(USUARIOS, {})
        usuario = payload.get('usuario')
        if usuario not in usuarios:
            return jsonify({"erro": "Conta não encontrada."}), 401
        return fn(usuarios[usuario], *args, **kwargs)
    return decorada

def gerar_token(usuario):
    return jwt.encode({
        "usuario": usuario, "tipo": "access",
        "exp": time.time() + ACCESS_EXP
    }, app.config['SECRET_KEY'], algorithm='HS256')

def gerar_refresh(usuario):
    return jwt.encode({
        "usuario": usuario, "tipo": "refresh",
        "exp": time.time() + REFRESH_EXP
    }, app.config['SECRET_KEY'], algorithm='HS256')

def calc_patente(xp_total):
    nome = PATENTES[0][1]
    for req, pat in PATENTES:
        if xp_total >= req: nome = pat
    return nome

def calc_nivel(xp_total):
    return int(math.sqrt(max(0, xp_total) / 100)) + 1

def calc_xp_proximo(nivel):
    return (nivel ** 2) * 100

def verificar_conquistas(usuario, conta):
    novas = []
    c = conta
    t = c.get('totais', {})
    r = c.get('recordes', {})
    desbloq = c.get('conquistas', {})

    checks = {
        "c1_primeira": c.get('patrulhas_total', 0) >= 1,
        "c10_patrulhas": c.get('patrulhas_total', 0) >= 10,
        "c50_patrulhas": c.get('patrulhas_total', 0) >= 50,
        "c1000_km": t.get('km_total', 0) >= 1000,
        "c5000_km": t.get('km_total', 0) >= 5000,
        "c100_abordagens": t.get('fiscalizacoes', 0) >= 100,
        "c500_abordagens": t.get('fiscalizacoes', 0) >= 500,
        "c100_art230": t.get('art230', 0) >= 100,
        "c50_prisoes": t.get('prisoes', 0) >= 50,
        "c10km_patrulha": r.get('km', 0) >= 10,
        "c100km_patrulha": r.get('km', 0) >= 100,
        "c10min_tempo": (r.get('tempo_direcao_seg', 0) or 0) >= 600,
        "c30min_tempo": (r.get('tempo_direcao_seg', 0) or 0) >= 1800,
        "c1000_pontos": t.get('pontos_total', 0) >= 1000,
        "c10000_pontos": t.get('pontos_total', 0) >= 10000,
        "c1000_pontos_patr": r.get('pontuacao', 0) >= 1000,
    }

    for cid, ok in checks.items():
        if ok and not desbloq.get(cid):
            desbloq[cid] = True
            for cd in CONQUISTAS_DEF:
                if cd['id'] == cid:
                    novas.append({"nome": cd['nome'], "descricao": cd['descricao']})
                    break

    c['conquistas'] = desbloq
    return novas

def conta_padrao(usuario, email_hash):
    return {
        "usuario": usuario, "email": email_hash, "senha": "",
        "plano": "pago", "nivel": 1, "xp_total": 0, "pontos": 0,
        "patente": PATENTES[0][1],
        "patrulhas_total": 0,
        "skins": {"farda": "padrao", "viatura": "via_padrao", "base": "base_prf", "arma": "arma_pistola", "posse": []},
        "recordes": {"pontuacao": 0, "km": 0, "tempo_direcao_seg": 0},
        "totais": {"fiscalizacoes": 0, "prisoes": 0, "art230": 0, "pontos_total": 0, "km_total": 0},
        "conquistas": {},
        "beta": False,
        "criado_em": datetime.now(timezone.utc).isoformat(),
    }


# ---- Static routes ----

@app.route('/')
def servir_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:nome>', methods=['GET', 'POST'])
def servir_estatico(nome):
    if nome.startswith('server/') or '..' in nome or nome.startswith('/'):
        return jsonify({"erro": "Acesso negado"}), 403
    if nome.startswith('cdn-cgi/'):
        return jsonify({"erro": "Not found"}), 404
    return send_from_directory(STATIC_DIR, nome)


# ---- Auth routes ----

@app.route('/api/registrar', methods=['POST'])
@limiter.limit("5 per minute")
def registrar():
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get('usuario', '')).strip()
    email = str(dados.get('email', '')).strip().lower()
    senha = str(dados.get('senha', ''))

    if not usuario or not email or not senha:
        return jsonify({"erro": "Preencha todos os campos."}), 400
    if len(usuario) < 3 or len(usuario) > 20 or not re.match(r'^[a-zA-Z0-9_]+$', usuario):
        return jsonify({"erro": "Usuário deve ter 3-20 caracteres (letras, números, _)."}), 400
    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({"erro": "E-mail inválido."}), 400
    if len(senha) < 6:
        return jsonify({"erro": "Senha deve ter no mínimo 6 caracteres."}), 400

    usuarios = ler_json(USUARIOS, {})
    if usuario in usuarios:
        return jsonify({"erro": "Este nome de usuário já está em uso."}), 409
    for u, c in usuarios.items():
        if c.get('email') == email:
            return jsonify({"erro": "Este e-mail já está cadastrado."}), 409

    conta = conta_padrao(usuario, email)
    conta['senha'] = generate_password_hash(senha)
    usuarios[usuario] = conta
    salvar_json(USUARIOS, usuarios)

    token = gerar_token(usuario)
    refresh = gerar_refresh(usuario)

    return jsonify({
        "token": token, "refresh_token": refresh,
        "conta": formatar_conta(conta)
    }), 201


@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get('usuario', '')).strip()
    senha = str(dados.get('senha', ''))

    if not usuario or not senha:
        return jsonify({"erro": "Informe usuário e senha."}), 400

    usuarios = ler_json(USUARIOS, {})
    conta = usuarios.get(usuario)
    if not conta or not check_password_hash(conta['senha'], senha):
        return jsonify({"erro": "Usuário ou senha incorretos."}), 401

    token = gerar_token(usuario)
    refresh = gerar_refresh(usuario)

    return jsonify({
        "token": token, "refresh_token": refresh,
        "conta": formatar_conta(conta)
    })


@app.route('/api/logout', methods=['POST'])
@token_obrigatorio
def logout(conta):
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '').strip()
    blacklist = ler_json(BLACKLIST, [])
    if token not in blacklist:
        blacklist.append(token)
        salvar_json(BLACKLIST, blacklist)
    return jsonify({"mensagem": "Sessão encerrada."})


@app.route('/api/refresh', methods=['POST'])
def refresh():
    dados = request.get_json(silent=True) or {}
    token = str(dados.get('refresh_token', ''))
    if not token:
        return jsonify({"erro": "Refresh token obrigatório."}), 401
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except:
        return jsonify({"erro": "Refresh token inválido ou expirado."}), 401
    if payload.get('tipo') != 'refresh':
        return jsonify({"erro": "Tipo de token inválido."}), 401
    usuarios = ler_json(USUARIOS, {})
    usuario = payload.get('usuario')
    if usuario not in usuarios:
        return jsonify({"erro": "Conta não encontrada."}), 401
    novo_token = gerar_token(usuario)
    return jsonify({"token": novo_token})


# ---- User routes ----

@app.route('/api/eu', methods=['GET'])
@token_obrigatorio
def eu(conta):
    return jsonify({"conta": formatar_conta(conta)})


@app.route('/api/senha', methods=['POST'])
@token_obrigatorio
@limiter.limit("3 per minute")
def alterar_senha(conta):
    dados = request.get_json(silent=True) or {}
    atual = str(dados.get('senha_atual', ''))
    nova = str(dados.get('senha_nova', ''))

    if not atual or not nova:
        return jsonify({"erro": "Informe a senha atual e a nova."}), 400
    if len(nova) < 6:
        return jsonify({"erro": "A nova senha precisa de pelo menos 6 caracteres."}), 400
    if not check_password_hash(conta['senha'], atual):
        return jsonify({"erro": "Senha atual incorreta."}), 403

    usuarios = ler_json(USUARIOS, {})
    usuarios[conta['usuario']]['senha'] = generate_password_hash(nova)
    salvar_json(USUARIOS, usuarios)
    return jsonify({"mensagem": "Senha alterada com sucesso."})


# ---- Patrol sync ----

@app.route('/api/patrulha', methods=['POST'])
@token_obrigatorio
@limiter.limit("30 per minute")
def salvar_patrulha(conta):
    dados = request.get_json(silent=True) or {}
    usuario = conta['usuario']

    pont = max(0, int(dados.get('pontuacao', 0)))
    km = max(0, float(dados.get('km', 0)))
    tempo_dir = max(0, int(dados.get('tempo_direcao_seg', 0)))
    tempo_turno = max(0, int(dados.get('tempo_turno_seg', 0)))
    fisc = max(0, int(dados.get('fiscalizacoes', 0)))
    erros = max(0, int(dados.get('erros_ctb', 0)))
    prisoes = max(0, int(dados.get('prisoes', 0)))
    art230 = max(0, int(dados.get('art230', 0)))

    usuarios = ler_json(USUARIOS, {})
    c = usuarios[usuario]

    xp_ganho = max(10, pont // 10) + (fisc * 5) + (prisoes * 10) - (erros * 2)
    xp_ganho = max(xp_ganho, 0)
    c['xp_total'] += xp_ganho
    pts_ganho = max(0, pont // 10 + fisc + prisoes * 2)
    c['pontos'] = c.get('pontos', 0) + pts_ganho

    c['patrulhas_total'] = c.get('patrulhas_total', 0) + 1

    totais = c.setdefault('totais', {})
    totais['fiscalizacoes'] = totais.get('fiscalizacoes', 0) + fisc
    totais['prisoes'] = totais.get('prisoes', 0) + prisoes
    totais['art230'] = totais.get('art230', 0) + art230
    totais['pontos_total'] = totais.get('pontos_total', 0) + pont
    totais['km_total'] = totais.get('km_total', 0) + km

    recordes = c.setdefault('recordes', {})
    novos_recordes = {}

    if pont > recordes.get('pontuacao', 0):
        recordes['pontuacao'] = pont
        novos_recordes['pontuacao'] = True
    if km > recordes.get('km', 0):
        recordes['km'] = km
        novos_recordes['km'] = True
    if tempo_dir > recordes.get('tempo_direcao_seg', 0):
        recordes['tempo_direcao_seg'] = tempo_dir
        novos_recordes['tempo'] = True

    nivel_antes = c.get('nivel', 1)
    c['nivel'] = calc_nivel(c['xp_total'])
    c['patente'] = calc_patente(c['xp_total'])
    subiu = c['nivel'] > nivel_antes

    conquistas_novas = verificar_conquistas(usuario, c)

    nova_patente = None
    if subiu:
        for req, pat in PATENTES:
            if c['xp_total'] >= req and c['patente'] == pat:
                if c['patente'] != calc_patente(c['xp_total'] - xp_ganho + 1):
                    nova_patente = pat

    salvar_json(USUARIOS, usuarios)

    return jsonify({
        "conta": formatar_conta(c),
        "xp_ganho": xp_ganho, "subiu_nivel": subiu,
        "nova_patente": nova_patente,
        "novos_recordes": novos_recordes,
        "conquistas_novas": conquistas_novas,
    })


# ---- Skins ----

@app.route('/api/skin/comprar-pontos', methods=['POST'])
@token_obrigatorio
@limiter.limit("10 per minute")
def comprar_skin(conta):
    dados = request.get_json(silent=True) or {}
    skin_id = str(dados.get('id', ''))

    cat = skin_categoria(skin_id)
    if not cat:
        return jsonify({"erro": "Skin não encontrada."}), 404

    item = cat.get(skin_id)
    if not item or item['desbloqueio']['tipo'] != 'pontos':
        return jsonify({"erro": "Esta skin não pode ser comprada com pontos."}), 400

    usuario = conta['usuario']
    usuarios = ler_json(USUARIOS, {})
    c = usuarios[usuario]

    if skin_id in c.get('skins', {}).get('posse', []):
        return jsonify({"mensagem": "Você já possui esta skin."}), 200

    preco = item['desbloqueio']['preco']
    nivel = item['desbloqueio']['nivel']

    if c['nivel'] < nivel:
        return jsonify({"erro": f"Necessário nível {nivel} para desbloquear esta skin."}), 400
    if c.get('pontos', 0) < preco:
        return jsonify({"erro": f"Você precisa de {preco} pontos. Você tem {c.get('pontos', 0)}."}), 400

    c['pontos'] -= preco
    c.setdefault('skins', {}).setdefault('posse', []).append(skin_id)
    salvar_json(USUARIOS, usuarios)

    return jsonify({
        "mensagem": f"Skin adquirida por {preco} pontos!",
        "conta": formatar_conta(c),
    })


@app.route('/api/skin/equipar', methods=['POST'])
@token_obrigatorio
def equipar_skin(conta):
    dados = request.get_json(silent=True) or {}
    skin_id = str(dados.get('id', ''))
    usuario = conta['usuario']
    usuarios = ler_json(USUARIOS, {})

    cat = skin_categoria(skin_id)
    if not cat:
        return jsonify({"erro": "Skin não encontrada."}), 404

    c = usuarios[usuario]
    chave = cat['chave']
    c.setdefault('skins', {})[chave] = skin_id
    salvar_json(USUARIOS, usuarios)

    return jsonify({
        "mensagem": "Skin equipada!",
        "conta": formatar_conta(c),
    })


def skin_categoria(skin_id):
    # Simplified catalog from frontend definitions
    mapa = {
        "padrao": {"id": "padrao", "desbloqueio": {"tipo": "free"}, "chave": "farda"},
        "macacao": {"id": "macacao", "desbloqueio": {"tipo": "pontos", "nivel": 3, "preco": 700}, "chave": "farda"},
        "tatico": {"id": "tatico", "desbloqueio": {"tipo": "pontos", "nivel": 7, "preco": 1600}, "chave": "farda"},
        "noe": {"id": "noe", "desbloqueio": {"tipo": "pago"}, "chave": "farda"},
        "apoiador": {"id": "apoiador", "desbloqueio": {"tipo": "pago"}, "chave": "farda"},
        "beta": {"id": "beta", "desbloqueio": {"tipo": "beta"}, "chave": "farda"},
        "branca": {"id": "branca", "desbloqueio": {"tipo": "premio"}, "chave": "farda"},
        "brasil": {"id": "brasil", "desbloqueio": {"tipo": "sazonal"}, "chave": "farda"},
        "via_padrao": {"id": "via_padrao", "desbloqueio": {"tipo": "free"}, "chave": "viatura"},
        "via_classica": {"id": "via_classica", "desbloqueio": {"tipo": "pontos", "nivel": 4, "preco": 800}, "chave": "viatura"},
        "via_noturna": {"id": "via_noturna", "desbloqueio": {"tipo": "pontos", "nivel": 6, "preco": 1200}, "chave": "viatura"},
        "via_noe": {"id": "via_noe", "desbloqueio": {"tipo": "pago"}, "chave": "viatura"},
        "via_apoiador": {"id": "via_apoiador", "desbloqueio": {"tipo": "pago"}, "chave": "viatura"},
        "via_beta": {"id": "via_beta", "desbloqueio": {"tipo": "beta"}, "chave": "viatura"},
        "via_brasil": {"id": "via_brasil", "desbloqueio": {"tipo": "sazonal"}, "chave": "viatura"},
        "base_prf": {"id": "base_prf", "desbloqueio": {"tipo": "free"}, "chave": "base"},
        "arma_pistola": {"id": "arma_pistola", "desbloqueio": {"tipo": "free"}, "chave": "arma"},
        "arma_carabina": {"id": "arma_carabina", "desbloqueio": {"tipo": "pontos", "nivel": 6, "preco": 1500}, "chave": "arma"},
        "arma_ak47": {"id": "arma_ak47", "desbloqueio": {"tipo": "pontos", "nivel": 20, "preco": 6000}, "chave": "arma"},
        "arma_m4a1": {"id": "arma_m4a1", "desbloqueio": {"tipo": "pago"}, "chave": "arma"},
    }
    return mapa.get(skin_id)


# ---- Achievements ----

@app.route('/api/conquistas', methods=['GET'])
@token_obrigatorio
def conquistas(conta):
    desbloq = conta.get('conquistas', {})
    lista = []
    for cd in CONQUISTAS_DEF:
        lista.append({
            "id": cd['id'], "nome": cd['nome'],
            "descricao": cd['descricao'],
            "desbloqueada": desbloq.get(cd['id'], False),
        })
    return jsonify({"conquistas": lista})


# ---- Leaderboard ----

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    usuarios = ler_json(USUARIOS, {})
    ranked = []
    for u, c in usuarios.items():
        ranked.append({
            "usuario": u,
            "patente": c.get('patente', ''),
            "nivel": c.get('nivel', 1),
            "pontuacao_max": c.get('recordes', {}).get('pontuacao', 0),
            "km_max": c.get('recordes', {}).get('km', 0),
        })
    ranked.sort(key=lambda x: (-x['pontuacao_max'], -x['km_max']))
    return jsonify({"ranking": ranked[:50]})


# ---- Health ----

@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok", "versao": "1.0.0"})


def formatar_conta(c):
    return {
        "usuario": c['usuario'],
        "email": c.get('email', ''),
        "plano": "pago",
        "nivel": c.get('nivel', 1),
        "xp_total": c.get('xp_total', 0),
        "xp_proximo_nivel": calc_xp_proximo(c.get('nivel', 1)),
        "pontos": c.get('pontos', 0),
        "patente": c.get('patente', PATENTES[0][1]),
        "patrulhas_total": c.get('patrulhas_total', 0),
        "recordes": c.get('recordes', {"pontuacao": 0, "km": 0, "tempo_direcao_seg": 0}),
        "totais": c.get('totais', {"fiscalizacoes": 0, "prisoes": 0, "art230": 0, "pontos_total": 0, "km_total": 0}),
        "skins": c.get('skins', {"farda": "padrao", "viatura": "via_padrao", "base": "base_prf", "arma": "arma_pistola", "posse": []}),
        "conquistas": c.get('conquistas', {}),
        "beta": c.get('beta', False),
    }


# ---- Security ----

@app.after_request
def seguranca(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-XSS-Protection'] = '1; mode=block'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
