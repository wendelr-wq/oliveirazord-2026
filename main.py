import os
import sys
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

# Adiciona o diretório atual ao path para importações relativas funcionarem corretamente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.megazord_app import MegazordApp

if __name__ == "__main__":
    app = MegazordApp()
    app.executar()
