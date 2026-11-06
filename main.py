from kivy.config import Config
Config.set('graphics', 'multisamples', '0')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
import random
import math
import json
import os
import time
import urllib.request
import urllib.parse
import webbrowser
import threading
from collections import Counter
from itertools import combinations

Window.clearcolor = (0.08, 0.08, 0.08, 1)
CRIADOR = "Gleidson José Angelo da Silva"

MODALIDADES = {
    "MEGA-SENA": ("megasena", 60, 6),
    "MEGA DA VIRADA": ("megasena", 60, 6),
    "QUINA": ("quina", 80, 5),
    "LOTOFACIL": ("lotofacil", 25, 15)
}
API_BASE = "https://servicebus2.caixa.gov.br/portaldeloterias/api/"

def consultar(api, concurso=None):
    url = API_BASE + api
    if concurso is not None:
        url += "/" + str(concurso)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    return {"concurso": int(d["numero"]), "data": d.get("dataApuracao", ""), "dezenas": sorted(int(x) for x in d["listaDezenas"])}

def baixar_historico(api):
    try:
        ultimo = consultar(api)
        mapa = {ultimo["concurso"]: ultimo}
        inicio = max(1, ultimo["concurso"] - 99)
        for numero in range(inicio, ultimo["concurso"] + 1):
            if numero not in mapa:
                try:
                    mapa[numero] = consultar(api, numero)
                except Exception:
                    continue
        return sorted(mapa.values(), key=lambda x: x["concurso"])
    except Exception:
        return []

def analisar(historico, n, k):
    posicoes = [[0] * (n + 1) for _ in range(k)]
    frequencia = Counter()
    pares = Counter()
    trincas = Counter()
    qtd_seguidos_hist = Counter()
    concursos = []

    for item in historico:
        dezenas = sorted(item["dezenas"])
        if len(dezenas) != k or len(set(dezenas)) != k or min(dezenas) < 1 or max(dezenas) > n:
            continue
        concursos.append(dezenas)
        frequencia.update(dezenas)
        seguidos = sum(dezenas[i+1] - dezenas[i] == 1 for i in range(len(dezenas)-1))
        qtd_seguidos_hist[seguidos] += 1
        for p, x in enumerate(dezenas):
            posicoes[p][x] += 1
        pares.update(combinations(dezenas, 2))
        if k >= 3: trincas.update(combinations(dezenas, 3))

    moda_seguidos = qtd_seguidos_hist.most_common(1)[0][0] if qtd_seguidos_hist else 1
    return {"posicoes": posicoes, "frequencia": frequencia, "pares": pares, "trincas": trincas, "moda_seguidos": moda_seguidos}

