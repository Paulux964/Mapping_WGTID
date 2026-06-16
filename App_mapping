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
def extraire_attributs(txt):
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

def score_structure(attrs_mto, attrs_wgt):
    total_poids = 0
    total_score = 0

    for cle, poids in POIDS.items():
        v_mto = attrs_mto.get(cle)
        v_wgt = attrs_wgt.get(cle)

        if v_mto is None and v_wgt is None:
            continue  # absent des deux : neutre

        total_poids += poids

        if v_mto is None or v_wgt is None:
            # L'un a l'attribut, l'autre non → pénalité
            total_score += poids * 0.1
            continue

        if isinstance(v_mto, list) and isinstance(v_wgt, list):
            communs = set(v_mto) & set(v_wgt)
            union = set(v_mto) | set(v_wgt)
            ratio = len(communs) / len(union) if union else 1.0
            total_score += poids * ratio
        else:
            if str(v_mto) == str(v_wgt):
                total_score += poids  # match exact : score plein
            elif cle == "categorie":
                # Catégorie : fuzzy tolérant (fautes de frappe légères)
                fuzzy = fuzz.ratio(str(v_mto), str(v_wgt)) / 100
                total_score += poids * fuzzy
            else:
                # Autres attributs : fuzzy partiel (crédit réduit)
                fuzzy = fuzz.ratio(str(v_mto), str(v_wgt)) / 100
                total_score += poids * fuzzy * 0.6

    if total_poids == 0:
        return 0

    score_struct = (total_score / total_poids) * 100

    # Complément fuzzy global (30% du score final)
    txt_mto = attrs_mto.get("_clean", "")
    txt_wgt = attrs_wgt.get("_clean", "")
    score_fuzzy = fuzz.token_sort_ratio(txt_mto, txt_wgt)

    return round(0.70 * score_struct + 0.30 * score_fuzzy, 1)

# ==============================
# MATCHING PRINCIPAL
# ==============================
def run_mapping(table_MTO, table_WGTID, col_MTO, col_WGTID_desc, col_WGTID_id):
    # Préparer MTO
    table_MTO["clean"] = table_MTO[col_MTO].apply(nettoyer_texte)
    table_MTO["attrs"] = table_MTO[col_MTO].apply(extraire_attributs)
    table_MTO["dn"] = table_MTO["attrs"].apply(lambda a: "dn" + a["dn_principal"] if "dn_principal" in a else None)
    for i, row in table_MTO.iterrows():
        table_MTO.at[i, "attrs"]["_clean"] = row["clean"]

    # Préparer WGTID
    table_WGTID["clean"] = table_WGTID[col_WGTID_desc].apply(nettoyer_texte)
    table_WGTID["attrs"] = table_WGTID[col_WGTID_desc].apply(extraire_attributs)
    table_WGTID["dn"] = table_WGTID["attrs"].apply(lambda a: "dn" + a["dn_principal"] if "dn_principal" in a else None)
    for i, row in table_WGTID.iterrows():
        table_WGTID.at[i, "attrs"]["_clean"] = row["clean"]

    # Double groupement : par catégorie+DN d'abord, fallback DN seul, fallback global
    wgtid_par_cat_dn = {}
    wgtid_par_dn = {}
    for _, row in table_WGTID.iterrows():
        cat = row["attrs"].get("categorie")
        dn = row["dn"]
        key_cat_dn = f"{cat}__{dn}" if cat and dn else None
        if key_cat_dn:
            wgtid_par_cat_dn.setdefault(key_cat_dn, []).append(row)
        if dn:
            wgtid_par_dn.setdefault(dn, []).append(row)

    resultats = []
    total = len(table_MTO)
    progress_bar = st.progress(0, text="Matching en cours...")

    for i, (_, row) in enumerate(table_MTO.iterrows()):
        desc_original = row[col_MTO]
        attrs_mto = row["attrs"]
        dn = row["dn"]
        cat = attrs_mto.get("categorie")

        # Sélection du sous-ensemble : catégorie+DN > DN seul > tout
        key_cat_dn = f"{cat}__{dn}" if cat and dn else None
        if key_cat_dn and key_cat_dn in wgtid_par_cat_dn:
            subset_rows = wgtid_par_cat_dn[key_cat_dn]
        elif dn and dn in wgtid_par_dn:
            subset_rows = wgtid_par_dn[dn]
        else:
            subset_rows = table_WGTID.to_dict("records")

        meilleur_score = -1
        meilleure_desc = None
        meilleur_id = None

        for row_wgt in subset_rows:
            attrs_wgt = row_wgt["attrs"] if isinstance(row_wgt, dict) else row_wgt["attrs"]
            s = score_structure(attrs_mto, attrs_wgt)
            if s > meilleur_score:
                meilleur_score = s
                meilleure_desc = row_wgt[col_WGTID_desc]
                meilleur_id = row_wgt[col_WGTID_id]

        attrs_str = " | ".join(f"{k}={v}" for k, v in attrs_mto.items() if k != "_clean")
        resultats.append([desc_original, meilleure_desc, meilleur_id, meilleur_score, attrs_str])
        progress_bar.progress((i + 1) / total, text=f"Matching... ({i+1}/{total})")

    progress_bar.empty()

    return pd.DataFrame(resultats, columns=[
        "Long description MTO",
        "Long description WGTID",
        "WGTID",
        "Score (%)",
        "Attributs extraits (debug)"
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
        table_MTO = pd.read_excel(uploaded_file, sheet_name="MTO à coller")
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

    # Test d'extraction
    with st.expander("🔬 Tester l'extraction d'attributs sur une description"):
        exemple = st.text_input(
            "Colle une description ici",
            value="Bossage a Souder SW 3000# - Svt ASME B16.11 / - ( 'X2CrNiMo17-12-2 Svt NFEN 10222-5 ' ) - DN100xDN15"
        )
        if exemple:
            attrs = extraire_attributs(exemple)
            attrs_display = {k: v for k, v in attrs.items() if k != "_clean"}
            st.json(attrs_display)

    with st.expander("Aperçu MTO"):
        st.dataframe(table_MTO[[col_MTO]].head(10), use_container_width=True)
    with st.expander("Aperçu WGTID"):
        st.dataframe(table_WGTID[[col_WGTID_desc, col_WGTID_id]].head(10), use_container_width=True)

    st.subheader("3. Lancer le matching")
    seuil = st.slider("Seuil de score minimum à afficher (%)", 0, 100, 0)
    show_debug = st.checkbox("Afficher la colonne 'Attributs extraits' (debug)", value=False)

    if st.button("▶️ Lancer le mapping structuré", type="primary"):
        df_resultat = run_mapping(
            table_MTO.copy(), table_WGTID.copy(),
            col_MTO, col_WGTID_desc, col_WGTID_id
        )

        st.success(f"✅ Mapping terminé — {len(df_resultat)} lignes traitées")

        df_affiche = df_resultat[df_resultat["Score (%)"] >= seuil].copy()
        if not show_debug:
            df_affiche = df_affiche.drop(columns=["Attributs extraits (debug)"])

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


