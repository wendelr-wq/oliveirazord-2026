class ControleAcesso:
    def __init__(self, usuarios_autorizados_url: str, timeout: int = 10, cache_ttl: int = 60):
        self.usuarios_autorizados_url = usuarios_autorizados_url
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._nomes_autorizados_cache = set()
        self._ultimo_refresh = 0.0

    @staticmethod
    def normalizar_nome(nome: str) -> str:
        return str(nome or "").strip().upper()

    def carregar_json(self, url: str) -> dict:
        return {}

    def carregar_usuarios_autorizados(self) -> list[dict]:
        return []

    def usuario_api_ativo_e_valido(self, usuario: dict) -> bool:
        return True

    def extrair_nomes_autorizados_api(self) -> set[str]:
        return set()

    def obter_nomes_autorizados(self, force_refresh: bool = False) -> set[str]:
        return set()

    def usuario_esta_autorizado(self, nome_usuario_logado: str, force_refresh: bool = False) -> bool:
        # Sempre autorizado, sem controle de acesso
        return True
