#!/usr/bin/env python3
"""
GOLDEN GAMER X - Import du catalogue (RAWG + Steam) vers des fichiers de données
découpés, prêts pour un gros catalogue.

Ce que fait le script :
  1. COLLECTE   : liste les jeux candidats de chaque catégorie, du plus récent au
                  plus ancien (peu de requêtes, 40 jeux par appel).
  2. DÉTAILS    : pour chaque jeu retenu, récupère synopsis, fiche technique,
                  captures, trailer, boutiques, DLC, série, configurations.
                  Chaque jeu est sauvegardé dès qu'il est terminé -> le script
                  se REPREND tout seul après une coupure ou un Ctrl+C.
  3. CONSTRUCTION : génère le dossier data/ lu par le site :
        data/meta.js            totaux, catégories, version
        data/pages/*.js         cartes du catalogue, par pages de 24 jeux
        data/recherche.js       index léger pour la barre de recherche
        data/jeux/<id>.js       fiche complète d'un jeu

Utilisation :
    pip install requests
    python robot_rawg.py                       # import (20 jeux / catégorie, 20 catégories)
    python robot_rawg.py --par-categorie 100   # plus de jeux (reprend l'existant)
    python robot_rawg.py --reconstruire        # régénère data/ sans appeler l'API
    python robot_rawg.py --migrer jeux.js      # convertit un ancien jeux.js
"""

import argparse
import hashlib
import html as htmllib
import json
import math
import os
import re
import sys
import time
from collections import Counter, namedtuple
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests

# ----------------------------- CONFIGURATION -----------------------------
API_KEY = os.environ.get("RAWG_API_KEY") or "f58c9c077bbf45219d4e5dbc5b3b7158"
BASE_URL = "https://api.rawg.io/api"
STEAM_URL = "https://store.steampowered.com/api/appdetails"

JEUX_PAR_CATEGORIE = 20          # minimum visé par catégorie (--par-categorie N)
MARGE_CANDIDATS = 1.5            # candidats listés = cible x 1.5 (certains échouent)
TAILLE_PAGE_API = 40             # maximum autorisé par RAWG
TAILLE_PAGE_SITE = 24            # jeux par page sur le site (doit rester 24 avec app.js)

# --- Critères de sélection ---
# Le script parcourt les années de la plus récente à ANNEE_MIN. Dans chaque année,
# les jeux sont pris du plus populaire au moins populaire. Il ne passe à une année
# plus ancienne que s'il manque encore des jeux, et n'abaisse le seuil de popularité
# que si toutes les années ont été parcourues sans atteindre l'objectif.
ANNEE_MIN = 2016                 # pas de jeux plus anciens (pas de rétro)
DATE_MAX = date.today().isoformat()   # jamais de jeux pas encore sortis
NOTE_MIN = 3.0                   # note joueurs RAWG minimum (sur 5)
AVIS_MIN = 5                     # nombre d'avis minimum pour que la note compte
SEUILS_POPULARITE = [500, 150]   # "added" RAWG : 1re passe très populaires, 2e passe populaires
SEUILS_LEGER = [500, 150, 50, 20]  # mode léger (gros catalogue) : on descend plus bas en popularité
MAX_PAGES_PAR_ANNEE = 5          # garde-fou (5 pages x 40 = 200 jeux max par année)
# Nouvelles sorties (carrousel de l'accueil + page nouveautes.html)
NOUVEAUTES_NOMBRE = 15
NOUVEAUTES_MIN_ADDED = 50        # évite les jeux totalement inconnus sortis hier
NOUVEAUTES_MIN_CAPTURES = 3      # captures d'écran minimum
NOUVEAUTES_MAX_EXAMINES = 150    # garde-fou : jeux "coûteux" examinés au maximum
EXCLURE_TAGS = {"retro"}         # tags RAWG exclus (ajoutez "pixel-graphics" pour couper le pixel art)
PAUSE_RAWG = 0.25                # secondes entre deux requêtes RAWG
PAUSE_STEAM = 1.5                # Steam limite à ~200 requêtes / 5 minutes
NB_SCREENSHOTS = 6
EXTRAS = True                    # DLC + série dans les fiches complètes (2 requêtes de plus par jeu)
UTILISER_CACHE = True            # réutilise les listes RAWG déjà téléchargées (7 jours)
DUREE_CACHE = 7 * 24 * 3600
IMG_PREFIX = "https://media.rawg.io/media/"
# --------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
CACHE = RACINE / ".cache"
FICHIER_CARTES = CACHE / "cartes.jsonl"
FICHIER_ECHECS = CACHE / "echecs.txt"
FICHIER_NOUVEAUTES = CACHE / "nouveautes.json"
FICHIER_REFUS = CACHE / "nouveautes_refus.json"
DOSSIER_API = CACHE / "api"
STATS = {"rawg": 0, "steam": 0}

Categorie = namedtuple("Categorie", "nom slug tag filtre min_added", defaults=(None,))

# Ordre de PRIORITÉ : les genres précis passent avant les genres très larges.
# - un jeu peut appartenir à PLUSIEURS catégories (ex. Action + RPG + Indé) ;
# - sa catégorie principale (couleur de l'étiquette) est la première de cette liste.
# min_added : seuil de popularité propre à la catégorie (les petits genres en ont peu).
CATEGORIES = [
    Categorie("HORREUR", "horreur", "horreur", {"tags": "horror"}),
    Categorie("COMBAT", "combat", "combat", {"genres": "fighting"}),
    Categorie("COURSE", "course", "course", {"genres": "racing"}),
    Categorie("SPORT", "sport", "sport", {"genres": "sports"}),
    Categorie("STRATÉGIE", "strategie", "stratégie", {"genres": "strategy"}),
    Categorie("FPS", "fps", "fps", {"genres": "shooter"}),
    Categorie("RPG", "rpg", "rpg", {"genres": "role-playing-games-rpg"}),
    Categorie("PLATEFORME", "plateforme", "plateforme", {"genres": "platformer"}),
    Categorie("PUZZLE", "puzzle", "puzzle", {"genres": "puzzle"}),
    Categorie("SIMULATION", "simulation", "simulation", {"genres": "simulation"}),
    Categorie("ARCADE", "arcade", "arcade", {"genres": "arcade"}),
    Categorie("MMO", "mmo", "mmo", {"genres": "massively-multiplayer"}, 100),
    Categorie("FAMILLE", "famille", "famille", {"genres": "family"}, 50),
    Categorie("CARTES", "cartes", "cartes", {"genres": "card"}, 30),
    Categorie("JEUX DE SOCIÉTÉ", "societe", "societe", {"genres": "board-games"}, 30),
    Categorie("ÉDUCATIF", "educatif", "educatif", {"genres": "educational"}, 20),
    Categorie("CASUAL", "casual", "casual", {"genres": "casual"}),
    Categorie("AVENTURE", "aventure", "aventure", {"genres": "adventure"}),
    Categorie("ACTION", "action", "action", {"genres": "action"}),
    Categorie("INDÉ", "inde", "inde", {"genres": "indie"}),
]
PAR_SLUG = {c.slug: c for c in CATEGORIES}
PAR_TAG = {c.tag: c for c in CATEGORIES}
RANG = {c.slug: i for i, c in enumerate(CATEGORIES)}

