import streamlit as st
from rapidfuzz import fuzz
import pandas as pd
import re
import io

# ==============================
# NETTOYAGE
# ==============================
def nettoyer_texte(txt):
    if pd.isna(txt):
        return ""
    txt = str(txt).lower()
    txt = re.sub(r"[-,./]", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()

# ==============================
# MATCHING PRINCIPAL
# ==============================
def run_mapping(table_MTO, table_WGTID):
    """
    - Filtre WGTID par Siz1 = Dn1 [mm] de la ligne MTO
    - Fuzzy matching entre 'Concaténation' (MTO) et 'Long_Description_FR' (WGTID)
    - Fallback sur toute la table WGTID si aucun match DN trouvé
    """

    # Groupement WGTID par Siz1
    wgtid_par_siz1 = {}
    for _, row in table_WGTID.iterrows():
        siz1 = str(row.get("Siz1", "")).strip()
        wgtid_par_siz1.setdefault(siz1, []).append(row)

    # Pré-calcul descriptions WGTID nettoyées
    table_WGTID["_long_desc_clean"] = table_WGTID["Description"].apply(nettoyer_texte)
    wgtid_records = table_WGTID.to_dict("records")

    resultats = []
    total = len(table_MTO)
    progress_bar = st.progress(0, text="Matching en cours...")

    for i, (_, row_mto) in enumerate(table_MTO.iterrows()):
        dn1_mto = str(row_mto.get("Dn1 [mm]", "")).strip()
        concat_mto = nettoyer_texte(row_mto.get("Designation", ""))

        # Filtrage par DN — fallback sur toute la table si DN absent/inconnu
        subset = wgtid_par_siz1.get(dn1_mto)

        meilleur_score = -1
        meilleure_long_desc = None
        meilleur_id = None

        for row_wgt in subset:
            long_desc_clean = row_wgt.get("_long_desc_clean") or nettoyer_texte(row_wgt.get("Long_Description_FR", ""))
            s = fuzz.token_sort_ratio(concat_mto, long_desc_clean)
            if s > meilleur_score:
                meilleur_score = s
                meilleure_long_desc = row_wgt.get("Long_Description_FR")
                meilleur_id = row_wgt.get("Wgt_ID")

        resultats.append([
            row_mto.get("Concaténation"),
            row_mto.get("Dn1 [mm]"),
            row_mto.get("Dn2 [mm]"),
            meilleure_long_desc,
            meilleur_id,
            meilleur_score,
        ])
        progress_bar.progress((i + 1) / total, text=f"Matching... ({i+1}/{total})")

    progress_bar.empty()

    return pd.DataFrame(resultats, columns=[
        "Concaténation",
        "Dn1 MTO",
        "Dn2 MTO",
        "Long_Description_FR",
        "Wgt_ID",
        "Score (%)",
    ])

# ==============================
# UI STREAMLIT
# ==============================
st.set_page_config(page_title="Mapping MTO ↔ WGTID", page_icon="🔗", layout="wide")
st.title("🔗 Mapping MTO ↔ WGTID")
st.caption("Filtrage par DN (Siz1) puis fuzzy matching Concaténation ↔ Long_Description_FR")

st.subheader("1. Charger le fichier Excel")
uploaded_file = st.file_uploader(
    "Fichier .xlsx ou .xlsm contenant les feuilles **MTO à coller** et **WGTID**",
    type=["xlsx", "xlsm"]
)

if uploaded_file:
    try:
        table_MTO = pd.read_excel(uploaded_file, sheet_name="MTO")
        table_WGTID = pd.read_excel(uploaded_file, sheet_name="WGTID")
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        st.stop()

    table_MTO.columns = table_MTO.columns.str.strip()
    table_WGTID.columns = table_WGTID.columns.str.strip()

    # Vérification colonnes requises
    cols_mto_requises = ["Concaténation", "Dn1 [mm]", "Dn2 [mm]"]
    cols_wgtid_requises = ["Long_Description_FR", "Wgt_ID", "Siz1"]
    manquantes_mto = [c for c in cols_mto_requises if c not in table_MTO.columns]
    manquantes_wgtid = [c for c in cols_wgtid_requises if c not in table_WGTID.columns]

    if manquantes_mto:
        st.error(f"Colonnes manquantes dans MTO : {manquantes_mto}")
        st.write("Colonnes disponibles :", list(table_MTO.columns))
        st.stop()
    if manquantes_wgtid:
        st.error(f"Colonnes manquantes dans WGTID : {manquantes_wgtid}")
        st.write("Colonnes disponibles :", list(table_WGTID.columns))
        st.stop()

    st.info(f"**MTO** : {len(table_MTO)} lignes  |  **WGTID** : {len(table_WGTID)} lignes")

    with st.expander("Aperçu MTO (Concaténation + DN)"):
        st.dataframe(table_MTO[["Concaténation", "Dn1 [mm]", "Dn2 [mm]"]].head(10), use_container_width=True)
    with st.expander("Aperçu WGTID (Long_Description_FR + Siz1 + Wgt_ID)"):
        st.dataframe(table_WGTID[["Long_Description_FR", "Siz1", "Wgt_ID"]].head(10), use_container_width=True)

    st.subheader("2. Lancer le matching")
    seuil = st.slider("Seuil de score minimum à afficher (%)", 0, 100, 0)

    if st.button("▶️ Lancer le mapping", type="primary"):
        df_resultat = run_mapping(table_MTO.copy(), table_WGTID.copy())

        st.success(f"✅ Mapping terminé — {len(df_resultat)} lignes traitées")

        df_affiche = df_resultat[df_resultat["Score (%)"] >= seuil].copy()

        c1, c2, c3 = st.columns(3)
        c1.metric("Lignes affichées", len(df_affiche))
        c2.metric("Score moyen", f"{df_resultat['Score (%)'].mean():.1f}%")
        c3.metric("Score < 70%", int((df_resultat["Score (%)"] < 70).sum()))

        def colorize(val):
            if val >= 85:
                return "background-color: #d4edda"
            elif val >= 70:
                return "background-color: #fff3cd"
            else:
                return "background-color: #f8d7da"

        st.dataframe(
            df_affiche.style.map(colorize, subset=["Score (%)"]),
            use_container_width=True,
            height=400
        )

        buffer = io.BytesIO()
        df_resultat.to_excel(buffer, index=False)
        st.download_button(
            label="⬇️ Télécharger le résultat (.xlsx)",
            data=buffer.getvalue(),
            file_name="resultat_mapping.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("👆 Chargez votre fichier Excel pour commencer.")