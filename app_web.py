import streamlit as st
import pandas as pd
import time
import os
import asyncio
import edge_tts
from pybit.unified_trading import HTTP
from google import genai
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Terminal IA 2.5", page_icon="⚡", layout="wide")

# Inicialização do estado
if "rodando" not in st.session_state:
    st.session_state.rodando = False

# Carregamento de Secrets
try:
    API_GEMINI = st.secrets["GEMINI_API_KEY"]
    API_BYBIT = st.secrets["BYBIT_API_KEY"]
    SECRET_BYBIT = st.secrets["BYBIT_API_SECRET"]
except Exception:
    st.error("⚠️ Erro: Configure as chaves nos Secrets do Streamlit!")
    st.stop()

# --- 2. FUNÇÕES ---
async def gerar_audio_async(texto):
    caminho = "alerta.mp3"
    comunicador = edge_tts.Communicate(texto, "pt-BR-FranciscaNeural")
    await comunicador.save(caminho)

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

def get_book(symbol, session):
    try:
        book = session.get_orderbook(category="linear", symbol=symbol, limit=20)
        v_c = sum([float(x[1]) for x in book['result']['b']])
        v_v = sum([float(x[1]) for x in book['result']['a']])
        ratio = v_c / v_v if v_v > 0 else 1.0
        status = "Compra Forte" if ratio > 1.3 else "Venda Forte" if ratio < 0.7 else "Neutro"
        return f"{status} (C: {v_c:.1f} | V: {v_v:.1f})"
    except: return "Book Indisponível"

# --- 3. INTERFACE ---
st.title("🚀 Terminal Trader IA 2.5")

with st.sidebar:
    st.header("⚙️ Painel de Controle")
    moeda = st.selectbox("Moeda Alvo", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "SUIUSDT"])
    tempo_analise = st.slider("Intervalo de Análise (Minutos)", 1, 60, 5)
    
    st.markdown("---")
    if st.button("🟢 INICIAR ROBÔ", use_container_width=True):
        st.session_state.rodando = True
        st.rerun() # Força o reinício para entrar no IF imediatamente
    
    if st.button("🔴 PARAR ROBÔ", use_container_width=True):
        st.session_state.rodando = False
        st.rerun()

# --- 4. EXECUÇÃO ---
if st.session_state.rodando:
    # Quando o robô está ligado, o aviso de "desligado" NÃO aparece
    placeholder_status = st.empty()
    placeholder_status.success(f"📡 Robô Ativo: Monitorando {moeda}")

    col1, col2, col3 = st.columns(3)
    m_btc = col1.empty()
    m_alvo = col2.empty()
    m_book = col3.empty()

    st.subheader("📝 Relatório da Inteligência Artificial")
    txt_ia = st.empty()
    aud_ia = st.empty()
    timer_ia = st.empty()

    client_ia = genai.Client(api_key=API_GEMINI)
    session_bybit = HTTP(testnet=False, api_key=API_BYBIT, api_secret=SECRET_BYBIT)

    while st.session_state.rodando:
        # AÇÃO IMEDIATA
        with st.status(f"Analisando {moeda} agora...", expanded=True) as status:
            bp, br = get_data("BTCUSDT", session_bybit)
            mp, mr = get_data(moeda, session_bybit)
            book_info = get_book(moeda, session_bybit)

            if bp and mp:
                m_btc.metric("Bitcoin (BTC)", f"${bp:,.2f}", f"RSI: {br:.0f}")
                m_alvo.metric(f"Alvo ({moeda})", f"${mp:,.4f}", f"RSI: {mr:.0f}")
                m_book.info(f"📊 {book_info}")

                prompt = f"Analise {moeda} (${mp}, RSI {mr:.0f}) com BTC (${bp}, RSI {br:.0f}) e Book {book_info}. Veredito curto em 1 frase."
                try:
                    resp = client_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    analise = resp.text
                    txt_ia.info(f"🤖 [{datetime.now().strftime('%H:%M:%S')}] {analise}")

                    # Áudio Neural
                    asyncio.run(gerar_audio_async(analise.replace("*", "")))
                    with open("alerta.mp3", "rb") as f:
                        aud_ia.audio(f.read(), format="audio/mp3", autoplay=True)
                except Exception as e:
                    st.error(f"Erro IA: {e}")
            
            status.update(label="Análise completa!", state="complete", expanded=False)

        # CONTAGEM REGRESSIVA
        total_segundos = tempo_analise * 60
        for i in range(total_segundos, 0, -1):
            if not st.session_state.rodando: 
                break
            mins, segs = divmod(i,
