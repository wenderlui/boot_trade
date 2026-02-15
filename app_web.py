import streamlit as st
import pandas as pd
import time
import os
import asyncio
import edge_tts
from pybit.unified_trading import HTTP
from google import genai
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="🤖 Trader AI Web",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CARREGA CHAVES ---
# No seu PC local usa .env, na nuvem usa st.secrets
load_dotenv()
try:
    API_GEMINI = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    API_BYBIT = os.getenv("BYBIT_API_KEY") or st.secrets["BYBIT_API_KEY"]
    SECRET_BYBIT = os.getenv("BYBIT_API_SECRET") or st.secrets["BYBIT_API_SECRET"]
except:
    st.error("❌ Chaves de API não encontradas. Configure o .env ou st.secrets")
    st.stop()

# --- FUNÇÕES ---
async def gerar_audio_async(texto):
    """Gera o arquivo de áudio MP3"""
    comunicador = edge_tts.Communicate(texto, "pt-BR-FranciscaNeural")
    await comunicador.save("alerta.mp3")

def get_market_data(symbol, session):
    try:
        # Preço
        t = session.get_tickers(category="linear", symbol=symbol)
        price = float(t['result']['list'][0]['lastPrice'])
        
        # RSI
        k = session.get_kline(category="linear", symbol=symbol, interval="60", limit=30)
        closes = [float(x[4]) for x in k['result']['list']]; closes.reverse()
        df = pd.DataFrame(closes, columns=['c']); delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        return price, rsi
    except:
        return None, None

def get_order_book(symbol, session):
    try:
        book = session.get_orderbook(category="linear", symbol=symbol, limit=20)
        vol_buy = sum([float(x[1]) for x in book['result']['b']])
        vol_sell = sum([float(x[1]) for x in book['result']['a']])
        ratio = vol_buy / vol_sell if vol_sell > 0 else 1.0
        status = "Compra Forte" if ratio > 1.3 else "Venda Forte" if ratio < 0.7 else "Neutro"
        return f"{status} (C:{vol_buy:.0f} vs V:{vol_sell:.0f})"
    except:
        return "Indisponível"

def consultar_ia(client, btc, alvo, book, symbol):
    prompt = f"""
    Atue como analista crypto.
    BTC: ${btc[0]} (RSI {btc[1]:.0f})
    {symbol}: ${alvo[0]} (RSI {alvo[1]:.0f})
    Book: {book}
    Responda curto para leitura em voz alta: Veredito (COMPRA/VENDA/AGUARDAR) e Motivo.
    """
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return response.text
    except Exception as e:
        return f"Erro IA: {e}"

# --- INTERFACE VISUAL (FRONTEND) ---
st.title("🤖 Terminal de Trading IA 3.0")
st.markdown("---")

# Barra Lateral
with st.sidebar:
    st.header("⚙️ Configurações")
    moeda = st.selectbox("Moeda Alvo", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "WIFUSDT"])
    rsi_compra = st.number_input("RSI Compra <", value=30)
    rsi_venda = st.number_input("RSI Venda >", value=70)
    tempo_atualizacao = st.slider("Atualizar a cada (min)", 1, 10, 5)
    
    if st.button("🔴 PARAR ROBÔ"):
        st.session_state.rodando = False
        st.rerun()

    if st.button("🟢 INICIAR ROBÔ"):
        st.session_state.rodando = True

# Inicialização de Clientes
if 'client_ia' not in st.session_state:
    st.session_state.client_ia = genai.Client(api_key=API_GEMINI)
    st.session_state.session_bybit = HTTP(testnet=False, api_key=API_BYBIT, api_secret=SECRET_BYBIT)

# Layout Principal
col1, col2, col3 = st.columns(3)
with col1:
    metric_btc = st.empty()
with col2:
    metric_alvo = st.empty()
with col3:
    metric_book = st.empty()

st.subheader("🧠 Cérebro da IA")
area_texto = st.empty()
area_audio = st.empty()

# --- LÓGICA DE LOOP ---
if "rodando" not in st.session_state:
    st.session_state.rodando = False

if st.session_state.rodando:
    with st.spinner(f"Monitorando {moeda}..."):
        while st.session_state.rodando:
            # 1. Dados
            btc_p, btc_r = get_market_data("BTCUSDT", st.session_state.session_bybit)
            alvo_p, alvo_r = get_market_data(moeda, st.session_state.session_bybit)
            book_info = get_order_book(moeda, st.session_state.session_bybit)

            if btc_p and alvo_p:
                # 2. Atualiza Métricas
                timestamp = datetime.now().strftime("%H:%M:%S")
                metric_btc.metric("Bitcoin (BTC)", f"${btc_p:,.2f}", f"RSI: {btc_r:.0f}")
                metric_alvo.metric(f"Alvo ({moeda})", f"${alvo_p:,.4f}", f"RSI: {alvo_r:.0f}")
                metric_book.info(f"Book: {book_info}")

                # 3. Consulta IA
                analise = consultar_ia(st.session_state.client_ia, (btc_p, btc_r), (alvo_p, alvo_r), book_info, moeda)
                
                # 4. Exibe Texto
                area_texto.info(f"[{timestamp}] {analise}")

                # 5. Gera Áudio e Toca
                asyncio.run(gerar_audio_async(analise.replace("*", "")))
                
                # Truque para recarregar o player de áudio
                with open("alerta.mp3", "rb") as f:
                    audio_bytes = f.read()
                    area_audio.audio(audio_bytes, format="audio/mp3", autoplay=True)

            # 6. Espera (Timer Visual)
            barra_progresso = st.progress(0)
            segundos = tempo_atualizacao * 60
            for i in range(segundos):
                if not st.session_state.rodando: break
                time.sleep(1)
                barra_progresso.progress((i + 1) / segundos)
            
            barra_progresso.empty()
            
            # Se parou, sai do loop
            if not st.session_state.rodando:
                st.warning("Robô Parado.")
                break
else:
    st.info("Clique em INICIAR na barra lateral.")