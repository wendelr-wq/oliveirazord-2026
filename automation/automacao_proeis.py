# ============================================================================
# ATUALIZAÇÃO APLICADA: PRIORIDADE PROFISSIONAL LOCAL + TIPO DE VAGA
# - Quando Tipo de Vaga = TITULAR:
#   1) tenta TODOS os locais como TITULAR na ordem digitada pelo usuário;
#   2) somente se não encontrar nenhuma TITULAR, tenta TODOS os locais como RESERVA;
#   3) exemplo: APERIBE TITULAR -> PADUA TITULAR -> ITAOCARA TITULAR -> CAMBUCI TITULAR
#               APERIBE RESERVA -> PADUA RESERVA -> ITAOCARA RESERVA -> CAMBUCI RESERVA
# - O robô não para mais apenas na primeira ou segunda opção de Local.
# - A rotina de clique agora percorre todas as vagas retornadas na ordem.
# ============================================================================
# ============================================================================
# ATUALIZAÇÃO APLICADA: USUÁRIO VISÍVEL DA BARRA SUPERIOR DA INTERFACE
# - O painel do relógio/agendamento mostra o usuário escolhido na interface.
# - A confirmação de saída pelo ESC mostra o usuário escolhido na interface.
# - Não depende mais do nome logado no PROEIS (#CrtMenu1_lblNomeLogado) para exibição visual.
# ============================================================================
# ATUALIZAÇÃO APLICADA: MODO ESTABILIDADE CONTRA TRAVAMENTO LONGO NA MARCAÇÃO
# - A confirmação da marcação agora aguarda até 25s quando o PROEIS demora.
# - O robô não desiste em 0,20s quando a tabela ainda está estabilizando.
# - O overlay 'Processando...' recebe mais tolerância antes de remoção forçada.
# - Após o ciclo 7s/9s, a espera do Processando subiu de 4s para 30s.
# ============================================================================

import os
import sys
import re
import time
import threading
from datetime import datetime, timedelta
from tkinter import Tk, Toplevel, Frame, Label, Button, Spinbox, StringVar, messagebox
import random
import keyboard
import pandas as pd
import parsel
import requests
import unicodedata
import ctypes
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from seleniumbase import SB

from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from models.inscricao import Inscricao

try:
    from .capmonster_solver import CapMonsterSolver
except ImportError:
    from automation.capmonster_solver import CapMonsterSolver

# from .controle_acesso import ControleAcesso

API_BASE = "https://restauranteinpelpadua.link/paladino/api"
USUARIOS_AUTORIZADOS_URL = f"{API_BASE}/usuarios_autorizados.json"

PROEIS_URL = "https://www.proeis.rj.gov.br/"
MENU_VOLUNTARIO_URL = "https://www.proeis.rj.gov.br/FrmMenuVoluntario.aspx"
ESCALA_VOLUNTARIO_URL = "https://www.proeis.rj.gov.br/FrmVoluntarioInscricoesConsultar.aspx"
TZ_BR = ZoneInfo("America/Sao_Paulo")


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


caminho_logo = resource_path("assets/-robot_86875.ico")


