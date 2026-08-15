
import streamlit as st
import pandas as pd
import plotly.express as px
from snowflake.snowpark import Session

st.set_page_config(
    page_title="Dashboard COVID-19 - OWID",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Dashboard COVID-19 — Our World in Data")
st.markdown("Pipeline: **OWID CSV ➜ Python/Pandas ➜ Snowflake ➜ Streamlit**")

# ============================================================
# CONFIGURAÇÃO DO SNOWFLAKE
# ============================================================

connection_parameters = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"],
    "warehouse": st.secrets["snowflake"]["warehouse"],
    "database": st.secrets["snowflake"]["database"],
    "schema": st.secrets["snowflake"]["schema"],
    "role": st.secrets["snowflake"]["role"],
}

DATABASE = st.secrets["snowflake"]["database"]
SCHEMA = st.secrets["snowflake"]["schema"]
WAREHOUSE = st.secrets["snowflake"]["warehouse"]

URL = (
    "https://raw.githubusercontent.com/owid/covid-19-data/"
    "master/public/data/owid-covid-data.csv"
)

TABELA = "COVID_DATA"

PAISES = [
    "Brazil",
    "United States",
    "India",
    "Germany",
    "United Kingdom",
    "France",
    "Italy",
]

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def abrir_sessao():
    session = Session.builder.configs(connection_parameters).create()

    # Define explicitamente o contexto da sessão.
    session.use_warehouse(WAREHOUSE)
    session.use_database(DATABASE)
    session.use_schema(SCHEMA)

    return session


def preparar_dados():
    colunas = [
        "location",
        "date",
        "new_cases",
        "total_cases",
        "total_deaths",
        "people_vaccinated",
        "population",
    ]

    partes = []

    for chunk in pd.read_csv(
        URL,
        usecols=colunas,
        chunksize=100_000,
        low_memory=False,
    ):
        filtrado = chunk[chunk["location"].isin(PAISES)].copy()

        if not filtrado.empty:
            partes.append(filtrado)

    if not partes:
        raise ValueError("Nenhum dado foi encontrado para os países selecionados.")

    df = pd.concat(partes, ignore_index=True)

    # Recorte opcional sugerido pela atividade.
    df = df[df["date"] >= "2021-01-01"].copy()
    df["date"] = pd.to_datetime(df["date"])

    # Facilita a criação e posterior leitura da tabela no Snowflake.
    df.columns = [c.upper() for c in df.columns]

    return df


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⚙️ Controle")
st.sidebar.caption("Execute os dois botões na ordem.")

# ============================================================
# BOTÃO 1 — CARREGAR DADOS NO SNOWFLAKE
# ============================================================

if st.sidebar.button(
    "📥 Carregar Dados no Snowflake",
    use_container_width=True,
):
    session = None

    try:
        with st.spinner("Baixando e filtrando dados da OWID..."):
            df_upload = preparar_dados()

        with st.spinner("Conectando e gravando no Snowflake..."):
            session = abrir_sessao()

            # Garante que o banco e schema usados pelo write_pandas
            # estejam explicitamente definidos.
            session.write_pandas(
                df_upload,
                TABELA,
                database=DATABASE,
                schema=SCHEMA,
                auto_create_table=True,
                overwrite=True,
            )

        st.session_state.pop("df", None)

        st.success(
            f"✅ {len(df_upload):,} registros foram gravados em "
            f"{DATABASE}.{SCHEMA}.{TABELA}."
        )

    except Exception as erro:
        st.error(f"❌ Erro ao carregar dados no Snowflake:\\n\\n{erro}")

    finally:
        if session is not None:
            session.close()


# ============================================================
# BOTÃO 2 — CARREGAR DASHBOARD
# ============================================================

if st.sidebar.button(
    "📊 Carregar Dashboard",
    use_container_width=True,
):
    session = None

    try:
        with st.spinner("Lendo dados do Snowflake..."):
            session = abrir_sessao()

            df_snowflake = (
                session
                .table(f"{DATABASE}.{SCHEMA}.{TABELA}")
                .to_pandas()
            )

        df_snowflake.columns = [
            c.lower() for c in df_snowflake.columns
        ]

        df_snowflake["date"] = pd.to_datetime(
            df_snowflake["date"]
        )

        st.session_state["df"] = df_snowflake

        st.success(
            "✅ Dashboard carregado com dados vindos do Snowflake."
        )

    except Exception as erro:
        st.error(f"❌ Erro ao carregar o dashboard:\\n\\n{erro}")

    finally:
        if session is not None:
            session.close()


# ============================================================
# DASHBOARD
# ============================================================

if "df" not in st.session_state:
    st.info(
        "👈 Primeiro clique em **Carregar Dados no Snowflake** "
        "e depois em **Carregar Dashboard**."
    )
    st.stop()