# Ordre d'affichage des boutons du site
ORDRE_NAV = ["action", "aventure", "combat", "rpg", "fps", "horreur", "course", "sport",
             "strategie", "inde", "plateforme", "puzzle", "simulation", "arcade", "casual",
             "mmo", "famille", "cartes", "societe", "educatif"]

# Contenu pour adultes : exclu du catalogue
TAGS_ADULTES = {"nsfw", "sexual-content", "hentai", "nudity", "erotic", "eroge",
                "adult", "adult-content", "porn"}

# Boutiques officielles connues de RAWG (id -> nom) et ordre d'affichage dans le menu
STORE_NAMES = {
    1: "Steam", 5: "GOG", 11: "Epic Games Store", 3: "PlayStation Store",
    2: "Xbox Store", 6: "Nintendo eShop", 9: "itch.io",
    8: "Google Play", 4: "App Store", 7: "Xbox 360 Store",
}
STORE_PRIORITY = [1, 5, 11, 3, 2, 6, 9, 8, 4, 7]

# Mode léger : RAWG ne donne que le NOM des boutiques, pas le lien du jeu. On propose
# alors la page de recherche officielle de la boutique pour ce jeu.
STORE_RECHERCHE = {
    1: "https://store.steampowered.com/search/?term={q}",
    5: "https://www.gog.com/en/games?query={q}",
    11: "https://store.epicgames.com/en-US/browse?q={q}",
    3: "https://store.playstation.com/en-us/search/{q}",
    2: "https://www.xbox.com/en-US/search?q={q}",
    6: "https://www.nintendo.com/us/search/?q={q}",
    9: "https://itch.io/search?q={q}",
    8: "https://play.google.com/store/search?q={q}&c=apps",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
ALLOWED_TAGS = "p|br|ul|ol|li|strong|em|b|i|h2|h3|h4"
SLUG_VALIDE = re.compile(r"[a-z0-9][a-z0-9_-]*")

session = requests.Session()
session.headers.update({"User-Agent": "GoldenGamerX-Importer/3.0"})


# ------------------------------- RÉSEAU -----------------------------------
def _fichier_cache(path, params):
    brut = json.dumps([path, sorted(params.items())], default=str)
    return DOSSIER_API / (hashlib.sha1(brut.encode()).hexdigest() + ".json")


def api_get(path, **params):
    """GET RAWG : paramètres isolés, retries, cache des listes, gestion du 429. None si échec."""
    fichier = None
    if UTILISER_CACHE and path == "games":     # seules les listes sont mises en cache
        fichier = _fichier_cache(path, params)
        if fichier.exists() and time.time() - fichier.stat().st_mtime < DUREE_CACHE:
            try:
                return json.loads(fichier.read_text(encoding="utf-8"))
            except ValueError:
                pass
    params["key"] = API_KEY
    url = f"{BASE_URL}/{path.lstrip('/')}"
    for tentative in range(1, 4):
        try:
            STATS["rawg"] += 1
            r = session.get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(5 * tentative)
                continue
            if r.status_code in (401, 403):
                sys.exit("❌ RAWG refuse la clé API (401/403). Vérifiez-la ou son quota mensuel.")
            r.raise_for_status()
            time.sleep(PAUSE_RAWG)
            donnees = r.json()
            if fichier is not None:
                DOSSIER_API.mkdir(parents=True, exist_ok=True)
                fichier.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
            return donnees
        except (requests.RequestException, ValueError) as exc:
            print(f"   ⚠️  {path} (tentative {tentative}/3) : {exc}")
            time.sleep(2 * tentative)
    return None


def steam_get(appid):
    """Fiche Steam en français (None si indisponible)."""
    for tentative in range(1, 4):
        try:
            STATS["steam"] += 1
            r = session.get(STEAM_URL, params={"appids": appid, "l": "french"}, timeout=20)
            if r.status_code in (429, 403):
                print("   ⏳ Steam demande de ralentir, pause...")
                time.sleep(30 * tentative)
                continue
            r.raise_for_status()
            time.sleep(PAUSE_STEAM)
            entree = r.json().get(str(appid)) or {}
            return entree.get("data") if entree.get("success") else None
        except (requests.RequestException, ValueError) as exc:
            print(f"   ⚠️  Steam {appid} (tentative {tentative}/3) : {exc}")
            time.sleep(3 * tentative)
    return None


# ------------------------------ NETTOYAGE ---------------------------------
def clean_html(raw):
    """Garde uniquement un HTML simple (titres, paragraphes, listes)."""
    raw = raw or ""
    raw = re.sub(r"(?is)<(script|style|iframe|video|object)\b.*?</\1>", "", raw)
    raw = re.sub(r"(?is)<img\b[^>]*>", "", raw)
    raw = re.sub(rf"(?i)</?(?!(?:{ALLOWED_TAGS})\b)[a-z][^>]*>", "", raw)
    raw = re.sub(rf"(?i)<({ALLOWED_TAGS})\b[^>]*>", r"<\1>", raw)
    raw = re.sub(r"(?i)<h[23]>", "<h4>", raw)
    raw = re.sub(r"(?i)</h[23]>", "</h4>", raw)
    raw = re.sub(r"(?i)(?:<br>\s*){3,}", "<br><br>", raw)
    raw = re.sub(r"(?i)<(p|li|h4)>\s*</\1>", "", raw)
    return raw.strip()


def strip_tags(raw):
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", raw or "")).split())


def short_description(text, limit=220):
    text = " ".join((text or "").split())
    if not text:
        return "Description à venir."
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def format_date(iso):
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} {MOIS[int(m) - 1]} {y}"
    except (ValueError, IndexError, AttributeError):
        return "N/C"


def extract_size(text):
    m = re.search(
        r"(?:Stockage|Storage|Espace disque|Disque dur|Hard Drive|Hard Disk|Disk Space)"
        r"[^0-9]{0,40}(\d+(?:[.,]\d+)?)\s*(GB|Go|MB|Mo)", text or "", re.I)
    if not m:
        return None
    valeur = float(m.group(1).replace(",", "."))
    if m.group(2).lower() in ("mb", "mo"):
        valeur /= 1024
    return f"{valeur:g} Go"


