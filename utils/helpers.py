# utils/helpers.py
import re
import os
import json
import unicodedata
from datetime import datetime

# ==================== CONSTANTES LOCAIS ====================
# A API Paladino externa foi removida para tornar a ferramenta independente
# de servidores externos. Os dados agora são armazenados localmente em data/

# ==================== FUNÇÃO DE API LOCAL ====================

def carregar_json_local(nome_arquivo: str):
    """Carrega um arquivo JSON da pasta data/ na raiz do projeto."""
    try:
        # Resolve o caminho para a pasta data/
        caminho_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        caminho = os.path.join(caminho_base, "data", nome_arquivo)
        
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            print(f"Aviso: arquivo local {caminho} não encontrado.")
            return None
    except Exception as e:
        print(f"Erro ao carregar JSON local {nome_arquivo}: {e}")
        return None


def extrair_lista_json(dados, chave):
    """Extrai uma lista de um JSON, seja dicionário ou lista."""
    if isinstance(dados, dict):
        return dados.get(chave, [])
    if isinstance(dados, list):
        return dados
    return []


# ==================== FUNÇÃO DE CENTRALIZAR A INTERFACE ====================

def centralizar_janela(janela, largura, altura):
    """Centraliza uma janela Tkinter na tela."""
    janela.update_idletasks()
    ws = janela.winfo_screenwidth()
    hs = janela.winfo_screenheight()
    x = int((ws / 2) - (largura / 2))
    y = int((hs / 2) - (altura / 2))
    janela.geometry(f"{largura}x{altura}+{x}+{y}")


def normalizar_nome(nome):
    """Normaliza strings removendo acentos e espaços extras."""
    if nome is None:
        return ""
    nome = str(nome).strip()
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(ch for ch in nome if not unicodedata.combining(ch))
    nome = re.sub(r"\s+", " ", nome).strip().upper()
    return nome


def achatar_estrutura(obj):
    """Achata estruturas aninhadas de listas e dicionários."""
    itens = []

    if isinstance(obj, dict):
        itens.append(obj)
        for valor in obj.values():
            itens.extend(achatar_estrutura(valor))
    elif isinstance(obj, list):
        for item in obj:
            itens.extend(achatar_estrutura(item))

    return itens
