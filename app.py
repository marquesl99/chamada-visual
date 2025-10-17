# -*- coding: utf-8 -*-
"""
Aplicação web Flask para o sistema de Chamada Visual do Colégio Carbonell.

Este aplicativo fornece uma interface para buscar alunos em tempo real a partir
da API do sistema de gestão Sophia e exibi-los em um painel. A autenticação é
realizada via Google OAuth, restrita a usuários do domínio da escola.

Versão 2.0:
- Adicionado suporte a múltiplos painéis de exibição, permitindo a separação
  de chamadas por segmento (Educação Infantil e Ensino Fundamental).

Principais funcionalidades:
- Autenticação segura com contas Google do Colégio Carbonell.
- Busca de alunos na API Sophia com filtro por nome e segmento.
- Exibição de fotos dos alunos.
- Interface de terminal para realizar as chamadas.
- Painéis de exibição segmentados que são atualizados em tempo real via Firestore.
"""

# --- 1. IMPORTAÇÕES DE BIBLIOTECAS ---
# Módulos essenciais para o funcionamento do sistema.
import os
import time
import unicodedata
import concurrent.futures
import requests
from dotenv import load_dotenv
from functools import wraps
from flask import (
    Flask, jsonify, request, redirect, url_for, session, render_template, flash
)
from authlib.integrations.flask_client import OAuth

# --- 2. CONFIGURAÇÕES E INICIALIZAÇÕES ---

# Carrega variáveis de ambiente do arquivo .env (essencial para chaves de API)
load_dotenv()

# Instância principal da aplicação Flask. É o coração do nosso sistema web.
app = Flask(__name__)

# --- Configurações do App e Chaves (lidas do ambiente) ---
# Chave secreta para proteger as sessões dos usuários.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
# Credenciais para a autenticação com o Google.
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
# URL de descoberta do Google para configuração automática do OAuth.
app.config['GOOGLE_DISCOVERY_URL'] = "https://accounts.google.com/.well-known/openid-configuration"

# --- Configurações da API Sophia (sistema de gestão escolar) ---
SOPHIA_TENANT = os.getenv('SOPHIA_TENANT')
SOPHIA_USER = os.getenv('SOPHIA_USER')
SOPHIA_PASSWORD = os.getenv('SOPHIA_PASSWORD')
SOPHIA_API_HOSTNAME = os.getenv('SOPHIA_API_HOSTNAME')
# Monta a URL base para todas as chamadas à API Sophia.
API_BASE_URL = f"https://{SOPHIA_API_HOSTNAME}/SophiAWebApi/{SOPHIA_TENANT}" if SOPHIA_API_HOSTNAME and SOPHIA_TENANT else None

# --- Inicialização do OAuth para Login com Google ---
# Configura o cliente OAuth para interagir com a API de login do Google.
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={'scope': 'openid email profile'} # Define as informações que pedimos ao Google
)

