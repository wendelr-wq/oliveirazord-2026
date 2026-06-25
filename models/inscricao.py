class Inscricao:
    def __init__(self, convenio, cpa, data, direcao, condicao_local, local,
                 condicao_hora, hora, turno, endereco, tipo_vaga):
        # Dados de Filtro (usados para navegar na página)
        self.convenio = convenio
        self.cpa = cpa
        self.data = data
        # Dados para localizar a vaga na tabela
        self.direcao = direcao
        self.condicao_local = condicao_local
        self.local = local
        self.condicao_hora = condicao_hora
        self.hora = hora
        self.turno = turno
        self.endereco = endereco
        self.tipo_vaga = tipo_vaga

    @classmethod
    def from_dict(cls, dados: dict):
        """Cria uma instância a partir do dicionário gerado pela interface."""
        return cls(
            convenio=dados.get("convenio", ""),
            cpa=dados.get("cpa", ""),
            data=dados.get("data", ""),
            direcao=dados.get("direcao", ""),
            condicao_local=dados.get("local_condicao", ""),
            local=dados.get("local", ""),
            condicao_hora=dados.get("hora_condicao", ""),
            hora=dados.get("hora", ""),
            turno=dados.get("turno", ""),
            endereco=dados.get("endereco", ""),
            tipo_vaga=dados.get("tipo", ""),
        )

    def obter_criterios_filtro(self):
        """Retorna um dicionário com os critérios prontos para aplicar_filtros."""
        # Mapeamento das condições de hora
        mapa_hora = {
            "Não filtrar": "não filtrar",
            "Depois de": "depois",
            "Antes de": "antes",
            "Exatamente": "igual",
        }
        # Mapeamento das condições de local
        mapa_local = {
            "Não filtrar": "não filtrar",
            "Contém a palavra": "contém",
            "Não contém a palavra": "não contém",
            "Exatamente igual": "igual",
        }
        # Tipo de vaga: mantemos "Titular" e "Reserva" em minúsculas;
        # "Titular/Reserva" passa como "titular/reserva" para a automação tratar
        if self.tipo_vaga == "Titular/Reserva":
            tipo_filtro = "titular/reserva"
        else:
            tipo_filtro = self.tipo_vaga.lower()

        return {
            "condicao_hora": mapa_hora.get(self.condicao_hora, "não filtrar"),
            "hora": self.hora,
            "tipo_vaga": tipo_filtro,
            "condicao_local": mapa_local.get(self.condicao_local, "não filtrar"),
            "local": self.local,
            "turno": self.turno,
            "endereco": self.endereco,
        }

    def __repr__(self):
        return (f"Inscricao(convenio={self.convenio!r}, cpa={self.cpa!r}, data={self.data!r}, "
                f"direcao={self.direcao!r}, condicao_local={self.condicao_local!r}, local={self.local!r}, "
                f"condicao_hora={self.condicao_hora!r}, hora={self.hora!r}, turno={self.turno!r}, "
                f"endereco={self.endereco!r}, tipo_vaga={self.tipo_vaga!r})")
