import streamlit as st
import pandas as pd
import ccxt
import time
import os
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Carrega chaves (Secrets do Streamlit)
load_dotenv()

st.set_page_config(page_title="Pocket Play CLOUD", page_icon="💎", layout="wide")

# --- CSS PARA CENTRALIZAR E AJUSTAR O LAYOUT ---
st.markdown("""
<style>
    /* Fundo Escuro Profundo */
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    
    /* Centralizar o conteúdo e descer do topo */
    .block-container {
        max-width: 1200px;      /* Largura máxima para não esticar demais */
        padding-top: 4rem;      /* Empurra para baixo (centro da tela) */
        padding-bottom: 4rem;
        margin: auto;           /* Centraliza horizontalmente */
    }
    
    /* Estilo dos Cards */
    div[data-testid="stMetricValue"] { font-size: 22px; color: #00ff00; }
    div[data-testid="stMarkdownContainer"] p { font-size: 16px; }
    
    /* Botões */
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        background-color: #262730;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURAÇÃO DE ESTADO (MEMÓRIA) ---
if "last_ai_run" not in st.session_state:
    st.session_state.last_ai_run = 0
if "ai_result" not in st.session_state:
    st.session_state.ai_result = "Iniciando sistema..."
if "ai_model_used" not in st.session_state:
    st.session_state.ai_model_used = "..."

# --- MAPEAMENTO DE DADOS (PROXY KRAKEN) ---
def get_exchange_data():
    return ccxt.kraken()

SYMBOL_MAP = {
    "BTCUSDT": "BTC/USD",
    "ETHUSDT": "ETH/USD",
    "SOLUSDT": "SOL/USD",
    "XRPUSDT": "XRP/USD",
    "POLUSDT": "MATIC/USD"
}

# --- FUNÇÕES TÉCNICAS ---
def calcular_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def pegar_dados_ia(symbol_bybit):
    try:
        exchange = get_exchange_data()
        symbol = SYMBOL_MAP.get(symbol_bybit, "BTC/USD")
        candles = exchange.fetch_ohlcv(symbol, timeframe="15m", limit=50)
        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = calcular_rsi(df)
        return df
    except:
        return pd.DataFrame()

# --- IA COM ROTAÇÃO AUTOMÁTICA (FAILOVER) ---
def consultar_ia_inteligente(simbolo, preco, rsi):
    # Lista de modelos por ordem de preferência (do melhor para o mais rápido)
    modelos = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
    
    api_key = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)

    prompt = (
        f"Analise {simbolo}. Preço: ${preco} | RSI: {rsi:.1f}.\n"
        f"Regra: RSI > 70 (Sobrecompra), RSI < 30 (Sobrevenda).\n"
        f"Responda CURTO: 1. Veredito (COMPRA/VENDA/NEUTRO). 2. Motivo em 1 frase."
    )

    for modelo in modelos:
        try:
            # Tenta o modelo atual
            response = client.models.generate_content(model=modelo, contents=prompt)
            return response.text, modelo # Sucesso! Retorna o texto e o nome do modelo
        except Exception as e:
            # Se der erro (cota excedida), o loop continua para o próximo modelo
            continue
            
    return "⚠️ Erro: Todos os modelos ocupados. Tente em 1 min.", "Offline"

# --- WIDGET TRADINGVIEW ---
def mostrar_grafico_tv(symbol):
    html = f"""
    <div class="tradingview-widget-container" style="height:500px;width:100%">
      <div id="tradingview_chart" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "BYBIT:{symbol}",
        "interval": "15",
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_chart"
      }});
      </script>
    </div>
    """
    components.html(html, height=500)

# --- INTERFACE ---
with st.sidebar:
    st.title("🎛️ Configuração")
    simbolo = st.selectbox("Ativo", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
    
    st.divider()
    st.subheader("🤖 Controle da IA")
    # SLIDER DE TEMPO (Otimização de Cota)
    intervalo_minutos = st.slider("Atualizar IA a cada (minutos):", 1, 60, 5, help="Quanto maior o tempo, menos gasta sua cota gratuita.")
    intervalo_segundos = intervalo_minutos * 60
    
    st.divider()
    if st.button("🔄 Forçar Atualização"):
        st.session_state.last_ai_run = 0 # Zera o timer para forçar update
        st.rerun()

# --- LAYOUT PRINCIPAL ---
st.title(f"Pocket Play | {simbolo}")

col_grafico, col_dados = st.columns([2, 1]) # Proporção 66% / 33%

# Coluna 1: Gráfico
with col_grafico:
    st.caption("Visualização em Tempo Real (Bybit)")
    mostrar_grafico_tv(simbolo)

# Coluna 2: Inteligência e Dados
with col_dados:
    st.caption("Cérebro Artificial (Gemini)")
    
    # Lógica do Timer
    agora = time.time()
    tempo_passado = agora - st.session_state.last_ai_run
    
    # Container da IA
    ia_box = st.container(border=True)
    
    with ia_box:
        # Se passou o tempo OU é a primeira vez, roda a IA
        if tempo_passado > intervalo_segundos:
            df = pegar_dados_ia(simbolo)
            if not df.empty:
                last = df.iloc[-1]
                texto, modelo = consultar_ia_inteligente(simbolo, last['close'], last['rsi'])
                
                # Salva na memória
                st.session_state.ai_result = texto
                st.session_state.ai_model_used = modelo
                st.session_state.last_ai_run = agora
                tempo_restante = intervalo_segundos
        else:
            tempo_restante = int(intervalo_segundos - tempo_passado)

        # Exibe o resultado (seja novo ou da memória)
        st.subheader(f"🧠 {st.session_state.ai_model_used}")
        res = st.session_state.ai_result.replace("*", "")
        
        if "COMPRA" in res.upper():
            st.success(res, icon="🚀")
        elif "VENDA" in res.upper():
            st.error(res, icon="📉")
        else:
            st.info(res, icon="⚖️")
            
        st.progress((intervalo_segundos - tempo_restante) / intervalo_segundos)
        st.caption(f"Próxima análise em: {tempo_restante}s")

# Auto-Refresh suave para manter o relógio rodando
time.sleep(1) 
st.rerun()