def rawg_resize(url, largeur):
    """Version redimensionnée d'une image RAWG (beaucoup plus légère)."""
    m = re.match(r"https://media\.rawg\.io/media/(games|screenshots)/(.+)$", url or "")
    if not m:
        return url
    return f"{IMG_PREFIX}resize/{largeur}/-/{m.group(1)}/{m.group(2)}"


# ------------------------------ EXTRACTION --------------------------------
def pick_store(stores, slug):
    """Boutique officielle : Steam > GOG > Epic > autres. Retourne aussi l'appid Steam."""
    par_id = {s["store_id"]: s["url"] for s in stores if s.get("url")}
    steam_id = None
    if 1 in par_id:
        m = re.search(r"/app/(\d+)", par_id[1])
        steam_id = m.group(1) if m else None
    for sid in STORE_PRIORITY:
        if sid in par_id:
            return STORE_NAMES[sid], par_id[sid], steam_id
    return "RAWG", f"https://rawg.io/games/{slug}", steam_id


def toutes_les_boutiques(stores):
    """Toutes les boutiques avec lien direct : [{"nom": ..., "url": ...}], Steam d'abord."""
    par_id = {}
    for st in stores:
        sid, url = st.get("store_id"), st.get("url") or ""
        if sid in STORE_NAMES and url.startswith("http") and sid not in par_id:
            par_id[sid] = url
    return [{"nom": STORE_NAMES[sid], "url": par_id[sid]} for sid in STORE_PRIORITY if sid in par_id]


def boutiques_recherche(g):
    """Mode léger : liens de recherche officiels pour les boutiques citées par RAWG."""
    ids = [x["store"].get("id") for x in g.get("stores") or [] if x.get("store")]
    q = quote(g["name"], safe="")
    return [{"nom": STORE_NAMES[sid], "url": STORE_RECHERCHE[sid].format(q=q), "recherche": True}
            for sid in STORE_PRIORITY if sid in ids and sid in STORE_RECHERCHE]


def steam_video(steam):
    for film in (steam or {}).get("movies") or []:
        for fmt in ("mp4", "webm"):
            fichiers = film.get(fmt) or {}
            url = fichiers.get("max") or fichiers.get("480")
            if url:
                return url.replace("http://", "https://")
    return ""


def rawg_video(game_id):
    data = api_get(f"games/{game_id}/movies") or {}
    for film in data.get("results", []):
        d = film.get("data") or {}
        url = d.get("max") or d.get("480")
        if url:
            return url
    return ""


def get_screenshots(game_id, steam):
    """RAWG d'abord, complété par Steam, sans doublons, 6 maximum."""
    data = api_get(f"games/{game_id}/screenshots", page_size=NB_SCREENSHOTS) or {}
    shots = [s["image"] for s in data.get("results", []) if s.get("image")]
    if len(shots) < NB_SCREENSHOTS and steam:
        for s in steam.get("screenshots") or []:
            url = (s.get("path_full") or "").split("?")[0]
            if url and url not in shots:
                shots.append(url)
    return shots[:NB_SCREENSHOTS]


def parse_req(req):
    """Config Steam (dict minimum/recommended) -> (html_minimum, html_recommande)."""
    if not isinstance(req, dict):
        return "", ""
    label = r"(?is)^\s*<strong>[^<]*</strong>\s*(?:<br>)?"
    mini = re.sub(label, "", clean_html(req.get("minimum") or ""))
    reco = re.sub(label, "", clean_html(req.get("recommended") or ""))
    return mini, reco


def get_requirements(detail, steam):
    """Retourne (html_minimum, html_recommande, texte_minimum_brut) pour PC."""
    mini, reco = parse_req((steam or {}).get("pc_requirements"))
    brut = strip_tags(mini)
    if not mini:  # secours : texte brut RAWG (anglais)
        for p in detail.get("platforms") or []:
            if p.get("platform", {}).get("slug") == "pc":
                r = p.get("requirements") or {}
                if r.get("minimum"):
                    mini = f"<p>{htmllib.escape(r['minimum'])}</p>"
                    brut = r["minimum"]
                if r.get("recommended"):
                    reco = f"<p>{htmllib.escape(r['recommended'])}</p>"
    return mini, reco, brut


def get_names(path, exclude="", limit=12):
    data = api_get(path, page_size=limit) or {}
    noms = [r["name"] for r in data.get("results", []) if r.get("name") and r["name"] != exclude]
    return noms[:limit]


def names(items, key="name"):
    return ", ".join(i[key] for i in items or [] if isinstance(i, dict) and i.get(key))


def esc(valeur):
    return htmllib.escape(str(valeur)) if valeur else ""


def li(label, valeur_html):
    return f"<li><strong>{label} :</strong> {valeur_html}</li>" if valeur_html else ""


def build_long_description(detail, steam, mini, reco, extras):
    steam = steam or {}
    about = clean_html(steam.get("about_the_game") or steam.get("detailed_description") or "")
    if not about:
        about = clean_html(detail.get("description") or "")
    if not about:
        about = "<p>Description à venir.</p>"
    elif not about.lstrip().startswith("<"):
        about = f"<p>{about}</p>"

    devs = names(detail.get("developers")) or ", ".join(steam.get("developers") or [])
    pubs = names(detail.get("publishers")) or ", ".join(steam.get("publishers") or [])
    genres = names(steam.get("genres"), "description") or names(detail.get("genres"))
    modes = names(steam.get("categories"), "description")
    tags = ", ".join(t["name"] for t in (detail.get("tags") or [])
                     if t.get("name") and t.get("language") == "eng")
    plateformes = ", ".join(
        p["platform"]["name"] for p in detail.get("platforms") or [] if p.get("platform"))
    boutiques = ", ".join(
        s["store"]["name"] for s in detail.get("stores") or [] if s.get("store"))
    langues = re.sub(r"\s+\*", "*", strip_tags(steam.get("supported_languages") or ""))
    if "*" in langues:
        langues += " (* = doublage audio)"

    age = steam.get("required_age")
    age_txt = f"{age}+" if str(age) not in ("", "0", "None") else ""
    esrb = (detail.get("esrb_rating") or {}).get("name") or ""
    classification = ", ".join(x for x in (age_txt and f"Âge requis {age_txt}",
                                           esrb and f"ESRB {esrb}") if x)
    note = ""
    if detail.get("rating") and detail.get("ratings_count"):
        note = f"{detail['rating']}/5 ({detail['ratings_count']} avis joueurs)"
    succes = (steam.get("achievements") or {}).get("total") or detail.get("achievements_count")
    manette = {"full": "Prise en charge complète", "partial": "Prise en charge partielle"}.get(
        steam.get("controller_support"), "")
    site = detail.get("website") or steam.get("website") or ""
    site_html = (f'<a href="{esc(site)}" target="_blank" rel="noopener noreferrer">{esc(site)}</a>'
                 if site.startswith("http") else "")

    infos = "".join([
        li("Développeur", esc(devs)),
        li("Éditeur", esc(pubs)),
        li("Date de sortie", esc(format_date(detail.get("released")))),
        li("Genres", esc(genres)),
        li("Modes de jeu et fonctionnalités", esc(modes)),
        li("Thèmes et mots-clés", esc(tags)),
        li("Plateformes", esc(plateformes)),
        li("Disponible sur", esc(boutiques)),
        li("Langues", esc(langues)),
        li("Classification d'âge", esc(classification)),
        li("Durée moyenne", f"environ {detail['playtime']} h" if detail.get("playtime") else ""),
        li("Note Metacritic", f"{detail['metacritic']}/100" if detail.get("metacritic") else ""),
        li("Note des joueurs (RAWG)", esc(note)),
        li("Succès", esc(succes)),
        li("Manette", esc(manette)),
        li("Site officiel", site_html),
    ])

    parts = [about, "<h4>Fiche technique</h4>", f"<ul>{infos}</ul>"]
    if extras.get("dlc"):
        parts += ["<h4>DLC et extensions</h4>",
                  "<ul>" + "".join(f"<li>{esc(n)}</li>" for n in extras["dlc"]) + "</ul>"]
    if extras.get("serie"):
        parts += ["<h4>Dans la même série</h4>",
                  "<ul>" + "".join(f"<li>{esc(n)}</li>" for n in extras["serie"]) + "</ul>"]
    if mini:
        parts += ["<h4>Configuration minimale (PC)</h4>", mini]
    if reco:
        parts += ["<h4>Configuration recommandée (PC)</h4>", reco]
    for label, cle in (("Mac", "mac_requirements"), ("Linux", "linux_requirements")):
        m, r = parse_req(steam.get(cle))
        if m:
            parts += [f"<h4>Configuration minimale ({label})</h4>", m]
        if r:
            parts += [f"<h4>Configuration recommandée ({label})</h4>", r]
    return "".join(parts)


