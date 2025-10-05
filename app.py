# app.py - Versão simplificada para Google Cloud App Engine

import os
import requests
import time
import base64
from dotenv import load_dotenv
from flask import (
    Flask, jsonify, request, redirect, url_for, session, render_template, flash
)
from authlib.integrations.flask_client import OAuth
from functools import wraps
import concurrent.futures
import unicodedata

# --- 1. CONFIGURAÇÕES E INICIALIZAÇÕES ---
load_dotenv() # Carrega variáveis do .env para testes locais
app = Flask(__name__)

# Configurações do App e Chaves (lidas do ambiente)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config['GOOGLE_DISCOVERY_URL'] = "https://accounts.google.com/.well-known/openid-configuration"

# Configurações da API Sophia
SOPHIA_TENANT = os.getenv('SOPHIA_TENANT')
SOPHIA_USER = os.getenv('SOPHIA_USER')
SOPHIA_PASSWORD = os.getenv('SOPHIA_PASSWORD')
SOPHIA_API_HOSTNAME = os.getenv('SOPHIA_API_HOSTNAME')
API_BASE_URL = f"https://{SOPHIA_API_HOSTNAME}/SophiAWebApi/{SOPHIA_TENANT}" if SOPHIA_API_HOSTNAME and SOPHIA_TENANT else None

# Inicialização do OAuth
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={'scope': 'openid email profile'}
)

