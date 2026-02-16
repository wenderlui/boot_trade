import streamlit as st
import pandas as pd
import ccxt
import time
import os
import streamlit.components.v1 as components
from google import genai
from dotenv import load_dotenv

# Carrega chaves
load_dotenv()

st.set_page_config(page_title="AI trader CLOUD", page_icon="💎", layout="wide")

# --- CSS: CENTRALIZAÇÃO E VISUAL ---
st.markdown("""
<style>
    /* Fundo Escuro Profundo */
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    
    /* CENTRALIZAÇÃO VERTICAL E HORIZONTAL */
    .block-container {
        max-width: 1000px;      /* Largura controlada */
        padding-top: 8rem;      /* AUMENTEI AQUI: Empurra tudo para baixo */
        padding-bottom: 5rem;
        margin: auto;
    }
    
    /* Estilo dos Cards e Textos */
    div[data-testid="stMetricValue"] { font-size: 22px; color: #00ff00; }
    div[data-testid="stMarkdownContainer"] p { font-size: 16px; }
    
    /* Botões mais bonitos */
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        background-color: #262730;
        color: white;
        border: 1px solid #444;
    }
    .stButton > button:hover {
        border-color: #00ff00;
        color: #00ff00;
    }
</style>
""", unsafe_allow_html=True)

# --- ESTADO (MEMÓRIA) ---
if "last_ai_run" not in st.session_state:
    st.session_state.last_ai_run = 0
if "ai_result" not in st.session_state:
    st.session_state.ai_result = "Iniciando sistema..."
if "ai_model_used" not in st.session_state:
    st.session_state.ai_model_used = "..."

# --- CONEXÃO DE DADOS (PROXY INTELIGENTE) ---
def get_exchange_data():
    return ccxt.kraken()

# Mapeia Bybit -> Kraken (Com fallback automático)
def resolver_simbolo_ia(symbol_bybit):
    # Mapa manual para exceções
    mapa = {
        "BTCUSDT": "BTC/USD",
        "ETHUSDT": "ETH/USD",
        "SOLUSDT": "SOL/USD",
        "XRPUSDT": "XRP/USD",
        "BNBUSDT": "BNB/USD",
        "DOGEUSDT": "DOGE/USD",
        "ADAUSDT": "ADA/USD",
        "AVAXUSDT": "AVAX/USD",
        "DOTUSDT": "DOT/USD",
        "LINKUSDT": "LINK/USD",
        "TRXUSDT": "TRX/USD",
        "POLUSDT": "MATIC/USD"
    }
    
    if symbol_bybit in mapa:
        return mapa[symbol_bybit]
    
    # Tenta converter automaticamente se for uma moeda nova (ex: PEPEUSDT -> PEPE/USD)
    # Remove 'USDT' do final e adiciona '/USD'
    base = symbol_bybit.replace("USDT", "")
    return f"{base}/USD"

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
        symbol_kraken = resolver_simbolo_ia(symbol_bybit)
        
        # Tenta baixar dados
        try:
            candles = exchange.fetch_ohlcv(symbol_kraken, timeframe="15m", limit=50)
        except:
            # Se falhar (moeda não listada na Kraken), retorna vazio
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = calcular_rsi(df)
        return df
    except:
        return pd.DataFrame()

# --- IA COM FAILOVER ---
def consultar_ia_inteligente(simbolo, preco, rsi):
    modelos = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
    
    # Pega chave do Cloud ou Local
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        api_key = os.getenv("GEMINI_API_KEY")
        
    client = genai.Client(api_key=api_key)

    prompt = (
        f"Analise Crípto: {simbolo}. Preço: ${preco} | RSI: {rsi:.1f}.\n"
        f"Contexto: RSI > 70 (Sobrecompra/Venda), RSI < 30 (Sobrevenda/Compra).\n"
        f"Saída Obrigatória: 'VEREDITO: [COMPRA/VENDA/NEUTRO] - [Motivo curto]'"
    )

    for modelo in modelos:
        try:
            response = client.models.generate_content(model=modelo, contents=prompt)
            return response.text, modelo
        except:
            continue
            
    return "⚠️ IA Ocupada. Aguarde...", "Offline"

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
    
    # SELETOR DE MOEDAS TOP 10 + MANUAL
    lista_moedas = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "TRXUSDT", "LINKUSDT", 
        "DOTUSDT", "POLUSDT", "Outro..."
    ]
    
    escolha = st.selectbox("Ativo", lista_moedas)
    
    if escolha == "Outro...":
        simbolo = st.text_input("Digite o Símbolo (ex: PEPEUSDT):", value="PEPEUSDT").upper()
    else:
        simbolo = escolha
    
    st.divider()
    st.subheader("🤖 IA Timer")
    intervalo_minutos = st.slider("Atualizar IA (min):", 1, 60, 5)
    intervalo_segundos = intervalo_minutos * 60
    
    st.divider()
    if st.button("🔄 Forçar Recarga"):
        st.session_state.last_ai_run = 0
        st.rerun()

# --- LAYOUT PRINCIPAL ---
st.header(f"Pocket Play | {simbolo}")

col_grafico, col_dados = st.columns([2, 1])

# Coluna 1: Gráfico
with col_grafico:
    mostrar_grafico_tv(simbolo)

# Coluna 2: IA
with col_dados:
    # Lógica do Timer
    agora = time.time()
    tempo_passado = agora - st.session_state.last_ai_run
    
    ia_box = st.container(border=True)
    
    with ia_box:
        # Verifica se deve rodar a IA
        if tempo_passado > intervalo_segundos:
            df = pegar_dados_ia(simbolo)
            if not df.empty:
                last = df.iloc[-1]
                texto, modelo = consultar_ia_inteligente(simbolo, last['close'], last['rsi'])
                
                st.session_state.ai_result = texto
                st.session_state.ai_model_used = modelo
                st.session_state.last_ai_run = agora
                tempo_restante = intervalo_segundos
            else:
                st.warning("Dados indisponíveis na fonte IA (Kraken) para este par.")
                tempo_restante = intervalo_segundos
        else:
            tempo_restante = int(intervalo_segundos - tempo_passado)

        # Exibe Resultado
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

# Loop suave
time.sleep(2) 
st.rerun()