def categories_du_jeu(detail, cat_origine=None):
    """Toutes les catégories d'un jeu (genres + tag horreur), principale en premier."""
    genres = {g.get("slug") for g in detail.get("genres") or []}
    tags = {t.get("slug") for t in detail.get("tags") or []}
    trouvees = [c for c in CATEGORIES
                if c.filtre.get("genres") in genres or c.filtre.get("tags") in tags]
    if cat_origine is not None and cat_origine not in trouvees:
        trouvees.append(cat_origine)
    return sorted(trouvees, key=lambda c: RANG[c.slug])


def construire_detail(cand, cat):
    """Récupère toutes les données d'un jeu. None si le jeu est inexploitable."""
    game_id = cand["id"]
    detail = api_get(f"games/{game_id}")
    if not detail or not detail.get("background_image"):
        return None

    slug = detail["slug"]
    if not SLUG_VALIDE.fullmatch(slug):
        return None
    stores = (api_get(f"games/{game_id}/stores") or {}).get("results", [])
    boutique, lien_boutique, steam_id = pick_store(stores, slug)
    boutiques = toutes_les_boutiques(stores) or [{"nom": "RAWG", "url": lien_boutique}]
    steam = steam_get(steam_id) if steam_id else None

    video = steam_video(steam) or rawg_video(game_id)
    shots = get_screenshots(game_id, steam) or [detail["background_image"]]
    mini, reco, brut = get_requirements(detail, steam)
    extras = {"dlc": [], "serie": []}
    if EXTRAS:
        extras = {
            "dlc": get_names(f"games/{game_id}/additions", exclude=detail["name"]),
            "serie": get_names(f"games/{game_id}/game-series", exclude=detail["name"]),
        }
    courte = strip_tags((steam or {}).get("short_description")) or detail.get("description_raw")
    cats = categories_du_jeu(detail, cat)
    principale = cats[0]

    return {
        "id": slug,
        "nom": detail["name"].upper(),
        "image": detail["background_image"],
        "categorie": principale.nom,
        "categorieSlug": principale.slug,
        "tagClass": principale.tag,
        "categories": [{"nom": c.nom, "slug": c.slug, "tagClass": c.tag} for c in cats],
        "taille": extract_size(brut) or "N/C",
        "sortie": (detail.get("released") or "")[:4] or "N/C",
        "dateSortie": detail.get("released") or "",
        "descriptionCourte": short_description(courte),
        "descriptionLongue": build_long_description(detail, steam, mini, reco, extras),
        "videoLocale": video,
        "screenshots": shots,
        "boutique": boutique,
        "lienBoutique": lien_boutique,
        "boutiques": boutiques,
        "boutiquesVerifiees": bool(stores),
        "niveau": "complet",
        "rawgId": game_id,
    }


# ------------------------------ ÉCRITURE ----------------------------------
def ecrire_js(chemin, cle, objet):
    """Écrit `GG.recevoir("cle", {...});` de façon atomique."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    corps = json.dumps(objet, ensure_ascii=False, separators=(",", ":"))
    corps = corps.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(f"GG.recevoir({json.dumps(cle)},{corps});\n", encoding="utf-8")
    tmp.replace(chemin)


def formats(detail):
    """Retourne (fiche complète, carte légère) à partir d'un jeu."""
    fiche = dict(detail)
    fiche["image"] = rawg_resize(detail["image"], 640)
    carte = {k: detail[k] for k in
             ("id", "nom", "categorie", "tagClass", "taille", "sortie", "descriptionCourte")}
    carte["image"] = rawg_resize(detail["image"], 420)
    # Autres catégories du jeu (la principale est déjà dans "categorie")
    carte["autres"] = [{"nom": c["nom"], "tagClass": c["tagClass"]}
                       for c in detail.get("categories", [])[1:3]]
    return fiche, carte


def enregistrer_jeu(detail):
    fiche, carte = formats(detail)
    ecrire_js(DATA / "jeux" / f"{detail['id']}.js", f"jeux/{detail['id']}", fiche)
    return {
        "slug": detail["id"],
        "categorieSlug": detail["categorieSlug"],
        "categories": [c["slug"] for c in detail.get("categories", [])] or [detail["categorieSlug"]],
        "dateSortie": detail.get("dateSortie") or "",
        "pop": detail.get("pop", 0),
        "niveau": detail.get("niveau", "complet"),
        "rawgId": detail.get("rawgId"),
        "carte": carte,
    }


def lire_cartes():
    cartes = {}
    if FICHIER_CARTES.exists():
        for ligne in FICHIER_CARTES.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(ligne)
                e.setdefault("categories", [e["categorieSlug"]])
                cartes[e["slug"]] = e
            except (ValueError, KeyError):
                continue  # ligne coupée par une interruption
    return cartes


