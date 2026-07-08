import os
import sys
from dotenv import load_dotenv

# Configura codificação UTF-8 para stdout/stderr no Windows para evitar UnicodeEncodeError com emojis/acentos
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Carrega as variáveis do arquivo .env
load_dotenv()

# Adiciona o diretório atual ao path para importações relativas funcionarem corretamente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.megazord_app import MegazordApp

if __name__ == "__main__":
    app = MegazordApp()
    app.executar()
