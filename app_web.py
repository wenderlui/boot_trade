import streamlit as st
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from pybit.unified_trading import HTTP
from google import genai
from dotenv import load_dotenv
import uuid

# Carrega chaves
load_dotenv()

# --- CONFIGURAÇÃO DA PÁGINA (Layout Wide OBRIGATÓRIO) ---
st.set_page_config(page_title="Pocket Play TERMINAL", page_icon="💎", layout="wide")

# CSS para ajustar a coluna lateral e remover margens extras
st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    div[data-testid="stMetricValue"] { font-size: 20px; font-weight: bold; color: #00ff00; }
    div[data-testid="stMetricLabel"] { font-size: 14px; color: #888; }
    .stProgress > div > div > div > div { background-color: #f0b90b; }
    
    /* Ajuste para colar o gráfico no topo */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# --- ESTADO (MEMÓRIA) ---
if "last_ai_text" not in st.session_state:
    st.session_state.last_ai_text = "Iniciando análise..."
if "last_ai_model" not in st.session_state:
    st.session_state.last_ai_model = "..."
if "last_run_time" not in st.session_state:
    st.session_state.last_run_time = 0

# --- MAPA DE TEMPOS ---
TIMEFRAMES = {
    "5 Minutos": "5",
    "15 Minutos": "15",
    "1 Hora": "60",
    "4 Horas": "240",
    "Diário": "D"
}

# --- FUNÇÕES TÉCNICAS ---
def calcular_indicadores(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['EMA9'] = df['Close'].ewm(span=9).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    return df

def calcular_probabilidade(df_moeda, df_btc, book_ratio):
    score = 50
    ultimo = df_moeda.iloc[-1]
    btc_trend = df_btc['Close'].iloc[-1] > df_btc['Close'].iloc[-5]
    
    if ultimo['RSI'] < 30: score += 20
    elif ultimo['RSI'] > 70: score -= 20
    elif ultimo['RSI'] > 50: score += 5
    else: score -= 5

    if ultimo['EMA9'] > ultimo['EMA21']: score += 15
    else: score -= 15
    
    if btc_trend: score += 10
    else: score -= 10
    
    if book_ratio > 1.2: score += 10
    elif book_ratio < 0.8: score -= 10
    
    return max(0, min(100, score))

def pegar_dados_mercado(symbol, interval_code):
    try:
        session = HTTP(testnet=False, api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))
        
        # Candles Moeda
        kline = session.get_kline(category="linear", symbol=symbol, interval=interval_code, limit=200)
        df = pd.DataFrame(kline['result']['list'], columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'Turnover'])
        df[['Open', 'High', 'Low', 'Close', 'Vol']] = df[['Open', 'High', 'Low', 'Close', 'Vol']].apply(pd.to_numeric)
        df = df.iloc[::-1].reset_index(drop=True)
        df['Time'] = pd.to_datetime(pd.to_numeric(df['Time']), unit='ms')
        df = calcular_indicadores(df)

        # Candles BTC
        kline_btc = session.get_kline(category="linear", symbol="BTCUSDT", interval=interval_code, limit=50)
        df_btc = pd.DataFrame(kline_btc['result']['list'], columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'Turnover'])
        df_btc['Close'] = pd.to_numeric(df_btc['Close'])
        df_btc = df_btc.iloc[::-1].reset_index(drop=True)

        # Order Book
        book = session.get_orderbook(category="linear", symbol=symbol, limit=50)
        bids = sum([float(x[1]) for x in book['result']['b']])
        asks = sum([float(x[1]) for x in book['result']['a']])
        book_ratio = bids / asks if asks > 0 else 1

        return df, df_btc, book_ratio
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), 0

# --- INTELIGÊNCIA ARTIFICIAL ---
def consultar_ia(simbolo, timeframe, preco, prob_alta, rsi, trend_btc):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = (
        f"Atue como Trader Institucional Sênior. Par {simbolo}, Tempo {timeframe}.\n"
        f"DADOS: Preço ${preco} | Chance Alta: {prob_alta}% | RSI: {rsi:.1f} | BTC: {'Alta' if trend_btc else 'Baixa'}\n"
        f"Responda EXATAMENTE neste formato:\n"
        f"VEREDITO: [COMPRA / VENDA / NEUTRO]\n"
        f"ALVO: [Preço sugerido ou 'Aguardar']\n"
        f"ANÁLISE: [Uma frase curta e técnica sobre Price Action e RSI]"
    )
    modelos = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    for m in modelos:
        try:
            return client.models.generate_content(model=m, contents=prompt).text, m
        except: continue
    return "Erro IA - Limite Excedido", "Off"