# --- 2. DECORADOR DE AUTENTICAÇÃO ---
def login_obrigatorio(f):
    """
    Decorator that requires login for a route.

    This decorator checks if a user is logged in by verifying the presence of
    the 'user' key in the session. If the user is not logged in, they are
    redirected to the login page.

    Args:
        f (function): The function to be decorated.

    Returns:
        function: The decorated function.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 3. FUNÇÕES AUXILIARES ---
api_token = None
token_expires_at = 0
def get_sophia_token():
    """
    Retrieves an authentication token for the Sophia API.

    This function checks if a valid token already exists and is not expired.
    If not, it requests a new token from the Sophia API using the configured
    credentials.

    Returns:
        str: The authentication token, or None if an error occurs.
    """
    global api_token, token_expires_at
    if not API_BASE_URL:
        print("AVISO: Variáveis da API Sophia não configuradas.")
        return None
    if api_token and time.time() < token_expires_at:
        return api_token
    auth_url = f"{API_BASE_URL}/api/v1/Autenticacao"
    auth_data = {"usuario": SOPHIA_USER, "senha": SOPHIA_PASSWORD}
    try:
        response = requests.post(auth_url, json=auth_data, timeout=10)
        response.raise_for_status()
        api_token = response.text.strip()
        token_expires_at = time.time() + (29 * 60)
        print("Novo token da API Sophia obtido com sucesso.")
        return api_token
    except requests.exceptions.RequestException as e:
        print(f"Erro ao obter token da API Sophia: {e}")
        return None

def fetch_photo(aluno_id, headers):
    """
    Fetches a student's photo from the Sophia API.

    Args:
        aluno_id (int): The ID of the student.
        headers (dict): The headers to be sent with the request, including the
                        authentication token.

    Returns:
        tuple: A tuple containing the student's ID and the base64-encoded
               photo, or (aluno_id, None) if the photo is not found or an
               error occurs.
    """
    try:
        photo_url = f"{API_BASE_URL}/api/v1/alunos/{aluno_id}/Fotos/FotosReduzida"
        response_foto = requests.get(photo_url, headers=headers, timeout=5)
        if response_foto.status_code == 200 and response_foto.text:
            dados_foto = response_foto.json()
            foto_base64 = dados_foto.get('foto')
            if foto_base64:
                return aluno_id, foto_base64
    except requests.exceptions.RequestException:
        pass
    return aluno_id, None

def normalize_text(text):
    """
    Normalizes a string by converting it to lowercase and removing diacritics.

    Args:
        text (str): The string to be normalized.

    Returns:
        str: The normalized string.
    """
    if not text:
        return ""
    text = str(text).lower()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# --- 4. ROTA DA API DE BUSCA ---
@app.route('/api/buscar-aluno', methods=['GET'])
@login_obrigatorio
def buscar_aluno():
    """
    API endpoint to search for students.

    This endpoint requires login and searches for students based on a partial
    name and an optional group filter. It fetches data from the Sophia API,
    filters the results, and returns a JSON list of students with their
    photos.

    Query Parameters:
        parteNome (str): The partial name of the student to search for.
        grupo (str): The group to filter by (e.g., 'EF', 'EM'). Defaults to
                     'todos'.

    Returns:
        JSON: A JSON response containing a list of students or an error
              message.
    """
    token = get_sophia_token()
    if not token:
        return jsonify({"erro": "Não foi possível autenticar com a API Sophia."}), 500

    parte_nome = request.args.get('parteNome', '').strip()
    grupo_filtro = request.args.get('grupo', 'todos').upper()

    if not parte_nome or len(parte_nome) < 2:
        return jsonify([])

    primeiro_nome = parte_nome.split(' ')[0]
    headers = {'token': token, 'Accept': 'application/json'}
    params = {"Nome": primeiro_nome}
    search_url = f"{API_BASE_URL}/api/v1/alunos"

    try:
        response_alunos = requests.get(search_url, headers=headers, params=params)
        response_alunos.raise_for_status()
        lista_alunos_api = response_alunos.json()

        alunos_filtrados = []
        termos_busca_normalizados = normalize_text(parte_nome).split()

        for aluno in lista_alunos_api:
            turma_aluno = aluno.get("turmas", [{}])[0].get("descricao", "")
            if turma_aluno.upper().startswith('EM'):
                continue
            if grupo_filtro != 'TODOS' and not turma_aluno.upper().startswith(grupo_filtro):
                continue

            nome_completo_normalizado = normalize_text(aluno.get("nome"))
            if all(termo in nome_completo_normalizado for termo in termos_busca_normalizados):
                alunos_filtrados.append(aluno)

        alunos_map = {
            aluno.get("codigo"): {
                "id": aluno.get("codigo"),
                "nomeCompleto": aluno.get("nome", "Nome não encontrado"),
                "turma": aluno.get("turmas", [{}])[0].get("descricao", "Sem turma")
            } for aluno in alunos_filtrados if aluno.get("codigo")
        }

        fotos = {}
        if alunos_map:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_to_id = {executor.submit(fetch_photo, aluno_id, headers): aluno_id for aluno_id in alunos_map.keys()}
                for future in concurrent.futures.as_completed(future_to_id):
                    aluno_id, foto_data = future.result()
                    if foto_data:
                        fotos[aluno_id] = foto_data

        alunos_formatados = []
        for aluno_id, aluno_data in alunos_map.items():
            aluno_data['fotoUrl'] = fotos.get(aluno_id)
            alunos_formatados.append(aluno_data)

        return jsonify(alunos_formatados)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar alunos na API Sophia: {e}")
        return jsonify({"erro": "Ocorreu um erro ao buscar os dados no sistema Sophia."}), 500

# --- 5. ROTAS DE AUTENTICAÇÃO E NAVEGAÇÃO ---
@app.route('/')
def index():
    """
    Redirects to the terminal if the user is logged in, otherwise to the
    login page.

    Returns:
        Response: A redirect to the terminal or login page.
    """
    if 'user' in session:
        return redirect(url_for('terminal'))
    return redirect(url_for('login'))

@app.route('/login')
def login():
    """
    Renders the login page.

    Returns:
        Response: The rendered login page.
    """
    return render_template('login.html')

@app.route('/entrar-google')
def login_google():
    """
    Initiates the Google OAuth login process.

    Returns:
        Response: A redirect to the Google authorization page.
    """
    redirect_uri = url_for('google_auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/google-auth')
def google_auth():
    """
    Handles the Google OAuth callback.

    This route receives the authorization token from Google, fetches the
    user's information, and checks if the user's email domain is allowed.
    If the user is authorized, their information is stored in the session.

    Returns:
        Response: A redirect to the terminal page on success, or back to the
                  login page on failure.
    """
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')

    if not user_info or not user_info.get('email', '').endswith('@colegiocarbonell.com.br'):
        flash('Acesso negado. Utilize uma conta do Colégio Carbonell.', 'danger')
        return redirect(url_for('login'))

    # Simplesmente salva na sessão, sem banco de dados
    session['user'] = {'email': user_info['email'], 'name': user_info['name']}
    return redirect(url_for('terminal'))

@app.route('/logout')
def logout():
    """
    Logs the user out by clearing the session.

    Returns:
        Response: A redirect to the login page.
    """
    session.pop('user', None)
    return redirect(url_for('login'))

# --- 6. ROTAS DA APLICAÇÃO ---
@app.route('/terminal')
@login_obrigatorio
def terminal():
    """
    Renders the main terminal page.

    This route requires the user to be logged in.

    Returns:
        Response: The rendered terminal page.
    """
    return render_template('terminal.html')

@app.route('/painel')
def painel():
    """
    Renders the panel page.

    Returns:
        Response: The rendered panel page.
    """
    return render_template('painel.html')

# A seção if __name__ == '__main__' foi removida pois o Gunicorn irá gerenciar o servidor.