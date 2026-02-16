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
st.set_page_config(page_title="Terminal IA 2.5 (Debug)", page_icon="🛠️", layout="wide")

if "rodando" not in st.session_state:
    st.session_state.rodando = False

# --- 2. CARREGAMENTO DE CHAVES COM VERIFICAÇÃO ---
try:
    API_GEMINI = st.secrets["GEMINI_API_KEY"]
    API_BYBIT = st.secrets["BYBIT_API_KEY"]
    SECRET_BYBIT = st.secrets["BYBIT_API_SECRET"]
except Exception:
    st.error("❌ ERRO CRÍTICO: As chaves de API não foram encontradas nos Secrets!")
    st.stop()

# --- 3. FUNÇÕES (COM RELATÓRIO DE ERRO) ---
async def gerar_audio_async(texto):
    try:
        caminho = "alerta.mp3"
        comunicador = edge_tts.Communicate(texto, "pt-BR-FranciscaNeural")
        await comunicador.save(caminho)
    except Exception as e:
        st.warning(f"Erro ao gerar áudio: {e}")

def get_data(symbol, session):
    """Busca dados e MOSTRA O ERRO se falhar"""
    try:
        # Tenta pegar preço
        t = session.get_tickers(category="linear", symbol=symbol)
        if not t or 'result' not in t or not t['result']['list']:
            st.error(f"Erro Bybit: Retorno vazio para {symbol}. Verifique se a moeda existe.")
            return None, None
            
        p = float(t['result']['list'][0]['lastPrice'])
        
        # Tenta pegar RSI
        k = session.get_kline(category="linear", symbol=symbol, interval="60", limit=30)
        c = [float(x[4]) for x in k['result']['list']]; c.reverse()
        df = pd.DataFrame(c, columns=['c']); d = df['c'].diff()
        g = d.where(d>0,0).rolling(14).mean(); l = -d.where(d<0,0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (g/l))).iloc[-1]
        
        return p, rsi
    except Exception as e:
        # AQUI ESTÁ A CORREÇÃO: Mostra o erro na tela!
        st.error(f"Erro ao ler dados de {symbol}: {str(e)}")
        return None, None

def get_book(symbol, session):
    try:
        book = session.get_orderbook(category="linear", symbol=symbol, limit=20)
        v_c = sum([float(x[1]) for x in book['result']['b']])
        v_v = sum([float(x[1]) for x in book['result']['a']])
        ratio = v_c / v_v if v_v > 0 else 1.0
        status = "Compra Forte" if ratio > 1.3 else "Venda Forte" if ratio < 0.7 else "Neutro"
        return f"{status} (C: {v_c:.1f} | V: {v_v:.1f})"
    except Exception as e:
        return f"Erro Book: {str(e)}"

# --- 4. INTERFACE ---
st.title("🛠️ Terminal de Diagnóstico IA")

with st.sidebar:
    st.header("Painel")
    moeda = st.selectbox("Moeda", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"])
    tempo = st.slider("Minutos", 1, 60, 5)
    
    if st.button("🟢 INICIAR COM DIAGNÓSTICO", use_container_width=True):
        st.session_state.rodando = True
        st.rerun()
    
    if st.button("🔴 PARAR", use_container_width=True):
        st.session_state.rodando = False
        st.rerun()

# --- 5. EXECUÇÃO ---
if st.session_state.rodando:
    # Cria os placeholders
    col1, col2, col3 = st.columns(3)
    m_btc = col1.empty()
    m_alvo = col2.empty()
    m_book = col3.empty()
    
    st.markdown("---")
    txt_ia = st.empty()
    aud_ia = st.empty()
    timer_ia = st.empty()

    # Inicializa API com tratamento de erro
    try:
        session_bybit = HTTP(testnet=False, api_key=API_BYBIT, api_secret=SECRET_BYBIT)
        client_ia = genai.Client(api_key=API_GEMINI)
    except Exception as e:
        st.error(f"Erro ao conectar nas APIs: {e}")
        st.stop()

    while st.session_state.rodando:
        with st.status(f"Analisando {moeda}...", expanded=True) as status:
            
            # Busca dados e exibe erros se houver
            bp, br = get_data("BTCUSDT", session_bybit)
            mp, mr = get_data(moeda, session_bybit)
            book_info = get_book(moeda, session_bybit)

            # Só prossegue se tiver dados válidos
            if bp is not None and mp is not None:
                # Se chegou aqui, os dados existem!
                m_btc.metric("BTC", f"${bp:,.2f}", f"RSI: {br:.0f}")
                m_alvo.metric(moeda, f"${mp:,.4f}", f"RSI: {mr:.0f}")
                m_book.info(f"Book: {book_info}")

                # Consulta IA
                try:
                    prompt = f"Analise {moeda} (${mp}, RSI {mr:.0f}) com BTC (${bp}, RSI {br:.0f}). Veredito curto."
                    resp = client_ia.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    analise = resp.text
                    txt_ia.success(f"🤖 {analise}")
                    
                    asyncio.run(gerar_audio_async(analise.replace("*", "")))
                    with open("alerta.mp3", "rb") as f:
                        aud_ia.audio(f.read(), format="audio/mp3", autoplay=True)
                        
                except Exception as ia_error:
                    st.error(f"Erro na IA (Gemini): {ia_error}")
            
            else:
                st.warning("⚠️ Não foi possível obter dados. Veja o erro acima em vermelho.")

            status.update(label="Ciclo finalizado", state="complete", expanded=False)

        # Timer
        for i in range(tempo * 60, 0, -1):
            if not st.session_state.rodando: break
            mins, segs = divmod(i, 60)
            timer_ia.info(f"⏳ Próxima em: {mins:02d}:{segs:02d}")
            time.sleep(1)
            
        if not st.session_state.rodando: break

else:
    st.info("Clique em INICIAR para começar o diagnóstico.")