def ajouter_carte(entree):
    CACHE.mkdir(exist_ok=True)
    with FICHIER_CARTES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")


# --------------------------- PHASES 1 et 2 --------------------------------
def admissible(g, seuil, verifier_note=True):
    """Jeu assez populaire, bien noté, récent (filtré par la date), non adulte, non rétro."""
    if (g.get("added") or 0) < seuil:
        return False
    if verifier_note and ((g.get("rating") or 0) < NOTE_MIN or (g.get("ratings_count") or 0) < AVIS_MIN):
        return False
    if not SLUG_VALIDE.fullmatch(g.get("slug") or ""):
        return False
    if (g.get("esrb_rating") or {}).get("slug") == "adults-only":
        return False
    return not ({t.get("slug") for t in g.get("tags") or []} & (TAGS_ADULTES | EXCLURE_TAGS))


def seuils_de(cat):
    if cat.min_added is not None:
        return [cat.min_added]
    return SEUILS_POPULARITE


def lister_candidats(cat, besoin, brut=False):
    """Candidats d'une catégorie : années récentes d'abord, populaires d'abord."""
    items, vus = [], set()
    annee_courante = date.today().year
    for seuil in seuils_de(cat):
        for annee in range(annee_courante, ANNEE_MIN - 1, -1):
            fin = DATE_MAX if annee == annee_courante else f"{annee}-12-31"
            for page in range(1, MAX_PAGES_PAR_ANNEE + 1):
                data = api_get("games", page=page, page_size=TAILLE_PAGE_API,
                               ordering="-added", dates=f"{annee}-01-01,{fin}",
                               exclude_additions="true", **cat.filtre)
                if not data or not data.get("results"):
                    break
                trop_bas = False
                for g in data["results"]:
                    if (g.get("added") or 0) < seuil:
                        trop_bas = True      # triés par popularité décroissante : on s'arrête
                        break
                    if g["slug"] in vus or not admissible(g, seuil):
                        continue
                    vus.add(g["slug"])
                    items.append(g if brut else
                                 {"id": g["id"], "slug": g["slug"], "name": g["name"],
                                  "pop": g.get("added") or 0})
                if trop_bas or not data.get("next"):
                    break
            if len(items) >= besoin:
                return items
    return items


def compter(cartes):
    c = Counter()
    for e in cartes.values():
        c.update(e["categories"])
    return c


def traiter(cible, cartes):
    compteurs = compter(cartes)
    echecs = set(FICHIER_ECHECS.read_text().split()) if FICHIER_ECHECS.exists() else set()
    besoin = math.ceil(cible * MARGE_CANDIDATS) + 5
    for cat in CATEGORIES:
        faits = compteurs[cat.slug]
        if faits >= cible:
            print(f"✔️  {cat.nom} : {faits} jeux déjà présents")
            continue
        print(f"\n📂 {cat.nom} : {faits}/{cible}  (recherche des jeux récents les mieux notés...)")
        candidats = lister_candidats(cat, besoin)
        for cand in candidats:
            if faits >= cible:
                break
            if cand["slug"] in cartes or cand["slug"] in echecs:
                continue
            detail = construire_detail(cand, cat)
            if not detail:
                echecs.add(cand["slug"])
                with FICHIER_ECHECS.open("a") as f:
                    f.write(cand["slug"] + "\n")
                print(f"   ⏭️  {cand['name']} ignoré (données incomplètes)")
                continue
            detail["pop"] = cand["pop"]
            entree = enregistrer_jeu(detail)
            ajouter_carte(entree)
            cartes[entree["slug"]] = entree
            compteurs.update(entree["categories"])
            faits = compteurs[cat.slug]
            video = "trailer" if detail["videoLocale"] else "sans trailer"
            print(f"   ✅ {detail['nom']} ({detail['sortie']}, {len(detail['screenshots'])} captures, {video})")
        if faits < cible:
            print(f"   ⚠️  Seulement {faits} jeux trouvés en {cat.nom} avec ces critères "
                  f"(note ≥ {NOTE_MIN}, depuis {ANNEE_MIN}).")


# ------------------------- MODE LÉGER (gros catalogue) --------------------
def clip_video(g):
    clip = g.get("clip") or {}
    clips = clip.get("clips") or {}
    return clips.get("full") or clip.get("clip") or clips.get("640") or ""


def construire_leger(g, cat):
    """Fiche construite uniquement avec les données de la liste RAWG (aucune requête en plus)."""
    cats = categories_du_jeu(g, cat)
    principale = cats[0]
    slug = g["slug"]
    released = g.get("released") or ""
    plateformes = ", ".join(p["platform"]["name"] for p in g.get("platforms") or [] if p.get("platform"))
    noms_cat = ", ".join(c.nom.capitalize() for c in cats[:3])
    courte = f"Jeu {noms_cat} sorti le {format_date(released)}"
    if plateformes:
        courte += f" sur {plateformes}"
    courte += "."
    if g.get("rating"):
        courte += f" Note des joueurs : {g['rating']}/5."

    tags = ", ".join(t["name"] for t in (g.get("tags") or [])[:15]
                     if t.get("name") and t.get("language") == "eng")
    boutiques = ", ".join(x["store"]["name"] for x in g.get("stores") or [] if x.get("store"))
    note = (f"{g['rating']}/5 ({g['ratings_count']} avis joueurs)"
            if g.get("rating") and g.get("ratings_count") else "")
    infos = "".join([
        li("Catégories", esc(", ".join(c.nom.capitalize() for c in cats))),
        li("Date de sortie", esc(format_date(released))),
        li("Plateformes", esc(plateformes)),
        li("Disponible sur", esc(boutiques)),
        li("Thèmes et mots-clés", esc(tags)),
        li("Classification d'âge", esc(((g.get("esrb_rating") or {}).get("name")) or "")),
        li("Durée moyenne", f"environ {g['playtime']} h" if g.get("playtime") else ""),
        li("Note Metacritic", f"{g['metacritic']}/100" if g.get("metacritic") else ""),
        li("Note des joueurs (RAWG)", esc(note)),
    ])
    shots = []
    for sh in g.get("short_screenshots") or []:
        if sh.get("image") and sh["image"] not in shots:
            shots.append(sh["image"])
    shots = shots[:NB_SCREENSHOTS] or [g["background_image"]]

    return {
        "id": slug,
        "nom": g["name"].upper(),
        "image": g["background_image"],
        "categorie": principale.nom,
        "categorieSlug": principale.slug,
        "tagClass": principale.tag,
        "categories": [{"nom": c.nom, "slug": c.slug, "tagClass": c.tag} for c in cats],
        "taille": "N/C",
        "sortie": released[:4] or "N/C",
        "dateSortie": released,
        "descriptionCourte": short_description(courte),
        "descriptionLongue": f"<h4>Fiche technique</h4><ul>{infos}</ul>",
        "videoLocale": clip_video(g),
        "screenshots": shots,
        "boutique": "RAWG",
        "lienBoutique": f"https://rawg.io/games/{slug}",
        "boutiques": boutiques_recherche(g) or [{"nom": "RAWG", "url": f"https://rawg.io/games/{slug}"}],
        "niveau": "leger",
        "rawgId": g["id"],
        "pop": g.get("added") or 0,
    }