df = st.session_state["df"]

# ============================================================
# FILTRO
# ============================================================

st.sidebar.markdown("---")
st.sidebar.header("🔎 Filtros")

paises_disponiveis = sorted(
    df["location"].dropna().unique().tolist()
)

pais_selecionado = st.sidebar.selectbox(
    "Selecione o país:",
    paises_disponiveis,
)

df_filtrado = (
    df[df["location"] == pais_selecionado]
    .sort_values("date")
    .copy()
)

# ============================================================
# KPIs
# ============================================================

st.subheader(f"📌 Indicadores — {pais_selecionado}")

col1, col2, col3 = st.columns(3)

total_casos = df_filtrado["total_cases"].dropna().max()
total_mortes = df_filtrado["total_deaths"].dropna().max()
populacao = df_filtrado["population"].dropna().max()

with col1:
    st.metric(
        "Total de Casos",
        f"{total_casos:,.0f}" if pd.notna(total_casos) else "N/D",
    )

with col2:
    st.metric(
        "Total de Óbitos",
        f"{total_mortes:,.0f}" if pd.notna(total_mortes) else "N/D",
    )

with col3:
    st.metric(
        "População",
        f"{populacao:,.0f}" if pd.notna(populacao) else "N/D",
    )

st.markdown("---")

# ============================================================
# 1. LINHA — NOVOS CASOS
# ============================================================

st.subheader("1️⃣ Evolução de Casos Novos")

fig_linha = px.line(
    df_filtrado,
    x="date",
    y="new_cases",
    title=f"Novos casos ao longo do tempo — {pais_selecionado}",
    labels={
        "date": "Data",
        "new_cases": "Novos casos",
    },
)

st.plotly_chart(fig_linha, use_container_width=True)

# ============================================================
# 2. BARRAS — ÓBITOS
# ============================================================

st.subheader("2️⃣ Total de Óbitos por País")

df_mortes = (
    df.groupby("location", as_index=False)["total_deaths"]
    .max()
)

fig_barras = px.bar(
    df_mortes,
    x="location",
    y="total_deaths",
    title="Total de óbitos por país",
    labels={
        "location": "País",
        "total_deaths": "Total de óbitos",
    },
)

st.plotly_chart(fig_barras, use_container_width=True)

# ============================================================
# 3. PIZZA — VACINAÇÃO
# ============================================================

st.subheader("3️⃣ Proporção de Pessoas Vacinadas")

dados_vacinacao = (
    df_filtrado[
        df_filtrado["people_vaccinated"].notna()
    ]
    .sort_values("date")
)

if dados_vacinacao.empty:
    st.warning(
        "Não há dados de vacinação disponíveis para esse país."
    )
else:
    ultimo_vax = dados_vacinacao.iloc[-1]

    vacinados = float(
        ultimo_vax["people_vaccinated"]
    )
    populacao_vax = float(
        ultimo_vax["population"]
    )

    nao_vacinados = max(
        0.0,
        populacao_vax - vacinados,
    )

    df_pizza = pd.DataFrame(
        {
            "Categoria": [
                "Pessoas vacinadas (≥ 1 dose)",
                "Restante da população",
            ],
            "Quantidade": [
                vacinados,
                nao_vacinados,
            ],
        }
    )

    fig_pizza = px.pie(
        df_pizza,
        names="Categoria",
        values="Quantidade",
        title=f"Vacinação — {pais_selecionado}",
    )

    st.plotly_chart(
        fig_pizza,
        use_container_width=True,
    )

# ============================================================
# 4. DISPERSÃO — POPULAÇÃO × CASOS
# ============================================================

st.subheader("4️⃣ População × Total de Casos")

df_disp = (
    df.groupby("location", as_index=False)
    .agg(
        population=("population", "max"),
        total_cases=("total_cases", "max"),
    )
    .dropna()
)

fig_disp = px.scatter(
    df_disp,
    x="population",
    y="total_cases",
    text="location",
    size="total_cases",
    title="População × Total de Casos",
    labels={
        "population": "População",
        "total_cases": "Total de casos",
    },
)

fig_disp.update_traces(
    textposition="top center"
)

st.plotly_chart(
    fig_disp,
    use_container_width=True,
)

# ============================================================
# DADOS BRUTOS + DOWNLOAD
# ============================================================

st.markdown("---")
st.subheader("📋 Dados Brutos")

st.dataframe(
    df_filtrado,
    use_container_width=True,
)

csv_data = (
    df_filtrado
    .to_csv(index=False)
    .encode("utf-8")
)

st.download_button(
    label="📥 Baixar dados filtrados em CSV",
    data=csv_data,
    file_name=(
        f"covid_"
        f"{pais_selecionado.lower().replace(' ', '_')}.csv"
    ),
    mime="text/csv",
)
