### A EXECUTER DANS LE TERMINAL : 
### streamlit run "C:\Users\PFAU\Desktop\PY\app_mapping_2.py"



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
# EXTRACTION DES ATTRIBUTS CLÉS
# ==============================
#def extraire_attributs(txt):
    if pd.isna(txt):
        return {}
    
    attrs = {}

    # --- CATÉGORIE : premier mot AVANT nettoyage (casse préservée puis lower)
    # On prend le texte brut, on cherche le premier "mot" (séquence sans espace)
    txt_brut = str(txt).strip()
    premier_mot = re.match(r"^(\S+)", txt_brut)
    if premier_mot:
        attrs["categorie"] = premier_mot.group(1).lower()

    # Travail sur texte nettoyé pour le reste
    t = nettoyer_texte(txt)

    # DN principal et secondaire (ex: DN100xDN15 ou DN100/DN15)
    dns = re.findall(r"dn\s*(\d+)", t)
    if dns:
        attrs["dn_principal"] = dns[0]
        if len(dns) > 1:
            attrs["dn_secondaire"] = dns[1]

    # Diamètre en mm (ex: Ø48.3 ou d=48.3)
    d_mm = re.search(r"[øod][\s=]*(\d+[\.,]\d+|\d+)", t)
    if d_mm:
        attrs["diam_mm"] = d_mm.group(1).replace(",", ".")

    # Schedule (ex: SCH40, SCH 80)
    sch = re.search(r"sch\s*(\d+)", t)
    if sch:
        attrs["schedule"] = sch.group(1)

    # Épaisseur (ex: EP3, ep=3.5)
    ep = re.search(r"\bep\s*[=]?\s*(\d+[\.,]?\d*)", t)
    if ep:
        attrs["epaisseur"] = ep.group(1).replace(",", ".")

    # Pression (ex: PN16, 3000#, 150LB) — priorité à # puis LB puis PN
    hash_p = re.search(r"(\d+)\s*#", t)
    lb = re.search(r"(\d+)\s*lb", t)
    pn = re.search(r"pn\s*(\d+)", t)
    if hash_p:
        attrs["pression"] = hash_p.group(1) + "#"
    elif lb:
        attrs["pression"] = lb.group(1) + "lb"
    elif pn:
        attrs["pression"] = "pn" + pn.group(1)

    # Matériau / nuance (ex: 316L, X2CrNiMo17-12-2, inox, carbone, fonte)
    nuance = re.search(
        r"(x\d+cr[a-z0-9\-]+|316l?|304l?|p265gh|\d{3}l?\b|\binox\b|\bacier\b|\bcarbone\b|\bfonte\b|\bpe\b|\bpvc\b)",
        t
    )
    if nuance:
        attrs["materiau"] = nuance.group(1).strip()

    # Normes (ex: ASME B16.11, EN10216, NFEN 10222-5, ISO, DIN)
    normes = re.findall(
        r"(asme\s*[a-z]\d+[\.\d]*|nfen\s*\d+[\-\d]*|en\s*\d+[\-\d]*|iso\s*\d+[\-\d]*|din\s*\d+[\-\d]*)",
        t
    )
    if normes:
        attrs["normes"] = sorted(set(n.replace(" ", "") for n in normes))

    return attrs

# ==============================
# SCORE STRUCTURÉ
# ==============================
# Poids par attribut — Catégorie en premier, DN en second
POIDS = {
    "categorie":      50,   # PRIORITÉ ABSOLUE : doit matcher
    "dn_principal":   30,   # Deuxième critère le plus important
    "dn_secondaire":  10,
    "pression":       20,
    "materiau":       15,
    "normes":         10,
    "schedule":        8,
    "epaisseur":       8,
    "diam_mm":         5,
}

