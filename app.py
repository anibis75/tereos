from io import BytesIO
import duckdb
import pandas as pd
import streamlit as st

# 🔧 Options de débug Streamlit
st.set_option("client.showErrorDetails", True)

# ─────────── Paramètres fixes ───────────
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImF6YWQuaG9zc2VpbmlAc2tlbWEuZWR1Iiwic2Vzc2lvbiI6ImF6YWQuaG9zc2Vpbmkuc2tlbWEuZWR1IiwicGF0IjoiYkZMVHkydUUyMHFmNVhnMkE1TXh4M1FBZkhwclh0cTBRbnl2cHc4TjhLNCIsInVzZXJJZCI6IjllYTRjNDUzLTIyNWEtNGE5NS04Y2NmLWVhMjk1NTUyNmFjZCIsImlzcyI6Im1kX3BhdCIsInJlYWRPbmx5IjpmYWxzZSwidG9rZW5UeXBlIjoicmVhZF93cml0ZSIsImlhdCI6MTc1MzYwNjUyMn0.b8KgBs8dKKymTLu4hdQ-6ZHiwjJrec9JA7_9q764EzE"
DB    = "my_db"
TABLE = "main.zonebourse_chunk_compte_renamed"

# ─────────── Connexion MotherDuck ───────────
con = duckdb.connect(f"md:{DB}?motherduck_token={TOKEN}")

# ─────────── Utilitaires ───────────
def sql_list(values):
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)

# ❌ Attention : désactivation temporaire du cache pour déboguer
def distinct(col: str):
    try:
        return [
            r[0]
            for r in con.execute(
                f'SELECT DISTINCT "{col}" FROM {TABLE} WHERE "{col}" IS NOT NULL ORDER BY 1'
            ).fetchall()
        ]
    except Exception as e:
        st.error(f"❌ Erreur colonne {col} : {e}")
        return []

def year_columns():
    return [
        col[1]
        for col in con.execute(f"PRAGMA table_info('{TABLE.split('.')[-1]}')").fetchall()
        if col[1].isdigit() and col[2] == "DOUBLE"
    ]

def run_query(sql: str) -> pd.DataFrame:
    return con.execute(sql).df()

def to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name="Données filtrées")
    buf.seek(0)
    return buf.getvalue()

# ─────────── Interface ───────────
st.title("📊 Screening M&A (MotherDuck)")

# 🔍 Debug info colonnes
try:
    colonnes_debug = con.execute(f"PRAGMA table_info('{TABLE.split('.')[-1]}')").df()
    st.expander("🧪 Colonnes disponibles").write(colonnes_debug["name"].tolist())
except Exception as e:
    st.error(f"Erreur chargement colonnes : {e}")

regions  = st.multiselect("🌍 Région(s)",  distinct("Région"))
pays     = st.multiselect("🏳️ Pays",       distinct("Pays"))
secteurs = st.multiselect("🏭 Secteur(s)", distinct("Secteur"))
poste    = st.selectbox("📌 Poste financier", distinct("Poste"))

annee = borne_min = borne_max = None
if poste:
    annee = st.selectbox("📅 Année", sorted(year_columns()))
    if annee:
        try:
            result = con.execute(
                f'''SELECT min(CAST("{annee}" AS DOUBLE)),
                           max(CAST("{annee}" AS DOUBLE))
                    FROM {TABLE}
                    WHERE "Poste" = '{poste.replace("'", "''")}' '''
            ).fetchone()
            min_val, max_val = result
            if min_val is not None and max_val is not None and min_val != max_val:
                min_val, max_val = float(min_val), float(max_val)
                borne_min, borne_max = st.slider(
                    "Plage de valeurs",
                    min_value=min_val,
                    max_value=max_val,
                    value=(min_val, max_val),
                    step=max((max_val - min_val) / 200, 1.0),
                )
        except Exception as e:
            st.error(f"Erreur récupération min/max : {e}")

# ─────────── Construction requête ───────────
clauses = []
if regions:  clauses.append(f'"Région"  IN ({sql_list(regions)})')
if pays:     clauses.append(f'"Pays"    IN ({sql_list(pays)})')
if secteurs: clauses.append(f'"Secteur" IN ({sql_list(secteurs)})')
if poste:    clauses.append(f'"Poste" = \'{poste.replace("'", "''")}\'')
if poste and annee and borne_min is not None:
    clauses.append(f'CAST("{annee}" AS DOUBLE) BETWEEN {borne_min} AND {borne_max}')

where_sql = " AND ".join(clauses) or "TRUE"
query_sql = f"SELECT * FROM {TABLE} WHERE {where_sql}"

# ─────────── Résultat ───────────
try:
    df = run_query(query_sql)
    st.markdown(f"### Résultats : {len(df):,} lignes")
    st.dataframe(df.head(10_000), use_container_width=True)
    if len(df) > 10_000:
        st.caption("Affichage limité aux 10 000 premières lignes ; l’export contient tout.")
    st.download_button(
        "📥 Exporter en XLSX",
        data=to_excel(df),
        file_name="filtrage_mna.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
except Exception as e:
    st.error(f"Erreur exécution requête finale : {e}")
