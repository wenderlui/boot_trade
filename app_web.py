import streamlit as st
import pandas as pd
import ccxt
import time
import os
import streamlit.components.v1 as components
from google import genai
from dotenv import load_dotenv

# Carrega chaves (Secrets do Streamlit ou .env local)
load_dotenv()

st.set_page_config(page_title="Pocket Play PRO", page_icon="💎", layout="wide")

# --- CSS: CENTRALIZAÇÃO E VISUAL PREMIUM ---
st.markdown("""
<style>
    /* Fundo Escuro Profundo */
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    
    /* CENTRALIZAÇÃO VERTICAL E HORIZONTAL */
    .block-container {
        max-width: 1200px;      /* Largura ideal para ver gráfico + IA */
        padding-top: 5rem;      /* Espaço no topo */
        padding-bottom: 5rem;
        margin: auto;
    }
    
    /* Estilo dos Cards e Métricas */
    div[data-testid="stMetricValue"] { font-size: 24px; color: #00ff00; font-weight: bold; }
    div[data-testid="stMetricLabel"] { font-size: 14px; color: #888; }
    
    /* Barra de Progresso Personalizada */
    .stProgress > div > div > div > div { background-color: #f0b90b; }
    
    /* Botões */
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
    st.session_state.ai_result = "Aguardando primeira análise..."
if "ai_model_used" not in st.session_state:
    st.session_state.ai_model_used = "..."

# --- CONEXÃO DE DADOS (PROXY KRAKEN) ---
def get_exchange_data():
    return ccxt.kraken()

# Mapeia Bybit -> Kraken (Resistente a erros)
def resolver_simbolo_ia(symbol_bybit):
    # Mapa manual para garantir os principais
    mapa = {
        "BTCUSDT": "BTC/USD", "ETHUSDT": "ETH/USD", "SOLUSDT": "SOL/USD",
        "XRPUSDT": "XRP/USD", "BNBUSDT": "BNB/USD", "DOGEUSDT": "DOGE/USD",
        "ADAUSDT": "ADA/USD", "AVAXUSDT": "AVAX/USD", "DOTUSDT": "DOT/USD",
        "LINKUSDT": "LINK/USD", "TRXUSDT": "TRX/USD", "POLUSDT": "MATIC/USD",
        "LTCUSDT": "LTC/USD", "BCHUSDT": "BCH/USD"
    }
    
    if symbol_bybit in mapa:
        return mapa[symbol_bybit]
    
    # Tentativa automática para manuais (ex: PEPEUSDT -> PEPE/USD)
    base = symbol_bybit.upper().replace("USDT", "").replace("USD", "")
    return f"{base}/USD"

# --- CÁLCULOS MATEMÁTICOS (RESTAURADOS) ---
def calcular_indicadores(df):
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Médias Móveis (Cruciais para probabilidade)
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    
    return df

def calcular_probabilidade_algoritmica(df):
    """
    Algoritmo Matemático restaurado.
    Calcula % de chance de ALTA baseado em RSI + Tendência.
    """
    if len(df) < 50: return 50 # Sem dados suficientes
    
    score = 50 # Começa neutro
    ultimo = df.iloc[-1]
    
    # 1. Peso RSI (30%)
    if ultimo['rsi'] < 30: score += 20    # Muito barato (Chance de subir)
    elif ultimo['rsi'] > 70: score -= 20  # Muito caro (Chance de cair)
    elif ultimo['rsi'] > 55: score -= 5
    elif ultimo['rsi'] < 45: score += 5

    # 2. Peso Tendência Curta (Cruzamento EMA 9 vs 21) (40%)
    if ultimo['ema9'] > ultimo['ema21']: score += 20
    else: score -= 20
    
    # 3. Peso Tendência Longa (Preço vs EMA 50) (30%)
    if ultimo['close'] > ultimo['ema50']: score += 10
    else: score -= 10
    
    # Trava entre 0 e 100
    return max(0, min(100, score))

def pegar_dados_ia(symbol_bybit):
    try:
        exchange = get_exchange_data()
        symbol_kraken = resolver_simbolo_ia(symbol_bybit)
        
        # Baixa 100 velas para ter dados suficientes para EMA50
        candles = exchange.fetch_ohlcv(symbol_kraken, timeframe="15m", limit=100)
        
        if not candles or len(candles) < 50:
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df = calcular_indicadores(df)
        return df
    except Exception as e:
        print(f"Erro dados: {e}")
        return pd.DataFrame()

# --- IA COM FAILOVER ---
def consultar_ia_inteligente(simbolo, preco, rsi, prob_alta):
    modelos = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
    
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        api_key = os.getenv("GEMINI_API_KEY")
        
    client = genai.Client(api_key=api_key)

    prompt = (
        f"Atue como Trader Profissional. Par: {simbolo}.\n"
        f"DADOS TÉCNICOS:\n"
        f"- Preço: ${preco}\n"
        f"- RSI (14): {rsi:.1f}\n"
        f"- Probabilidade Algorítmica de Alta: {prob_alta}%\n"
        f"Instrução: RSI > 70 é Venda/Risco. RSI < 30 é Compra/Oportunidade.\n"
        f"FORMATO DA RESPOSTA:\n"
        f"VEREDITO: [COMPRA FORTE / COMPRA / NEUTRO / VENDA / VENDA FORTE]\n"
        f"ANÁLISE: [Explique o motivo em 1 frase técnica curta]"
    )

    for modelo in modelos:
        try:
            response = client.models.generate_content(model=modelo, contents=prompt)
            return response.text, modelo
        except:
            continue
            
    return "⚠️ IA Indisponível (Cota). Tente em breve.", "Offline"

# --- WIDGET TRADINGVIEW ---
def mostrar_grafico_tv(symbol):
    html = f"""
    <div class="tradingview-widget-container" style="height:600px;width:100%">
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
    components.html(html, height=600)

# --- SIDEBAR (CONFIGURAÇÕES) ---
with st.sidebar:
    st.header("🎛️ Configuração")
    
    # SELETOR (Top 10 + Manual)
    lista_moedas = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", 
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "TRXUSDT", "LINKUSDT", 
        "POLUSDT", "Outro..."
    ]
    
    escolha = st.selectbox("Ativo", lista_moedas)
    
    if escolha == "Outro...":
        simbolo = st.text_input("Digite o Símbolo (ex: PEPEUSDT):", value="PEPEUSDT").upper()
    else:
        simbolo = escolha
    
    st.divider()
    st.subheader("🤖 Timer da IA")
    intervalo_minutos = st.slider("Atualizar IA (min):", 1, 60, 5, help="Controle para economizar cota.")
    intervalo_segundos = intervalo_minutos * 60
    
    st.divider()
    if st.button("🔄 Forçar Recarga"):
        st.session_state.last_ai_run = 0
        st.rerun()