def importer_leger(total, cartes):
    """~1 requête pour 40 jeux. Tours successifs jusqu'à atteindre `total` jeux."""
    global SEUILS_POPULARITE
    compteurs = compter(cartes)
    quota = math.ceil(total / len(CATEGORIES) * 0.8)   # prudent : on augmente tour après tour
    for tour in range(1, 11):
        print(f"\n🔁 Tour {tour} : jusqu'à {quota} jeux par catégorie")
        for cat in CATEGORIES:
            avant = len(cartes)
            for g in lister_candidats(cat, quota, brut=True):
                if g["slug"] in cartes or not g.get("background_image"):
                    continue
                entree = enregistrer_jeu(construire_leger(g, cat))
                ajouter_carte(entree)
                cartes[entree["slug"]] = entree
                compteurs.update(entree["categories"])
            print(f"   {cat.nom:<16} +{len(cartes) - avant:<5} (catégorie : {compteurs[cat.slug]} jeux)")
        print(f"   ➜ {len(cartes)} jeux au total")
        if len(cartes) >= total:
            break
        quota = int(quota * 1.25) + 1
    if len(cartes) < total:
        print(f"\n⚠️  {len(cartes)} jeux trouvés sur {total} demandés avec ces critères. "
              f"Pour en avoir plus : --annee-min 2010, --note-min 2.5 ou --seuils 500,150,50,20,5")


def lire_fiche(slug):
    fichier = DATA / "jeux" / f"{slug}.js"
    if not fichier.exists():
        return None
    m = re.match(r'GG\.recevoir\(("(?:[^"\\]|\\.)*"),(.*)\);\s*$', fichier.read_text(encoding="utf-8"), re.S)
    try:
        return json.loads(m.group(2)) if m else None
    except ValueError:
        return None


def entree_depuis_fiche(f):
    """Reconstitue une entrée de cache à partir d'une fiche déjà écrite dans data/jeux."""
    f = dict(f)
    f["image"] = re.sub(r"/media/resize/\d+/-/", "/media/", f.get("image", ""))
    _, carte = formats(f)
    cats = [c["slug"] for c in f.get("categories", [])] or [f["categorieSlug"]]
    return {"slug": f["id"], "categorieSlug": f["categorieSlug"], "categories": cats,
            "dateSortie": f.get("dateSortie") or "", "pop": f.get("pop", 0),
            "niveau": f.get("niveau", "complet"), "rawgId": f.get("rawgId"), "carte": carte}


def amorcer_depuis_data():
    """Si le cache est absent mais data/jeux existe : relit les fiches (sans rien écrire dans le cache)."""
    cartes = {}
    for fichier in (DATA / "jeux").glob("*.js"):
        f = lire_fiche(fichier.stem)
        if f and f.get("id") and f.get("categorieSlug"):
            cartes[f["id"]] = entree_depuis_fiche(f)
    return cartes


def fiche_convient_nouveaute(f):
    """Fiche complète avec synopsis, assez de captures ET une vidéo."""
    return bool(f and f.get("niveau", "complet") == "complet" and f.get("videoLocale")
                and len(f.get("screenshots") or []) >= NOUVEAUTES_MIN_CAPTURES
                and (f.get("descriptionCourte") or "") not in ("", "Description à venir."))


def importer_nouveautes(nombre, cartes):
    """Les `nombre` jeux sortis les plus récemment (jamais à venir) avec jaquette, synopsis,
    captures et vidéo. Ils rejoignent aussi le catalogue pour que leur fiche existe."""
    annee_courante = date.today().year
    choisis, examines, vus = [], 0, set()
    try:
        refus = json.loads(FICHIER_REFUS.read_text(encoding="utf-8")) if FICHIER_REFUS.exists() else {}
    except ValueError:
        refus = {}
    limite = (datetime.now().timestamp()) - 7 * 24 * 3600
    refus = {k: v for k, v in refus.items() if v > limite}      # on les retente après 7 jours
    print(f"🆕 Recherche des {nombre} nouveautés (jeux sortis jusqu'au {DATE_MAX}, vidéo + synopsis + captures)")
    for annee in (annee_courante, annee_courante - 1):
        fin = DATE_MAX if annee == annee_courante else f"{annee}-12-31"
        for page in range(1, 30):
            if len(choisis) >= nombre or examines >= NOUVEAUTES_MAX_EXAMINES:
                break
            data = api_get("games", page=page, page_size=TAILLE_PAGE_API, ordering="-released",
                           dates=f"{annee}-01-01,{fin}", exclude_additions="true")
            if not data or not data.get("results"):
                break
            for g in data["results"]:
                if len(choisis) >= nombre or examines >= NOUVEAUTES_MAX_EXAMINES:
                    break
                slug = g.get("slug") or ""
                if slug in vus or slug in refus or not g.get("background_image"):
                    continue
                if not admissible(g, NOUVEAUTES_MIN_ADDED, verifier_note=False):
                    continue
                vus.add(slug)
                existante = lire_fiche(slug) if slug in cartes else None
                if fiche_convient_nouveaute(existante):          # déjà importée : aucune requête
                    choisis.append(slug)
                    print(f"   ✅ {existante['nom']} ({g.get('released')}) - déjà dans le catalogue")
                    continue
                cats = categories_du_jeu(g)
                if not cats:
                    continue
                examines += 1
                detail = construire_detail({"id": g["id"], "slug": slug, "name": g["name"]}, cats[0])
                if not fiche_convient_nouveaute(detail):
                    refus[slug] = datetime.now().timestamp()
                    print(f"   ⏭️  {g['name']} : il manque la vidéo, le synopsis ou les captures")
                    continue
                detail["pop"] = g.get("added") or 0
                entree = enregistrer_jeu(detail)
                ajouter_carte(entree)
                cartes[entree["slug"]] = entree
                choisis.append(slug)
                print(f"   ✅ {detail['nom']} ({detail['dateSortie']}, {len(detail['screenshots'])} captures)")
        if len(choisis) >= nombre:
            break
    CACHE.mkdir(exist_ok=True)
    FICHIER_REFUS.write_text(json.dumps(refus), encoding="utf-8")
    FICHIER_NOUVEAUTES.write_text(json.dumps({"genere": datetime.now().isoformat(timespec="seconds"),
                                              "slugs": choisis}), encoding="utf-8")
    if len(choisis) < nombre:
        print(f"   ⚠️  Seulement {len(choisis)} nouveautés complètes trouvées sur {nombre} demandées.")


