import streamlit as st
import pandas as pd
import time
import os
import asyncio
import edge_tts
from pybit.unified_trading import HTTP
from google import genai
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA (Sempre a primeira coisa) ---
st.set_page_config(page_title="Trader AI 2.5", page_icon="📈", layout="wide")

# --- 2. INICIALIZAÇÃO DE ESTADO (Secrets e Variáveis) ---
if "rodando" not in st.session_state:
    st.session_state.rodando = False

# Carregar Chaves (Prioridade para Secrets do Streamlit Cloud)
try:
    # Tenta ler do Streamlit Cloud Secrets primeiro
    API_GEMINI = st.secrets["GEMINI_API_KEY"]
    API_BYBIT = st.secrets["BYBIT_API_KEY"]
    SECRET_BYBIT = st.secrets["BYBIT_API_SECRET"]
except Exception:
    st.error("⚠️ Erro: Chaves de API não configuradas nos Secrets do Streamlit!")
    st.stop()

# --- 3. FUNÇÕES TÉCNICAS ---
async def gerar_audio_async(texto):
    comunicador = edge_tts.Communicate(texto, "pt-BR-FranciscaNeural")
    await comunicador.save("alerta.mp3")

def get_data(symbol, session):
    try:
        t = session.get_tickers(category="linear", symbol=symbol)
        p = float(t['result']['list'][0]['lastPrice'])
        k = session.get_kline(category="linear", symbol=symbol, interval="60", limit=30)
        c = [float(x[4]) for x in k['result']['list']]; c.reverse()
        df = pd.DataFrame(c, columns=['c']); d = df['c'].diff()
        g = d.where(d>0,0).rolling(14).mean(); l = -d.where(d<0,0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (g/l))).iloc[-1]
        return p, rsi
    except: return None, None

# --- 4. INTERFACE VISUAL (Desenhada ANTES de qualquer loop) ---
st.title("🤖 Terminal Trader AI - Gemini 2.5")

# Barra Lateral
with st.sidebar:
    st.header("⚙️ Painel de Controlo")
    moeda = st.selectbox("Escolha a Moeda", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"])
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🟢 INICIAR", use_container_width=True):
            st.session_state.rodando = True
    with col_btn2:
        if st.button("🔴 PARAR", use_container_width=True):
            st.session_state.rodando = False

# Área de Exibição (Métricas)
col1, col2 = st.columns(2)
metric_btc = col1.empty()
metric_alvo = col2.empty()

st.markdown("---")
st.subheader("🧠 Análise em Tempo Real")
area_texto = st.empty()
area_audio = st.empty()

# --- 5. LÓGICA DE EXECUÇÃO ---
if st.session_state.rodando:
    # Inicializa as APIs
    client_ia = genai.Client(api_key=API_GEMINI)
    session_bybit = HTTP(testnet=False, api_key=API_BYBIT, api_secret=SECRET_BYBIT)

    # LOOP DO ROBÔ
    while st.session_state.rodando:
        with st.spinner(f"A analisar {moeda}..."):
            # Pegar Dados
            bp, br = get_data("BTCUSDT", session_bybit)
            mp, mr = get_data(moeda, session_bybit)

            if bp and mp:
                # Atualizar Visual
                metric_btc.metric("Bitcoin (BTC)", f"${bp:,.2f}", f"RSI: {br:.0f}")
                metric_alvo.metric(f"Alvo ({moeda})", f"${mp:,.4f}", f"RSI: {mr:.0f}")

                # Consultar IA (Gemini 2.5)
                prompt = f"Analise {moeda} (${mp}, RSI {mr:.0f}) com BTC (${bp}, RSI {br:.0f}). Responda curto: Veredito e Motivo."
                try:
                    resp = client_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    texto_ia = resp.text
                    area_texto.success(f"[{datetime.now().strftime('%H:%M:%S')}] {texto_ia}")

                    # Áudio Neural
                    asyncio.run(gerar_audio_async(texto_ia.replace("*", "")))
                    with open("alerta.mp3", "rb") as f:
                        area_audio.audio(f.read(), format="audio/mp3", autoplay=True)
                except Exception as e:
                    st.error(f"Erro na IA: {e}")

            # Contagem Regressiva Visual (5 Minutos)
            tempo_espera = 300
            placeholder_timer = st.empty()
            for i in range(tempo_espera, 0, -1):
                if not st.session_state.rodando: break
                mins, segs = divmod(i, 60)
                placeholder_timer.caption(f"⏱️ Próxima atualização em {mins:02d}:{segs:02d}")
                time.sleep(1)
            placeholder_timer.empty()
else:
    st.info("O robô está parado. Use o painel lateral para iniciar.")