# --- LAYOUT PRINCIPAL ---
st.title(f"Pocket Play PRO | {simbolo}")

# 1. MÉTRICAS NO TOPO (RESTAURADO!)
col1, col2, col3, col4 = st.columns(4)
with col1: metric_price = st.empty()
with col2: metric_prob = st.empty()
with col3: metric_rsi = st.empty()
with col4: metric_trend = st.empty()

st.divider()

# 2. ÁREA CENTRAL (Gráfico + IA)
col_grafico, col_dados = st.columns([2.5, 1]) # Gráfico maior, IA lateral

# Coluna Esquerda: Gráfico
with col_grafico:
    mostrar_grafico_tv(simbolo)

# Coluna Direita: IA e Detalhes
with col_dados:
    # Lógica do Timer
    agora = time.time()
    tempo_passado = agora - st.session_state.last_ai_run
    
    # Container Estilizado
    ia_box = st.container(border=True)
    
    # --- PROCESSAMENTO DE DADOS ---
    with ia_box:
        # Busca dados (com proteção contra erros)
        df = pegar_dados_ia(simbolo)
        
        if not df.empty:
            last = df.iloc[-1]
            prob_alta = calcular_probabilidade_algoritmica(df)
            prob_baixa = 100 - prob_alta
            
            # Atualiza Métricas do Topo
            metric_price.metric("Preço Atual", f"${last['close']:,.4f}")
            metric_prob.metric("Probabilidade Alta", f"{prob_alta:.0f}%", delta_color="off")
            
            cor_rsi = "normal" if 30 <= last['rsi'] <= 70 else "inverse"
            metric_rsi.metric("RSI (14)", f"{last['rsi']:.1f}", 
                              "Sobrecompra" if last['rsi']>70 else "Sobrevenda" if last['rsi']<30 else "Neutro",
                              delta_color=cor_rsi)
            
            sinal_ema = "Alta 🟢" if last['ema9'] > last['ema21'] else "Baixa 🔴"
            metric_trend.metric("Tendência (EMA)", sinal_ema)

            # Lógica da IA (Respeita o Timer)
            if tempo_passado > intervalo_segundos:
                texto, modelo = consultar_ia_inteligente(simbolo, last['close'], last['rsi'], prob_alta)
                
                st.session_state.ai_result = texto
                st.session_state.ai_model_used = modelo
                st.session_state.last_ai_run = agora
                tempo_restante = intervalo_segundos
            else:
                tempo_restante = int(intervalo_segundos - tempo_passado)

            # --- EXIBIÇÃO DA IA ---
            st.subheader(f"🧠 Análise ({st.session_state.ai_model_used})")
            
            # Limpeza do texto da IA
            res = st.session_state.ai_result.replace("*", "")
            
            if "COMPRA" in res.upper():
                st.success(res, icon="🚀")
            elif "VENDA" in res.upper():
                st.error(res, icon="📉")
            else:
                st.info(res, icon="⚖️")
            
            st.write("---")
            st.caption("Termômetro do Algoritmo:")
            st.progress(prob_alta / 100)
            st.caption(f"Próxima análise IA em: {tempo_restante}s")
            
        else:
            # Caso a moeda digitada não exista na Kraken ou erro de API
            st.warning(f"Dados técnicos indisponíveis para {simbolo} na fonte de dados (Kraken).")
            st.caption("O gráfico visual (Bybit) continua funcionando, mas a IA precisa de dados da Kraken/Coinbase.")

# Auto-refresh lento para atualizar o contador
time.sleep(240) 
st.rerun()


