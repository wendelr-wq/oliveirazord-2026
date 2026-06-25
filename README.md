# OLIVEIRAZORD 2026 — MEGAZORD v18.4.M.1

Automação de inscrição em vagas de voluntariado no **PROEIS** (Programa Estadual de Integração de Segurança) do estado do Rio de Janeiro.

## Funcionalidades

- Login automatizado no site do PROEIS com resolução de CAPTCHA via CapMonster Cloud
- Painel Duplo de Agendamento (horário de login + horário de disparo das vagas)
- Sincronização precisa com o relógio do servidor PROEIS
- Modo "Extreme Speed" com dezenas de parâmetros de timing ajustáveis
- Gerenciamento de múltiplas inscrições simultaneamente via interface gráfica
- Hotkeys para ações rápidas durante a automação

## Tecnologias

- **Python 3.13+**
- **Tkinter** — Interface gráfica
- **SeleniumBase** — Automação de navegador
- **CapMonster Cloud API** — Solução de CAPTCHA
- **requests / parsel** — Requisições HTTP e parsing HTML

## Instalação

1. Tenha o **Python 3.10+** instalado e adicionado ao PATH.
2. Execute o instalador:
   ```
   instalar.bat
   ```
   OU manualmente:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Configuração

Renomeie `.env.example` para `.env` e preencha:

```
CAPMONSTER_API_KEY=sua_chave_capmonster
PROEIS_LOGIN=seu_cpf
PROEIS_SENHA=sua_senha
```

> ⚠️ Mantenha o `.env` seguro e **nunca** o compartilhe.

## Execução

```
executar.bat
```
OU
```
venv\Scripts\activate
python main.py
```

## Hotkeys (durante a automação)

| Tecla | Ação |
|-------|------|
| `Ctrl+1` | Disparar login |
| `Q` | Disparar inscrição/busca de vaga |
| `Z` | Abrir painel duplo de agendamento |
| `ESC` | Sair da aplicação |

## Estrutura do Projeto

```
├── main.py                 # Ponto de entrada
├── gui/
│   └── megazord_app.py     # Interface gráfica (Tkinter)
├── automation/
│   ├── automacao_proeis.py # Motor principal de automação
│   └── capmonster_solver.py# Integração com CapMonster Cloud
├── models/
│   └── inscricao.py        # Modelo de dados de inscrição
├── utils/
│   └── helpers.py          # Funções utilitárias
├── data/
│   ├── convenios.json      # Dados de convênios
│   └── cpa.json            # Dados de CPA
└── assets/
    └── MEGAZORD.ico        # Ícone da aplicação
```

## Aviso

Esta ferramenta foi desenvolvida para fins de estudo e otimização de processos internos. Use com responsabilidade e apenas em conformidade com os termos de uso do PROEIS.
