#!/usr/bin/env python3
"""
Renseigne d'un coup vos identifiants AdSense et vos informations légales.

Exemple (PowerShell) :
  python configurer_site.py --editeur ca-pub-1234567890123456 --emplacement 1234567890 `
      --cle=-fb+5w+4e-db+86 --nom "Prénom Nom" --email contact@monsite.com `
      --adresse "Rue X, Yaoundé, Cameroun" --pays "Cameroun" `
      --hebergeur "Nom de l'hébergeur" --hebergeur-adresse "Adresse" --hebergeur-site https://hebergeur.com

Tous les arguments sont facultatifs : lancez-le plusieurs fois si besoin.
Attention : écrivez --cle=VALEUR avec le signe égal (la clé commence souvent par « - »).
"""
import argparse
import html
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent

CHAMPS = {   # option -> libellés "[À COMPLÉTER : ...]" à remplacer dans les pages légales
    "nom": ["nom ou raison sociale", "nom complet ou nom de l'entreprise", "nom"],
    "email": ["adresse e-mail de contact"],
    "adresse": ["adresse postale"],
    "pays": ["pays de l'éditeur"],
    "hebergeur": ["nom de l'hébergeur"],
    "hebergeur_adresse": ["adresse de l'hébergeur"],
    "hebergeur_site": ["site de l'hébergeur"],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--editeur", help="ID éditeur AdSense (ca-pub-0000000000000000)")
    ap.add_argument("--emplacement", help="data-ad-slot de l'unité in-feed (chiffres)")
    ap.add_argument("--cle", help="data-ad-layout-key de l'unité in-feed")
    for opt in CHAMPS:
        ap.add_argument("--" + opt.replace("_", "-"))
    a = ap.parse_args()

    if a.editeur and not re.fullmatch(r"ca-pub-\d{16}", a.editeur):
        sys.exit("❌ L'ID éditeur doit ressembler à ca-pub-1234567890123456 (16 chiffres).")
    if a.emplacement and not re.fullmatch(r"\d{6,15}", a.emplacement):
        sys.exit("❌ L'emplacement (data-ad-slot) ne contient que des chiffres.")

    modifies = []
    for f in list(RACINE.glob("*.html")) + [RACINE / "pub.js", RACINE / "ads.txt"]:
        t = f.read_text(encoding="utf-8")
        n = t
        if a.editeur:
            n = n.replace("ca-pub-XXXXXXXXXXXXXXXX", a.editeur)
            n = n.replace("pub-XXXXXXXXXXXXXXXX", a.editeur.replace("ca-", ""))
            n = re.sub(r"ca-pub-\d{16}", a.editeur, n) if f.name == "pub.js" else n
        if f.name == "pub.js":
            if a.emplacement:
                n = re.sub(r"(emplacement: ')[^']*(')", lambda m: m.group(1) + a.emplacement + m.group(2), n)
            if a.cle:
                n = re.sub(r"(cleMiseEnPage: ')[^']*(')", lambda m: m.group(1) + a.cle.replace("\\", "\\\\") + m.group(2), n)
        if f.suffix == ".html":
            for opt, libelles in CHAMPS.items():
                valeur = getattr(a, opt)
                if not valeur:
                    continue
                for lib in libelles:
                    motif = re.escape(f'<span class="a-completer">[À COMPLÉTER : {lib}]</span>')
                    n = re.sub(motif, lambda m: html.escape(valeur), n)
        if n != t:
            f.write_text(n, encoding="utf-8")
            modifies.append(f.name)

    print("✅ Fichiers modifiés :", ", ".join(modifies) if modifies else "aucun")
    restants = [f.name for f in RACINE.glob("*.html") if "a-completer" in f.read_text(encoding="utf-8")]
    if restants:
        print("⚠️  Il reste des champs « À COMPLÉTER » dans :", ", ".join(restants))
    if "XXXXXXXX" in (RACINE / "pub.js").read_text(encoding="utf-8"):
        print("ℹ️  Identifiants AdSense non renseignés : aucune publicité ne s'affichera (c'est voulu).")


if __name__ == "__main__":
    main()
