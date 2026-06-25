import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import datetime, timedelta
import threading

from utils.helpers import (
    carregar_json_local,
    extrair_lista_json,
    centralizar_janela,
)

from automation.automacao_proeis import AutomacaoProeis
from models.inscricao import Inscricao

CAPMONSTER_API_KEY = os.getenv("CAPMONSTER_API_KEY", "429840b44274fcbfaae0c6bf810c9c11")


class MegazordApp:
    BG_APP = "#e5e7eb"
    BG_CARD = "#ffffff"
    BG_TOP = "#0f172a"
    BG_LEFT = "#ffffff"
    FG_DARK = "#111827"
    FG_MUTED = "#6b7280"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    DANGER = "#ef4444"
    INFO = "#3b82f6"
    FONT_LABEL = ("Segoe UI", 9, "bold")
    FONT_TEXT = ("Segoe UI", 10)
    FONT_BUTTON = ("Segoe UI", 10, "bold")
    FONT_TOP = ("Segoe UI", 10, "bold")

    def __init__(self):
        self.inscricoes = []
        
        # Carrega credenciais do arquivo .env
        self.id_salvo = os.getenv("PROEIS_LOGIN", "")
        self.senha_salva = os.getenv("PROEIS_SENHA", "")
        self.usuario_selecionado = f"Operador (.env: {self.id_salvo})"
        
        self.usuariosPALADINO_map = {
            self.usuario_selecionado: {
                "id_funcional": self.id_salvo,
                "senha": self.senha_salva
            }
        }
        self.convenio_map = {}
        self.cpa_map = {}
        self.usuarios_autorizados = []
        self.usuario_autorizado_logado = {"nome": "Operador Único"}
        self.login_autorizado_logado = self.id_salvo

        self.root = None
        self.usuario_select = None
        self.convenio = None
        self.cpa = None
        self.direcao = None
        self.data = None
        self.condicao_local = None
        self.local_entry = None
        self.condicao_hora = None
        self.hora_entry = None
        self.turno = None
        self.endereco_entry = None
        self.tipo_vaga = None
        self.lista_vagas = None
        self.dono_label = None

        self.automacao = None
        self.thread_automacao = None

    def executar(self):
        # Ignora a tela de login inicial do Paladino e vai direto para a interface principal
        self.criar_interface_principal()

    def criar_interface_principal(self):
        self.root = tk.Tk()
        self.root.title("MEGAZORD 18.4.M.1")
        centralizar_janela(self.root, 1400, 680)
        self.root.resizable(True, False)
        self.root.minsize(1100, 680)
        self.root.configure(bg=self.BG_APP)

        top_frame = tk.Frame(self.root, bg=self.BG_TOP, height=40)
        top_frame.pack(fill="x")
        top_frame.pack_propagate(False)

        self.dono_label = tk.Label(
            top_frame,
            text=f"🔐 Usuário logado: {self.usuario_autorizado_logado.get('nome', '')} ({self.login_autorizado_logado})",
            fg="white",
            bg=self.BG_TOP,
            font=self.FONT_TOP
        )
        self.dono_label.pack(anchor="w", padx=12, pady=10)

        body_frame = tk.Frame(self.root, bg=self.BG_APP)
        body_frame.pack(fill="both", expand=True, padx=8, pady=8)

        left_frame = self.criar_coluna_esquerda_rolavel(body_frame)

        right_container = tk.Frame(body_frame, bg=self.BG_CARD, bd=1, relief="solid")
        right_container.pack(side="right", fill="both", expand=True)

        right_frame = tk.Frame(right_container, bg=self.BG_CARD, padx=10, pady=8)
        right_frame.pack(fill="both", expand=True)

        self.preencher_campos_esquerda(left_frame)

        tk.Label(
            right_frame,
            text="📋 Lista de Vagas",
            bg=self.BG_CARD,
            fg=self.FG_DARK,
            font=("Segoe UI", 11, "bold")
        ).pack(fill="x", pady=(0, 6))

        frame_lista = tk.Frame(right_frame, bg=self.BG_CARD)
        frame_lista.pack(fill="both", expand=True)

        scroll = tk.Scrollbar(frame_lista)
        scroll.pack(side="right", fill="y")

        self.lista_vagas = tk.Listbox(
            frame_lista,
            yscrollcommand=scroll.set,
            font=("Consolas", 10),
            bd=1,
            relief="solid"
        )
        self.lista_vagas.pack(fill="both", expand=True)
        scroll.config(command=self.lista_vagas.yview)

        tk.Button(
            right_frame,
            text="🗑 Remover Vaga",
            bg=self.DANGER,
            fg="white",
            font=self.FONT_BUTTON,
            relief="flat",
            cursor="hand2",
            command=self.remover_vaga
        ).pack(fill="x", pady=(10, 6), ipady=8)

        tk.Button(
            right_frame,
            text="🚀 Gerar Processos",
            bg=self.INFO,
            fg="white",
            font=self.FONT_BUTTON,
            relief="flat",
            cursor="hand2",
            command=self.gerar_processos
        ).pack(fill="x", ipady=8)

        self.root.protocol("WM_DELETE_WINDOW", self.fechar_aplicacao)
        self.atualizar_dados_api()
        self.root.mainloop()

    def criar_coluna_esquerda_rolavel(self, parent):
        largura_coluna = 440

        container = tk.Frame(parent, bg=self.BG_APP, width=largura_coluna)
        container.pack(side="left", fill="y", padx=(0, 12))
        container.pack_propagate(False)

        card = tk.Frame(container, bg=self.BG_CARD, bd=1, relief="solid")
        card.pack(fill="both", expand=True)
        card.pack_propagate(False)

        canvas = tk.Canvas(
            card,
            bg=self.BG_LEFT,
            highlightthickness=0,
            bd=0,
            width=largura_coluna - 20
        )
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=canvas.yview)

        scrollable_frame = tk.Frame(canvas, bg=self.BG_LEFT)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def ajustar_largura(event):
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", ajustar_largura)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        inner = tk.Frame(scrollable_frame, bg=self.BG_LEFT, padx=12, pady=12)
        inner.pack(fill="both", expand=True)

        return inner

    def preencher_campos_esquerda(self, left_frame):
        def criar_campo_label(parent, texto):
            tk.Label(
                parent,
                text=texto,
                anchor="w",
                bg=self.BG_LEFT,
                fg=self.FG_DARK,
                font=self.FONT_LABEL
            ).pack(fill="x", pady=(4, 1))

        criar_campo_label(left_frame, "👤 Usuário")
        self.usuario_select = ttk.Combobox(left_frame, state="readonly", font=self.FONT_TEXT)
        self.usuario_select.pack(fill="x", ipady=3)
        self.usuario_select.bind("<<ComboboxSelected>>", self.selecionar_usuario)

        criar_campo_label(left_frame, "🤝 Convênio")
        self.convenio = ttk.Combobox(left_frame, state="readonly", font=self.FONT_TEXT)
        self.convenio.pack(fill="x", ipady=3)

        criar_campo_label(left_frame, "🏢 CPA")
        self.cpa = ttk.Combobox(left_frame, state="readonly", font=self.FONT_TEXT)
        self.cpa.pack(fill="x", ipady=3)

        criar_campo_label(left_frame, "🔎 Direção da Busca na Tabela")
        self.direcao = ttk.Combobox(
            left_frame,
            values=["De cima para baixo", "De baixo para cima"],
            state="readonly",
            font=self.FONT_TEXT
        )
        self.direcao.current(0)
        self.direcao.pack(fill="x", ipady=3)

        criar_campo_label(left_frame, "📅 Data")
        data_minima = datetime.now().date() + timedelta(days=2)
        self.data = DateEntry(left_frame, date_pattern="yyyy-mm-dd", mindate=data_minima, font=self.FONT_TEXT)
        self.data.pack(fill="x", ipady=3)

        criar_campo_label(left_frame, "📍 Local (opcional)")
        frame_local = tk.Frame(left_frame, bg=self.BG_LEFT)
        frame_local.pack(fill="x", pady=(0, 2))

        self.condicao_local = ttk.Combobox(
            frame_local,
            values=["Não filtrar", "Contém a palavra", "Não contém a palavra", "Exatamente igual"],
            state="readonly",
            width=18,
            font=self.FONT_TEXT
        )
        self.condicao_local.current(0)
        self.condicao_local.pack(side="left", padx=(0, 6))

        self.local_entry = ttk.Entry(frame_local, font=self.FONT_TEXT)
        self.local_entry.pack(side="left", fill="x", expand=True)

        criar_campo_label(left_frame, "⏰ Hora (opcional)")
        frame_hora = tk.Frame(left_frame, bg=self.BG_LEFT)
        frame_hora.pack(fill="x", pady=(0, 2))

        self.condicao_hora = ttk.Combobox(
            frame_hora,
            values=["Não filtrar", "Depois de", "Antes de", "Exatamente"],
            state="readonly",
            width=16,
            font=self.FONT_TEXT
        )
        self.condicao_hora.current(0)
        self.condicao_hora.pack(side="left", padx=(0, 6))

        self.hora_entry = ttk.Combobox(frame_hora, state="readonly", font=self.FONT_TEXT, width=12)
        self.hora_entry.pack(side="left", fill="x", expand=True)
        self.hora_entry["values"] = [
            f"{h:02d}:{m:02d}:00"
            for h in range(24)
            for m in (0, 15)
        ]

        criar_campo_label(left_frame, "🌤 Turno")

        self.turno = ttk.Combobox(
            left_frame,
            values=["Não filtrar", "8 h", "12 h"],
            state="readonly",
            font=self.FONT_TEXT
        )

        self.turno.current(0)
        self.turno.pack(fill="x", ipady=3)
        
        criar_campo_label(left_frame, "🧭 Endereço")
        self.endereco_entry = ttk.Entry(left_frame, font=self.FONT_TEXT)
        self.endereco_entry.pack(fill="x", ipady=3)

        criar_campo_label(left_frame, "🧾 Tipo de Vaga")
        self.tipo_vaga = ttk.Combobox(
            left_frame,
            values=["Titular", "Titular/Reserva", "Reserva"],
            state="readonly",
            font=self.FONT_TEXT
        )
        self.tipo_vaga.current(0)
        self.tipo_vaga.pack(fill="x", ipady=3)

        tk.Button(
            left_frame,
            text="➕ Adicionar Vaga",
            bg=self.SUCCESS,
            fg="white",
            font=self.FONT_BUTTON,
            relief="flat",
            cursor="hand2",
            command=self.adicionar_vaga
        ).pack(fill="x", pady=(10, 5), ipady=8)

    def selecionar_usuario(self, event=None):
        nome = self.usuario_select.get()
        if nome in self.usuariosPALADINO_map:
            usuario = self.usuariosPALADINO_map[nome]
            self.usuario_selecionado = nome
            self.id_salvo = usuario.get("id_funcional")
            self.senha_salva = usuario.get("senha")
            print("Usuário selecionado:", self.usuario_selecionado)
            print("ID funcional:", self.id_salvo)

    def adicionar_vaga(self):
        if not self.usuario_selecionado:
            messagebox.showwarning("Aviso", "Selecione um usuário.")
            return

        vaga = {
            "convenio": self.convenio_map.get(self.convenio.get(), ""),
            "cpa": self.cpa_map.get(self.cpa.get(), ""),
            "data": self.data.get(),
            "direcao": self.direcao.get(),
            "local_condicao": self.condicao_local.get(),
            "local": self.local_entry.get().strip(),
            "hora_condicao": self.condicao_hora.get(),
            "hora": self.hora_entry.get(),
            "turno": self.turno.get(),
            "endereco": self.endereco_entry.get().strip(),
            "tipo": self.tipo_vaga.get()
        }

        self.inscricoes.append(vaga)

        self.lista_vagas.insert(
            tk.END,
            f"Convênio: {self.convenio.get() or '—'} | CPA: {self.cpa.get() or '—'} | Data: {self.data.get()} | Direção: {self.direcao.get()}"
        )
        self.lista_vagas.insert(
            tk.END,
            f"Local: {self.condicao_local.get()} | {self.local_entry.get().strip() or '—'}"
        )
        self.lista_vagas.insert(
            tk.END,
            f"Hora: {self.condicao_hora.get()} | {self.hora_entry.get() or '—'}"
        )
        self.lista_vagas.insert(
            tk.END,
            f"Turno: {self.turno.get() or '—'} | Endereço: {self.endereco_entry.get().strip() or '—'}"
        )
        self.lista_vagas.insert(
            tk.END,
            f"Tipo: {self.tipo_vaga.get() or '—'}"
        )
        self.lista_vagas.insert(tk.END, "-" * 90)

    def remover_vaga(self):
        try:
            index = self.lista_vagas.curselection()[0]

            inicio = index
            while inicio > 0 and not self.lista_vagas.get(inicio).startswith("-"):
                inicio -= 1
            if self.lista_vagas.get(inicio).startswith("-"):
                inicio += 1

            fim = inicio
            while fim < self.lista_vagas.size() and not self.lista_vagas.get(fim).startswith("-"):
                fim += 1
            if fim < self.lista_vagas.size():
                fim += 1

            for i in range(fim - 1, inicio - 1, -1):
                self.lista_vagas.delete(i)

            if self.inscricoes:
                contador = 0
                i = 0
                while i < inicio:
                    if self.lista_vagas.size() > i and self.lista_vagas.get(i).startswith("-"):
                        contador += 1
                    i += 1

                posicao = contador
                if 0 <= posicao < len(self.inscricoes):
                    self.inscricoes.pop(posicao)

        except IndexError:
            messagebox.showwarning("Aviso", "Selecione qualquer linha da vaga para remover.")

    def sessao_ativa(self):
        return (
            self.automacao is not None
            and self.thread_automacao is not None
            and self.thread_automacao.is_alive()
            and not self.automacao.finalizar_programa
        )

    def gerar_processos(self):
        if not self.usuario_selecionado:
            messagebox.showerror("Erro", "Selecione um usuário.")
            return

        if not self.id_salvo or not self.senha_salva:
            messagebox.showerror("Erro", "Usuário inválido ou credenciais ausentes no .env.")
            return

        if not self.inscricoes:
            messagebox.showinfo("Aviso", "Nenhuma vaga cadastrada.")
            return

        if self.sessao_ativa():
            try:
                self.automacao.abrir_painel_duplo_agendamento()
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao abrir o painel de agendamento: {e}")
            return

        objetos_inscricao = [Inscricao.from_dict(vaga) for vaga in self.inscricoes]

        capmonster_api_key = CAPMONSTER_API_KEY.strip()
        if not capmonster_api_key:
            messagebox.showerror("Erro", "A chave da API do CapMonster não foi definida no arquivo .env.")
            return

        self.automacao = AutomacaoProeis(
            id_funcional=self.id_salvo,
            senha=self.senha_salva,
            capmonster_api_key=capmonster_api_key,
            inscricoes=objetos_inscricao,
            headless=False,
            incognito=True,
            browser="chrome",
            ui_root=self.root
        )

        self.root.withdraw()

        def iniciar_automacao():
            try:
                self.automacao.executar()
            except Exception as e:
                print(f"Erro na automação: {e}")
                self.root.after(0, lambda: messagebox.showerror("Erro na automação", str(e)))
            finally:
                self.root.after(0, self.root.deiconify)

        self.thread_automacao = threading.Thread(target=iniciar_automacao, daemon=True)
        self.thread_automacao.start()

        self.root.after(1500, self._aguardar_automacao_e_abrir_painel)

    def _aguardar_automacao_e_abrir_painel(self):
        try:
            if self.automacao and self.automacao.sb is not None:
                self.automacao.abrir_painel_duplo_agendamento()
                return
        except Exception:
            pass

        if self.thread_automacao and self.thread_automacao.is_alive():
            self.root.after(500, self._aguardar_automacao_e_abrir_painel)

    def atualizar_dados_api(self):
        try:
            # Carrega dados locais de convênios
            dados_convenios = carregar_json_local("convenios.json")
            lista_convenios = extrair_lista_json(dados_convenios, "convenios")
            self.convenio_map = {
                str(i.get("nome", "")).strip(): str(i.get("value", "")).strip()
                for i in lista_convenios
                if i.get("nome")
            }
            self.convenio["values"] = list(self.convenio_map.keys())
            if self.convenio["values"]:
                self.convenio.current(0)

            # Carrega dados locais de CPA
            dados_cpa = carregar_json_local("cpa.json")
            lista_cpa = extrair_lista_json(dados_cpa, "cpa")
            self.cpa_map = {
                str(i.get("nome", "")).strip(): str(i.get("value", "")).strip()
                for i in lista_cpa
                if i.get("nome")
            }
            self.cpa["values"] = list(self.cpa_map.keys())
            if self.cpa["values"]:
                self.cpa.current(0)

            # Define usuário do combobox a partir do .env
            self.usuario_select["values"] = list(self.usuariosPALADINO_map.keys())
            if self.usuario_select["values"]:
                self.usuario_select.current(0)
                self.selecionar_usuario()

        except Exception as e:
            print(f"Erro ao carregar dados locais: {e}")

        # Como os dados são estáticos e locais, não há necessidade de pollar a cada minuto,
        # mas mantemos o callback para compatibilidade ou caso queiram atualizar dinamicamente.
        finally:
            if self.root and self.root.winfo_exists():
                self.root.after(60000, self.atualizar_dados_api)

    def fechar_aplicacao(self):
        if self.automacao:
            try:
                self.automacao.encerrar_externamente()
            except Exception:
                pass

        if self.root is not None:
            try:
                self.root.destroy()
            except Exception:
                pass