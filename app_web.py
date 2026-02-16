import streamlit as st
import pandas as pd
import ccxt
import time
import os
import streamlit.components.v1 as components
from google import genai
from dotenv import load_dotenv

# Carrega chaves (Secrets do Streamlit)
load_dotenv()

st.set_page_config(page_title="Pocket Play CLOUD", page_icon="☁️", layout="wide")

# CSS Ajustado
st.markdown("""
<style>
    .stApp { background-color: #131722; color: #d1d4dc; }
    div[data-testid="stMetricValue"] { font-size: 18px; color: #00ff00; }
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURAÇÃO DA FONTE DE DADOS (PROXY) ---
# Usamos a Kraken ou Coinbase para a IA, pois elas funcionam nos servidores dos EUA
# O visual continua sendo BYBIT via Widget.
def get_exchange_data_source():
    return ccxt.kraken() # Kraken é permitida nos EUA (Streamlit Cloud)

# Mapeia símbolos da Bybit para a Kraken (para a IA ler)
SYMBOL_MAP = {
    "BTCUSDT": "BTC/USD", # Kraken usa USD real, mas o gráfico é quase idêntico
    "ETHUSDT": "ETH/USD",
    "SOLUSDT": "SOL/USD",
    "XRPUSDT": "XRP/USD",
    "POLUSDT": "MATIC/USD" # POL ainda é listado como MATIC em muitos lugares
}

# --- FUNÇÕES TÉCNICAS (RSI, MÁDIAS) ---
def calcular_indicadores(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema21'] = df['close'].ewm(span=21).mean()
    return df

def pegar_dados_ia(symbol_bybit, timeframe="15m"):
    try:
        exchange = get_exchange_data_source()
        symbol_kraken = SYMBOL_MAP.get(symbol_bybit, "BTC/USD")
        
        # Baixa velas (OHLCV)
        candles = exchange.fetch_ohlcv(symbol_kraken, timeframe=timeframe, limit=50)
        
        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        # Calcula indicadores
        df = calcular_indicadores(df)
        return df
    except Exception as e:
        # st.error(f"Erro Dados: {e}") # Comentado para não sujar a tela
        return pd.DataFrame()

# --- WIDGET TRADINGVIEW (VISUAL CLIENT-SIDE) ---
def mostrar_grafico_tv(symbol):
    # O Widget roda no navegador do usuário (Brasil), então acessa Bybit normal!
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "width": "100%",
        "height": 600,
        "symbol": "BYBIT:{symbol}",
        "interval": "15",
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_chart"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=600)

# --- IA GOOGLE GEMINI ---
def consultar_ia(simbolo, timeframe, preco, rsi):
    try:
        # Tenta pegar a chave dos Secrets (Nuvem) ou .env (Local)
        api_key = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
        client = genai.Client(api_key=api_key)
        
        prompt = (
            f"Você é um Trader IA Profissional. Analisando {simbolo} ({timeframe}).\n"
            f"Mercado Atual: ${preco} | RSI: {rsi:.1f}\n"
            f"Instrução: O RSI acima de 70 é sobrecompra (risco de queda), abaixo de 30 é sobrevenda (chance de alta).\n"
            f"Saída: Dê um veredito curto [COMPRA/VENDA/NEUTRO] e explique o porquê em 1 frase."
        )
        
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text
    except Exception as e:
        return "Aguardando conexão IA..."

# --- INTERFACE ---
with st.sidebar:
    st.header("Pocket Play Cloud ☁️")
    simbolo = st.selectbox("Ativo (Bybit)", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
    st.caption("Visual: Bybit | Dados IA: Kraken (Mirror)")
    
    st.divider()
    ligar = st.toggle("LIGAR SISTEMA", value=True)

col_grafico, col_ia = st.columns([3, 1])

# 1. Coluna Esquerda: O Gráfico (Roda no Cliente)
with col_grafico:
    mostrar_grafico_tv(simbolo)

# 2. Coluna Direita: A IA (Roda no Servidor)
with col_ia:
    st.subheader("🧠 Análise IA")
    painel_ia = st.empty()
    painel_dados = st.empty()

    if ligar:
        # Loop seguro para Streamlit Cloud (use st.empty para updates)
        # Nota: Streamlit Cloud mata loops infinitos longos. O ideal é usar o botão "Rerun"
        # Mas vamos tentar uma atualização suave.
        
        df = pegar_dados_ia(simbolo)
        
        if not df.empty:
            ultimo = df.iloc[-1]
            rsi_val = ultimo['rsi']
            preco_val = ultimo['close']
            
            # Chama IA
            analise = consultar_ia(simbolo, "15m", preco_val, rsi_val)
            
            with painel_ia.container(border=True):
                st.markdown(f"**Veredito:**")
                if "COMPRA" in analise.upper():
                    st.success(analise)
                elif "VENDA" in analise.upper():
                    st.error(analise)
                else:
                    st.info(analise)
            
            with painel_dados.container(border=True):
                st.metric("Preço (Ref)", f"${preco_val:,.2f}")
                st.metric("RSI (14)", f"{rsi_val:.1f}")
                st.progress(rsi_val / 100)
        
        st.caption("O sistema atualiza automaticamente a cada interação.")
        if st.button("🔄 Atualizar Análise Agora"):
            st.rerun()