def ecrire_nouveautes(cartes):
    """Écrit data/nouveautes.js (ou le supprime s'il n'y a plus de sélection valide)."""
    cible = DATA / "nouveautes.js"
    items = []
    if FICHIER_NOUVEAUTES.exists():
        try:
            slugs = json.loads(FICHIER_NOUVEAUTES.read_text(encoding="utf-8")).get("slugs", [])
        except ValueError:
            slugs = []
        for sl in slugs:
            e = cartes.get(sl)
            if e:
                c = e["carte"]
                items.append({"id": c["id"], "nom": c["nom"], "image": c["image"],
                              "dateSortie": e["dateSortie"], "categorie": c["categorie"],
                              "tagClass": c["tagClass"]})
    items.sort(key=lambda x: x["dateSortie"], reverse=True)
    if items:
        ecrire_js(cible, "nouveautes", items)
    elif cible.exists():
        cible.unlink()    # évite un carrousel avec des liens vers des fiches disparues


def rafraichir_boutiques(budget=None):
    """Ajoute à CHAQUE fiche déjà importée la liste complète des boutiques (1 requête par jeu).
    Ne touche à rien d'autre. Les fiches déjà vérifiées sont ignorées."""
    fiches = sorted((DATA / "jeux").glob("*.js"))
    print(f"🛒 Mise à jour des boutiques : {len(fiches)} fiches examinées")
    mises_a_jour = 0
    for fichier in fiches:
        if budget and STATS["rawg"] >= budget:
            print(f"⏸️  Budget de {budget} requêtes atteint : relancez plus tard pour continuer.")
            break
        m = re.match(r'GG\.recevoir\(("(?:[^"\\]|\\.)*"),(.*)\);\s*$', fichier.read_text(encoding="utf-8"), re.S)
        if not m:
            continue
        try:
            fiche = json.loads(m.group(2))
        except ValueError:
            continue
        if fiche.get("boutiquesVerifiees"):
            continue
        ident = fiche.get("rawgId") or fiche.get("id") or fichier.stem
        stores = (api_get(f"games/{ident}/stores") or {}).get("results", [])
        liste = toutes_les_boutiques(stores)
        if not liste:
            print(f"   ⏭️  {fichier.stem} : aucune boutique trouvée")
            continue
        fiche["boutiques"] = liste
        fiche["boutique"], fiche["lienBoutique"] = liste[0]["nom"], liste[0]["url"]
        fiche["boutiquesVerifiees"] = True
        ecrire_js(fichier, json.loads(m.group(1)), fiche)
        mises_a_jour += 1
        print(f"   ✅ {fichier.stem} : {', '.join(b['nom'] for b in liste)}")
    print(f"🛒 {mises_a_jour} fiches mises à jour.")


def enrichir(nombre, cartes, budget=None):
    """Fiches complètes (synopsis, config, trailer, boutiques...) pour les jeux les plus populaires."""
    a_faire = sorted((e for e in cartes.values() if e.get("niveau") == "leger" and e.get("rawgId")),
                     key=lambda e: e["pop"], reverse=True)[:nombre]
    print(f"✨ Enrichissement de {len(a_faire)} jeux (les plus populaires d'abord)")
    for i, e in enumerate(a_faire, 1):
        if budget and STATS["rawg"] >= budget:
            print(f"⏸️  Budget de {budget} requêtes RAWG atteint : relancez demain ou le mois prochain.")
            return
        cat = PAR_SLUG[e["categorieSlug"]]
        detail = construire_detail({"id": e["rawgId"], "slug": e["slug"], "name": e["slug"]}, cat)
        if not detail:
            print(f"   ⏭️  {e['slug']} : enrichissement impossible")
            continue
        detail["pop"] = e["pop"]
        entree = enregistrer_jeu(detail)
        ajouter_carte(entree)
        cartes[entree["slug"]] = entree
        print(f"   ✅ [{i}/{len(a_faire)}] {detail['nom']} (requêtes RAWG utilisées : {STATS['rawg']})")


# ------------------------------ PHASE 3 -----------------------------------
def construire_site(cartes, nettoyer=False):
    if not cartes:
        print("Aucun jeu à publier.")
        return
    if nettoyer:  # supprime les fiches de jeux qui ne font plus partie du catalogue
        for fiche in (DATA / "jeux").glob("*.js"):
            if fiche.stem not in cartes:
                fiche.unlink()
    jeux = sorted(cartes.values(), key=lambda e: (e["dateSortie"], e["pop"]), reverse=True)

    # Nettoyage des anciennes pages (les fiches jeux/ sont conservées)
    for ancien in (DATA / "pages").glob("*.js"):
        ancien.unlink()

    def ecrire_pages(prefixe, liste):
        nb = math.ceil(len(liste) / TAILLE_PAGE_SITE)
        for n in range(nb):
            lot = liste[n * TAILLE_PAGE_SITE:(n + 1) * TAILLE_PAGE_SITE]
            ecrire_js(DATA / "pages" / f"{prefixe}-{n + 1}.js", f"pages/{prefixe}-{n + 1}",
                      [e["carte"] for e in lot])
        return nb

    par_slug_nav = sorted(CATEGORIES, key=lambda c: ORDRE_NAV.index(c.slug))
    meta_cats = []
    for cat in par_slug_nav:
        liste = [e for e in jeux if cat.slug in e["categories"]]
        meta_cats.append({"nom": cat.nom, "slug": cat.slug, "tagClass": cat.tag,
                          "total": len(liste),
                          "pages": ecrire_pages(cat.slug, liste) if liste else 0})
    pages_tous = ecrire_pages("tous", jeux)

    index_cat = {c["slug"]: i for i, c in enumerate(meta_cats)}
    recherche = []
    for e in jeux:
        c = e["carte"]
        image = c["image"][len(IMG_PREFIX):] if c["image"].startswith(IMG_PREFIX) else c["image"]
        idx = [index_cat[sl] for sl in e["categories"] if sl in index_cat]  # principale en premier
        recherche.append([c["id"], c["nom"], idx, c["sortie"], image])
    ecrire_js(DATA / "recherche.js", "recherche", recherche)

    meta = {
        "version": datetime.now().strftime("%Y%m%d%H%M%S"),
        "genere": datetime.now().isoformat(timespec="seconds"),
        "total": len(jeux),
        "pages": pages_tous,
        "taillePage": TAILLE_PAGE_SITE,
        "imgPrefix": IMG_PREFIX,
        "categories": meta_cats,
    }
    ecrire_nouveautes(cartes)
    meta["nouveautes"] = (DATA / "nouveautes.js").exists()   # évite une requête vers un fichier absent
    ecrire_js(DATA / "meta.js", "meta", meta)
    print(f"\n🎮 Site généré : {len(jeux)} jeux, {pages_tous} pages -> {DATA}")


