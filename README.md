# ⚡ OLIVEIRAZORD 2026

> **Robô de automação para inscrições no PROEIS-RJ**  
> Automatiza login, resolução de captcha e marcação de vagas na escala voluntária do PROEIS com precisão de milissegundos.

---

## 📋 Índice

- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
- [Configuração do .env](#-configuração-do-env)
- [Como Usar](#-como-usar)
- [Atalhos de Teclado](#-atalhos-de-teclado)
- [Painel de Agendamento (Z)](#-painel-de-agendamento-z)
- [Reconexão Automática](#-reconexão-automática)
- [Resolução de Problemas](#-resolução-de-problemas)

---

## 🖥️ Requisitos

| Requisito | Versão mínima |
|---|---|
| **Windows** | 10 ou superior |
| **Python** | 3.10+ |
| **Google Chrome** | Versão atual (atualizado) |
| **Conta CapMonster Cloud** | Saldo disponível |
| **Acesso ao PROEIS-RJ** | Login e ID Funcional válidos |

> ⚠️ Durante a instalação do Python, marque a opção **"Add Python to PATH"**.

---

## 🚀 Instalação

### Passo 1 — Baixe ou clone o projeto

Coloque a pasta do projeto em qualquer local do seu computador.

### Passo 2 — Configure o arquivo `.env`

Antes de instalar, preencha suas credenciais (veja a seção [Configuração do .env](#-configuração-do-env)).

### Passo 3 — Execute o instalador

Clique duas vezes em **`instalar.bat`**.

O instalador fará automaticamente:
- ✅ Verificar se o Python está instalado
- ✅ Criar o ambiente virtual (`venv`)
- ✅ Atualizar o pip
- ✅ Instalar todas as dependências (`requirements.txt`)
- ✅ Instalar o driver do Chrome (ChromeDriver)

> ⏱️ A instalação pode levar de **2 a 10 minutos** dependendo da sua conexão com a internet.

---

## 🔑 Configuração do `.env`

Na pasta do projeto existe um arquivo chamado **`.env`**. Abra-o com o Bloco de Notas e preencha com seus dados:

```env
# Chave da API do CapMonster Cloud para resolução de Captchas
CAPMONSTER_API_KEY=SUA_CHAVE_CAPMONSTER_AQUI

# Seu ID Funcional (login do PROEIS)
PROEIS_LOGIN=SEU_ID_FUNCIONAL

# Sua senha do PROEIS
PROEIS_SENHA=SUA_SENHA
```

### Como obter a chave do CapMonster Cloud

1. Acesse [capmonster.cloud](https://capmonster.cloud/)
2. Crie uma conta e adicione créditos
3. Copie sua **API Key** no painel
4. Cole no campo `CAPMONSTER_API_KEY` do `.env`

> 🔒 **Nunca compartilhe seu arquivo `.env` com ninguém.** Ele contém suas credenciais de acesso.

---

## ▶️ Como Usar

### Iniciando o programa

Clique duas vezes em **`executar.bat`**.

O programa abrirá:
1. **Uma janela de interface** (painel principal com lista de inscrições)
2. **Um navegador Chrome** abrindo o site do PROEIS

### Fluxo completo de uso

```
1. Executar executar.bat
2. Na interface, preencher a lista de locais desejados
3. Aguardar o site do PROEIS abrir no navegador
4. Pressionar Ctrl+1 para fazer login automático
5. Pressionar Q para iniciar a busca por vagas
```

---

## ⌨️ Atalhos de Teclado

| Tecla | Função |
|---|---|
| `Ctrl+1` | Faz login automático no PROEIS (com captcha) |
| `Q` | Inicia a busca inteligente por vagas |
| `ESC` | Encerra o programa |
| `Z` | Abre/fecha o Painel de Agendamento |

### Comportamento do Q (contextual)

O botão `Q` age de forma inteligente dependendo da página atual:

| Página atual | O que Q faz |
|---|---|
| Menu Voluntário | Clica em "Escala" |
| Lista de Inscrições | Clica em "Nova Inscrição" |
| Tela de Associar Evento | Inicia a marcação automática |

---

## 📅 Painel de Agendamento (Z)

O painel de agendamento permite programar o login e o disparo automático para um horário exato, com sincronização pelo relógio do servidor do PROEIS.

### Como usar

1. Pressione **`Z`** para abrir o painel
2. Defina o **horário do login** (ex: `05:55:00`)
3. Defina o **horário do disparo** (ex: `06:00:00`)
4. Clique em **▶ START**

### Funcionalidades do painel

- 🕐 **Relógio sincronizado** com o servidor do PROEIS (milissegundos)
- 🔁 **Resincronização automática** na reta final (60s antes do disparo)
- 🛡️ **Monitor anti-congelamento** durante a espera longa
- 📡 **Operação em background**: fechar o painel com X **não cancela** o agendamento

### Painel fechado com X → agendamento continua!

Se você fechar o painel Z com o botão X enquanto o agendamento está ativo:
- O robô **continua contando** o tempo em background
- Ao reabrir com **Z**, o painel mostra os horários e a etapa atual (login/disparo)
- O agendamento **nunca é perdido** ao fechar o painel

---

## 🔄 Reconexão Automática

O sistema detecta automaticamente quando a sessão do PROEIS é perdida:

| Situação | Ação automática |
|---|---|
| Sessão expirada durante marcação | Faz relogin silencioso e retoma |
| Erro ViewState / MAC failed | Recarrega a página e recupera |
| Captcha inválido | Tenta novamente automaticamente |
| Select de data/convênio falhou | Recarrega a tela (até 8 tentativas) |

> ⚠️ **Atenção:** Se desconectar **antes** de pressionar Q (modo de espera), pressione `Ctrl+1` para reconectar manualmente. O agendamento automático navega para o login sozinho.

---

## 🗂️ Estrutura do Projeto

```
OLIVEIRAZORD 2026/
├── instalar.bat          ← Execute para instalar
├── executar.bat          ← Execute para rodar o programa
├── main.py               ← Ponto de entrada
├── .env                  ← Suas credenciais (não compartilhe!)
├── .env.example          ← Modelo do .env
├── requirements.txt      ← Dependências Python
├── automation/
│   ├── automacao_proeis.py   ← Núcleo do robô
│   └── capmonster_solver.py  ← Resolução de captcha
├── gui/
│   └── megazord_app.py       ← Interface gráfica
├── models/
│   └── inscricao.py          ← Modelo de dados
├── data/                     ← Listas de inscrições
└── assets/                   ← Ícones e recursos
```

---

## 🛠️ Resolução de Problemas

### ❌ "Python não foi encontrado"
Instale o Python em [python.org](https://www.python.org/downloads/) e marque **"Add Python to PATH"** durante a instalação.

### ❌ O navegador abre e fecha imediatamente
Verifique se o Chrome está atualizado. O ChromeDriver é instalado automaticamente pelo instalador.

### ❌ "Não está na página de login"
Aguarde o site carregar completamente antes de pressionar `Ctrl+1`.

### ❌ Captcha sempre inválido
- Verifique se a `CAPMONSTER_API_KEY` no `.env` está correta
- Verifique se há saldo na sua conta CapMonster Cloud

### ❌ Login falha com "ID/Senha inválidos"
Confirme as credenciais `PROEIS_LOGIN` e `PROEIS_SENHA` no arquivo `.env`.

### ❌ O agendamento não dispara
- Confirme que o relógio está sincronizado (botão 🔄 no painel Z)
- Verifique se o horário configurado não está no passado
- Certifique-se de que clicou em **▶ START** antes de fechar o painel

---

## 📦 Dependências

| Pacote | Finalidade |
|---|---|
| `seleniumbase` | Automação do navegador Chrome |
| `python-dotenv` | Leitura do arquivo `.env` |
| `keyboard` | Captura de atalhos de teclado globais |
| `parsel` | Parsing de HTML |
| `pandas` | Manipulação de listas de inscrições |
| `requests` | Requisições HTTP (sincronização de relógio) |
| `tkcalendar` | Interface gráfica (seletor de datas) |

---

## ⚖️ Aviso Legal

Este software foi desenvolvido para uso pessoal e automatiza ações que o próprio usuário realizaria manualmente no site do PROEIS-RJ. O uso é de responsabilidade exclusiva do usuário.

---

*OLIVEIRAZORD 2026 — Desenvolvido para o PROEIS-RJ*