# ==============================
# SCORE STRUCTURÉ (colonnes directes)
# ==============================
def score_structure(row_mto, row_wgt):
    score = 0
    poids_total = 0

    # 1. Désignation vs Short_Code_Desc (priorité 1 — poids 50)
    des_mto = nettoyer_texte(row_mto.get("Designation"))
    des_wgt = nettoyer_texte(row_wgt.get("Short_Code_Desc"))
    if des_mto or des_wgt:
        poids_total += 50
        if des_mto and des_wgt:
            score += 50 * (fuzz.token_sort_ratio(des_mto, des_wgt) / 100)

    # 2. Dn1 vs Siz1 (priorité 2 — poids 30)
    dn1_mto = str(row_mto.get("Dn1 [mm]", "")).strip()
    dn1_wgt = str(row_wgt.get("Siz1", "")).strip()
    if dn1_mto or dn1_wgt:
        poids_total += 30
        if dn1_mto and dn1_wgt:
            score += 30 if dn1_mto == dn1_wgt else 0

    # 3. Dn2 vs Siz2 (priorité 3 — poids 20)
    dn2_mto = str(row_mto.get("Dn2 [mm]", "")).strip()
    dn2_wgt = str(row_wgt.get("Siz2", "")).strip()
    if dn2_mto or dn2_wgt:
        poids_total += 20
        if dn2_mto and dn2_wgt:
            score += 20 if dn2_mto == dn2_wgt else 0

    return round((score / poids_total * 100), 1) if poids_total > 0 else 0


# ==============================
# MATCHING PRINCIPAL
# ==============================
def run_mapping(table_MTO, table_WGTID):

    # Groupement WGTID par Siz1 pour réduire le nb de comparaisons
    wgtid_par_siz1 = {}
    for _, row in table_WGTID.iterrows():
        siz1 = str(row.get("Siz1", "")).strip()
        wgtid_par_siz1.setdefault(siz1, []).append(row)

    resultats = []
    total = len(table_MTO)
    progress_bar = st.progress(0, text="Matching en cours...")

    for i, (_, row_mto) in enumerate(table_MTO.iterrows()):
        dn1_mto = str(row_mto.get("Dn1 [mm]", "")).strip()

        subset = wgtid_par_siz1[dn1_mto]
        meilleur_score = -1
        meilleure_desc = None
        meilleur_id = None

        for row_wgt in subset:
            s = score_structure(row_mto, row_wgt)
            if s > meilleur_score:
                meilleur_score = s
                meilleure_desc = row_wgt.get("Short_Code_Desc")
                meilleur_id = row_wgt.get("Wgt_ID")

        resultats.append([
            row_mto.get("Designation"),
            row_mto.get("Dn1 [mm]"),
            row_mto.get("Dn2 [mm]"),
            meilleure_desc,
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
st.title("Mapping MTO ↔ WGTID")
st.caption("Matching structuré : Catégorie → DN → Pression / Matériau / Norme")

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

    st.subheader("2. Vérifier les colonnes")
    col1, col2, col3 = st.columns(3)
    with col1:
        col_MTO = st.selectbox("Colonne description MTO", table_MTO.columns,
            index=list(table_MTO.columns).index("Long description fr à coller")
            if "Long description fr à coller" in table_MTO.columns else 0)
    with col2:
        col_WGTID_desc = st.selectbox("Colonne description WGTID", table_WGTID.columns,
            index=list(table_WGTID.columns).index("Long_Description_FR")
            if "Long_Description_FR" in table_WGTID.columns else 0)
    with col3:
        col_WGTID_id = st.selectbox("Colonne ID WGTID", table_WGTID.columns,
            index=list(table_WGTID.columns).index("Wgt_ID")
            if "Wgt_ID" in table_WGTID.columns else 0)

    st.info(f"**MTO** : {len(table_MTO)} lignes  |  **WGTID** : {len(table_WGTID)} lignes")

    with st.expander("Aperçu MTO"):
        st.dataframe(table_MTO[[col_MTO]].head(10), use_container_width=True)
    with st.expander("Aperçu WGTID"):
        st.dataframe(table_WGTID[[col_WGTID_desc, col_WGTID_id]].head(10), use_container_width=True)

    st.subheader("3. Lancer le matching")
    seuil = st.slider("Seuil de score minimum à afficher (%)", 0, 100, 0)
    show_debug = st.checkbox("Afficher la colonne 'Attributs extraits' (debug)", value=False)

    if st.button("▶️ Lancer le mapping structuré", type="primary"):
        df_resultat = run_mapping(table_MTO.copy(), table_WGTID.copy())

        st.success(f"✅ Mapping terminé — {len(df_resultat)} lignes traitées")

        df_affiche = df_resultat[df_resultat["Score (%)"] >= seuil].copy()

        c1, c2, c3 = st.columns(3)
        c1.metric("Lignes matchées", len(df_affiche))
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
            file_name="resultat_mapping_structure.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("👆 Chargez votre fichier Excel pour commencer.")