def avaliar_equilibrio(jogo, n, k):
    pares = sum(x % 2 == 0 for x in jogo)
    impares = k - pares
    baixos = sum(x <= n / 3 for x in jogo)
    medios = sum(n / 3 < x <= 2 * n / 3 for x in jogo)
    altos = k - baixos - medios
    soma = sum(jogo)
    media = k * (n + 1) / 2
    variancia = k * (n - k) * (n + 1) / 12
    desvio = math.sqrt(variancia) if variancia > 0 else 0
    z = (soma - media) / desvio if desvio else 0
    consecutivos = sum(jogo[i + 1] - jogo[i] == 1 for i in range(k - 1))
    pontos = 100
    if abs(pares - impares) > 2: pontos -= 12
    ideal = k / 3
    desequilibrio = abs(baixos - ideal) + abs(medios - ideal) + abs(altos - ideal)
    pontos -= min(20, desequilibrio * 2)
    if abs(z) > 2: pontos -= 15
    if abs(z) > 3: pontos -= 10
    if consecutivos >= max(3, k // 3): pontos -= 10
    return max(0, round(pontos, 1))

def pontuar_historico(jogo, stats, n):
    valores = [stats["frequencia"].get(x, 0) for x in range(1, n + 1)]
    if not valores: return 0
    media = sum(valores) / len(valores)
    variancia = sum((x - media) ** 2 for x in valores) / len(valores)
    desvio = math.sqrt(variancia) if variancia > 0 else 0
    if desvio == 0: return 0
    notas = [max(-2, min(2, (stats["frequencia"].get(x, 0) - media) / desvio)) for x in jogo]
    return sum(notas) / len(notas)

def pontuar_combinacoes(jogo, stats):
    pares_vals = [math.log1p(stats["pares"].get(p, 0)) for p in combinations(jogo, 2)]
    nota_pares = sum(pares_vals) / len(pares_vals) if pares_vals else 0
    trincas_vals = [math.log1p(stats["trincas"].get(t, 0)) for t in combinations(jogo, 3)] if len(jogo) >= 3 else []
    nota_trincas = sum(trincas_vals) / len(trincas_vals) if trincas_vals else 0
    return float(nota_pares * 0.15 + nota_trincas * 0.05)

def avaliar(jogo, stats, n, k):
    return avaliar_equilibrio(jogo, n, k) + pontuar_historico(jogo, stats, n) * 2 + pontuar_combinacoes(jogo, stats)

def gerar_jogos_matematicos(stats, n, k, qtd_desejada):
    candidatos_para_gerar = 3000 if k > 10 or qtd_desejada > 10 else 20000
    candidatos = {}
    for _ in range(candidatos_para_gerar):
        jogo = sorted(random.sample(range(1, n + 1), k))
        chave = tuple(jogo)
        if chave not in candidatos:
            candidatos[chave] = avaliar(jogo, stats, n, k)
    ranking = sorted(candidatos.items(), key=lambda x: x[1], reverse=True)
    jogos = []
    ocorrencias = Counter()
    limite = max(1, int(k * 0.70))
    limite_numero = math.ceil(qtd_desejada * k / n) + 1
    for chave, nota in ranking:
        jogo = list(chave)
        if any(len(set(jogo) & set(outro)) > limite for outro in jogos): continue
        if any(ocorrencias[x] >= limite_numero for x in jogo): continue
        jogos.append(jogo)
        ocorrencias.update(jogo)
        if len(jogos) == qtd_desejada: break
    while len(jogos) < qtd_desejada:
        jogo = sorted(random.sample(range(1, n + 1), k))
        if jogo not in jogos: jogos.append(jogo)
    return jogos

def gerar_sequencias_matematicas(n, k, stats, qtd_desejada):
    jogos = []
    moda = stats["moda_seguidos"]
    if moda * 2 > k: moda = k // 2
    while len(jogos) < qtd_desejada:
        jogo = []
        for _ in range(moda):
            inicio = random.randint(1, n - 1)
            if inicio not in jogo and (inicio + 1) not in jogo:
                jogo.append(inicio); jogo.append(inicio + 1)
        while len(jogo) < k:
            num = random.randint(1, n)
            if num not in jogo: jogo.append(num)
        jogo = sorted(jogo)
        if len(jogo) == k and jogo not in jogos: jogos.append(jogo)
    return jogos

class TelaPrincipal(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.modalidade_atual = "MEGA-SENA"
        self.texto_jogos_atual = ""
        self.criar_layout()

    def criar_layout(self):
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        topo = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40))
        topo.add_widget(Label(text="[b][color=00E676]MILIONÁRIO DA VEZ[/color][/b]", markup=True, font_size=dp(20), size_hint_x=1))
        layout.add_widget(topo)
        
        layout.add_widget(Label(text="Selecione a Loteria:", size_hint_y=None, height=dp(20), font_size=dp(14)))
        loterias = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(5))
        
        self.btn_mega = Button(text="MEGA", bold=True, background_normal='', background_color=(0, 0.6, 0.3, 1))
        self.btn_mega.bind(on_press=lambda x: self.set_modalidade("MEGA-SENA", self.btn_mega))
        self.btn_virada = Button(text="VIRADA", bold=True, background_normal='', background_color=(0.3, 0.3, 0.3, 1))
        self.btn_virada.bind(on_press=lambda x: self.set_modalidade("MEGA DA VIRADA", self.btn_virada))
        self.btn_quina = Button(text="QUINA", bold=True, background_normal='', background_color=(0.3, 0.3, 0.3, 1))
        self.btn_quina.bind(on_press=lambda x: self.set_modalidade("QUINA", self.btn_quina))
        self.btn_loto = Button(text="LOTO", bold=True, background_normal='', background_color=(0.3, 0.3, 0.3, 1))
        self.btn_loto.bind(on_press=lambda x: self.set_modalidade("LOTOFACIL", self.btn_loto))
        
        loterias.add_widget(self.btn_mega); loterias.add_widget(self.btn_virada); loterias.add_widget(self.btn_quina); loterias.add_widget(self.btn_loto)
        layout.add_widget(loterias)

        self.qtd_input = TextInput(text="5", multiline=False, input_filter="int", size_hint_y=None, height=dp(45), background_normal='', background_color=(0.2, 0.2, 0.2, 1), foreground_color=(1, 1, 1, 1), font_size=dp(16), hint_text="Quantos jogos? (Max: 50)")
        layout.add_widget(self.qtd_input)
        
        self.concurso_input = TextInput(text="", multiline=False, input_filter="int", size_hint_y=None, height=dp(45), background_normal='', background_color=(0.2, 0.2, 0.2, 1), foreground_color=(1, 1, 1, 1), font_size=dp(16), hint_text="Concurso Específico (Opcional)")
        layout.add_widget(self.concurso_input)
        
        layout.add_widget(Label(text="[b][color=00E676]COMBINAÇÕES ESTATÍSTICAS[/color][/b]", markup=True, size_hint_y=None, height=dp(25), font_size=dp(14)))
        
        btns = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50), spacing=dp(10))
        self.btn_normal = Button(text="JOGOS NORMAIS", bold=True, background_normal='', background_color=(0, 0.7, 0.4, 1))
        self.btn_normal.bind(on_press=lambda x: self.iniciar_geracao(False))
        btns.add_widget(self.btn_normal)
        
        self.btn_sequencia = Button(text="SEQUÊNCIAS", bold=True, background_normal='', background_color=(1, 0.5, 0, 1))
        self.btn_sequencia.bind(on_press=lambda x: self.iniciar_geracao(True))
        btns.add_widget(self.btn_sequencia)
        layout.add_widget(btns)
        
        self.btn_zap = Button(text="ENVIAR PARA O WHATSAPP", size_hint_y=None, height=dp(45), background_normal='', background_color=(0.1, 0.6, 0.2, 1), bold=True)
        self.btn_zap.bind(on_press=self.enviar_whatsapp)
        layout.add_widget(self.btn_zap)
        
        self.scroll = ScrollView(size_hint=(1, 1))
        self.resultado_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(10))
        self.resultado_layout.bind(minimum_height=self.resultado_layout.setter('height'))
        self.status_label = Label(text="Escolha a loteria e clique em gerar.", halign='center', valign='top', font_size=dp(16), color=(0.9, 0.9, 0.9, 1), size_hint_y=None, height=dp(40))
        self.resultado_layout.add_widget(self.status_label)
        self.scroll.add_widget(self.resultado_layout)
        layout.add_widget(self.scroll)
        layout.add_widget(Label(text=f"Criado por: {CRIADOR}", halign='center', color=(0.5, 0.5, 0.5, 1), size_hint_y=None, height=dp(20), font_size=dp(12)))
        self.add_widget(layout)

    def set_modalidade(self, nome, botao_clicado):
        self.modalidade_atual = nome
        for btn in [self.btn_mega, self.btn_virada, self.btn_quina, self.btn_loto]:
            btn.background_color = (0.3, 0.3, 0.3, 1)
        botao_clicado.background_color = (0, 0.6, 0.3, 1)

    def iniciar_geracao(self, is_sequencia):
        try:
            qtd = int(self.qtd_input.text)
            if qtd <= 0: qtd = 1
            if qtd > 50: qtd = 50
        except ValueError:
            self.status_label.text = "Digite um número válido."
            return
        concurso_alvo = self.concurso_input.text.strip()
        self.btn_normal.disabled = True
        self.btn_sequencia.disabled = True
        self.resultado_layout.clear_widgets()
        self.status_label = Label(text=f"Analisando {self.modalidade_atual}...\n\nAguarde...", halign='center', font_size=dp(16), color=(1, 1, 0, 1), size_hint_y=None, height=dp(60))
        self.resultado_layout.add_widget(self.status_label)
        threading.Thread(target=self.processar, args=(qtd, is_sequencia, self.modalidade_atual, concurso_alvo)).start()

    def processar(self, qtd, is_sequencia, modalidade, concurso_alvo):
        api, n, k = MODALIDADES[modalidade]
        historico = baixar_historico(api)
        if not historico:
            Clock.schedule_once(lambda dt: self.erro("Erro de conexão. Verifique sua internet."))
            return
        stats = analisar(historico, n, k)
        if is_sequencia:
            jogos = gerar_sequencias_matematicas(n, k, stats, qtd)
            cor = "ff9800"
        else:
            jogos = gerar_jogos_matematicos(stats, n, k, qtd)
            cor = "00E676"
        texto = ""
        for i, jogo in enumerate(jogos, 1):
            texto += f"Jogo {i}: {' - '.join(f'{x:02d}' for x in jogo)}\n"
        self.texto_jogos_atual = f"*Jogos do Milionário da Vez*\n\n" + texto
        Clock.schedule_once(lambda dt: self.desenhar(jogos, cor))

    def desenhar(self, jogos, cor):
        self.resultado_layout.clear_widgets()
        for i, jogo in enumerate(jogos, 1):
            texto = f"[b]Jogo {i}:[/b]  "
            for num in jogo:
                texto += f"[b][color={cor}]{num:02d}[/color][/b]  "
            self.resultado_layout.add_widget(Label(text=texto, markup=True, size_hint_y=None, height=dp(30), font_size=dp(18), halign='center'))
        self.btn_normal.disabled = False
        self.btn_sequencia.disabled = False

    def erro(self, texto):
        self.resultado_layout.clear_widgets()
        self.status_label = Label(text=f"[color=ff0000]{texto}[/color]", markup=True, halign='center', font_size=dp(16), size_hint_y=None, height=dp(60))
        self.resultado_layout.add_widget(self.status_label)
        self.btn_normal.disabled = False
        self.btn_sequencia.disabled = False

    def enviar_whatsapp(self, instance):
        if self.texto_jogos_atual:
            try:
                webbrowser.open(f"whatsapp://send?text={urllib.parse.quote(self.texto_jogos_atual)}")
            except Exception:
                pass

class MilionarioApp(App):
    def build(self):
        self.title = "Milionário da Vez"
        sm = ScreenManager()
        sm.add_widget(TelaPrincipal(name='tela_principal'))
        return sm

if __name__ == '__main__':
    MilionarioApp().run()
