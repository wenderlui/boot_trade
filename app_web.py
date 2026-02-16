import streamlit as st
import pandas as pd
import time
import os
import asyncio
import edge_tts
from pybit.unified_trading import HTTP
from google import genai
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Terminal IA 2.5 Pro", page_icon="⚡", layout="wide")

# --- INICIALIZAÇÃO DE ESTADO ---
if "rodando" not in st.session_state:
    st.session_state.rodando = False

# Tenta carregar as chaves dos Secrets do Streamlit
try:
    API_GEMINI = st.secrets["GEMINI_API_KEY"]
    API_BYBIT = st.secrets["BYBIT_API_KEY"]
    SECRET_BYBIT = st.secrets["BYBIT_API_SECRET"]
except Exception:
    st.error("⚠️ Configura as chaves de API nos 'Secrets' do Streamlit Cloud!")
    st.stop()

# --- FUNÇÕES TÉCNICAS ---
async def gerar_audio_async(texto):
    """Gera o áudio neural"""
    caminho = "alerta.mp3"
    comunicador = edge_tts.Communicate(texto, "pt-BR-FranciscaNeural")
    await comunicador.save(caminho)

def get_data(symbol, session):
    """Busca Preço e RSI"""
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

def get_order_book(symbol, session):
    """Analisa pressão do Book"""
    try:
        book = session.get_orderbook(category="linear", symbol=symbol, limit=20)
        v_c = sum([float(x[1]) for x in book['result']['b']])
        v_v = sum([float(x[1]) for x in book['result']['a']])
        ratio = v_c / v_v if v_v > 0 else 1.0
        status = "Compra Forte" if ratio > 1.3 else "Venda Forte" if ratio < 0.7 else "Neutro"
        return f"{status} (C: {v_c:.1f} | V: {v_v:.1f})"
    except: return "Book Indisponível"

# --- INTERFACE ---
st.title("🚀 Terminal Trader IA 2.5 - Web Edition")

with st.sidebar:
    st.header("⚙️ Configurações")
    moeda = st.selectbox("Moeda Alvo", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "SUIUSDT"])
    
    # OPÇÃO DE TEMPO (O que pediste)
    tempo_analise = st.slider("Intervalo de Análise (Minutos)", min_value=1, max_value=60, value=5)
    
    st.markdown("---")
    if st.button("🟢 INICIAR ROBÔ", use_container_width=True):
        st.session_state.rodando = True
    if st.button("🔴 PARAR ROBÔ", use_container_width=True):
        st.session_state.rodando = False
        st.rerun()

# Espaços reservados para os dados (evita que a página "pule")
col1, col2, col3 = st.columns(3)
m_btc = col1.empty()
m_alvo = col2.empty()
m_book = col3.empty()

st.subheader("📝 Relatório da Inteligência Artificial")
txt_ia = st.empty()
aud_ia = st.empty()
progresso_espera = st.empty()

# --- LÓGICA PRINCIPAL ---
if st.session_state.rodando:
    client_ia = genai.Client(api_key=API_GEMINI)
    session_bybit = HTTP(testnet=False, api_key=API_BYBIT, api_secret=SECRET_BYBIT)

    while st.session_state.rodando:
        # 1. ANALISA IMEDIATAMENTE
        with st.spinner("📡 A capturar dados do mercado..."):
            bp, br = get_data("BTCUSDT", session_bybit)
            mp, mr = get_data(moeda, session_bybit)
            book = get_order_book(moeda, session_bybit)

            if bp and mp:
                m_btc.metric("Bitcoin (BTC)", f"${bp:,.2f}", f"RSI: {br:.0f}")
                m_alvo.metric(f"Alvo ({moeda})", f"${mp:,.4f}", f"RSI: {mr:.0f}")
                m_book.info(f"📊 {book}")

                # Consulta Gemini 2.5
                prompt = f"Analise {moeda} (${mp}, RSI {mr:.0f}) com BTC (${bp}, RSI {br:.0f}) e Book {book}. Veredito curto em 1 frase."
                try:
                    resp = client_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    analise = resp.text
                    txt_ia.success(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] {analise}")

                    # Áudio
                    asyncio.run(gerar_audio_async(analise.replace("*", "")))
                    with open("alerta.mp3", "rb") as f:
                        aud_ia.audio(f.read(), format="audio/mp3", autoplay=True)
                except Exception as e:
                    st.error(f"Erro na IA: {e}")

        # 2. ESPERA PELO PRÓXIMO CICLO (Com contagem visual)
        total_segundos = tempo_analise * 60
        for i in range(total_segundos, 0, -1):
            if not st.session_state.rodando: break
            
            minutos, segundos = divmod(i, 60)
            progresso_espera.write(f"⏱️ Próxima análise em: **{minutos:02d}:{segundos:02d}**")
            time.sleep(1)
        
        progresso_espera.empty()

else:
    st.warning("💤 O robô está desligado. Configura e clica em 'Iniciar' no menu lateral.")
