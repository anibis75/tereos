import os, urllib.parse, streamlit as st, duckdb, pandas as pd
from io import BytesIO

# === CONFIGURATION ===
DB        = "my_db"
TABLE     = "main.tereos"
TOKEN     = os.getenv("MOTHERDUCK_TOKEN", "").strip() or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImF6YWQuaG9zc2VpbmlAc2tlbWEuZWR1Iiwic2Vzc2lvbiI6ImF6YWQuaG9zc2Vpbmkuc2tlbWEuZWR1IiwicGF0IjoiYkZMVHkydUUyMHFmNVhnMkE1TXh4M1FBZkhwclh0cTBRbnl2cHc4TjhLNCIsInVzZXJJZCI6IjllYTRjNDUzLTIyNWEtNGE5NS04Y2NmLWVhMjk1NTUyNmFjZCIsImlzcyI6Im1kX3BhdCIsInJlYWRPbmx5IjpmYWxzZSwidG9rZW5UeXBlIjoicmVhZF93cml0ZSIsImlhdCI6MTc1MzYwNjUyMn0.b8KgBs8dKKymTLu4hdQ-6ZHiwjJrec9JA7_9q764EzE"
TOKEN_Q   = urllib.parse.quote_plus(TOKEN)
con       = duckdb.connect(f"md:{DB}?motherduck_token={TOKEN_Q}")

# === COLONNES ===
REGION_COL   = "Région"      # Americas / EMEA / APAC …
COUNTRY_COL  = "Pays"        # France / Brazil …
SECTOR_COL   = "Secteur"
POSTE_COL    = "Poste"       # Operating profit, Net debt …

# === LOGO ===
LOGO_URL = "https://raw.githubusercontent.com/yourrepo/tereos_logo.png"

# === PAGE ===
st.set_page_config("Tereos – M&A Screener", page_icon="📈", layout="wide")
st.sidebar.image(LOGO_URL, caption="Tereos", use_column_width=False)
st.markdown("""
<style>
:root      { --tereos-red:#E2001A; }
h1, h2, h3 { color:var(--tereos-red); }
.stButton>button { background:var(--tereos-red); color:white; }
[data-testid="stToolbar"] { visibility:hidden; }
.main > div { padding-top:2rem; padding-bottom:2rem; }
</style>
""", unsafe_allow_html=True)
st.title("📈 Tereos – M&A Screener")
st.caption("Filtrage dynamique MotherDuck – export Excel")

# === UTILS ===
sql_list = lambda v: ",".join("'" + x.replace("'", "''") + "'" for x in v)

def distinct(col):
    return [r[0] for r in con.execute(
        f'SELECT DISTINCT "{col}" FROM {TABLE} '
        f'WHERE "{col}" IS NOT NULL AND TRIM("{col}")<>\'\' ORDER BY 1'
    ).fetchall()]

def years():
    return [c[1] for c in con.execute(
        f"PRAGMA table_info('{TABLE.split('.')[-1]}')"
    ).fetchall() if c[1].isdigit()]

def to_xlsx(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df.to_excel(w, "Filtrage", index=False)
    buf.seek(0); return buf.getvalue()

# === SIDEBAR ===
st.sidebar.header("🎛️ Filtres")
regions   = st.sidebar.multiselect("🌍 Région",  distinct(REGION_COL),  key="regions")
countries = st.sidebar.multiselect("🏳️ Pays",   distinct(COUNTRY_COL), key="countries")
sectors   = st.sidebar.multiselect("🏭 Secteur", distinct(SECTOR_COL),  key="sectors")
postes    = st.sidebar.multiselect("📌 Postes financiers", distinct(POSTE_COL), key="postes")

if st.sidebar.button("♻️ Réinitialiser filtres"):
    for k in ("regions", "countries", "sectors", "postes", "yrsel"):
        st.session_state.pop(k, None)
    st.experimental_rerun()

num_clauses, yr = [], None
if postes:
    yr = st.sidebar.selectbox("📅 Année", sorted(years()), key="yrsel")
    if yr:
        for p in postes:
            lo, hi = con.execute(
                f'SELECT min(CAST("{yr}" AS DOUBLE)), max(CAST("{yr}" AS DOUBLE)) '
                f'FROM {TABLE} WHERE "{POSTE_COL}" = ?', [p]
            ).fetchone()
            if lo is not None and hi is not None and lo != hi:
                vmin, vmax = st.sidebar.slider(
                    f"{p} – plage ({yr})", float(lo), float(hi),
                    (float(lo), float(hi)), key=p
                )
                num_clauses.append(
                    f'("{POSTE_COL}" = \'{p.replace("'", "''")}\' AND '
                    f'CAST("{yr}" AS DOUBLE) BETWEEN {vmin} AND {vmax})'
                )

# === REQUÊTE ===
clauses = []
if regions:   clauses.append(f'"{REGION_COL}"  IN ({sql_list(regions)})')
if countries: clauses.append(f'"{COUNTRY_COL}" IN ({sql_list(countries)})')
if sectors:   clauses.append(f'"{SECTOR_COL}"  IN ({sql_list(sectors)})')
if num_clauses: clauses.append("(" + " OR ".join(num_clauses) + ")")
where = " AND ".join(clauses) or "TRUE"

df = con.execute(f"SELECT * FROM {TABLE} WHERE {where}").df()

# === AFFICHAGE & EXPORT ===
st.success(f"✅ {len(df):,} lignes affichées")
st.dataframe(df.head(10_000), use_container_width=True)
if len(df) > 10_000:
    st.caption("⚠️ Affichage limité à 10 000 lignes. L'export contient tout.")

st.download_button("📥 Exporter Excel",
    data=to_xlsx(df),
    file_name="tereos_filtrage.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