# --- 3. DECORADOR DE AUTENTICAÇÃO ---
def login_obrigatorio(f):
    """
    Decorador que garante que o usuário esteja logado para acessar uma rota.

    Ele verifica se as informações do usuário ('user') estão na sessão do navegador.
    Se não estiverem, o usuário é redirecionado para a página de login.
    Isso protege as páginas internas, como o terminal de chamada.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 4. FUNÇÕES AUXILIARES ---

# Variáveis globais para armazenar o token da API Sophia e seu tempo de expiração.
# Isso evita que precisemos pedir um novo token a cada busca de aluno.
api_token = None
token_expires_at = 0

def get_sophia_token():
    """
    Obtém um token de autenticação para a API Sophia, reutilizando se for válido.

    1. Verifica se já temos um token e se ele não expirou.
    2. Se não houver token ou se estiver expirado, solicita um novo.
    3. Armazena o novo token e calcula seu tempo de expiração (29 minutos).
    """
    global api_token, token_expires_at
    # Se a URL base não estiver configurada, a função não prossegue.
    if not API_BASE_URL:
        print("AVISO: Variáveis da API Sophia não configuradas no arquivo .env.")
        return None
    # Reutiliza o token se ele ainda for válido.
    if api_token and time.time() < token_expires_at:
        return api_token

    # Se precisar de um novo token, faz a requisição.
    auth_url = f"{API_BASE_URL}/api/v1/Autenticacao"
    auth_data = {"usuario": SOPHIA_USER, "senha": SOPHIA_PASSWORD}
    try:
        response = requests.post(auth_url, json=auth_data, timeout=10)
        response.raise_for_status() # Lança um erro se a requisição falhar
        api_token = response.text.strip()
        token_expires_at = time.time() + (29 * 60) # Define a expiração para 29 min
        print("Novo token da API Sophia obtido com sucesso.")
        return api_token
    except requests.exceptions.RequestException as e:
        print(f"Erro ao obter token da API Sophia: {e}")
        return None

def fetch_photo(aluno_id, headers):
    """
    Busca a foto de um aluno específico na API Sophia.

    Esta função é projetada para ser executada em paralelo (usando ThreadPoolExecutor)
    para agilizar o carregamento de fotos de múltiplos alunos.
    """
    try:
        photo_url = f"{API_BASE_URL}/api/v1/alunos/{aluno_id}/Fotos/FotosReduzida"
        response_foto = requests.get(photo_url, headers=headers, timeout=5)
        if response_foto.status_code == 200 and response_foto.text:
            # A foto vem em formato JSON, dentro de um campo 'foto' em base64.
            dados_foto = response_foto.json()
            foto_base64 = dados_foto.get('foto')
            if foto_base64:
                return aluno_id, foto_base64
    except requests.exceptions.RequestException:
        pass # Ignora erros de fotos individuais para não travar a busca principal
    return aluno_id, None

def normalize_text(text):
    """
    Normaliza uma string: remove acentos e converte para minúsculas.

    Isso é crucial para que a busca de alunos funcione independentemente de o usuário
    digitar "joao" ou "João".
    """
    if not text:
        return ""
    text = str(text).lower()
    # Decompõe os caracteres (ex: 'á' vira 'a' + ´) e remove os acentos.
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# --- 5. ROTA DA API DE BUSCA ---
@app.route('/api/buscar-aluno', methods=['GET'])
@login_obrigatorio # Protege esta rota, só usuários logados podem buscar.
def buscar_aluno():
    """
    Endpoint da API interna para buscar alunos no sistema Sophia.

    Recebe um termo de busca e um filtro de segmento, consulta a API do Sophia,
    processa os resultados, busca as fotos em paralelo e retorna uma lista
    de alunos em formato JSON.
    """
    token = get_sophia_token()
    if not token:
        return jsonify({"erro": "Não foi possível autenticar com a API Sophia."}), 500

    parte_nome = request.args.get('parteNome', '').strip()
    grupo_filtro = request.args.get('grupo', 'todos').upper()

    # Evita buscas vazias ou muito curtas para não sobrecarregar a API.
    if not parte_nome or len(parte_nome) < 2:
        return jsonify([])

    headers = {'token': token, 'Accept': 'application/json'}
    params = {"Nome": parte_nome.split(' ')[0]} # Busca pelo primeiro nome na API.
    search_url = f"{API_BASE_URL}/api/v1/alunos"

    try:
        response_alunos = requests.get(search_url, headers=headers, params=params)
        response_alunos.raise_for_status()
        lista_alunos_api = response_alunos.json()

        alunos_filtrados = []
        termos_busca_normalizados = normalize_text(parte_nome).split()

        # Filtra os resultados localmente para refinar a busca
        for aluno in lista_alunos_api:
            turma_aluno = aluno.get("turmas", [{}])[0].get("descricao", "")
            # Regras de negócio: Ignorar Ensino Médio e aplicar filtro de segmento
            if turma_aluno.upper().startswith('EM'):
                continue
            if grupo_filtro != 'TODOS' and not turma_aluno.upper().startswith(grupo_filtro):
                continue

            # Garante que todos os termos digitados estão no nome do aluno
            nome_completo_normalizado = normalize_text(aluno.get("nome"))
            if all(termo in nome_completo_normalizado for termo in termos_busca_normalizados):
                alunos_filtrados.append(aluno)

        # Mapeia os dados dos alunos para um formato mais simples
        alunos_map = {
            aluno.get("codigo"): {
                "id": aluno.get("codigo"),
                "nomeCompleto": aluno.get("nome", "Nome não encontrado"),
                "turma": aluno.get("turmas", [{}])[0].get("descricao", "Sem turma")
            } for aluno in alunos_filtrados if aluno.get("codigo")
        }

        # Busca as fotos de todos os alunos filtrados em paralelo para otimizar o tempo
        fotos = {}
        if alunos_map:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_to_id = {executor.submit(fetch_photo, aluno_id, headers): aluno_id for aluno_id in alunos_map.keys()}
                for future in concurrent.futures.as_completed(future_to_id):
                    aluno_id, foto_data = future.result()
                    if foto_data:
                        fotos[aluno_id] = foto_data

        # Adiciona a URL da foto aos dados do aluno e formata a lista final
        alunos_formatados = []
        for aluno_id, aluno_data in alunos_map.items():
            aluno_data['fotoUrl'] = fotos.get(aluno_id)
            alunos_formatados.append(aluno_data)

        return jsonify(alunos_formatados)

    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar alunos na API Sophia: {e}")
        return jsonify({"erro": "Ocorreu um erro ao buscar os dados no sistema Sophia."}), 500

# --- 6. ROTAS DE AUTENTICAÇÃO E NAVEGAÇÃO ---
@app.route('/')
def index():
    """
    Página inicial. Redireciona para o terminal se o usuário já estiver
    logado, ou para a página de login caso contrário.
    """
    if 'user' in session:
        return redirect(url_for('terminal'))
    return redirect(url_for('login'))

@app.route('/login')
def login():
    """Renderiza a página de login."""
    return render_template('login.html')

@app.route('/entrar-google')
def login_google():
    """Inicia o fluxo de autenticação com o Google."""
    redirect_uri = url_for('google_auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/google-auth')
def google_auth():
    """
    Callback do Google após o login.
    Processa a resposta, verifica se o e-mail é do domínio permitido e
    salva as informações do usuário na sessão.
    """
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')

    # Validação de segurança: apenas e-mails do domínio correto podem acessar.
    if not user_info or not user_info.get('email', '').endswith('@colegiocarbonell.com.br'):
        flash('Acesso negado. Utilize uma conta do Colégio Carbonell.', 'danger')
        return redirect(url_for('login'))

    # Salva as informações do usuário na sessão, marcando-o como logado.
    session['user'] = {'email': user_info['email'], 'name': user_info['name']}
    return redirect(url_for('terminal'))

@app.route('/logout')
def logout():
    """
    Faz o logout do usuário, limpando a sessão e redirecionando para o login.
    """
    session.pop('user', None)
    flash('Você saiu da sua conta.', 'success')
    return redirect(url_for('login'))

# --- 7. ROTAS PRINCIPAIS DA APLICAÇÃO ---
@app.route('/terminal')
@login_obrigatorio
def terminal():
    """Renderiza a página do terminal de chamada (protegida por login)."""
    return render_template('terminal.html')

@app.route('/painel')
def painel():
    """Renderiza a página do painel de exibição original (legado)."""
    return render_template('painel.html')

@app.route('/painel-infantil')
def painel_infantil():
    """Renderiza o painel de exibição exclusivo da Educação Infantil."""
    return render_template('painel_ei.html')

@app.route('/painel-fundamental')
def painel_fundamental():
    """Renderiza o painel de exibição exclusivo do Ensino Fundamental."""
    return render_template('painel_fund.html')

# --- 8. BLOCO DE EXECUÇÃO PARA DESENVOLVIMENTO ---
if __name__ == '__main__':
    """
    Este bloco permite que a aplicação seja executada diretamente com 'python app.py'.
    É ideal para testes locais.
    - debug=True: Ativa o modo de depuração, que reinicia o servidor
      automaticamente a cada alteração no código e mostra erros detalhados.
    - ATENÇÃO: Nunca use debug=True em um ambiente de produção!
    """
    app.run(host='0.0.0.0', port=5000, debug=True)