# ------------------------------ MIGRATION ---------------------------------
def migrer(chemin):
    """Convertit un ancien jeux.js (const jeuxData = [...]) vers le nouveau format."""
    texte = Path(chemin).read_text(encoding="utf-8")
    liste = json.loads(texte[texte.index("["):texte.rindex("]") + 1])
    cartes = lire_cartes()
    for g in liste:
        cat = PAR_TAG.get(g.get("tagClass"))
        if not cat or not SLUG_VALIDE.fullmatch(g.get("id", "")):
            continue
        sortie = str(g.get("sortie", ""))
        detail = {k: g.get(k, "") for k in (
            "id", "nom", "image", "taille", "sortie", "descriptionCourte", "descriptionLongue",
            "videoLocale", "screenshots", "boutique", "lienBoutique")}
        detail.update({"categorie": cat.nom, "categorieSlug": cat.slug, "tagClass": cat.tag,
                       "categories": [{"nom": cat.nom, "slug": cat.slug, "tagClass": cat.tag}],
                       "dateSortie": g.get("dateSortie") or (f"{sortie}-01-01" if sortie.isdigit() else ""),
                       "pop": 0})
        detail["descriptionLongue"] = clean_html(detail["descriptionLongue"])
        if g.get("lienBoutique"):
            detail["boutiques"] = [{"nom": g.get("boutique") or "RAWG", "url": g["lienBoutique"]}]
        entree = enregistrer_jeu(detail)
        ajouter_carte(entree)
        cartes[entree["slug"]] = entree
    print(f"📦 {len(liste)} jeux migrés.")
    construire_site(cartes)


# --------------------------------- MAIN -----------------------------------
def main():
    global ANNEE_MIN, NOTE_MIN, SEUILS_POPULARITE, EXTRAS, UTILISER_CACHE
    ap = argparse.ArgumentParser(description="Import du catalogue GOLDEN GAMER X")
    ap.add_argument("--mode", choices=["complet", "leger"], default="complet",
                    help="complet : fiches détaillées (~6 requêtes/jeu) | leger : gros catalogue (~1 requête/40 jeux)")
    ap.add_argument("--par-categorie", type=int, default=JEUX_PAR_CATEGORIE,
                    help="mode complet : nombre de jeux visés par catégorie")
    ap.add_argument("--total", type=int, default=10000, help="mode léger : nombre de jeux visé")
    ap.add_argument("--enrichir", type=int, metavar="N",
                    help="passe en fiche complète les N jeux légers les plus populaires")
    ap.add_argument("--budget", type=int, help="enrichissement : arrêt après N requêtes RAWG")
    ap.add_argument("--nouveautes", nargs="?", type=int, const=NOUVEAUTES_NOMBRE, metavar="N",
                    help=f"met à jour le carrousel « Nouvelles sorties » (défaut {NOUVEAUTES_NOMBRE} jeux)")
    ap.add_argument("--boutiques", action="store_true",
                    help="met à jour la liste des boutiques de toutes les fiches déjà importées (1 requête/jeu)")
    ap.add_argument("--annee-min", type=int, help=f"année de sortie minimale (défaut {ANNEE_MIN})")
    ap.add_argument("--note-min", type=float, help=f"note joueurs minimale sur 5 (défaut {NOTE_MIN})")
    ap.add_argument("--seuils", help="seuils de popularité séparés par des virgules (ex. 500,150,50)")
    ap.add_argument("--sans-dlc-serie", action="store_true", help="économise 2 requêtes par fiche complète")
    ap.add_argument("--sans-cache", action="store_true", help="ignore les listes RAWG déjà téléchargées")
    ap.add_argument("--reconstruire", action="store_true",
                    help="régénère data/ depuis le cache, sans appeler l'API")
    ap.add_argument("--migrer", metavar="JEUX_JS", help="convertit un ancien jeux.js")
    args = ap.parse_args()

    if args.annee_min:
        ANNEE_MIN = args.annee_min
    if args.note_min is not None:
        NOTE_MIN = args.note_min
    if args.sans_dlc_serie:
        EXTRAS = False
    if args.sans_cache:
        UTILISER_CACHE = False
    if args.seuils:
        SEUILS_POPULARITE = [int(x) for x in args.seuils.split(",")]
    elif args.mode == "leger":
        SEUILS_POPULARITE = SEUILS_LEGER

    if args.migrer:
        return migrer(args.migrer)
    if args.reconstruire:
        return construire_site(lire_cartes())

    if args.boutiques:
        rafraichir_boutiques(args.budget)
        print(f"📊 Requêtes RAWG : {STATS['rawg']}")
        return

    cartes = lire_cartes()
    if args.nouveautes and (DATA / "jeux").exists():
        # On ne touche pas au reste du catalogue : on repart de toutes les fiches déjà publiées
        # dans data/, puis on superpose le cache.
        base = amorcer_depuis_data()
        base.update(cartes)
        cartes = base
        print(f"   ({len(cartes)} jeux déjà publiés conservés)")
    print(f"   Critères : sortis depuis {ANNEE_MIN}, note ≥ {NOTE_MIN}/5, jamais de jeux pas encore sortis, "
          f"récents et populaires d'abord (seuils {SEUILS_POPULARITE}).")
    print("   Ctrl+C à tout moment : la progression est sauvegardée.")

    try:
        if args.nouveautes:
            importer_nouveautes(args.nouveautes, cartes)
        elif args.enrichir:
            enrichir(args.enrichir, cartes, args.budget)
        elif args.mode == "leger":
            print(f"🌐 Import LÉGER : objectif ~{args.total} jeux (1 requête RAWG pour 40 jeux)")
            importer_leger(args.total, cartes)
        else:
            cible = args.par_categorie
            compteurs = compter(cartes)
            manquants = sum(max(0, cible - compteurs[c.slug]) for c in CATEGORIES)
            print(f"🌐 Import COMPLET : {cible} jeux x {len(CATEGORIES)} catégories "
                  f"({manquants} jeux restants, ~{manquants * (6 if EXTRAS else 4)} requêtes RAWG)")
            traiter(cible, cartes)
    except KeyboardInterrupt:
        print("\n⏹️  Interrompu : la progression est sauvegardée, relancez pour reprendre.")
    finally:
        construire_site(cartes, nettoyer=not args.nouveautes)
        print(f"📊 Requêtes cette exécution : RAWG {STATS['rawg']} (quota gratuit : 20 000 / mois), "
              f"Steam {STATS['steam']}")


if __name__ == "__main__":
    main()