class AutomacaoProeis:
    BG_APP = "#e5e7eb"
    BG_CARD = "#ffffff"
    BG_TOP = "#0f172a"
    FG_DARK = "#111827"
    FG_MUTED = "#6b7280"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    DANGER = "#ef4444"
    INFO = "#3b82f6"

    def __init__(
        self,
        id_funcional: str,
        senha: str,
        capmonster_api_key: str,
        inscricoes: list[Inscricao] = None,
        browser: str = "chrome",
        headless: bool = False,
        incognito: bool = True,
        uc: bool = False,
        extension_dir: str = None,
        ui_root=None,
        usuario_selecionado_interface: str = None,
    ):
        self.id_funcional = id_funcional
        self.senha = senha
        self.inscricoes = inscricoes.copy() if inscricoes else []
        self.inscricoes_principais = self.inscricoes.copy()
        self.capmonster = CapMonsterSolver(capmonster_api_key)

        self.browser = browser
        self.headless = headless
        self.incognito = incognito
        self.uc = uc
        self.extension_dir = extension_dir
        self.ui_root = ui_root

        self.sb = None
        self.login_em_andamento = False
        self.login_sucesso = False
        self.inscricao_em_andamento = False
        self.finalizar_programa = False
        self.encerrando_programa = False
        self.saida_em_confirmacao = False
        self.monitor_thread_iniciado = False
        self.inscricao_realizada = False

        self.driver_lock = threading.Lock()
        self.interromper_inscricao = False

        self.controle_acesso = None

        # ==================== ATUALIZAÇÃO USUÁRIO SELECIONADO NA INTERFACE ====================
        # Exibe nas telas auxiliares o usuário escolhido na interface do MEGAZORD,
        # e não o usuário capturado da sessão do PROEIS.
        # Compatível com a chamada antiga: se a interface não passar o nome,
        # será exibido o ID funcional selecionado.
        self.usuario_selecionado_interface = str(usuario_selecionado_interface or self.id_funcional or "").strip()

        # Mantidos apenas para validação interna/autorização do PROEIS, sem uso visual no relógio/ESC.
        self.usuario_logado_sessao = ""
        self.nome_usuario_logado = self.usuario_logado_sessao

        self.ultimo_clique_inscricao = None

        # ==================== EXTREME SPEED ====================
        self.modo_extreme_speed = True

        # Tempo TOTAL desejado por marcação
        self.tempo_total_primeira_vaga = 7.0
        self.tempo_total_demais_vagas = 9.0

        # Controle do início da tentativa atual
        self.inicio_tentativa_inscricao = None

        self.thread_inscricao = None

        self.hotkey_login = None
        self.hotkey_inscricao = None
        self.hotkey_cronometro = None
        self.hotkey_sair = None

        self.proeis_server_sync_dt = None
        self.proeis_sync_monotonic = None
        self.offset_servidor_segundos = 0.0
        self.melhor_latencia_servidor = None

        # Agendamento ultra preciso
        # Sincronização híbrida: Header HTTP no início + lblSemana do PROEIS na reta final.
        # Quando faltar até 60 segundos para o disparo, o sistema:
        # 1) entra em Nova Inscrição;
        # 2) lê o horário oficial do #lblSemana;
        # 3) recalibra o cronômetro;
        # 4) volta para a tela de espera FrmVoluntarioInscricoesConsultar.aspx;
        # 5) no horário exato, clica novamente em Nova Inscrição para marcar.
        self.segundos_resincronizacao_final = 60
        self.sincronizacao_lbl_semana_ativa = True
        self.ultima_sincronizacao_lbl_semana = None
        self.ultimo_texto_lbl_semana = ""
        self.preparo_fino_ms = 2

        # ==================== AJUSTE FINO DE DISPARO ====================
        # Compensação positiva: o sistema considera o alvo atingido alguns
        # milissegundos antes, para compensar latência do Tkinter/Selenium/clique.
        # Se ainda ficar 1s atrasado no teste, aumente para 850 ou 1000.
        # Se disparar adiantado, reduza para 400 ou 500.
        self.compensacao_disparo_ms = 700
        self.janela_polling_final_segundos = 5
        self.intervalo_polling_final_ms = 5

        self.login_disparado = False
        self.disparo_disparado = False

        self.janela_agendamento = None
        self.agendamento_servidor_var = None
        self.agendamento_status_var = None

        self.login_horas_var = None
        self.login_minutos_var = None
        self.login_segundos_var = None
        self.login_alvo_var = None
        self.login_restante_var = None
        self.login_horario_alvo_texto = None
        self.login_resincronizacao_final_feita = False

        self.disparo_horas_var = None
        self.disparo_minutos_var = None
        self.disparo_segundos_var = None
        self.disparo_alvo_var = None
        self.disparo_restante_var = None
        self.disparo_horario_alvo_texto = None
        self.disparo_resincronizacao_final_feita = False

        self.agendamento_rodando = False
        self.agendamento_after_id = None
        self.etapa_atual = "login"

        self.frame_login = None
        self.frame_disparo = None

        self.retomar_automaticamente_apos_login = False

        # Anti-expulsão / estabilidade - EXTREME SPEED
        self.tempo_espera_antes_clique_vaga = 0.001
        self.tempo_espera_pos_clique_vaga = 0.020
        self.tempo_espera_processando_pre_remocao = 1.0  # Atualizado: só remove o overlay após dar tempo real ao servidor
        self.tempo_espera_transicao_url = 0.06
        self.timeout_curto_processando = 1
        self.timeout_validacao_pos_clique = 4  # Atualizado: mais tolerância quando o PROEIS trava/libera lentamente

        # Híbrido inteligente EXTREME SPEED
        self.timeout_confirmacao_marcacao_rapida = 1.2  # Atualizado: evita desistir em 0,20s quando a tabela ainda está estabilizando
        self.timeout_confirmacao_marcacao_lenta = 60.0  # Atualizado: aguarda travamentos longos antes de considerar falha
        self.passo_espera_marcacao_inteligente = 0.05  # Atualizado: polling estável sem sobrecarregar o navegador

        # Recuperação quando o PROEIS abre antes de carregar corretamente
        # os selects de Convênio/CPA/Data. Mantém a vaga pendente e tenta novamente.
        self.max_recuperacoes_select_indisponivel = 8
        self.pausa_recuperacao_select = 0.08

        # Relogin turbo: usado somente quando a sessão cair/deslogar durante o processo.
        # Mantém o login manual normal, mas reduz esperas na recuperação automática.
        self.relogin_turbo_ativo = True
        self.relogin_turbo_timeout_ready = 6
        self.relogin_turbo_timeout_click = 1.2
        self.relogin_turbo_timeout_pos_login = 7
        self.relogin_turbo_sleep_curto = 0.02

        # ==================== MONITOR PROFISSIONAL ANTI-CONGELAMENTO ====================
        # Objetivo: manter Windows/Chrome/cronômetro vivos durante longas esperas,
        # sem interferir no minuto final antes do login agendado.
        self.monitor_anti_congelamento_ativo = False
        self.monitor_anti_congelamento_thread = None
        self.monitor_anti_congelamento_parado_por_login = False

        self.ultimo_heartbeat_agendamento = time.time()
        self.ultimo_heartbeat_selenium = 0.0
        self.ultima_resync_periodica = 0.0

        self.intervalo_heartbeat_selenium = 45.0
        self.intervalo_resync_periodica = 15 * 60.0
        self.limite_congelamento_agendamento = 12.0
        self.parar_monitor_antes_login_segundos = 60.0

        self._anti_sleep_windows_ativo = False

    # ==================== UTIL ====================

    def centralizar_janela(self, janela, largura, altura):
        janela.update_idletasks()
        screen_w = janela.winfo_screenwidth()
        screen_h = janela.winfo_screenheight()
        x = (screen_w // 2) - (largura // 2)
        y = (screen_h // 2) - (altura // 2)
        janela.geometry(f"{largura}x{altura}+{x}+{y}")

    def remover_hotkeys(self):
        try:
            if self.hotkey_login is not None:
                keyboard.remove_hotkey(self.hotkey_login)
                self.hotkey_login = None
        except Exception:
            pass

        try:
            if self.hotkey_inscricao is not None:
                keyboard.remove_hotkey(self.hotkey_inscricao)
                self.hotkey_inscricao = None
        except Exception:
            pass

        try:
            if self.hotkey_cronometro is not None:
                keyboard.remove_hotkey(self.hotkey_cronometro)
                self.hotkey_cronometro = None
        except Exception:
            pass

        try:
            if self.hotkey_sair is not None:
                keyboard.remove_hotkey(self.hotkey_sair)
                self.hotkey_sair = None
        except Exception:
            pass

    def encerrar_externamente(self):
        self.finalizar_programa = True
        self.interromper_inscricao = True
        self.encerrando_programa = True
        self.parar_agendamento()
        self.remover_hotkeys()

        try:
            if self.sb and self.sb.driver:
                self.sb.driver.quit()
        except Exception:
            pass

    def obter_url_atual(self):
        try:
            if self.sb and self.sb.driver:
                return self.sb.driver.current_url or ""
        except Exception:
            pass
        return ""


    def aguardar_estabilidade_navegacao(self, timeout_ready=10, sleep_extra=0.25):
        try:
            if not self.sb or not self.sb.driver:
                return False
            self.sb.wait_for_ready_state_complete(timeout=timeout_ready)
            self.sb.sleep(sleep_extra)
            return True
        except Exception:
            return False

    def ir_para_menu_voluntario(self):
        try:
            url_atual = self.obter_url_atual()
            if "FrmMenuVoluntario.aspx" in url_atual:
                return True

            self.sb.open(MENU_VOLUNTARIO_URL)
            self.sb.wait_for_ready_state_complete(timeout=60)
            self.sb.sleep(0.3)
            return "FrmMenuVoluntario.aspx" in self.obter_url_atual()
        except Exception as e:
            print(f"⚠️ Erro ao ir para FrmMenuVoluntario.aspx: {e}")
            return False

    def preparar_pagina_escala(self, origem="fluxo"):
        try:
            if not self.sb or not self.sb.driver:
                return False

            if not self.login_sucesso:
                print(f"⚠️ Preparação da Escala ignorada ({origem}): login ainda não confirmado.")
                return False

            self.verificar_autorizacao_usuario()

            url_atual = self.obter_url_atual()
            if "FrmVoluntarioInscricoesConsultar.aspx" in url_atual:
                print(f"✅ Página de Escala já aberta ({origem}).")
                return True

            if not self.ir_para_menu_voluntario():
                print(f"⚠️ Não foi possível abrir a página FrmMenuVoluntario.aspx ({origem}).")
                return False

            self.verificar_autorizacao_usuario()

            if self.sb.is_element_present("a#btnEscala"):
                self.sb.click("a#btnEscala", timeout=5)
                self.sb.wait_for_ready_state_complete(timeout=60)
                self.sb.sleep(0.3)
                print(f"✅ Botão Escala clicado com sucesso ({origem}). Sistema em espera na página de inscrições.")
                return True

            url_atual = self.obter_url_atual()
            if "FrmVoluntarioInscricoesConsultar.aspx" in url_atual:
                print(f"✅ Página de Escala aberta com sucesso ({origem}).")
                return True

            print(f"⚠️ Botão btnEscala não encontrado em FrmMenuVoluntario.aspx ({origem}).")
            return False
        except Exception as e:
            print(f"⚠️ Erro ao preparar página de Escala ({origem}): {e}")
            return False

    # ==================== HORA DO SERVIDOR PROEIS ====================

    def capturar_hora_servidor_proeis(self, tentativas=7):
        melhor_amostra = None

        for i in range(tentativas):
            try:
                t0_mono = time.perf_counter()
                t0_local = datetime.now(TZ_BR)

                resposta = requests.get(PROEIS_URL, timeout=5)

                t1_mono = time.perf_counter()
                t1_local = datetime.now(TZ_BR)

                data_header = resposta.headers.get("Date")
                if not data_header:
                    continue

                dt_utc = parsedate_to_datetime(data_header)
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))

                dt_servidor = dt_utc.astimezone(TZ_BR)

                rtt = t1_mono - t0_mono
                meio_local = t0_local + (t1_local - t0_local) / 2
                offset = (dt_servidor - meio_local).total_seconds()

                amostra = {
                    "dt_servidor": dt_servidor,
                    "offset": offset,
                    "rtt": rtt,
                    "meio_local": meio_local,
                }

                if melhor_amostra is None or amostra["rtt"] < melhor_amostra["rtt"]:
                    melhor_amostra = amostra

            except Exception as e:
                print(f"Tentativa {i + 1} falhou ao capturar hora do servidor: {e}")

        if not melhor_amostra:
            return None

        self.offset_servidor_segundos = melhor_amostra["offset"]
        self.melhor_latencia_servidor = melhor_amostra["rtt"]

        agora_local = datetime.now(TZ_BR)
        agora_estimado_servidor = agora_local + timedelta(seconds=self.offset_servidor_segundos)

        print(
            f"Melhor sincronização: servidor={melhor_amostra['dt_servidor'].strftime('%H:%M:%S')} "
            f"| RTT={melhor_amostra['rtt']:.4f}s "
            f"| offset={melhor_amostra['offset']:+.4f}s "
            f"| agora_estimado={agora_estimado_servidor.strftime('%H:%M:%S.%f')[:-3]}"
        )

        return agora_estimado_servidor

    def sincronizar_relogio_proeis(self):
        dt_servidor_estimado = self.capturar_hora_servidor_proeis(tentativas=7)
        if not dt_servidor_estimado:
            return False

        self.proeis_server_sync_dt = dt_servidor_estimado
        self.proeis_sync_monotonic = time.monotonic()

        print(
            f"Sincronizado com precisão melhorada: "
            f"{dt_servidor_estimado.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
        )
        return True

    def agora_servidor_sincronizado(self):
        if not self.proeis_server_sync_dt or self.proeis_sync_monotonic is None:
            return None

        decorrido = time.monotonic() - self.proeis_sync_monotonic
        return self.proeis_server_sync_dt + timedelta(seconds=decorrido)

    def resincronizacao_rapida_final(self):
        try:
            dt_servidor_estimado = self.capturar_hora_servidor_proeis(tentativas=12)
            if not dt_servidor_estimado:
                return False

            self.proeis_server_sync_dt = dt_servidor_estimado
            self.proeis_sync_monotonic = time.monotonic()
            return True
        except Exception as e:
            print(f"Erro na resincronização rápida final: {e}")
            return False

    # ==================== SINCRONIZAÇÃO FINAL PELO lblSemana ====================

    def capturar_horario_lbl_semana(self):
        """
        Captura o horário oficial exibido na tela de marcação do PROEIS:
        <span id="lblSemana">14/05/2026 06:00:00 (Quinta)</span>

        Este horário é usado como referência final do disparo, pois representa
        o tempo apresentado dentro da própria página de associação de eventos.
        """
        try:
            if not self.sb or not self.sb.driver:
                return None

            texto = self.sb.execute_script("""
                const el = document.querySelector('#lblSemana');
                return el ? (el.innerText || el.textContent || '').trim() : '';
            """)

            texto = str(texto or '').strip()
            if not texto:
                return None

            match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})', texto)
            if not match:
                print(f"⚠️ lblSemana encontrado, mas sem data/hora reconhecida: {texto}")
                return None

            data_hora = f"{match.group(1)} {match.group(2)}"
            horario_site = datetime.strptime(data_hora, "%d/%m/%Y %H:%M:%S")
            horario_site = horario_site.replace(tzinfo=TZ_BR)

            self.ultimo_texto_lbl_semana = texto
            return horario_site

        except Exception as e:
            print(f"⚠️ Erro ao capturar horário do lblSemana: {e}")
            return None

    def garantir_tela_marcacao_para_sincronizacao_lbl_semana(self):
        """
        Garante que a automação esteja na tela FrmEventoAssociar.aspx para conseguir
        ler o #lblSemana antes do disparo. Esta etapa é usada apenas na reta final
        do disparo das vagas.
        """
        try:
            if not self.sb or not self.sb.driver:
                return False

            url_atual = (self.obter_url_atual() or '').lower()

            if 'frmeventoassociar.aspx' in url_atual and self.sb.is_element_present('#lblSemana'):
                return True

            if 'frmmenuvoluntario.aspx' in url_atual:
                print("🕒 Sincronização final: abrindo Escala para acessar o lblSemana...")
                try:
                    if self.sb.is_element_present('a#btnEscala'):
                        self.sb.click('a#btnEscala', timeout=2)
                    else:
                        self.sb.execute_script("""
                            const btn = document.querySelector('a#btnEscala');
                            if (btn) { btn.click(); return true; }
                            return false;
                        """)
                    self.sb.wait_for_ready_state_complete(timeout=20)
                    self.sb.sleep(0.10)
                except Exception as e:
                    print(f"⚠️ Falha ao abrir Escala para sincronização final: {e}")

                url_atual = (self.obter_url_atual() or '').lower()

            if 'frmvoluntarioinscricoesconsultar.aspx' in url_atual:
                print("🕒 Sincronização final: clicando em Nova Inscrição para ler o lblSemana...")
                try:
                    if self.sb.is_element_present('input#btnNovaInscricao'):
                        self.sb.click('input#btnNovaInscricao', timeout=2)
                    else:
                        self.sb.execute_script("""
                            const btn = document.querySelector('input#btnNovaInscricao');
                            if (btn) { btn.click(); return true; }
                            return false;
                        """)
                    self.sb.wait_for_ready_state_complete(timeout=25)
                    self.sb.sleep(0.10)
                except Exception as e:
                    print(f"⚠️ Falha ao abrir Nova Inscrição para sincronização final: {e}")

                url_atual = (self.obter_url_atual() or '').lower()

            if 'frmeventoassociar.aspx' in url_atual:
                try:
                    self.sb.wait_for_element('#lblSemana', timeout=8)
                except Exception:
                    pass
                return self.sb.is_element_present('#lblSemana')

            return False

        except Exception as e:
            print(f"⚠️ Erro ao preparar tela para sincronização lblSemana: {e}")
            return False

    def voltar_para_pagina_espera_nova_inscricao(self):
        """
        Após a sincronização de 60 segundos pelo #lblSemana, volta para a tela
        de espera da Nova Inscrição: FrmVoluntarioInscricoesConsultar.aspx.

        Importante: esta etapa NÃO resolve captcha, NÃO filtra e NÃO marca vaga.
        Ela apenas deixa o navegador posicionado na página correta para que,
        no horário exato, o disparo real clique novamente em Nova Inscrição.
        """
        try:
            if not self.sb or not self.sb.driver:
                return False

            url_atual = (self.obter_url_atual() or '').lower()
            if 'frmvoluntarioinscricoesconsultar.aspx' in url_atual:
                return True

            print("↩️ Sincronização 60s concluída. Voltando para a tela de espera da Nova Inscrição...")

            # 1ª opção: usar o botão Voltar da própria página, quando existir.
            if 'frmeventoassociar.aspx' in url_atual:
                try:
                    clicou = self.sb.execute_script("""
                        const candidatos = Array.from(document.querySelectorAll('input, button, a'));
                        const alvo = candidatos.find(el => {
                            const texto = ((el.value || el.innerText || el.textContent || '') + '').trim().toLowerCase();
                            const id = ((el.id || '') + '').trim().toLowerCase();
                            return texto === 'voltar' || texto.includes('voltar') || id.includes('voltar');
                        });
                        if (alvo) { alvo.click(); return true; }
                        return false;
                    """)
                    if clicou:
                        try:
                            self.sb.wait_for_ready_state_complete(timeout=20)
                        except Exception:
                            pass
                        self.sb.sleep(0.10)
                        if 'frmvoluntarioinscricoesconsultar.aspx' in (self.obter_url_atual() or '').lower():
                            print("✅ Página de espera da Nova Inscrição pronta após sincronização 60s.")
                            return True
                except Exception as e:
                    print(f"⚠️ Botão Voltar não funcionou após sincronização 60s: {e}")

            # 2ª opção: abrir diretamente a página de espera.
            try:
                self.sb.open(ESCALA_VOLUNTARIO_URL)
                self.sb.wait_for_ready_state_complete(timeout=25)
                self.sb.sleep(0.15)
            except Exception as e:
                print(f"⚠️ Falha ao abrir tela de espera diretamente: {e}")

            url_atual = (self.obter_url_atual() or '').lower()
            if 'frmvoluntarioinscricoesconsultar.aspx' in url_atual:
                print("✅ Página de espera da Nova Inscrição pronta após sincronização 60s.")
                return True

            # 3ª opção: se cair no menu, reabre Escala.
            if 'frmmenuvoluntario.aspx' in url_atual and self.sb.is_element_present('a#btnEscala'):
                try:
                    self.sb.click('a#btnEscala', timeout=3)
                    self.sb.wait_for_ready_state_complete(timeout=25)
                    self.sb.sleep(0.15)
                except Exception:
                    pass

            ok = 'frmvoluntarioinscricoesconsultar.aspx' in (self.obter_url_atual() or '').lower()
            if ok:
                print("✅ Página de espera da Nova Inscrição pronta após sincronização 60s.")
            else:
                print("⚠️ Sincronizou pelo lblSemana, mas não conseguiu confirmar retorno à página de espera.")
            return ok

        except Exception as e:
            print(f"⚠️ Erro ao voltar para tela de espera após sincronização 60s: {e}")
            return False

    def resincronizar_pelo_lbl_semana(self, preparar_tela=True, voltar_para_espera=True):
        """
        Recalibra o relógio interno da automação usando o horário do #lblSemana.
        Se não conseguir capturar, retorna False para permitir fallback pelo Header HTTP.

        Quando usada no disparo faltando 60 segundos, também volta para
        FrmVoluntarioInscricoesConsultar.aspx para deixar o sistema aguardando
        o disparo real sem gastar captcha antes da hora.
        """
        try:
            if preparar_tela and not self.garantir_tela_marcacao_para_sincronizacao_lbl_semana():
                print("⚠️ Não foi possível acessar a tela de marcação para ler o lblSemana.")
                return False

            horario_site = self.capturar_horario_lbl_semana()
            if not horario_site:
                print("⚠️ lblSemana não disponível para sincronização final.")
                return False

            agora_local = datetime.now(TZ_BR)
            self.offset_servidor_segundos = (horario_site - agora_local).total_seconds()
            self.proeis_server_sync_dt = horario_site
            self.proeis_sync_monotonic = time.monotonic()
            self.ultima_sincronizacao_lbl_semana = horario_site

            print(
                "✅ Sincronização FINAL pelo lblSemana do PROEIS: "
                f"{horario_site.strftime('%d/%m/%Y %H:%M:%S')} | "
                f"offset={self.offset_servidor_segundos:+.3f}s | "
                f"texto='{self.ultimo_texto_lbl_semana}'"
            )

            if voltar_para_espera:
                self.voltar_para_pagina_espera_nova_inscricao()

            return True

        except Exception as e:
            print(f"⚠️ Erro na sincronização pelo lblSemana: {e}")
            return False

    def resincronizacao_final_hibrida(self, etapa="disparo"):
        """
        Header HTTP = referência inicial.
        lblSemana = referência final prioritária para o disparo das vagas.
        Para login, mantém Header HTTP porque o usuário ainda pode não estar na tela de marcação.
        """
        try:
            etapa = str(etapa or '').lower()

            if etapa == 'disparo' and self.sincronizacao_lbl_semana_ativa:
                if self.resincronizar_pelo_lbl_semana(preparar_tela=True, voltar_para_espera=True):
                    return True

                print("⚠️ Fallback: usando Header HTTP do PROEIS porque o lblSemana não foi capturado.")

            return self.resincronizacao_rapida_final()

        except Exception as e:
            print(f"⚠️ Erro na resincronização final híbrida: {e}")
            return False

    def formatar_tempo_hms(self, total_segundos):
        if total_segundos < 0:
            total_segundos = 0
        horas = int(total_segundos // 3600)
        minutos = int((total_segundos % 3600) // 60)
        segundos = int(total_segundos % 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def formatar_tempo_preciso(self, total_segundos):
        if total_segundos < 0:
            total_segundos = 0

        horas = int(total_segundos // 3600)
        minutos = int((total_segundos % 3600) // 60)
        segundos = int(total_segundos % 60)
        milissegundos = int((total_segundos - int(total_segundos)) * 1000)

        if horas > 0 or minutos > 0:
            return f"{horas:02d}:{minutos:02d}:{segundos:02d}.{milissegundos:03d}"
        return f"{segundos:02d}.{milissegundos:03d}s"

    def chegou_no_horario_alvo_preciso(self, agora, horario_alvo_texto, compensacao_ms=0):
        """
        Compara o horário atual estimado do servidor com o horário alvo.

        compensacao_ms:
            Valor positivo antecipa o disparo em milissegundos.
            Exemplo: compensacao_ms=700 faz o sistema acionar quando faltar
            aproximadamente 0,700s para o horário alvo oficial.

        Retorna: (atingiu, restante_segundos, alvo_datetime)
        """
        if not agora or not horario_alvo_texto:
            return False, 0, None

        h, m, s = map(int, horario_alvo_texto.split(":"))
        alvo = agora.replace(hour=h, minute=m, second=s, microsecond=0)

        # Se o alvo já passou muito, entende que é para o próximo dia.
        # Se passou por poucos milissegundos/segundos, permite disparar imediatamente.
        if alvo < agora and (agora - alvo).total_seconds() > 10:
            alvo += timedelta(days=1)

        try:
            compensacao_ms = int(compensacao_ms or 0)
        except Exception:
            compensacao_ms = 0

        alvo_efetivo = alvo - timedelta(milliseconds=max(compensacao_ms, 0))
        restante = (alvo_efetivo - agora).total_seconds()
        atingiu = restante <= 0
        return atingiu, restante, alvo

    # ==================== CONTROLE DE USUÁRIO ====================

    def verificar_usuario_logado_site(self):
        try:
            nome_site = self.obter_nome_usuario_logado_site()

            if not nome_site:
                return

            autorizado = self.controle_acesso.usuario_esta_autorizado(nome_site)

            if not autorizado:
                self.negar_acesso_e_encerrar(
                    f"Usuário logado no site não está autorizado: {nome_site}"
                )

        except Exception as e:
            print("Erro ao verificar usuário do site:", e)

    def obter_nome_usuario_logado_site(self):
        try:
            if not self.sb or not self.sb.driver:
                return self.usuario_logado_sessao or ""

            elementos = self.sb.find_elements("#CrtMenu1_lblNomeLogado")
            if not elementos:
                return self.usuario_logado_sessao or ""

            nome = elementos[0].text.strip()
            if nome:
                self.usuario_logado_sessao = nome
                self.nome_usuario_logado = nome
                return nome

            return self.usuario_logado_sessao or ""

        except Exception:
            return self.usuario_logado_sessao or ""

    def obter_usuario_logado_para_tela(self):
        """Retorna o nome do usuário logado no PROEIS apenas para validações internas."""
        try:
            nome = self.obter_nome_usuario_logado_site()
            nome = str(nome or "").strip()
            return nome if nome else "Usuário não identificado"
        except Exception:
            return self.usuario_logado_sessao or "Usuário não identificado"

    def definir_usuario_selecionado_interface(self, usuario):
        """Permite que a interface atualize o usuário selecionado antes de abrir relógio/ESC."""
        try:
            usuario = str(usuario or "").strip()
            if usuario:
                self.usuario_selecionado_interface = usuario
        except Exception:
            pass

    # ==================== USUÁRIO VISÍVEL DA INTERFACE PRINCIPAL ====================
    # Esta rotina NÃO busca o ID funcional e NÃO busca o usuário logado no site PROEIS.
    # Ela procura o texto exibido na própria interface principal, por exemplo:
    # "Usuário logado: BISMARQUE DA ROCHA FERNANDES (bismarque)".

    def _extrair_nome_usuario_da_barra_interface(self, texto):
        """Extrai apenas o conteúdo após 'Usuário logado:' a partir de um texto de Label."""
        try:
            texto = str(texto or "").strip()
            if not texto:
                return ""

            texto_limpo = " ".join(texto.split())
            texto_lower = texto_limpo.lower()

            marcadores = [
                "usuário logado:",
                "usuario logado:",
                "usuário selecionado:",
                "usuario selecionado:",
            ]

            for marcador in marcadores:
                pos = texto_lower.find(marcador)
                if pos >= 0:
                    nome = texto_limpo[pos + len(marcador):].strip()
                    return nome or texto_limpo

            return ""
        except Exception:
            return ""

    def _buscar_usuario_visivel_na_interface(self):
        """
        Varre a árvore de widgets do Tkinter e captura o texto visível da barra superior.
        Funciona mesmo se o Label não estiver salvo como self.lbl_usuario_logado.
        """
        try:
            if self.ui_root is None or not self.ui_root.winfo_exists():
                return ""
        except Exception:
            return ""

        # 1) Tenta atributos comuns, caso a interface tenha salvo o Label em self.<nome>.
        atributos_possiveis = [
            "lbl_usuario_logado",
            "label_usuario_logado",
            "usuario_logado_label",
            "lblUsuarioLogado",
            "label_top_usuario",
            "usuario_label",
        ]

        for atributo in atributos_possiveis:
            try:
                widget = getattr(self.ui_root, atributo, None)
                if widget is not None:
                    nome = self._extrair_nome_usuario_da_barra_interface(widget.cget("text"))
                    if nome:
                        return nome
            except Exception:
                pass

        # 2) Varre todos os widgets visíveis e procura Labels com "Usuário logado:".
        def varrer_widgets(widget, profundidade=0):
            if profundidade > 12:
                return ""

            try:
                texto = ""

                try:
                    texto = widget.cget("text")
                except Exception:
                    texto = ""

                nome = self._extrair_nome_usuario_da_barra_interface(texto)
                if nome:
                    return nome

                # Alguns Labels usam textvariable.
                try:
                    textvariable = widget.cget("textvariable")
                    if textvariable:
                        valor_var = widget.getvar(textvariable)
                        nome = self._extrair_nome_usuario_da_barra_interface(valor_var)
                        if nome:
                            return nome
                except Exception:
                    pass

                for filho in widget.winfo_children():
                    nome = varrer_widgets(filho, profundidade + 1)
                    if nome:
                        return nome
            except Exception:
                return ""

            return ""

        return varrer_widgets(self.ui_root)

    def obter_usuario_selecionado_interface_para_tela(self):
        """
        Retorna o usuário visível na barra superior da interface.
        Prioridade:
        1. Texto exibido na interface: "Usuário logado: NOME (login)";
        2. valor passado por usuario_selecionado_interface, se existir;
        3. fallback final: ID funcional.
        """

        # Prioridade máxima: nome visível na barra superior da interface.
        try:
            usuario_barra = self._buscar_usuario_visivel_na_interface()
            if usuario_barra:
                self.usuario_selecionado_interface = usuario_barra
                return usuario_barra
        except Exception:
            pass

        # Fallback: valor informado pela tela principal ao criar a automação.
        try:
            usuario = str(getattr(self, "usuario_selecionado_interface", "") or "").strip()
            if usuario:
                return usuario
        except Exception:
            pass

        try:
            return str(self.id_funcional or "Usuário não selecionado").strip()
        except Exception:
            return "Usuário não selecionado"

    def negar_acesso_e_encerrar(self, motivo="Sem permissão"):
        if self.encerrando_programa:
            return

        self.encerrando_programa = True
        self.finalizar_programa = True
        self.interromper_inscricao = True

        try:
            root = Tk()
            root.withdraw()
            messagebox.showerror(
                "Acesso Negado",
                f"SEM PERMISSÃO PARA UTILIZAR O SISTEMA\nMotivo: {motivo}"
            )
            root.destroy()
        except Exception:
            pass

        time.sleep(1)

        self.parar_agendamento()
        self.remover_hotkeys()

        try:
            if self.sb and self.sb.driver:
                self.sb.driver.quit()
        except Exception:
            pass

        os._exit(0)

    def verificar_autorizacao_usuario(self):
        return True

    def monitorar_usuario_logado(self):
        pass

    def iniciar_monitoramento_usuario(self):
        pass

    # ==================== MONITOR PROFISSIONAL ANTI-CONGELAMENTO ====================

    def ativar_anti_sleep_windows(self):
        """Impede suspensão/ociosidade agressiva do Windows durante o agendamento."""
        try:
            if os.name != "nt":
                return False
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            self._anti_sleep_windows_ativo = True
            print("🛡️ Anti-sleep do Windows ativado para manter o agendamento acordado.")
            return True
        except Exception as e:
            print(f"⚠️ Não foi possível ativar anti-sleep do Windows: {e}")
            return False

    def liberar_anti_sleep_windows(self):
        """Libera o estado de execução do Windows quando o monitor é parado."""
        try:
            if os.name != "nt":
                return False
            # ES_CONTINUOUS: restaura comportamento padrão.
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            self._anti_sleep_windows_ativo = False
            print("✅ Anti-sleep do Windows liberado.")
            return True
        except Exception as e:
            print(f"⚠️ Não foi possível liberar anti-sleep do Windows: {e}")
            return False

    def calcular_restante_login_agendado(self):
        """Retorna quantos segundos faltam para o login agendado, ou None."""
        try:
            if self.etapa_atual != "login" or not self.login_horario_alvo_texto:
                return None
            agora = self.agora_servidor_sincronizado()
            if not agora:
                return None
            _, restante, _ = self.chegou_no_horario_alvo_preciso(agora, self.login_horario_alvo_texto)
            return restante
        except Exception:
            return None

    def deve_parar_monitor_anti_congelamento_para_login(self):
        """Para o monitor anti-congelamento quando faltar 1 minuto para o login."""
        restante = self.calcular_restante_login_agendado()
        return restante is not None and 0 < restante <= self.parar_monitor_antes_login_segundos

    def iniciar_monitor_anti_congelamento(self):
        """Inicia watchdog, heartbeat do Chrome, ressincronização periódica e anti-sleep."""
        if self.monitor_anti_congelamento_ativo:
            return

        self.monitor_anti_congelamento_ativo = True
        self.monitor_anti_congelamento_parado_por_login = False
        self.ultimo_heartbeat_agendamento = time.time()
        self.ultimo_heartbeat_selenium = 0.0
        self.ultima_resync_periodica = time.time()

        self.ativar_anti_sleep_windows()

        self.monitor_anti_congelamento_thread = threading.Thread(
            target=self.monitor_anti_congelamento_loop,
            daemon=True
        )
        self.monitor_anti_congelamento_thread.start()
        print("🛡️ Monitor profissional anti-congelamento iniciado.")

    def parar_monitor_anti_congelamento(self, motivo="parada solicitada"):
        if not self.monitor_anti_congelamento_ativo:
            return
        self.monitor_anti_congelamento_ativo = False
        print(f"🛡️ Monitor anti-congelamento parado: {motivo}")
        self.liberar_anti_sleep_windows()

    def navegador_responde(self):
        try:
            if not self.sb or not self.sb.driver:
                return False
            self.sb.execute_script("return document.readyState")
            return True
        except Exception:
            return False

    def heartbeat_selenium_seguro(self):
        """Mantém o Chrome acordado sem disputar o driver em momentos críticos."""
        if self.login_em_andamento or self.inscricao_em_andamento:
            return
        if not self.sb or not self.sb.driver:
            return

        adquiriu_lock = False
        try:
            adquiriu_lock = self.driver_lock.acquire(timeout=0.2)
            if not adquiriu_lock:
                return
            self.sb.execute_script("return document.readyState")
            self.ultimo_heartbeat_selenium = time.time()
        except Exception as e:
            print(f"⚠️ Heartbeat do navegador falhou: {e}")
        finally:
            if adquiriu_lock:
                try:
                    self.driver_lock.release()
                except Exception:
                    pass

    def ressincronizacao_periodica_segura(self):
        """Ressincroniza a cada 15 minutos, sem atuar no minuto final do login."""
        if self.login_em_andamento or self.inscricao_em_andamento:
            return
        if self.deve_parar_monitor_anti_congelamento_para_login():
            return

        try:
            print("🕒 Ressincronização periódica anti-drift do relógio PROEIS...")
            self.sincronizar_relogio_proeis()
            self.ultima_resync_periodica = time.time()
        except Exception as e:
            print(f"⚠️ Falha na ressincronização periódica: {e}")

    def monitor_anti_congelamento_loop(self):
        """Watchdog independente para longos períodos de espera/agendamento."""
        while self.monitor_anti_congelamento_ativo and not self.finalizar_programa:
            try:
                if self.deve_parar_monitor_anti_congelamento_para_login():
                    self.monitor_anti_congelamento_parado_por_login = True
                    self.parar_monitor_anti_congelamento(
                        "faltando 1 minuto para o login agendado"
                    )
                    break

                agora_ts = time.time()

                # Watchdog do loop visual do agendamento.
                if self.agendamento_rodando:
                    tempo_sem_heartbeat = agora_ts - self.ultimo_heartbeat_agendamento
                    if tempo_sem_heartbeat > self.limite_congelamento_agendamento:
                        print(
                            f"⚠️ Possível congelamento do agendamento detectado "
                            f"({tempo_sem_heartbeat:.1f}s sem heartbeat). Reforçando loop visual."
                        )
                        try:
                            if self.ui_root and self.ui_root.winfo_exists():
                                self.ui_root.after(1, self.atualizar_relogio_visual_agendamento)
                                self.ultimo_heartbeat_agendamento = time.time()
                        except Exception as e:
                            print(f"⚠️ Não foi possível reforçar loop visual: {e}")

                # Heartbeat leve do Chrome/Selenium.
                if (agora_ts - self.ultimo_heartbeat_selenium) >= self.intervalo_heartbeat_selenium:
                    self.heartbeat_selenium_seguro()

                # Ressincronização periódica para reduzir drift em longas esperas.
                if self.agendamento_rodando and (agora_ts - self.ultima_resync_periodica) >= self.intervalo_resync_periodica:
                    self.ressincronizacao_periodica_segura()

            except Exception as e:
                print(f"⚠️ Erro no monitor anti-congelamento: {e}")

            time.sleep(1)

    # ==================== CONTROLE DE SAÍDA ====================

    def confirmar_saida(self):
        if self.saida_em_confirmacao or self.encerrando_programa:
            return

        self.saida_em_confirmacao = True
        root = None

        try:
            root = Tk()
            root.withdraw()

            usuario_interface = self.obter_usuario_selecionado_interface_para_tela()

            resposta = messagebox.askyesno(
                "Encerrar Sistema",
                f"USUÁRIO SELECIONADO NA INTERFACE:\n{usuario_interface}\n\nDeseja realmente fechar o sistema?"
            )

            if not resposta:
                return

            self.finalizar_programa = True
            self.interromper_inscricao = True
            self.encerrando_programa = True

            self.parar_agendamento()
            self.remover_hotkeys()

            try:
                if self.sb and self.sb.driver:
                    self.sb.driver.quit()
            except Exception:
                pass

            os._exit(0)

        except Exception as e:
            print(f"Erro ao confirmar saída: {e}")
        finally:
            try:
                if root:
                    root.destroy()
            except Exception:
                pass
            self.saida_em_confirmacao = False

    def iniciar_saida_em_thread(self):
        if self.saida_em_confirmacao or self.encerrando_programa:
            return
        threading.Thread(target=self.confirmar_saida, daemon=True).start()

    # ==================== EXECUÇÃO ====================

    def executar(self):
        with SB(
            browser=self.browser,
            headless=self.headless,
            uc=self.uc,
            incognito=self.incognito,
            extension_dir=self.extension_dir,
        ) as sb:
            self.sb = sb

            self.sb.open(PROEIS_URL)
            self.iniciar_monitoramento_usuario()
            self.iniciar_monitor_anti_congelamento()

            self.hotkey_login = keyboard.add_hotkey("ctrl+1", self.solicitar_login)
            self.hotkey_inscricao = keyboard.add_hotkey("q", self.solicitar_inscricao)

            # Hotkey Z protegida: evita travar a automação caso o painel de agendamento
            # não exista em alguma versão/arquivo carregado.
            if hasattr(self, "abrir_painel_duplo_agendamento") and callable(getattr(self, "abrir_painel_duplo_agendamento", None)):
                self.hotkey_cronometro = keyboard.add_hotkey("z", self.abrir_painel_duplo_agendamento)
            else:
                print("⚠️ Painel de agendamento não disponível nesta versão. Hotkey Z não registrada.")
                self.hotkey_cronometro = None

            self.hotkey_sair = keyboard.add_hotkey("esc", self.iniciar_saida_em_thread)

            print("Hotkeys: Ctrl+1 = Login | Q = Inscrições | Z = Painel duplo | ESC = Sair")
            print("Monitoramento de usuário ativo.")
            print("Aguardando comandos. Pressione Ctrl+C para encerrar.")

            try:
                while not self.finalizar_programa:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nEncerrado pelo usuário.")
            finally:
                self.parar_monitor_anti_congelamento("encerramento do sistema")
                self.parar_agendamento()
                self.remover_hotkeys()
                self.sb = None

    # ==================== LOGIN ====================

    def limpar_campo_se_existir(self, seletor):
        try:
            if self.sb and self.sb.is_element_present(seletor):
                self.sb.clear(seletor)
                return True
        except Exception:
            pass
        return False

    def preencher_input_rapido(self, seletor, valor):
        try:
            script = """
                const el = document.querySelector(arguments[0]);
                if (!el) return false;
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            """
            if self.sb.execute_script(script, seletor, str(valor)):
                return True
        except Exception:
            pass

        try:
            self.sb.clear(seletor)
            self.sb.type(seletor, str(valor))
            return True
        except Exception:
            return False

    def preencher_captcha_rapido(self, resposta):
        try:
            script = """
                const el = document.querySelector('input#TextCaptcha');
                if (!el) return false;
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.value = arguments[0];
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            """
            return bool(self.sb.execute_script(script, str(resposta)))
        except Exception:
            return False

    def obter_valor_captcha(self):
        try:
            script = """
                const el = document.querySelector('input#TextCaptcha');
                if (!el) return '';
                return (el.value || '').trim();
            """
            valor = self.sb.execute_script(script)
            return str(valor or '').strip()
        except Exception:
            return ''

    def captcha_preenchido_corretamente(self, resposta_esperada):
        try:
            valor_atual = self.obter_valor_captcha()
            return valor_atual == str(resposta_esperada).strip()
        except Exception:
            return False

    def preencher_captcha_e_confirmar(self, resposta, tentativas=2):
        resposta = str(resposta).strip()
        for _ in range(tentativas):
            try:
                ok = self.sb.execute_script("""
                    const el = document.querySelector('#TextCaptcha');
                    if (!el) return false;
                    el.focus();
                    el.value = '';
                    el.value = arguments[0];
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    return (el.value || '').trim() === String(arguments[0]).trim();
                """, resposta)
                if ok:
                    return True
            except Exception:
                pass

            try:
                campo = self.sb.find_element('input#TextCaptcha', timeout=0.25)
                campo.clear()
                campo.send_keys(resposta)
                return True
            except Exception:
                pass
        return False

    def selecionar_dropdown_rapido(self, seletor, valor=None, texto=None):
        try:
            script = """
                const el = document.querySelector(arguments[0]);
                if (!el) return false;

                const valor = arguments[1];
                const texto = arguments[2];
                let achou = false;

                for (const opt of el.options) {
                    const optText = (opt.textContent || '').trim();
                    const optValue = (opt.value || '').trim();

                    if (valor !== null && valor !== undefined && String(valor).trim() !== '' && optValue === String(valor).trim()) {
                        el.value = opt.value;
                        achou = true;
                        break;
                    }

                    if (texto !== null && texto !== undefined && String(texto).trim() !== '' && optText === String(texto).trim()) {
                        el.value = opt.value;
                        achou = true;
                        break;
                    }
                }

                if (!achou) return false;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            """
            return bool(self.sb.execute_script(script, seletor, valor, texto))
        except Exception:
            return False


    def selecionar_dropdown_extreme_validado(self, seletor, valor=None, texto=None, nome_campo="campo", tentativas=4):
        """Seleciona rápido via JavaScript e confirma se o valor realmente entrou."""
        for tentativa in range(1, tentativas + 1):
            try:
                if not self.opcao_select_disponivel(seletor, valor=valor, texto=texto):
                    self.sb.sleep(0.04)
                    continue

                ok = self.selecionar_dropdown_rapido(seletor, valor=valor, texto=texto)
                if not ok:
                    if valor:
                        self.sb.select_option_by_value(seletor, str(valor), timeout=0)
                    elif texto:
                        self.sb.select_option_by_text(seletor, str(texto), timeout=0)

                confirmado = self.sb.execute_script("""
                    const el = document.querySelector(arguments[0]);
                    if (!el) return false;
                    const valor = arguments[1];
                    const texto = arguments[2];
                    const opt = el.options[el.selectedIndex];
                    if (!opt) return false;
                    const optValue = (opt.value || '').trim();
                    const optText = (opt.textContent || '').trim();
                    if (valor !== null && valor !== undefined && String(valor).trim() !== '') {
                        return optValue === String(valor).trim();
                    }
                    if (texto !== null && texto !== undefined && String(texto).trim() !== '') {
                        return optText === String(texto).trim();
                    }
                    return false;
                """, seletor, valor, texto)

                if confirmado:
                    return True
                self.sb.sleep(0.035)
            except Exception as e:
                print(f"   ⚠️ Falha ao selecionar {nome_campo} na tentativa {tentativa}: {e}")
                self.sb.sleep(0.04)
        return False


    def opcao_select_disponivel(self, seletor, valor=None, texto=None):
        """Verifica se uma opção existe no select antes de tentar selecionar.
        Evita remover a inscrição quando o site carregou cedo demais e o PROEIS
        ainda não populou Convênio/CPA/Data corretamente.
        """
        try:
            script = """
                const el = document.querySelector(arguments[0]);
                if (!el || !el.options) return false;
                const valor = arguments[1];
                const texto = arguments[2];
                for (const opt of el.options) {
                    const optText = (opt.textContent || '').trim();
                    const optValue = (opt.value || '').trim();
                    if (valor !== null && valor !== undefined && String(valor).trim() !== '' && optValue === String(valor).trim()) return true;
                    if (texto !== null && texto !== undefined && String(texto).trim() !== '' && optText === String(texto).trim()) return true;
                }
                return false;
            """
            return bool(self.sb.execute_script(script, seletor, valor, texto))
        except Exception:
            return False

    def recuperar_fluxo_select_indisponivel(self, motivo="select indisponível"):
        """Volta ao Menu Voluntário, clica em Escala/Nova Inscrição e repete a mesma vaga.
        Usado quando Data, Convênio ou CPA não aparecem porque o disparo entrou
        antes de o servidor carregar os selects.
        """
        try:
            if self.finalizar_programa or self.interromper_inscricao:
                return False

            if self.sessao_perdida_ou_fluxo_interrompido():
                return self.tentar_recuperar_sessao_automaticamente(motivo)

            print(f"   🔄 {motivo}. Reabrindo Menu Voluntário > Escala para recarregar os selects...")

            if not self.ir_para_menu_voluntario():
                print("   ⚠️ Não foi possível voltar ao Menu Voluntário para recarregar os selects.")
                return False

            self.verificar_autorizacao_usuario()

            if self.sb.is_element_present("a#btnEscala"):
                try:
                    self.sb.click("a#btnEscala", timeout=3)
                except Exception:
                    self.sb.execute_script("const el = document.querySelector('a#btnEscala'); if (el) { el.click(); return true; } return false;")
                try:
                    self.sb.wait_for_ready_state_complete(timeout=30)
                except Exception:
                    pass
                self.sb.sleep(self.pausa_recuperacao_select)

            if self.sb.is_element_present("input#btnNovaInscricao"):
                try:
                    self.sb.click("input#btnNovaInscricao", timeout=3)
                except Exception:
                    self.sb.execute_script("const el = document.querySelector('input#btnNovaInscricao'); if (el) { el.click(); return true; } return false;")
                try:
                    self.sb.wait_for_ready_state_complete(timeout=30)
                except Exception:
                    pass
                self.sb.sleep(self.pausa_recuperacao_select)

            url_atual = (self.obter_url_atual() or "").lower()
            if "frmeventoassociar.aspx" in url_atual or self.sb.is_element_present("#ddlDataEvento"):
                print("   ✅ Fluxo recarregado. Tentando novamente a mesma inscrição.")
                return True

            print("   ⚠️ Fluxo recarregado, mas a página de nova inscrição ainda não ficou pronta.")
            return False

        except Exception as e:
            print(f"   ⚠️ Erro ao recuperar fluxo por select indisponível: {e}")
            return False

    def resolver_captcha_inteligente(self, base64_captcha, contexto="captcha"):
        """Captcha em modo EXTREME SPEED com fallback seguro."""
        contexto_lower = str(contexto or "").lower()
        if "data" in contexto_lower or "extreme" in contexto_lower:
            estrategias = [
                {"threshold": 0.74, "max_attempts": 4, "poll_interval": 0.008, "label": "extreme"},
                {"threshold": 0.80, "max_attempts": 6, "poll_interval": 0.012, "label": "turbo"},
                {"threshold": 0.86, "max_attempts": 8, "poll_interval": 0.018, "label": "seguro"},
            ]
        else:
            estrategias = [
                {"threshold": 0.79, "max_attempts": 6, "poll_interval": 0.015, "label": "turbo"},
                {"threshold": 0.84, "max_attempts": 8, "poll_interval": 0.020, "label": "preciso"},
            ]

        ultimo_erro = None
        for idx, cfg in enumerate(estrategias, start=1):
            try:
                resposta = self.capmonster.resolver_captcha(
                    base64_captcha,
                    threshold=cfg["threshold"],
                    max_attempts=cfg["max_attempts"],
                    poll_interval=cfg["poll_interval"]
                )
                resposta = str(resposta).strip()
                if len(resposta) >= 4:
                    print(f"Captcha {contexto} resolvido [{cfg['label']}] estratégia {idx}: {resposta}")
                    return resposta
            except Exception as e:
                ultimo_erro = e

        if ultimo_erro:
            raise ultimo_erro
        raise ValueError(f"Não foi possível resolver o {contexto}.")

    def garantir_pagina_login_rapida(self, modo_relogin=False):
        try:
            if self.esta_na_pagina_login():
                return True

            self.sb.open(PROEIS_URL)

            if modo_relogin and self.relogin_turbo_ativo:
                try:
                    self.sb.wait_for_element("#ddlTipoAcesso", timeout=self.relogin_turbo_timeout_ready)
                    return True
                except Exception:
                    try:
                        self.sb.wait_for_ready_state_complete(timeout=self.relogin_turbo_timeout_ready)
                    except Exception:
                        pass
                    return self.esta_na_pagina_login()

            self.sb.wait_for_ready_state_complete(timeout=12)
            self.sb.sleep(0.15)
            return self.esta_na_pagina_login()
        except Exception:
            return False

    def clicar_login_turbo(self, modo_relogin=False):
        try:
            timeout_click = self.relogin_turbo_timeout_click if modo_relogin else 3
            timeout_ready = self.relogin_turbo_timeout_pos_login if modo_relogin else 15

            try:
                self.sb.click("input#btnEntrar", timeout=timeout_click)
            except Exception:
                self.sb.execute_script("""
                    const btn = document.querySelector('input#btnEntrar');
                    if (!btn) return false;
                    btn.click();
                    return true;
                """)

            try:
                self.sb.wait_for_ready_state_complete(timeout=timeout_ready)
            except Exception:
                pass

            return True
        except Exception as e:
            print(f"Erro ao clicar no botão de login: {e}")
            return False

    def _executar_login_sem_lock(self, modo_relogin=False):
        self.login_em_andamento = True
        try:
            if not self.garantir_pagina_login_rapida(modo_relogin=modo_relogin):
                raise ValueError("Página de login não disponível para o relogin automático")

            try:
                if not self.selecionar_dropdown_rapido("#ddlTipoAcesso", valor="ID"):
                    self.sb.select_option_by_value("#ddlTipoAcesso", "ID")
            except Exception:
                self.sb.select_option_by_value("#ddlTipoAcesso", "ID")

            captcha_ok = False
            tentativas_login = 0
            max_tentativas_login = 8 if modo_relogin else 12

            while not captcha_ok and not self.finalizar_programa and tentativas_login < max_tentativas_login:
                tentativas_login += 1

                if modo_relogin:
                    print(f"⚡ Relogin turbo em andamento (tentativa {tentativas_login}/{max_tentativas_login})...")

                self.preencher_input_rapido("#txtLogin", self.id_funcional)
                self.preencher_input_rapido("#txtSenha", self.senha)

                html = self.sb.get_page_source()
                selector = parsel.Selector(html)

                img_captcha = selector.css("div#captcha div")
                if not img_captcha:
                    if self.esta_na_pagina_login():
                        self.sb.sleep(self.relogin_turbo_sleep_curto if modo_relogin else 0.15)
                        continue
                    raise ValueError("Elemento de captcha não encontrado na página de login")

                try:
                    base64_captcha = self.extrair_base64_captcha(img_captcha)
                except Exception as e:
                    print(f"Erro ao extrair base64: {e}.")
                    self.sb.sleep(self.relogin_turbo_sleep_curto if modo_relogin else 0.1)
                    continue

                try:
                    resposta = self.resolver_captcha_inteligente(base64_captcha, contexto="relogin turbo" if modo_relogin else "login")
                except Exception as e:
                    print(f"Erro ao resolver captcha: {e}.")
                    continue

                try:
                    if not self.preencher_captcha_e_confirmar(resposta, tentativas=1 if modo_relogin else 2):
                        if not self.preencher_captcha_rapido(resposta):
                            campo_captcha = self.sb.find_element("input#TextCaptcha", timeout=0.12 if modo_relogin else 0.20)
                            campo_captcha.clear()
                            campo_captcha.send_keys(resposta)
                except Exception:
                    if not self.esta_na_pagina_login():
                        raise ValueError("Campo TextCaptcha não disponível porque a página de login foi interrompida")
                    self.limpar_campo_se_existir("input#TextCaptcha")
                    self.sb.sleep(self.relogin_turbo_sleep_curto if modo_relogin else 0.05)
                    continue

                if not self.clicar_login_turbo(modo_relogin=modo_relogin):
                    continue

                if self.captcha_valido_login():
                    captcha_ok = True
                    self.login_sucesso = True
                    print("Login realizado com sucesso!" if not modo_relogin else "⚡ Relogin turbo realizado com sucesso!")
                    self.verificar_autorizacao_usuario()

                    if self.retomar_automaticamente_apos_login:
                        if modo_relogin:
                            self.preparar_fluxo_pos_relogin_turbo("relogin turbo")
                        else:
                            self.preparar_fluxo_pos_relogin_automatico("relogin automático")
                    else:
                        self.preparar_pagina_escala("pós-login")
                else:
                    print("Captcha inválido.")
                    self.limpar_campo_se_existir("input#TextCaptcha")
                    if modo_relogin:
                        try:
                            self.gerar_captcha()
                        except Exception:
                            pass
                    continue

            return self.login_sucesso

        except Exception as e:
            print(f"Erro durante login: {e}")
            self.login_sucesso = False
            return False
        finally:
            self.login_em_andamento = False

    def fazer_login(self):
        with self.driver_lock:
            return self._executar_login_sem_lock()

    def captcha_valido_login(self):
        return not self.sb.is_element_visible(
            "//span[text()='Erro ao confirmar Imagem']",
            by="xpath",
        )

    def mensagem_processando_visivel(self):
        try:
            if not self.sb or not self.sb.driver:
                return False

            elementos = self.sb.find_elements("#aguarde")
            if not elementos:
                return False

            for el in elementos:
                try:
                    if el.is_displayed():
                        texto = (el.text or "").strip().lower()
                        if "processando" in texto and "aguarde" in texto:
                            return True
                except Exception:
                    continue

            return False
        except Exception:
            return False

    def aguardar_mensagem_processando_sumir(self, timeout=15):
        try:
            if not self.sb or not self.sb.driver:
                return False

            WebDriverWait(self.sb.driver, timeout=timeout, poll_frequency=0.05).until(
                lambda d: not self.mensagem_processando_visivel()
            )
            return True
        except TimeoutException:
            return False
        except Exception:
            return False

    def remover_mensagem_processando(self):
        try:
            if not self.sb or not self.sb.driver:
                return False

            script = """
                const el = document.querySelector('#aguarde');
                if (!el) return false;
                el.style.display = 'none';
                el.style.visibility = 'hidden';
                el.style.opacity = '0';
                el.setAttribute('hidden', 'hidden');
                return true;
            """
            resultado = self.sb.execute_script(script)
            self.sb.sleep(0.05)
            return bool(resultado)
        except Exception:
            return False

    def seletor_ainda_disponivel(self, seletor):
        try:
            if not self.sb or not self.sb.driver:
                return False
            return self.sb.is_element_present(seletor)
        except Exception:
            return False

    def esperar_confirmacao_marcacao_inteligente(self, seletor, timeout_rapido=None, timeout_lento=None):
        timeout_rapido = self.timeout_confirmacao_marcacao_rapida if timeout_rapido is None else timeout_rapido
        timeout_lento = self.timeout_confirmacao_marcacao_lenta if timeout_lento is None else timeout_lento

        inicio = time.time()
        mensagem_ja_detectada = False
        mensagem_removida = False

        while (time.time() - inicio) <= timeout_lento:
            if self.interromper_inscricao or self.finalizar_programa:
                raise Exception("Inscrição interrompida por solicitação.")

            if self.sessao_perdida_ou_fluxo_interrompido():
                return "relogin"

            try:
                self.sb.wait_for_ready_state_complete(timeout=0.6)
            except Exception:
                pass

            if self.vaga_foi_marcada(seletor):
                return True

            if self.mensagem_processando_visivel():
                mensagem_ja_detectada = True
                tempo_decorrido = time.time() - inicio

                if tempo_decorrido >= self.tempo_espera_processando_pre_remocao and not mensagem_removida:
                    removida = self.remover_mensagem_processando()
                    if removida:
                        print("   ✅ Mensagem 'Processando...' removida pela automação na espera inteligente.")
                        mensagem_removida = True

                self.sb.sleep(self.passo_espera_marcacao_inteligente)
                continue

            # Se não houve processamento visível e o site respondeu rápido,
            # não fica esperando além do necessário
            if not mensagem_ja_detectada and (time.time() - inicio) >= timeout_rapido:
                break

            self.sb.sleep(self.passo_espera_marcacao_inteligente)

        if self.sessao_perdida_ou_fluxo_interrompido():
            return "relogin"

        if self.vaga_foi_marcada(seletor):
            return True

        return False

    def vaga_foi_marcada(self, seletor):
        try:
            if not self.sb or not self.sb.driver:
                return False

            url_atual = self.obter_url_atual().lower()
            if "frmeventoassociar" not in url_atual:
                return True

            if not self.seletor_ainda_disponivel(seletor):
                return True

            return False
        except Exception:
            return False

    def obter_intervalo_tentativa_marcacao(self, tentativa):
        return 0.5 if tentativa <= 10 else 1.0
    
    def iniciar_cronometro_inscricao(self):
        self.inicio_tentativa_inscricao = time.perf_counter()


    def aguardar_intervalo_inscricao(self):
        """
        Controla o tempo TOTAL da marcação.

        Primeira vaga: fecha em 7 segundos totais.
        Segunda em diante: fecha em 9 segundos totais.

        Se captcha + filtros já demoraram parte do tempo,
        aguarda somente o restante.
        """

        if self.inicio_tentativa_inscricao is None:
            return

        # Primeira vaga
        if self.ultimo_clique_inscricao is None:
            tempo_alvo = self.tempo_total_primeira_vaga
            descricao = "primeira vaga"
        else:
            tempo_alvo = self.tempo_total_demais_vagas
            descricao = "segunda vaga em diante"

        tempo_decorrido = time.perf_counter() - self.inicio_tentativa_inscricao
        tempo_restante = tempo_alvo - tempo_decorrido

        if tempo_restante > 0:
            print(
                f"   ⏳ Controle de tempo total: {descricao}. "
                f"Decorrido: {tempo_decorrido:.2f}s | "
                f"Aguardando restante: {tempo_restante:.2f}s | "
                f"Alvo total: {tempo_alvo:.2f}s"
            )
            time.sleep(tempo_restante)
        else:
            print(
                f"   ⚡ Controle de tempo total: {descricao}. "
                f"Tempo já atingido: {tempo_decorrido:.2f}s | "
                f"Alvo: {tempo_alvo:.2f}s"
            )

        # Aguarda caso o PROEIS ainda esteja processando
        if self.mensagem_processando_visivel():
            print("   ⏳ Mensagem Processando ainda visível. Aguardando liberação.")
            self.aguardar_mensagem_processando_sumir(timeout=30)  # Atualizado: tolera travamento longo do PROEIS

    def recarregar_lista_principal_se_necessario(self):
        if self.inscricoes:
            return False

        if not self.inscricoes_principais:
            print("📋 Não existe lista principal cadastrada para reiniciar o ciclo.")
            return False

        self.inscricoes = self.inscricoes_principais.copy()
        print(f"🔄 Reiniciando ciclo de inscrições com {len(self.inscricoes)} item(ns) da lista principal.")
        return True

    def remover_inscricao_da_lista(self, inscricao):
        try:
            if inscricao in self.inscricoes:
                self.inscricoes.remove(inscricao)
                return True
        except Exception as e:
            print(f"⚠️ Erro ao remover inscrição da lista pendente: {e}")
        return False

    def esta_na_pagina_login(self):
        try:
            url = (self.obter_url_atual() or "").lower()
            if "login" in url or "default.aspx" in url:
                return True

            html = self.sb.get_page_source()
            selector = parsel.Selector(html)
            if selector.css("select#ddlTipoAcesso").get():
                return True
            if selector.css("input#btnEntrar").get():
                return True
            return False
        except Exception:
            return False

    def contexto_inscricao_ativo(self):
        try:
            if self.esta_na_pagina_login():
                return False

            url = (self.obter_url_atual() or "").lower()
            if "proeis.rj.gov.br" not in url:
                return False

            return True
        except Exception:
            return False

    def sessao_perdida_ou_fluxo_interrompido(self):
        try:
            if self.esta_na_pagina_login():
                return True

            url = (self.obter_url_atual() or "").lower()
            if not url:
                return False

            if "proeis.rj.gov.br" not in url:
                return True

            return False
        except Exception:
            return True

    def preparar_fluxo_pos_relogin_automatico(self, origem="relogin-automático"):
        try:
            if not self.sb or not self.sb.driver:
                return False

            self.verificar_autorizacao_usuario()
            url_atual = (self.obter_url_atual() or "").lower()

            if "frmeventoassociar.aspx" in url_atual:
                print(f"✅ Fluxo de marcação já está ativo ({origem}).")
                return True

            if "frmvoluntarioinscricoesconsultar.aspx" not in url_atual:
                if not self.ir_para_menu_voluntario():
                    print(f"⚠️ Não foi possível voltar ao menu do voluntário ({origem}).")
                    return False

                if self.sb.is_element_present("a#btnEscala"):
                    self.sb.click("a#btnEscala", timeout=5)
                    self.sb.wait_for_ready_state_complete(timeout=60)
                    self.sb.sleep(0.3)
                    print(f"✅ Botão Escala clicado com sucesso ({origem}).")

            if self.sb.is_element_present("input#btnNovaInscricao"):
                self.sb.click("input#btnNovaInscricao", timeout=5)
                self.sb.wait_for_ready_state_complete(timeout=60)
                self.sb.sleep(0.3)
                print(f"✅ Página de nova inscrição preparada com sucesso ({origem}).")

            return "frmeventoassociar.aspx" in (self.obter_url_atual() or "").lower()
        except Exception as e:
            print(f"⚠️ Erro ao preparar fluxo após relogin automático ({origem}): {e}")
            return False

    def preparar_fluxo_pos_relogin_turbo(self, origem="relogin-turbo"):
        """
        Retoma o caminho de inscrição com o mínimo de espera possível após queda de sessão.
        Usa cliques por JavaScript como primeira opção e timeouts curtos.
        """
        try:
            if not self.sb or not self.sb.driver:
                return False

            self.verificar_autorizacao_usuario()
            url_atual = (self.obter_url_atual() or "").lower()

            if "frmeventoassociar.aspx" in url_atual:
                print(f"⚡ Fluxo de marcação já ativo ({origem}).")
                return True

            if "frmvoluntarioinscricoesconsultar.aspx" not in url_atual:
                if "frmmenuvoluntario.aspx" not in url_atual:
                    self.sb.open(MENU_VOLUNTARIO_URL)
                    try:
                        self.sb.wait_for_element("a#btnEscala", timeout=4)
                    except Exception:
                        try:
                            self.sb.wait_for_ready_state_complete(timeout=4)
                        except Exception:
                            pass

                if self.sb.is_element_present("a#btnEscala"):
                    clicou = self.sb.execute_script("""
                        const btn = document.querySelector('a#btnEscala');
                        if (!btn) return false;
                        btn.click();
                        return true;
                    """)
                    if not clicou:
                        self.sb.click("a#btnEscala", timeout=1)

                    try:
                        self.sb.wait_for_element("input#btnNovaInscricao", timeout=5)
                    except Exception:
                        try:
                            self.sb.wait_for_ready_state_complete(timeout=5)
                        except Exception:
                            pass
                    print(f"⚡ Escala aberta em modo turbo ({origem}).")

            if self.sb.is_element_present("input#btnNovaInscricao"):
                clicou = self.sb.execute_script("""
                    const btn = document.querySelector('input#btnNovaInscricao');
                    if (!btn) return false;
                    btn.click();
                    return true;
                """)
                if not clicou:
                    self.sb.click("input#btnNovaInscricao", timeout=1)

                try:
                    self.sb.wait_for_element("#ddlDataEvento", timeout=5)
                except Exception:
                    try:
                        self.sb.wait_for_ready_state_complete(timeout=5)
                    except Exception:
                        pass
                print(f"⚡ Nova inscrição preparada em modo turbo ({origem}).")

            return "frmeventoassociar.aspx" in (self.obter_url_atual() or "").lower()
        except Exception as e:
            print(f"⚠️ Erro ao preparar fluxo turbo após relogin ({origem}): {e}")
            return False

    def tentar_recuperar_sessao_automaticamente(self, motivo="sessão perdida"):
        if self.finalizar_programa or self.interromper_inscricao or not self.inscricoes:
            return False

        print(f"🔐 Sessão interrompida detectada ({motivo}). Iniciando login automático para continuar de onde parou...")
        self.login_sucesso = False
        estado_anterior = self.retomar_automaticamente_apos_login
        self.retomar_automaticamente_apos_login = True

        try:
            sucesso = self._executar_login_sem_lock(modo_relogin=True)
            if sucesso:
                print("✅ Relogin automático concluído. Retomando a marcação da vaga pendente...")
            else:
                print("❌ Não foi possível concluir o relogin automático.")
            return bool(sucesso)
        finally:
            self.retomar_automaticamente_apos_login = estado_anterior

    def clicar_vaga_com_tratamento_processando(self, seletor, max_tentativas=20):
        ultimo_erro = None

        for tentativa in range(1, max_tentativas + 1):
            if self.interromper_inscricao or self.finalizar_programa:
                raise Exception("Inscrição interrompida por solicitação.")

            if self.sessao_perdida_ou_fluxo_interrompido():
                return "relogin"

            intervalo = self.obter_intervalo_tentativa_marcacao(tentativa)

            try:
                self.aguardar_estabilidade_navegacao(timeout_ready=2, sleep_extra=0.01)

                if self.mensagem_processando_visivel():
                    print("   ⏳ Mensagem de processamento detectada antes do clique. Aguardando um pouco antes de remover...")
                    self.sb.sleep(self.tempo_espera_processando_pre_remocao)
                    if self.mensagem_processando_visivel():
                        self.remover_mensagem_processando()
                        self.sb.sleep(0.08)

                print(f"   ⏳ Aguardando {self.tempo_espera_antes_clique_vaga:.2f}s antes do clique para estabilizar a página...")
                self.sb.sleep(self.tempo_espera_antes_clique_vaga)

                print(f"   🎯 Tentando marcar a vaga (tentativa {tentativa}/{max_tentativas})...")

                try:
                    self.sb.click(seletor)
                except Exception:
                    self.sb.execute_script(
                        "const el = document.querySelector(arguments[0]); if (el) { el.click(); return true; } return false;",
                        seletor
                    )

                self.sb.sleep(self.tempo_espera_pos_clique_vaga)

                try:
                    self.sb.wait_for_ready_state_complete(timeout=self.timeout_validacao_pos_clique)
                except Exception:
                    pass

                self.sb.sleep(self.tempo_espera_transicao_url)

                resultado_confirmacao = self.esperar_confirmacao_marcacao_inteligente(seletor)

                if resultado_confirmacao == "relogin":
                    return "relogin"

                if resultado_confirmacao is True:
                    try:
                        self.sb.wait_for_ready_state_complete(timeout=5)
                    except Exception:
                        pass
                    self.sb.sleep(0.20)
                    return True

                if self.sb.is_alert_present():
                    try:
                        self.sb.accept_alert()
                    except Exception:
                        pass

                print(f"   🔁 Vaga ainda não confirmou. Nova tentativa em {intervalo:.1f} segundo(s)...")
                self.sb.sleep(intervalo)

            except Exception as e:
                ultimo_erro = e
                print(f"   ⚠️ Falha ao tentar marcar a vaga na tentativa {tentativa}: {e}")
                self.sb.sleep(intervalo)

        if ultimo_erro:
            print(f"   ❌ Falha definitiva ao tentar marcar a vaga: {ultimo_erro}")
        return False

    def executar_inscricoes(self):
        with self.driver_lock:
            self.inscricao_em_andamento = True
            self.interromper_inscricao = False
            try:
                if not self.login_sucesso:
                    print("❌ Faça login primeiro.")
                    return

                self.verificar_autorizacao_usuario()

                total_inscricoes = len(self.inscricoes)
                inscricoes_realizadas = 0
                indice_atual = 0

                while indice_atual < len(self.inscricoes):
                    if self.interromper_inscricao:
                        print("🛑 Inscrição interrompida por solicitação.")
                        break

                    inscricao = self.inscricoes[indice_atual]
                    print("\n───────────────────────────────────────────────────────────────")
                    print(f"📋 [Inscrição {indice_atual + 1}/{max(total_inscricoes, len(self.inscricoes))}]")
                    self.iniciar_cronometro_inscricao()
                    print(f"    Convênio: {inscricao.convenio or '—'} | CPA: {inscricao.cpa or '—'} | Data: {inscricao.data}")

                    recuperacoes_select = 0

                    while True:
                        if self.interromper_inscricao:
                            print("🛑 Inscrição interrompida por solicitação.")
                            break

                        self.verificar_autorizacao_usuario()

                        if self.sessao_perdida_ou_fluxo_interrompido():
                            if self.tentar_recuperar_sessao_automaticamente("antes de processar a inscrição"):
                                continue
                            print("🛑 Não foi possível recuperar a sessão automaticamente. Mantendo a inscrição pendente.")
                            indice_atual += 1
                            break

                        if not self.inscricao_valida(inscricao):
                            print("   ⏭️ Pulando inscrição inválida")
                            removida = self.remover_inscricao_da_lista(inscricao)
                            print(f"   🗑️ Removida da lista pendente por inscrição inválida: {removida}")
                            break

                        if self.sb.is_element_present("input#btnNovaInscricao"):
                            try:
                                self.sb.click("input#btnNovaInscricao", timeout=0)
                                self.sb.wait_for_ready_state_complete(timeout=60)
                            except Exception:
                                pass

                        if not self.data_disponivel(inscricao.data):
                            if self.sessao_perdida_ou_fluxo_interrompido():
                                if self.tentar_recuperar_sessao_automaticamente(f"ao verificar a data {inscricao.data}"):
                                    continue
                                print(f"   🛑 Não foi possível recuperar a sessão ao verificar a data {inscricao.data}. Mantendo a inscrição pendente.")
                                indice_atual += 1
                                break

                            recuperacoes_select += 1
                            print(f"   ⚠️ Data {inscricao.data} não apareceu no select. Tentativa de recarregamento {recuperacoes_select}/{self.max_recuperacoes_select_indisponivel}.")
                            if recuperacoes_select <= self.max_recuperacoes_select_indisponivel and self.recuperar_fluxo_select_indisponivel(f"Data {inscricao.data} indisponível no select"):
                                continue

                            print(f"   ⚠️ Data {inscricao.data} continuou indisponível após recarregar. Mantendo pendente e passando para a próxima.")
                            indice_atual += 1
                            break

                        try:
                            if inscricao.convenio:
                                if not self.opcao_select_disponivel("#ddlConvenios", valor=inscricao.convenio):
                                    recuperacoes_select += 1
                                    print(f"   ⚠️ Convênio {inscricao.convenio} não apareceu no select. Tentativa de recarregamento {recuperacoes_select}/{self.max_recuperacoes_select_indisponivel}.")
                                    if recuperacoes_select <= self.max_recuperacoes_select_indisponivel and self.recuperar_fluxo_select_indisponivel(f"Convênio {inscricao.convenio} indisponível no select"):
                                        continue
                                    print("   ⚠️ Convênio continuou indisponível após recarregar. Mantendo pendente e passando para a próxima.")
                                    indice_atual += 1
                                    break

                                ok_convenio = self.selecionar_dropdown_extreme_validado("#ddlConvenios", valor=inscricao.convenio, nome_campo="Convênio")
                                if not ok_convenio:
                                    self.sb.select_option_by_value("#ddlConvenios", inscricao.convenio, timeout=0)

                                if self.ultimo_clique_inscricao is None:
                                    self.aguardar_estabilizacao_filtros(timeout=0.25, pausa=0.003)
                                else:
                                    self.aguardar_estabilizacao_filtros(timeout=1.2, pausa=0.025)

                            if inscricao.cpa:
                                if not self.opcao_select_disponivel("#ddlCPAS", valor=inscricao.cpa):
                                    recuperacoes_select += 1
                                    print(f"   ⚠️ CPA {inscricao.cpa} não apareceu no select. Tentativa de recarregamento {recuperacoes_select}/{self.max_recuperacoes_select_indisponivel}.")
                                    if recuperacoes_select <= self.max_recuperacoes_select_indisponivel and self.recuperar_fluxo_select_indisponivel(f"CPA {inscricao.cpa} indisponível no select"):
                                        continue
                                    print("   ⚠️ CPA continuou indisponível após recarregar. Mantendo pendente e passando para a próxima.")
                                    indice_atual += 1
                                    break

                                ok_cpa = self.selecionar_dropdown_extreme_validado("#ddlCPAS", valor=inscricao.cpa, nome_campo="CPA")
                                if not ok_cpa:
                                    self.sb.select_option_by_value("#ddlCPAS", inscricao.cpa, timeout=0)

                                if self.ultimo_clique_inscricao is None:
                                    self.aguardar_estabilizacao_filtros(timeout=0.25, pausa=0.003)
                                else:
                                    self.aguardar_estabilizacao_filtros(timeout=1.2, pausa=0.025)

                            if inscricao.data:
                                if self.ultimo_clique_inscricao is None:
                                    self.sb.sleep(0.001)
                                else:
                                    self.sb.sleep(0.015)

                                if not self.opcao_select_disponivel("#ddlDataEvento", texto=inscricao.data):
                                    recuperacoes_select += 1
                                    print(f"   ⚠️ Data {inscricao.data} sumiu antes da seleção. Tentativa de recarregamento {recuperacoes_select}/{self.max_recuperacoes_select_indisponivel}.")
                                    if recuperacoes_select <= self.max_recuperacoes_select_indisponivel and self.recuperar_fluxo_select_indisponivel(f"Data {inscricao.data} indisponível antes da seleção"):
                                        continue
                                    print("   ⚠️ Data continuou indisponível após recarregar. Mantendo pendente e passando para a próxima.")
                                    indice_atual += 1
                                    break

                                ok_data = self.selecionar_dropdown_extreme_validado("#ddlDataEvento", texto=inscricao.data, nome_campo="Data")
                                if not ok_data:
                                    self.sb.select_option_by_text("#ddlDataEvento", inscricao.data, timeout=0)

                                if self.ultimo_clique_inscricao is None:
                                    self.sb.sleep(0.001)
                                else:
                                    self.sb.sleep(0.005)
                        except Exception as e:
                            if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"ao preencher os filtros da data {inscricao.data}"):
                                continue

                            recuperacoes_select += 1
                            print(f"   ⚠️ Erro ao preencher filtros/selects: {e}. Tentativa de recarregamento {recuperacoes_select}/{self.max_recuperacoes_select_indisponivel}.")
                            if recuperacoes_select <= self.max_recuperacoes_select_indisponivel and self.recuperar_fluxo_select_indisponivel(f"erro ao preencher filtros da data {inscricao.data}"):
                                continue

                            print("   ⚠️ Não foi possível normalizar os selects após recarregar. Mantendo pendente e passando para a próxima.")
                            indice_atual += 1
                            break

                        captcha_ok = False
                        tentativas_captcha = 0
                        max_tentativas_captcha = 20
                        reiniciar_inscricao_atual = False

                        while not captcha_ok and not self.interromper_inscricao:
                            if self.sessao_perdida_ou_fluxo_interrompido():
                                if self.tentar_recuperar_sessao_automaticamente(f"durante o captcha da data {inscricao.data}"):
                                    print(f"   🔄 Sessão recuperada durante o captcha da data {inscricao.data}. Reiniciando a mesma inscrição do ponto correto...")
                                    reiniciar_inscricao_atual = True
                                    break
                                print(f"   🛑 Não foi possível recuperar a sessão durante o captcha da data {inscricao.data}. Mantendo a inscrição pendente.")
                                indice_atual += 1
                                break

                            tentativas_captcha += 1
                            print(f"   🤖 Resolvendo captcha (tentativa {tentativas_captcha}/{max_tentativas_captcha})...")

                            html = self.sb.get_page_source()
                            selector = parsel.Selector(html)
                            img_captcha = selector.css("div#captcha div")
                            if not img_captcha:
                                print("      ❌ Elemento de captcha não encontrado")
                                self.gerar_captcha()
                                continue

                            try:
                                base64_captcha = self.extrair_base64_captcha(img_captcha)

                                # ==============================
                                # MEDIR TEMPO DE RESOLUÇÃO
                                # ==============================
                                inicio_captcha = time.time()

                                resposta = self.resolver_captcha_inteligente(
                                    base64_captcha,
                                    contexto=f"data {inscricao.data}"
                                )

                                tempo_resolver = time.time() - inicio_captcha

                                print(f"      🔑 Resposta: {resposta}")
                                print(f"      ⏱️ CapMonster respondeu em {tempo_resolver:.2f}s")

                                # ==============================
                                # MEDIR TEMPO DE PREENCHIMENTO
                                # ==============================
                                inicio_preencher = time.time()

                                if not self.preencher_captcha_e_confirmar(resposta, tentativas=1):
                                    raise ValueError("Captcha não ficou preenchido corretamente")

                                tempo_preencher = time.time() - inicio_preencher

                                print(f"      ⚡ Campo preenchido em {tempo_preencher:.3f}s")
                            except Exception as e:
                                if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"ao preencher o captcha da data {inscricao.data}"):
                                    print(f"      🔄 Sessão recuperada ao preencher o captcha da data {inscricao.data}. Reiniciando a mesma inscrição...")
                                    reiniciar_inscricao_atual = True
                                    break
                                print(f"      ❌ Erro: {e}")
                                self.limpar_campo_se_existir("input#TextCaptcha")
                                self.gerar_captcha()
                                continue

                            try:
                                valor_captcha_antes_filtrar = self.obter_valor_captcha()
                                if not valor_captcha_antes_filtrar:
                                    raise ValueError('Campo do captcha está vazio antes do clique em Filtrar')

                                btn_filtrar = self.sb.find_element("input#btnConsultar", timeout=0.15 if self.ultimo_clique_inscricao is None else 1)
                                self.sb.click("input#btnConsultar")
                                WebDriverWait(self.sb.driver, timeout=10 * 60, poll_frequency=0.01).until(
                                    EC.staleness_of(btn_filtrar)
                                )
                                print("      ✅ Página carregada com sucesso")
                                captcha_ok = True
                                self.sb.sleep(0.005)
                            except UnexpectedAlertPresentException as e:
                                alert_text = e.alert_text if hasattr(e, "alert_text") else "Erro desconhecido"
                                print(f"      ⚠️ Alerta: {alert_text}")
                                self.limpar_campo_se_existir("input#TextCaptcha")
                                self.sb.sleep(2)
                                continue
                            except TimeoutException:
                                if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"após clicar em filtrar na data {inscricao.data}"):
                                    print(f"      🔄 Sessão recuperada após clicar em filtrar na data {inscricao.data}. Reiniciando a mesma inscrição...")
                                    reiniciar_inscricao_atual = True
                                    break
                                print("      ⏰ Timeout: página não carregou no tempo esperado!")
                                if tentativas_captcha < max_tentativas_captcha:
                                    print("      🔄 Gerando nova imagem...")
                                    self.limpar_campo_se_existir("input#TextCaptcha")
                                    self.gerar_captcha()
                                continue
                            except Exception as e:
                                if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"após o filtro da data {inscricao.data}"):
                                    print(f"      🔄 Sessão recuperada após o filtro da data {inscricao.data}. Reiniciando a mesma inscrição...")
                                    reiniciar_inscricao_atual = True
                                    break
                                print(f"      ❌ Erro inesperado: {e}")
                                self.limpar_campo_se_existir("input#TextCaptcha")
                                continue

                        if self.interromper_inscricao:
                            break

                        if reiniciar_inscricao_atual:
                            continue

                        if not captcha_ok:
                            if self.sessao_perdida_ou_fluxo_interrompido():
                                continue
                            print(f"   ❌ Captcha não confirmado para a data {inscricao.data}. Mantendo pendente para o próximo ciclo.")
                            indice_atual += 1
                            break

                        try:
                            self.sb.wait_for_selector("div#accordionConvenio", timeout=3)
                            self.sb.sleep(0.05)
                        except Exception:
                            if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"antes de carregar a tabela da data {inscricao.data}"):
                                continue
                            raise

                        if not self.sb.is_element_present("table#accordionConvenio_Pane_0_content_GridView1"):
                            if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"antes da leitura da tabela da data {inscricao.data}"):
                                continue
                            print("   ⚠️ Tabela de eventos não encontrada. Possivelmente não há vagas.")
                            removida = self.remover_inscricao_da_lista(inscricao)
                            print(f"   🗑️ Removida da lista pendente por ausência de tabela/vaga: {removida}")
                            break

                        html = self.sb.get_page_source()
                        tabela = self.extrair_tabela_eventos(html)
                        criterios_filtro = inscricao.obter_criterios_filtro()

                        # Seleção ultra profissional por tipo de vaga:
                        # - Se o usuário escolher TITULAR, tenta primeiro vaga titular nos locais informados.
                        # - Se não houver titular em nenhum local, tenta RESERVA nos mesmos locais.
                        # - Se não houver titular nem reserva, pula para a próxima inscrição.
                        # - Se escolher RESERVA, procura somente reserva.
                        # - Se escolher NÃO FILTRAR, mantém a lógica padrão.
                        tabela_filtrada = self.selecionar_vaga_titular_com_fallback_reserva(
                            tabela,
                            criterios_filtro
                        )

                        self.sb.sleep(0.05)

                        if tabela_filtrada.empty:
                            if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente(f"durante a leitura das vagas da data {inscricao.data}"):
                                continue
                            print("   ⚠️ Nenhum evento encontrado com esses critérios.")
                            removida = self.remover_inscricao_da_lista(inscricao)
                            print(f"   🗑️ Removida da lista pendente por ausência de vaga: {removida}")
                            break

                        print(f"   📊 Encontradas {len(tabela_filtrada)} vaga(s) disponíveis.")

                        direcao = (inscricao.direcao or "").strip().lower()
                        if direcao == "de baixo para cima":
                            vagas_para_tentar = tabela_filtrada.iloc[::-1]
                        else:
                            vagas_para_tentar = tabela_filtrada

                        sucesso_marcacao = False
                        precisa_relogin = False

                        for tentativa_vaga, (_, vaga) in enumerate(vagas_para_tentar.iterrows(), start=1):
                            seletor = vaga.get("seletor")

                            local_vaga = str(vaga.get("nome", "") or "").strip()
                            disponibilidade_vaga = str(vaga.get("disponivel", "") or "").strip()

                            print(
                                f"   🎯 Tentando vaga {tentativa_vaga}/{len(vagas_para_tentar)} "
                                f"| Local: {local_vaga} | Disponível: {disponibilidade_vaga}"
                            )

                            if not seletor:
                                print("   ⚠️ Vaga sem seletor. Pulando para a próxima opção.")
                                continue

                            self.aguardar_intervalo_inscricao()
                            sucesso_marcacao = self.clicar_vaga_com_tratamento_processando(seletor)

                            if sucesso_marcacao == "relogin":
                                precisa_relogin = True
                                break

                            if sucesso_marcacao is True:
                                break

                            print("   ⏭️ Essa vaga não confirmou. Tentando a próxima opção disponível na ordem.")

                        if precisa_relogin:
                            if self.tentar_recuperar_sessao_automaticamente(f"durante a marcação da data {inscricao.data}"):
                                continue
                            print(f"   🛑 Não foi possível recuperar a sessão durante a marcação da data {inscricao.data}. Mantendo pendente.")
                            indice_atual += 1
                            break

                        if sucesso_marcacao is True:
                            print("   🖱️ Clique realizado na vaga.")
                            print("   ✅ Inscrição confirmada com sucesso!")
                            self.inscricao_realizada = True
                            inscricoes_realizadas += 1
                            self.ultimo_clique_inscricao = time.time()
                            removida = self.remover_inscricao_da_lista(inscricao)
                            print(f"   🗑️ Removida da lista pendente após sucesso: {removida}")
                            break

                        print("   ⏭️ Nenhuma vaga da lista confirmou. Mantendo pendente para o próximo ciclo.")
                        indice_atual += 1
                        break

                    # se foi removida, não avança o índice porque a lista encolheu
                    if indice_atual < len(self.inscricoes) and self.inscricoes[indice_atual] is inscricao:
                        # permaneceu pendente e ainda é o mesmo objeto na posição atual
                        pass
                    elif inscricao in self.inscricoes:
                        # pendente movida adiante; garante avanço para não loopar na mesma posição
                        indice_atual += 1

                print(f"\n{'=' * 60}")
                print("📊 RESUMO DO PROCESSO")
                print(f"{'=' * 60}")
                print(f"   📋 Total de inscrições no início do ciclo: {total_inscricoes}")
                print(f"   ✅ Inscrições realizadas com sucesso: {inscricoes_realizadas}")
                print(f"   ⏭️ Inscrições restantes na lista pendente: {len(self.inscricoes)}")
                print(f"{'=' * 60}")
                print("\n───────────────────────────────────────────────────────────────")
                print("🏁 Processo finalizado.")

                try:
                    resumo_msg = (
                        f"RESUMO DO PROCESSO\n\n"
                        f"Total de inscricoes no inicio do ciclo: {total_inscricoes}\n"
                        f"Inscricoes realizadas com sucesso: {inscricoes_realizadas}\n"
                        f"Inscricoes restantes na lista pendente: {len(self.inscricoes)}"
                    )
                    messagebox.showinfo("MEGAZORD - Processo Concluido", resumo_msg)
                except Exception:
                    pass

            except Exception as e:
                if self.interromper_inscricao:
                    print("🛑 Inscrição interrompida por solicitação.")
                    return
                if self.sessao_perdida_ou_fluxo_interrompido() and self.tentar_recuperar_sessao_automaticamente("após erro geral durante inscrições"):
                    print("🔄 Sessão recuperada após erro geral. Mantendo as pendências para continuação imediata do ciclo atual.")
                else:
                    print(f"❌ Erro durante inscrições: {e}")
            finally:
                if not self.finalizar_programa and self.login_sucesso and self.sb and self.sb.driver:
                    self.verificar_autorizacao_usuario()
                    print(f"🏁 Processo encerrado. Permanecendo na página atual: {self.obter_url_atual()}")
                self.inscricao_em_andamento = False

    def extrair_tabela_eventos(self, html: str):
        selector = parsel.Selector(html)
        linhas = selector.css("table#accordionConvenio_Pane_0_content_GridView1 tbody tr")[1:]

        dados = []
        for linha in linhas:
            colunas = linha.css("td")
            if len(colunas) >= 6:
                nome = colunas[0].css("::text").get("").strip()
                hora = colunas[1].css("::text").get("").strip()
                turno = colunas[2].css("::text").get("").strip()
                endereco = colunas[3].css("::text").get("").strip()
                disponivel = colunas[4].css("::text").get("").strip()
                botao_id = colunas[5].css("a::attr(id)").get()
                if not botao_id:
                    botao_id = colunas[5].css("input::attr(id)").get()
                if not botao_id:
                    botao_id = colunas[5].css("button::attr(id)").get()

                dados.append({
                    "nome": nome,
                    "hora": hora,
                    "turno": turno,
                    "endereco": endereco,
                    "disponivel": disponivel,
                    "botao_id": botao_id,
                    "seletor": f"#{botao_id}" if botao_id else None,
                })

        df = pd.DataFrame(dados)
        if not df.empty:
            df["hora"] = pd.to_datetime(df["hora"], format="%H:%M:%S", errors="coerce").dt.time
        return df


    def normalizar_texto_filtro(self, texto):
        texto = str(texto or "").strip()
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
        return texto.upper()

    def quebrar_multiplas_opcoes_texto(self, valor):
        if valor is None:
            return []
        partes = re.split(r'[;,\n]+', str(valor))
        opcoes = [self.normalizar_texto_filtro(p) for p in partes if str(p).strip()]
        # remove duplicadas preservando ordem
        vistas = set()
        resultado = []
        for op in opcoes:
            if op not in vistas:
                vistas.add(op)
                resultado.append(op)
        return resultado

    def aplicar_prioridade_dinamica_local(self, tabela_filtrada: pd.DataFrame, criterios: dict):
        """
        Reorganiza as vagas seguindo TODOS os locais informados pelo usuário,
        preservando exatamente a ordem digitada.

        Exemplo no painel:
            Condição Local = "Contém"
            Local = "APERIBE, PADUA, ITAOCARA, CAMBUCI"

        Resultado dentro do tipo informado:
            APERIBE -> PADUA -> ITAOCARA -> CAMBUCI

        Importante:
            Esta função NÃO escolhe apenas o primeiro local encontrado.
            Ela monta uma lista ordenada com todas as vagas encontradas em todos
            os locais informados, para o robô tentar uma por uma.
        """
        try:
            if tabela_filtrada is None or tabela_filtrada.empty:
                return tabela_filtrada

            if not criterios:
                return tabela_filtrada

            condicao_local = str(criterios.get("condicao_local", "") or "").strip().lower()
            local_texto = str(criterios.get("local", "") or "").strip()

            # Só ativa a prioridade quando o filtro de Local estiver em "contém".
            if "cont" not in condicao_local:
                return tabela_filtrada

            ordem_locais = self.quebrar_multiplas_opcoes_texto(local_texto)
            if not ordem_locais:
                return tabela_filtrada

            coluna_local = "nome" if "nome" in tabela_filtrada.columns else None
            if not coluna_local:
                print("   ⚠️ Prioridade por local ignorada: coluna 'nome' não encontrada na tabela.")
                return tabela_filtrada

            serie_local_normalizada = tabela_filtrada[coluna_local].fillna("").map(self.normalizar_texto_filtro)

            partes_ordenadas = []
            indices_usados = set()

            for posicao, local_prioritario in enumerate(ordem_locais, start=1):
                mascara = serie_local_normalizada.map(lambda nome: local_prioritario in nome)
                vagas_local = tabela_filtrada[mascara].copy()

                if vagas_local.empty:
                    print(f"   ⚠️ Local sem vaga nesta etapa: {local_prioritario}")
                    continue

                # Evita duplicar a mesma linha caso duas palavras do usuário batam na mesma vaga.
                vagas_local = vagas_local[~vagas_local.index.isin(indices_usados)]
                if vagas_local.empty:
                    continue

                vagas_local["_prioridade_local"] = posicao
                vagas_local["_local_prioridade_nome"] = local_prioritario

                partes_ordenadas.append(vagas_local)
                indices_usados.update(vagas_local.index.tolist())

            if not partes_ordenadas:
                print("   ⚠️ Nenhum local da prioridade foi encontrado. Mantendo resultado filtrado original.")
                return tabela_filtrada

            resultado = pd.concat(partes_ordenadas, ignore_index=False)

            print(f"   📍 Ordem de locais aplicada: {', '.join(ordem_locais)}")
            print(f"   ✅ Total de vagas ordenadas por local: {len(resultado)}")

            return resultado

        except Exception as e:
            print(f"   ⚠️ Erro ao aplicar prioridade dinâmica por local: {e}")
            return tabela_filtrada

    def selecionar_vaga_titular_com_fallback_reserva(self, tabela: pd.DataFrame, criterios: dict):
        """
        Seleção dinâmica e profissional de vaga por tipo.

        Fluxo principal:
            1. Mantém todos os filtros já existentes: local, hora, endereço, turno e direção.
            2. Se tipo_vaga = "titular":
               - tenta primeiro vagas TITULARES nos locais informados pelo usuário;
               - se não achar titular em nenhum local, tenta vagas RESERVA nos mesmos locais;
               - se não achar nada, retorna DataFrame vazio para o sistema pular para a próxima inscrição.
            3. Se tipo_vaga = "reserva": procura somente RESERVA.
            4. Se tipo_vaga = "não filtrar": mantém o comportamento padrão.

        Exemplo:
            Local = "PADUA, MIRACEMA, ITAOCARA"
            Tipo da vaga = "Titular"

        Ordem de tentativa:
            PADUA TITULAR -> MIRACEMA TITULAR -> ITAOCARA TITULAR
            PADUA RESERVA -> MIRACEMA RESERVA -> ITAOCARA RESERVA
        """
        try:
            if tabela is None or tabela.empty:
                return pd.DataFrame()

            criterios_base = dict(criterios or {})
            tipo_original = str(criterios_base.get("tipo_vaga", "não filtrar") or "não filtrar").strip()
            tipo_normalizado = self.normalizar_texto_filtro(tipo_original)

            print(f"   🔎 Tipo de vaga solicitado: {tipo_original}")

            def _filtrar_e_priorizar(tipo_alvo: str):
                criterios_tipo = dict(criterios_base)
                criterios_tipo["tipo_vaga"] = tipo_alvo

                filtrada = self.aplicar_filtros(tabela, criterios_tipo)
                filtrada = self.aplicar_prioridade_dinamica_local(filtrada, criterios_tipo)
                return filtrada

            # Quando o usuário selecionar TITULAR, procura somente TITULAR (estrito).
            if tipo_normalizado == "TITULAR":
                vagas_titular = _filtrar_e_priorizar("titular")

                if vagas_titular is not None and not vagas_titular.empty:
                    print(f"   ✅ Vaga TITULAR encontrada: {len(vagas_titular)} resultado(s).")
                    return vagas_titular

                print("   ⏭️ Nenhuma vaga TITULAR encontrada nas condições informadas.")
                return pd.DataFrame()

            # Quando o usuário selecionar TITULAR/RESERVA, tenta TITULAR primeiro.
            # Se não achar, tenta RESERVA como fallback (um ou outro).
            if tipo_normalizado == "TITULAR/RESERVA":
                vagas_titular = _filtrar_e_priorizar("titular")

                if vagas_titular is not None and not vagas_titular.empty:
                    print(f"   ✅ Vaga TITULAR encontrada: {len(vagas_titular)} resultado(s).")
                    return vagas_titular

                print("   ⚠️ Nenhuma vaga TITULAR encontrada. Tentando RESERVA como fallback...")

                vagas_reserva = _filtrar_e_priorizar("reserva")

                if vagas_reserva is not None and not vagas_reserva.empty:
                    print(f"   ✅ Vaga RESERVA encontrada como fallback: {len(vagas_reserva)} resultado(s).")
                    return vagas_reserva

                print("   ⏭️ Nenhuma vaga TITULAR nem RESERVA encontrada.")
                return pd.DataFrame()

            # Quando o usuário selecionar RESERVA, procura somente reserva.
            if tipo_normalizado == "RESERVA":
                vagas_reserva = _filtrar_e_priorizar("reserva")
                if vagas_reserva is not None and not vagas_reserva.empty:
                    print(f"   ✅ Vaga RESERVA encontrada: {len(vagas_reserva)} resultado(s).")
                    return vagas_reserva

                print("   ⏭️ Nenhuma vaga RESERVA encontrada nas condições informadas.")
                return pd.DataFrame()

            # Não filtrar / valor vazio / qualquer outro valor mantém a lógica original.
            tabela_filtrada = self.aplicar_filtros(tabela, criterios_base)
            tabela_filtrada = self.aplicar_prioridade_dinamica_local(tabela_filtrada, criterios_base)
            return tabela_filtrada

        except Exception as e:
            print(f"   ⚠️ Erro na seleção titular/reserva com fallback: {e}")
            try:
                tabela_filtrada = self.aplicar_filtros(tabela, criterios or {})
                return self.aplicar_prioridade_dinamica_local(tabela_filtrada, criterios or {})
            except Exception:
                return pd.DataFrame()

    def aplicar_filtros(self, tabela: pd.DataFrame, criterios: dict):
        tabela_filtrada = tabela.copy()

        if "condicao_hora" in criterios and criterios["condicao_hora"] != "não filtrar":
            op = criterios["condicao_hora"]
            valor = criterios.get("hora")
            if valor:
                hora_ref = pd.to_datetime(valor, format="%H:%M:%S").time()
                if op == "igual":
                    tabela_filtrada = tabela_filtrada[tabela_filtrada["hora"] == hora_ref]
                elif op == "antes":
                    tabela_filtrada = tabela_filtrada[tabela_filtrada["hora"] < hora_ref]
                elif op == "depois":
                    tabela_filtrada = tabela_filtrada[tabela_filtrada["hora"] > hora_ref]

        if "tipo_vaga" in criterios:
            tipo = self.normalizar_texto_filtro(criterios.get("tipo_vaga"))
            if tipo and tipo not in ("NAO FILTRAR", "NÃO FILTRAR"):
                if tipo == "TITULAR":
                    tabela_filtrada = tabela_filtrada[
                        ~tabela_filtrada["disponivel"].astype(str).str.contains("RESERVA", case=False, na=False)
                    ]
                elif tipo == "RESERVA":
                    tabela_filtrada = tabela_filtrada[
                        tabela_filtrada["disponivel"].astype(str).str.contains("RESERVA", case=False, na=False)
                    ]

        if "condicao_local" in criterios and criterios["condicao_local"] != "não filtrar":
            op = criterios["condicao_local"]
            valor = criterios.get("local")
            if valor:
                opcoes_local = self.quebrar_multiplas_opcoes_texto(valor)
                if opcoes_local:
                    serie_nome_normalizada = tabela_filtrada["nome"].fillna("").map(self.normalizar_texto_filtro)

                    if op == "igual":
                        tabela_filtrada = tabela_filtrada[
                            serie_nome_normalizada.isin(opcoes_local)
                        ]
                    elif op == "contém":
                        mascara = serie_nome_normalizada.map(
                            lambda nome: any(opcao in nome for opcao in opcoes_local)
                        )
                        tabela_filtrada = tabela_filtrada[mascara]
                    elif op == "não contém":
                        mascara = serie_nome_normalizada.map(
                            lambda nome: all(opcao not in nome for opcao in opcoes_local)
                        )
                        tabela_filtrada = tabela_filtrada[mascara]

        if "endereco" in criterios and criterios["endereco"] not in (None, "", "não filtrar"):
            valor = criterios["endereco"]
            if valor:
                tabela_filtrada = tabela_filtrada[
                    tabela_filtrada["endereco"].str.contains(valor, case=False, na=False)
                ]

        if "turno" in criterios:
            valor = str(criterios.get("turno") or "").strip()

            valor_normalizado = self.normalizar_texto_filtro(valor)

            if valor and valor_normalizado not in ("NAO FILTRAR", "NÃO FILTRAR"):
                tabela_filtrada = tabela_filtrada[
                    tabela_filtrada["turno"].astype(str).str.strip() == valor
                ]

        return tabela_filtrada

    def inscricao_valida(self, inscricao: Inscricao) -> bool:
        if not inscricao.data or not str(inscricao.data).strip():
            print("❌ Inscrição inválida: data não preenchida.")
            return False

        tem_convenio = inscricao.convenio and str(inscricao.convenio).strip()
        tem_cpa = inscricao.cpa and str(inscricao.cpa).strip()

        if not (tem_convenio or tem_cpa):
            print("❌ Inscrição inválida: é necessário informar convênio OU CPA.")
            return False

        return True

    def aguardar_estabilizacao_filtros(self, timeout=1.2, pausa=0.025):
        """Espera curta e segura para estabilizar os filtros sem atrasar a marcação."""
        try:
            self.sb.wait_for_element("#ddlDataEvento", timeout=timeout)
            try:
                self.sb.wait_for_ready_state_complete(timeout=timeout)
            except Exception:
                pass
            self.sb.sleep(pausa)
            return True
        except Exception:
            return False

    def data_disponivel(self, data: str) -> bool:
        try:
            self.sb.wait_for_element("#ddlDataEvento", timeout=10)
            data_ref = str(data or "").strip()
            options = self.sb.get_select_options("#ddlDataEvento")
            options_normalizadas = [str(op or "").strip() for op in options]
            return data_ref in options_normalizadas
        except Exception as e:
            print(f"⚠️ Erro ao verificar disponibilidade da data: {e}")
            return False

    # ==================== AUXILIARES ====================

    def gerar_captcha(self):
        self.sb.click("//a[text()='Gerar Nova Imagem']", by="xpath", timeout=2)

    def extrair_base64_captcha(self, elemento: parsel.Selector):
        style = elemento.css("::attr(style)").get()
        if not style:
            raise ValueError("Elemento não possui atributo style.")
        match = re.search(r"url\(['\"]?data:image/[^;]+;base64,([^'\")\s]+)['\"]?\)", style)
        if not match:
            raise ValueError("Base64 não encontrado no style.")
        return match.group(1)

    # ==================== HOTKEYS / DISPAROS ====================

    def solicitar_login(self):
        if self.login_em_andamento:
            print("⏳ Login já em andamento.")
            return

        try:
            html = self.sb.get_page_source()
            selector = parsel.Selector(html)
            select_elmt = selector.css("select#ddlTipoAcesso").get()
            if select_elmt:
                print("✅ Está na página de login. Prosseguindo...")
            else:
                print("🔙 Não está na página de login. Volte manualmente e tente novamente.")
                return
        except Exception as e:
            print(f"⚠️ Erro ao verificar página de login: {e}")
            return

        if self.inscricao_em_andamento:
            print("🛑 Interrompendo inscrição para realizar login manual...")
            self.interromper_inscricao = True
            print("✅ Sinal de interrupção enviado.")

        self.retomar_automaticamente_apos_login = False
        self.login_sucesso = False
        self.login_em_andamento = True
        threading.Thread(target=self.fazer_login, daemon=True).start()

    def solicitar_inscricao(self):
        """
        Hotkey Q inteligente e contextual.

        Comportamento ao pressionar Q:
        - FrmMenuVoluntario.aspx: clica em Escala.
        - FrmVoluntarioInscricoesConsultar.aspx: clica em Nova Inscrição.
        - FrmEventoAssociar.aspx: inicia a marcação.
        """
        if self.inscricao_em_andamento:
            print("⏳ Inscrição já em andamento nesta instância. Ignorando...")
            return

        threading.Thread(target=self._fluxo_hotkey_q_inteligente, daemon=True).start()


    def _iniciar_execucao_inscricoes_por_hotkey(self):
        """Valida login/lista e inicia executar_inscricoes em thread separada."""
        if self.inscricao_em_andamento:
            print("⏳ Inscrição já em andamento nesta instância. Ignorando...")
            return False

        if not self.login_sucesso:
            print("❌ Faça login primeiro (Ctrl+1).")
            return False

        if not self.inscricoes:
            reiniciado = self.recarregar_lista_principal_se_necessario()
            if not reiniciado:
                print("📋 Lista de inscrições vazia.")
                return False
        else:
            print(f"📌 Retomando inscrições pendentes: {len(self.inscricoes)} item(ns) restante(s).")

        print("🚀 Iniciando novo processo de inscrição.")
        self.thread_inscricao = threading.Thread(target=self.executar_inscricoes, daemon=True)
        self.thread_inscricao.start()
        return True


    def _fluxo_hotkey_q_inteligente(self):
        try:
            if not self.sb or not self.sb.driver:
                print("❌ Navegador não iniciado.")
                return

            if not self.login_sucesso:
                print("❌ Faça login primeiro (Ctrl+1).")
                return

            self.verificar_autorizacao_usuario()
            url_atual = (self.obter_url_atual() or "").lower()
            print(f"🔎 Página atual detectada: {url_atual}")

            # =========================================================
            # 1) MENU VOLUNTÁRIO -> CLICA EM ESCALA
            # =========================================================
            if "frmmenuvoluntario.aspx" in url_atual:
                print("📍 Tela Menu Voluntário detectada. Clicando em Escala...")

                try:
                    if self.sb.is_element_present("a#btnEscala"):
                        try:
                            self.sb.click("a#btnEscala", timeout=2)
                        except Exception:
                            self.sb.execute_script("""
                                const btn = document.querySelector('a#btnEscala');
                                if (btn) { btn.click(); return true; }
                                return false;
                            """)

                        try:
                            self.sb.wait_for_ready_state_complete(timeout=30)
                        except Exception:
                            pass
                        self.sb.sleep(0.15)
                    else:
                        print("⚠️ Botão Escala não encontrado na tela do Menu Voluntário.")
                except Exception as e:
                    print(f"⚠️ Erro ao clicar em Escala: {e}")

                url_atual = (self.obter_url_atual() or "").lower()

            # =========================================================
            # 2) TELA DE INSCRIÇÕES -> CLICA EM NOVA INSCRIÇÃO
            # =========================================================
            if "frmvoluntarioinscricoesconsultar.aspx" in url_atual:
                print("📍 Tela de inscrições detectada. Clicando em Nova Inscrição...")

                try:
                    if self.sb.is_element_present("input#btnNovaInscricao"):
                        try:
                            self.sb.click("input#btnNovaInscricao", timeout=2)
                        except Exception:
                            self.sb.execute_script("""
                                const btn = document.querySelector('input#btnNovaInscricao');
                                if (btn) { btn.click(); return true; }
                                return false;
                            """)

                        try:
                            self.sb.wait_for_ready_state_complete(timeout=30)
                        except Exception:
                            pass
                        self.sb.sleep(0.15)
                    else:
                        print("⚠️ Botão Nova Inscrição não encontrado.")
                except Exception as e:
                    print(f"⚠️ Erro ao clicar em Nova Inscrição: {e}")

                url_atual = (self.obter_url_atual() or "").lower()

            # =========================================================
            # 3) TELA DE MARCAÇÃO -> EXECUTA INSCRIÇÕES
            # =========================================================
            if "frmeventoassociar.aspx" in url_atual:
                print("🚀 Tela de marcação detectada. Iniciando execução das inscrições...")
                self._iniciar_execucao_inscricoes_por_hotkey()
                return

            # =========================================================
            # 4) RECUPERAÇÃO AUTOMÁTICA DO FLUXO
            # =========================================================
            print("⚠️ Página não reconhecida para a hotkey Q.")
            print("🔄 Tentando recuperar fluxo automaticamente...")

            if self.preparar_fluxo_pos_relogin_turbo("hotkey Q"):
                self._iniciar_execucao_inscricoes_por_hotkey()
                return

            print("❌ Não foi possível recuperar o fluxo pela hotkey Q.")

        except Exception as e:
            print(f"❌ Erro na hotkey Q inteligente: {e}")

    # ==================== PAINEL DUPLO ====================

    def abrir_painel_duplo_agendamento(self):
        if self.ui_root is None or not self.ui_root.winfo_exists():
            return

        if not self.sincronizar_relogio_proeis():
            messagebox.showerror("Erro", "Não foi possível capturar a hora do servidor do PROEIS.")
            return

        if self.agendamento_servidor_var is None:
            self.agendamento_servidor_var = StringVar(master=self.ui_root, value="")
        if self.agendamento_status_var is None:
            self.agendamento_status_var = StringVar(master=self.ui_root, value="Sincronizado com o servidor")

        if self.login_horas_var is None:
            self.login_horas_var = StringVar(master=self.ui_root, value="05")
        if self.login_minutos_var is None:
            self.login_minutos_var = StringVar(master=self.ui_root, value="55")
        if self.login_segundos_var is None:
            self.login_segundos_var = StringVar(master=self.ui_root, value="00")
        if self.login_alvo_var is None:
            self.login_alvo_var = StringVar(master=self.ui_root, value="")
        if self.login_restante_var is None:
            self.login_restante_var = StringVar(master=self.ui_root, value="00.000s")

        if self.disparo_horas_var is None:
            self.disparo_horas_var = StringVar(master=self.ui_root, value="06")
        if self.disparo_minutos_var is None:
            self.disparo_minutos_var = StringVar(master=self.ui_root, value="00")
        if self.disparo_segundos_var is None:
            self.disparo_segundos_var = StringVar(master=self.ui_root, value="00")
        if self.disparo_alvo_var is None:
            self.disparo_alvo_var = StringVar(master=self.ui_root, value="")
        if self.disparo_restante_var is None:
            self.disparo_restante_var = StringVar(master=self.ui_root, value="00.000s")

        if self.janela_agendamento is not None:
            try:
                if self.janela_agendamento.winfo_exists():
                    self.janela_agendamento.lift()
                    self.janela_agendamento.focus_force()
                    return
            except Exception:
                self.janela_agendamento = None

        usuario_interface = self.obter_usuario_selecionado_interface_para_tela()

        # Painel compacto final: sem espaço morto entre status e botões.
        self.janela_agendamento = Toplevel(self.ui_root)
        self.janela_agendamento.title(f"MEGAZORD • Agendamento PROEIS • {usuario_interface}")
        self.janela_agendamento.configure(bg="#020617")
        self.janela_agendamento.resizable(False, False)
        self.centralizar_janela(self.janela_agendamento, 660, 610)

        card = Frame(
            self.janela_agendamento,
            bg="#0f172a",
            bd=0,
            highlightthickness=1,
            highlightbackground="#334155"
        )
        card.place(relx=0.5, rely=0.5, anchor="center", width=628, height=578)

        header = Frame(card, bg="#111827", height=46)
        header.pack(fill="x")
        header.pack_propagate(False)

        Label(
            header,
            text="⚡ MEGAZORD PROEIS",
            bg="#111827",
            fg="#38bdf8",
            font=("Segoe UI", 15, "bold")
        ).pack(pady=(4, 0))

        Label(
            header,
            text="Agendamento sincronizado • modo precisão",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 8)
        ).pack()

        Label(
            header,
            text=f"USUÁRIO SELECIONADO: {usuario_interface}",
            bg="#111827",
            fg="#facc15",
            font=("Segoe UI", 8, "bold")
        ).pack()

        body = Frame(card, bg="#0f172a")
        body.pack(fill="both", expand=True, padx=12, pady=(7, 7))

        clock_box = Frame(
            body,
            bg="#020617",
            bd=0,
            height=92,
            highlightthickness=1,
            highlightbackground="#1e40af"
        )
        clock_box.pack(fill="x", pady=(0, 6))
        clock_box.pack_propagate(False)

        Label(
            clock_box,
            text="HORÁRIO DO SERVIDOR PROEIS",
            bg="#020617",
            fg="#60a5fa",
            font=("Segoe UI", 8, "bold")
        ).pack(pady=(6, 0))

        Label(
            clock_box,
            textvariable=self.agendamento_servidor_var,
            bg="#020617",
            fg="#22c55e",
            font=("Consolas", 26, "bold")
        ).pack(pady=(0, 5))

        info_grid = Frame(body, bg="#0f172a", height=48)
        info_grid.pack(fill="x", pady=(0, 6))
        info_grid.pack_propagate(False)

        def criar_card_status(parent, titulo, valor, cor):
            box = Frame(
                parent,
                bg="#020617",
                height=48,
                highlightthickness=1,
                highlightbackground="#334155"
            )
            box.pack(side="left", expand=True, fill="both", padx=3)
            box.pack_propagate(False)

            Label(
                box,
                text=titulo,
                bg="#020617",
                fg="#94a3b8",
                font=("Segoe UI", 7, "bold")
            ).pack(pady=(5, 0))

            Label(
                box,
                text=valor,
                bg="#020617",
                fg=cor,
                font=("Segoe UI", 9, "bold")
            ).pack(pady=(0, 4))

        criar_card_status(info_grid, "OFFSET", f"{self.offset_servidor_segundos * 1000:+.1f} ms", "#38bdf8")
        criar_card_status(info_grid, "LATÊNCIA", f"{(self.melhor_latencia_servidor or 0) * 1000:.1f} ms", "#facc15")
        criar_card_status(info_grid, "PRECISÃO", "ULTRA", "#22c55e")

        self.frame_login = Frame(
            body,
            bg="#111827",
            bd=0,
            height=104,
            highlightthickness=1,
            highlightbackground="#2563eb"
        )
        self.frame_login.pack(fill="x", pady=(0, 6))
        self.frame_login.pack_propagate(False)
        self._montar_bloco_horario(
            parent=self.frame_login,
            titulo="🔐 Horário do Login",
            horas_var=self.login_horas_var,
            minutos_var=self.login_minutos_var,
            segundos_var=self.login_segundos_var,
            alvo_var=self.login_alvo_var,
            restante_var=self.login_restante_var
        )

        self.frame_disparo = Frame(
            body,
            bg="#111827",
            bd=0,
            height=104,
            highlightthickness=1,
            highlightbackground="#16a34a"
        )
        self.frame_disparo.pack(fill="x", pady=(0, 6))
        self.frame_disparo.pack_propagate(False)
        self._montar_bloco_horario(
            parent=self.frame_disparo,
            titulo="🎯 Horário do Disparo das Vagas",
            horas_var=self.disparo_horas_var,
            minutos_var=self.disparo_minutos_var,
            segundos_var=self.disparo_segundos_var,
            alvo_var=self.disparo_alvo_var,
            restante_var=self.disparo_restante_var
        )

        status_box = Frame(
            body,
            bg="#020617",
            height=34,
            highlightthickness=1,
            highlightbackground="#334155"
        )
        status_box.pack(fill="x", pady=(0, 5))
        status_box.pack_propagate(False)

        Label(
            status_box,
            textvariable=self.agendamento_status_var,
            bg="#020617",
            fg="#e5e7eb",
            font=("Segoe UI", 8, "bold"),
            wraplength=560,
            justify="center"
        ).pack(expand=True)

        # Botões logo abaixo do status, sem side="bottom", para não criar espaço vazio.
        botoes = Frame(body, bg="#0f172a", height=48)
        botoes.pack(fill="x", pady=(0, 0))
        botoes.pack_propagate(False)

        Button(
            botoes,
            text="▶ START",
            bg="#22c55e",
            fg="#052e16",
            activebackground="#86efac",
            activeforeground="#052e16",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
            command=self.iniciar_agendamento
        ).pack(side="left", expand=True, fill="both", padx=(0, 5), pady=4)

        Button(
            botoes,
            text="■ STOP",
            bg="#ef4444",
            fg="white",
            activebackground="#f87171",
            activeforeground="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
            command=self.parar_agendamento
        ).pack(side="left", expand=True, fill="both", padx=5, pady=4)

        Button(
            botoes,
            text="↻ SYNC",
            bg="#38bdf8",
            fg="#082f49",
            activebackground="#7dd3fc",
            activeforeground="#082f49",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
            command=self.resincronizar_agendamento
        ).pack(side="left", expand=True, fill="both", padx=(5, 0), pady=4)

        self.janela_agendamento.protocol("WM_DELETE_WINDOW", self.fechar_painel_duplo_agendamento)
        self.atualizar_relogio_visual_agendamento()

    def _montar_bloco_horario(self, parent, titulo, horas_var, minutos_var, segundos_var, alvo_var, restante_var):
        container = Frame(parent, bg="#111827", padx=10, pady=5)
        container.pack(fill="both", expand=True)

        Label(
            container,
            text=titulo,
            bg="#111827",
            fg="#f8fafc",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        linha = Frame(container, bg="#111827")
        linha.pack(fill="x", pady=(4, 0))

        campos = Frame(linha, bg="#111827")
        campos.pack(side="left", fill="x", expand=True)

        def campo_tempo(label, var):
            box = Frame(campos, bg="#111827")
            box.pack(side="left", expand=True, fill="x", padx=3)

            Label(
                box,
                text=label,
                bg="#111827",
                fg="#94a3b8",
                font=("Segoe UI", 7, "bold")
            ).pack()

            Spinbox(
                box,
                from_=0,
                to=59 if label != "Hora" else 23,
                textvariable=var,
                font=("Consolas", 11, "bold"),
                justify="center",
                width=5,
                bg="#020617",
                fg="#22c55e",
                buttonbackground="#1e293b",
                relief="flat",
                insertbackground="#22c55e"
            ).pack(ipady=1)

        campo_tempo("Hora", horas_var)
        campo_tempo("Min", minutos_var)
        campo_tempo("Seg", segundos_var)

        restante_box = Frame(linha, bg="#111827", width=145)
        restante_box.pack(side="right", fill="y", padx=(8, 0))
        restante_box.pack_propagate(False)

        Label(
            restante_box,
            text="Tempo restante",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 7, "bold")
        ).pack(anchor="w")

        Label(
            restante_box,
            textvariable=restante_var,
            bg="#111827",
            fg="#facc15",
            font=("Consolas", 18, "bold")
        ).pack(anchor="w")

        Label(
            container,
            textvariable=alvo_var,
            bg="#111827",
            fg="#38bdf8",
            font=("Segoe UI", 7, "bold")
        ).pack(anchor="w", pady=(1, 0))

    def iniciar_agendamento(self):
        if self.agendamento_rodando:
            return

        try:
            lh = int(str(self.login_horas_var.get()).strip())
            lm = int(str(self.login_minutos_var.get()).strip())
            ls = int(str(self.login_segundos_var.get()).strip())

            dh = int(str(self.disparo_horas_var.get()).strip())
            dm = int(str(self.disparo_minutos_var.get()).strip())
            ds = int(str(self.disparo_segundos_var.get()).strip())
        except Exception:
            messagebox.showerror("Erro", "Informe horários válidos.")
            return

        if not (0 <= lh <= 23 and 0 <= lm <= 59 and 0 <= ls <= 59):
            messagebox.showerror("Erro", "Horário do login inválido.")
            return
        if not (0 <= dh <= 23 and 0 <= dm <= 59 and 0 <= ds <= 59):
            messagebox.showerror("Erro", "Horário do disparo inválido.")
            return

        self.login_horario_alvo_texto = f"{lh:02d}:{lm:02d}:{ls:02d}"
        self.disparo_horario_alvo_texto = f"{dh:02d}:{dm:02d}:{ds:02d}"

        self.login_alvo_var.set(f"Login agendado para: {self.login_horario_alvo_texto}")
        self.disparo_alvo_var.set(f"Disparo agendado para: {self.disparo_horario_alvo_texto}")
        self.agendamento_status_var.set(
            "Aguardando horário do login. O disparo usará sincronização final pelo #lblSemana do PROEIS."
        )

        self.agendamento_rodando = True
        self.etapa_atual = "login"
        self.login_resincronizacao_final_feita = False
        self.disparo_resincronizacao_final_feita = False
        self.login_disparado = False
        self.disparo_disparado = False
        self.ultimo_heartbeat_agendamento = time.time()
        self.monitor_anti_congelamento_parado_por_login = False

        # Liga o monitor profissional durante a espera longa.
        # Ele será parado automaticamente quando faltar 1 minuto para o login.
        self.iniciar_monitor_anti_congelamento()

        self.atualizar_relogio_visual_agendamento()

    def atualizar_relogio_visual_agendamento(self):
        if not self.janela_agendamento or not self.janela_agendamento.winfo_exists():
            return

        # Heartbeat usado pelo watchdog anti-congelamento.
        self.ultimo_heartbeat_agendamento = time.time()

        agora = self.agora_servidor_sincronizado()
        if agora:
            horario_atual_ms = agora.strftime("%H:%M:%S.%f")[:-3]
            self.agendamento_servidor_var.set(horario_atual_ms)

            if self.agendamento_rodando:
                # ==================== ETAPA LOGIN ====================
                if self.etapa_atual == "login" and self.login_horario_alvo_texto:
                    atingiu, restante, alvo_hoje = self.chegou_no_horario_alvo_preciso(
                        agora,
                        self.login_horario_alvo_texto
                    )

                    if (
                        self.monitor_anti_congelamento_ativo
                        and not self.monitor_anti_congelamento_parado_por_login
                        and 0 < restante <= self.parar_monitor_antes_login_segundos
                    ):
                        self.monitor_anti_congelamento_parado_por_login = True
                        self.parar_monitor_anti_congelamento(
                            "faltando 1 minuto para o login agendado"
                        )
                        self.agendamento_status_var.set(
                            "Monitor anti-congelamento parado. Faltam até 1 minuto para o login."
                        )

                    if (not self.login_resincronizacao_final_feita) and 0 < restante <= self.segundos_resincronizacao_final:
                        self.agendamento_status_var.set(
                            "Sincronizando relógio do servidor na reta final do login..."
                        )
                        self.resincronizacao_final_hibrida(etapa="login")
                        self.login_resincronizacao_final_feita = True
                        agora = self.agora_servidor_sincronizado()
                        if agora:
                            horario_atual_ms = agora.strftime("%H:%M:%S.%f")[:-3]
                            self.agendamento_servidor_var.set(horario_atual_ms)
                            atingiu, restante, alvo_hoje = self.chegou_no_horario_alvo_preciso(
                                agora,
                                self.login_horario_alvo_texto
                            )

                    self.login_restante_var.set(self.formatar_tempo_preciso(max(restante, 0)))

                    if 0 < restante <= (self.preparo_fino_ms / 1000):
                        self.agendamento_status_var.set(
                            f"Preparação final: faltam até {self.preparo_fino_ms}ms para o login."
                        )
                    elif restante > 0:
                        self.agendamento_status_var.set(
                            "Aguardando horário do login pelo relógio sincronizado do servidor."
                        )

                    if atingiu and not self.login_disparado:
                        self.login_disparado = True
                        self.agendamento_status_var.set(
                            "Horário exato do servidor atingido. Executando login automático..."
                        )
                        self.solicitar_login()
                        self.etapa_atual = "disparo"

                        try:
                            if self.frame_login and self.frame_login.winfo_exists():
                                self.frame_login.pack_forget()
                        except Exception:
                            pass

                        self.login_horario_alvo_texto = None
                        self.login_alvo_var.set("")
                        self.login_restante_var.set("00.000s")

                # ==================== ETAPA DISPARO ====================
                if self.etapa_atual == "disparo" and self.disparo_horario_alvo_texto:
                    atingiu, restante, alvo_hoje = self.chegou_no_horario_alvo_preciso(
                        agora,
                        self.disparo_horario_alvo_texto,
                        compensacao_ms=self.compensacao_disparo_ms
                    )

                    if (not self.disparo_resincronizacao_final_feita) and 0 < restante <= self.segundos_resincronizacao_final:
                        self.agendamento_status_var.set(
                            "Faltam 60s: entrando em Nova Inscrição, sincronizando pelo #lblSemana e voltando para espera..."
                        )
                        self.resincronizacao_final_hibrida(etapa="disparo")
                        self.disparo_resincronizacao_final_feita = True
                        agora = self.agora_servidor_sincronizado()
                        if agora:
                            horario_atual_ms = agora.strftime("%H:%M:%S.%f")[:-3]
                            self.agendamento_servidor_var.set(horario_atual_ms)
                            atingiu, restante, alvo_hoje = self.chegou_no_horario_alvo_preciso(
                                agora,
                                self.disparo_horario_alvo_texto,
                                compensacao_ms=self.compensacao_disparo_ms
                            )

                    self.disparo_restante_var.set(self.formatar_tempo_preciso(max(restante, 0)))

                    if 0 < restante <= (self.preparo_fino_ms / 1000):
                        self.agendamento_status_var.set(
                            f"Preparação final: faltam até {self.preparo_fino_ms}ms para o disparo."
                        )
                    elif restante > 0:
                        self.agendamento_status_var.set(
                            f"Aguardando disparo: #lblSemana sincronizado | compensação {self.compensacao_disparo_ms}ms ativa."
                        )

                    if atingiu and not self.disparo_disparado:
                        self.disparo_disparado = True
                        self.agendamento_status_var.set(
                            "Horário exato do servidor atingido. Buscando vagas..."
                        )
                        self.agendamento_rodando = False
                        self.fechar_painel_duplo_agendamento()
                        self.solicitar_inscricao()
                        return

        intervalo_ms = 1 if self.agendamento_rodando else 200
        self.agendamento_after_id = self.ui_root.after(intervalo_ms, self.atualizar_relogio_visual_agendamento)

    def parar_agendamento(self):
        self.parar_monitor_anti_congelamento("agendamento parado")
        self.agendamento_rodando = False
        self.login_horario_alvo_texto = None
        self.disparo_horario_alvo_texto = None
        self.login_resincronizacao_final_feita = False
        self.disparo_resincronizacao_final_feita = False
        self.login_disparado = False
        self.disparo_disparado = False
        self.etapa_atual = "login"

        if self.login_alvo_var:
            self.login_alvo_var.set("")
        if self.login_restante_var:
            self.login_restante_var.set("00:00:00")
        if self.disparo_alvo_var:
            self.disparo_alvo_var.set("")
        if self.disparo_restante_var:
            self.disparo_restante_var.set("00:00:00")
        if self.agendamento_status_var:
            self.agendamento_status_var.set("Parado")

        if self.agendamento_after_id and self.ui_root and self.ui_root.winfo_exists():
            try:
                self.ui_root.after_cancel(self.agendamento_after_id)
            except Exception:
                pass
        self.agendamento_after_id = None

    def resincronizar_agendamento(self):
        if not self.sincronizar_relogio_proeis():
            messagebox.showerror("Erro", "Não foi possível resincronizar com o servidor do PROEIS.")
            return

        agora = self.agora_servidor_sincronizado()
        if agora:
            self.agendamento_servidor_var.set(agora.strftime("%H:%M:%S.%f")[:-3])
            if self.melhor_latencia_servidor is not None:
                self.agendamento_status_var.set(
                    f"Resincronizado em {agora.strftime('%H:%M:%S')} | latência={self.melhor_latencia_servidor:.4f}s"
                )
            else:
                self.agendamento_status_var.set(f"Resincronizado em {agora.strftime('%H:%M:%S')}")

    def fechar_painel_duplo_agendamento(self):
        self.parar_agendamento()

        if self.janela_agendamento is not None:
            try:
                if self.janela_agendamento.winfo_exists():
                    self.janela_agendamento.destroy()
            except Exception:
                pass

        self.janela_agendamento = None
        self.frame_login = None
        self.frame_disparo = None

        self.retomar_automaticamente_apos_login = False