# --- SIDEBAR (CONTROLES) ---
with st.sidebar:
    st.header("🎛️ Painel de Controle")
    simbolo = st.selectbox("Ativo", ["POLUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
    tf_label = st.selectbox("Tempo Gráfico", list(TIMEFRAMES.keys()), index=1)
    
    st.divider()
    st.markdown("### 🤖 Cérebro IA")
    intervalo_ia_min = st.slider("Atualizar IA (min)", 1, 60, 5)
    intervalo_ia_seg = intervalo_ia_min * 60
    
    st.divider()
    ligar = st.toggle("🚀 INICIAR SISTEMA", value=False)

# --- LAYOUT PRINCIPAL (DIVISÃO DE TELA) ---
# Topo: Métricas Rápidas
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1: metric_price = st.empty()
with col_m2: metric_prob = st.empty()
with col_m3: metric_rsi = st.empty()
with col_m4: metric_btc = st.empty()

st.divider()

# Corpo: Coluna Esquerda (Gráfico 75%) e Direita (Dados 25%)
col_grafico, col_lateral = st.columns([3, 1])

with col_grafico:
    st.subheader(f"📈 Gráfico {simbolo} ({tf_label})")
    chart_area = st.empty()

with col_lateral:
    st.subheader("🧠 Análise IA")
    ia_container = st.container(border=True) # Caixa com borda para destacar a IA
    with ia_container:
        ia_area = st.empty()
    
    st.write("") # Espaço
    st.subheader("📊 Order Book")
    stats_container = st.container(border=True)
    with stats_container:
        stats_area = st.empty()

# --- LOOP DE TRADING ---
if ligar:
    while ligar:
        # 1. Coleta Dados
        df, df_btc, book_ratio = pegar_dados_mercado(simbolo, TIMEFRAMES[tf_label])
        
        if not df.empty and not df_btc.empty:
            ultimo = df.iloc[-1]
            ultimo_btc = df_btc.iloc[-1]
            btc_var = ((ultimo_btc['Close'] - df_btc.iloc[-2]['Close']) / df_btc.iloc[-2]['Close']) * 100
            prob_alta = calcular_probabilidade(df, df_btc, book_ratio)

            # 2. Métricas de Topo
            metric_price.metric(f"{simbolo}", f"${ultimo['Close']:,.4f}")
            metric_prob.metric("Probabilidade Alta", f"{prob_alta:.0f}%", delta_color="off")
            
            cor_rsi = "normal" if 30 <= ultimo['RSI'] <= 70 else "inverse"
            metric_rsi.metric(f"RSI", f"{ultimo['RSI']:.1f}", "Sobrecompra" if ultimo['RSI']>70 else "Sobrevenda" if ultimo['RSI']<30 else "Neutro", delta_color=cor_rsi)
            
            metric_btc.metric("BTC (Ref)", f"${ultimo_btc['Close']:,.0f}", f"{btc_var:+.2f}%")

            # 3. Gráfico (Coluna Esquerda)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
            fig.add_trace(go.Candlestick(x=df['Time'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Preço"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Time'], y=df['EMA9'], line=dict(color='#00ff00', width=1), name="EMA 9"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Time'], y=df['EMA50'], line=dict(color='yellow', width=2), name="EMA 50"), row=1, col=1)
            
            # Cores do Volume
            colors = ['#ef5350' if r['Open'] > r['Close'] else '#26a69a' for i, r in df.iterrows()]
            fig.add_trace(go.Bar(x=df['Time'], y=df['Vol'], marker_color=colors, name="Volume"), row=2, col=1)
            
            fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)")
            chart_area.plotly_chart(fig, use_container_width=True, key=f"chart_{uuid.uuid4()}")

            # 4. Timer e IA (Coluna Direita)
            agora = time.time()
            tempo_passado = agora - st.session_state.last_run_time
            
            if tempo_passado >= intervalo_ia_seg:
                analise, modelo = consultar_ia(simbolo, tf_label, ultimo['Close'], prob_alta, ultimo['RSI'], btc_var > 0)
                st.session_state.last_ai_text = analise
                st.session_state.last_ai_model = modelo
                st.session_state.last_run_time = agora
                tempo_restante = intervalo_ia_seg
            else:
                tempo_restante = int(intervalo_ia_seg - tempo_passado)

            with ia_area.container():
                st.caption(f"Modelo: {st.session_state.last_ai_model}")
                texto = st.session_state.last_ai_text.replace("*", "")
                if "COMPRA" in texto.upper(): st.success(texto)
                elif "VENDA" in texto.upper(): st.error(texto)
                else: st.info(texto)
                st.progress((intervalo_ia_seg - tempo_restante) / intervalo_ia_seg)
                st.caption(f"Próx. Análise: {tempo_restante}s")

            with stats_area.container():
                st.metric("Pressão Compradora", f"{book_ratio:.2f}")
                st.progress(book_ratio / 2 if book_ratio < 2 else 1.0)
                if book_ratio > 1.2: st.caption("🟢 Touros no Comando")
                elif book_ratio < 0.8: st.caption("🔴 Ursos no Comando")
                else: st.caption("⚖️ Briga Equilibrada")

        time.sleep(5)
else:
    st.info("👈 Ative o sistema na barra lateral.")
