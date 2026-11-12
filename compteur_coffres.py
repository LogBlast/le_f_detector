"""
le_f_detector — compteur de coffres Fortnite / Fortnite chest counter.

Compte les coffres ouverts en direct (détection à l'écran) et lit les replays après chaque partie
pour les coffres à esprit, rares et cassés. Ne touche jamais au jeu : il regarde l'écran, comme OBS,
et lit les fichiers .replay que Fortnite enregistre.

Commandes :
    py compteur_coffres.py              lancer le compteur (configuration au premier lancement)
    py compteur_coffres.py calibrer     refaire le calibrage de la détection
    py compteur_coffres.py config       refaire la configuration (langue, nombre de départ, calibrage)
    py compteur_coffres.py carte        option : carte de tes coffres et chemin conseillé (data/carte.html)
Options : debug (affiche la ressemblance en direct), sans-overlay (pas de compteur à l'écran),
          minicarte (carte en direct dans le compteur, avec les 3 prochains coffres ; minicarte-config avant)
Raccourcis : F8 = +1   F7 = -1   F10 / Ctrl+C = quitter

Voir README.md pour l'installation.
"""

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import mss
import numpy as np
from pynput import keyboard

MSS = getattr(mss, "MSS", None) or mss.mss

# ---------- fichiers ----------
DOSSIER = Path(__file__).resolve().parent
ASSETS = DOSSIER / "assets"
DATA = DOSSIER / "data"                          # données de l'utilisateur (ignorées par git)
REGLAGES = DATA / "reglages.json"                # langue
CALIBRATION = DATA / "calibration.json"          # zone du message à l'écran
MODELE = DATA / "modele_coffre.png"              # mot violet capturé au calibrage
SAUVEGARDE = DATA / "compteur.json"              # total + heure de chaque coffre compté
TEXTE_OBS = DATA / "compteur.txt"                # pour une source texte OBS
RESULTATS_REPLAYS = DATA / "replays.json"        # début du suivi + résultat de chaque replay
POSITIONS = DATA / "positions.json"              # option carte : positions lues dans chaque replay
CARTE = DATA / "carte.html"                      # option carte : page générée depuis carte_modele.html
MINICARTE_ZONE = DATA / "minicarte.json"         # option minicarte : emplacement de la minicarte à l'écran
LECTEUR = DOSSIER / "lecteur" / "LecteurCoffres.dll"
DOSSIER_DEMOS = Path(os.environ.get("LOCALAPPDATA", "")) / "FortniteGame" / "Saved" / "Demos"

# ---------- réglages ----------
SEUIL = 0.70                 # ressemblance minimale (0-1). Baisse si ça rate, monte si faux positifs
DELAI_MIN = 1.5              # secondes minimum entre deux coffres comptés
MARGE = 250                  # pixels de marge autour de la zone (le message bouge un peu)
ECRAN = 1                    # 1 = écran principal
OVERLAY_X, OVERLAY_Y = 15, 110   # position du compteur à l'écran (pixels)
AJOUTER_CASSES = True        # total = coffres ouverts + coffres cassés
CORRIGER_AVEC_REPLAY = True  # en fin de partie, le nombre de coffres ouverts est recalé sur le replay
# Chance d'obtenir Pirate Shop Access par coffre en partie normale : 1 sur 137 500 (taux donné par
# Fortnite Status). Les "Treasure Hours" augmentent ce taux : non pris en compte.
CHANCE_TOKEN = 1 / 137_500
# Option carte : replay (mètres) -> pixels de data/carte.*. Calé sur l'image officielle 1920 px de la saison de
# novembre 2026 avec la formule de fortnite.gg (carré de 3 km, X vers la droite, Y vers le bas) et le contour de l'île.
# o = orientation (0..7, voir ORIENT), s = pixels par mètre, tx / ty = décalage. Nouvelle image : recaler.
CALAGE_CARTE = {"o": 0, "s": 0.85, "tx": 811, "ty": 786}
ORIENT = [(1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0), (-1, 0, 0, 1), (0, 1, 1, 0), (1, 0, 0, -1), (0, -1, -1, 0)]
MINIMAP_METRES = 300         # côté de la zone affichée par la minicarte en direct

ARGS = [a.lower() for a in sys.argv[1:]]
DEBUG = "debug" in ARGS
MINICARTE = "minimap" in ARGS or "minicarte" in ARGS

# Couleur violette du mot "COFFRE" / "CHEST" (HSV d'OpenCV)
VIOLET_BAS = np.array([122, 110, 130])
VIOLET_HAUT = np.array([148, 255, 255])

FOND, GRIS, DORE = "#1c1c28", "#9a9ab0", "#ffd23f"


# ---------- langue ----------
LANGUE = "fr"


def T(fr, en):
    return fr if LANGUE == "fr" else en


def lire_json(chemin, defaut=None):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except Exception:
        return defaut


def ecrire_json(chemin, valeur):
    DATA.mkdir(exist_ok=True)
    tmp = Path(f"{chemin}.{threading.get_ident()}.tmp")  # un fichier temporaire par thread : jamais partagé
    tmp.write_text(json.dumps(valeur, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(chemin)


def migrer_anciens_fichiers():
    """Les premières versions rangeaient tout à côté du script : on déplace dans data/."""
    anciens = {"config.json": CALIBRATION, "modele_coffre.png": MODELE, "compteur.json": SAUVEGARDE,
               "compteur.txt": TEXTE_OBS, "replays_suivi.json": RESULTATS_REPLAYS}
    # fichiers devenus inutiles
    for inutile in ("replays_coffres.json", "lecteur/Microsoft.Extensions.Logging.Abstractions.dll"):
        try:
            (DOSSIER / inutile).unlink(missing_ok=True)
        except OSError:
            pass
    if not any((DOSSIER / a).exists() for a in anciens) or REGLAGES.exists():
        return
    DATA.mkdir(exist_ok=True)
    for ancien, nouveau in anciens.items():
        if (DOSSIER / ancien).exists() and not nouveau.exists():
            shutil.move(str(DOSSIER / ancien), str(nouveau))
    ecrire_json(REGLAGES, {"langue": "fr"})


# ---------- compteur ----------
VERROU = threading.RLock()  # la détection écran, la correction replay et l'arrêt modifient le compteur en parallèle


def charger_etat():
    d = lire_json(SAUVEGARDE, {}) or {}
    return {"total": d.get("total", 0), "detections": d.get("detections", [])}


def sauver(etat):
    with VERROU:
        limite = time.time() - 3 * 86400  # on garde 3 jours de détections
        etat["detections"] = [t for t in etat["detections"] if t > limite]
        ecrire_json(SAUVEGARDE, {"total": etat["total"], "maj": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "detections": etat["detections"]})
        TEXTE_OBS.write_text(T(f"Coffres : {etat['total']}", f"Chests: {etat['total']}"), encoding="utf-8")


def ajouter_coffre(etat, n=1):
    with VERROU:
        etat["total"] += n
        if n > 0:
            etat["detections"].extend([time.time()] * n)
        elif etat["detections"]:
            del etat["detections"][n:]  # F7 : retire les dernières détections
        sauver(etat)


def heure():
    return time.strftime("%H:%M:%S")


# ---------- configuration (premier lancement) ----------
def choix(question, options, defaut=1):
    print(question)
    for i, o in enumerate(options, 1):
        print(f"  {i}) {o}")
    while True:
        r = input("> ").strip()
        if r == "":
            return defaut
        if r.isdigit() and 1 <= int(r) <= len(options):
            return int(r)


def configurer():
    global LANGUE
    print("\n=== le_f_detector — configuration ===\n")
    LANGUE = "fr" if choix("Langue / Language :", ["Français", "English"]) == 1 else "en"
    ecrire_json(REGLAGES, {"langue": LANGUE})

    print()
    c = choix(T("Combien de coffres as-tu déjà ouverts cette saison ?",
                "How many chests have you already opened this season?"),
              [T("0 (par défaut)", "0 (default)"),
               T("1000 (maximum du compteur de la quête Fortnite)", "1000 (maximum of the Fortnite quest counter)"),
               T("Autre : je tape mon nombre", "Other: I type my number")])
    depart = {1: 0, 2: 1000}.get(c)
    while depart is None:
        r = input(T("Ton nombre de coffres : ", "Your number of chests: ")).strip().replace(" ", "")
        if r.isdigit():
            depart = int(r)
    sauver({"total": depart, "detections": []})
    # les coffres esprit / rares / cassés sont comptés à partir de maintenant
    ecrire_json(RESULTATS_REPLAYS, {"depuis": time.time(), "replays": {}})
    print(T(f"Départ : {depart} coffres.", f"Starting at {depart} chests."))

    print()
    if choix(T("Calibrer la détection maintenant ? (Fortnite doit être lancé)",
               "Calibrate the detection now? (Fortnite must be running)"),
             [T("Oui", "Yes"), T("Plus tard", "Later")]) == 1:
        calibrer()
    else:
        print(T("Pour calibrer plus tard : py compteur_coffres.py calibrer",
                "To calibrate later: py compteur_coffres.py calibrate"))

    print()
    verifier_replays(afficher_ok=True)
    print()


def verifier_replays(afficher_ok=False):
    """Vérifie ce qu'il faut pour lire les replays. Renvoie le chemin de dotnet, ou None."""
    dotnet = shutil.which("dotnet")
    ok = True
    if not LECTEUR.exists():
        ok = False
        print(T("✖ Dossier « lecteur » introuvable : esprit / rares / cassés ne seront pas comptés (voir README).",
                "✖ \"lecteur\" folder not found: sprite / rare / broken chests won't be counted (see README)."))
    if not dotnet:
        ok = False
        print(T("✖ Runtime .NET 10 manquant : winget install Microsoft.DotNet.Runtime.10",
                "✖ .NET 10 runtime missing: winget install Microsoft.DotNet.Runtime.10"))
    if not DOSSIER_DEMOS.exists():
        print(T("✖ Aucun replay : dans Fortnite, Paramètres > Jeu > Rediffusions > Enregistrer les rediffusions : Oui",
                "✖ No replays: in Fortnite, Settings > Game > Replays > Record Replays: On"))
    elif ok and afficher_ok:
        print(T("✔ Lecture des replays prête.", "✔ Replay reading ready."))
    return dotnet if ok else None


# ---------- calibrage ----------
def masque_violet(img_bgr):
    """Garde seulement les pixels violets (le mot COFFRE / CHEST) : le décor disparaît."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return cv2.GaussianBlur(cv2.inRange(hsv, VIOLET_BAS, VIOLET_HAUT), (5, 5), 0)


def capture_f9():
    """Attend F9 et renvoie une capture de l'écran du jeu."""
    capture = {}

    def touche(k):
        if k == keyboard.Key.f9:
            with MSS() as sct:
                capture["img"] = cv2.cvtColor(np.array(sct.grab(sct.monitors[ECRAN])), cv2.COLOR_BGRA2BGR)
            return False

    with keyboard.Listener(on_press=touche) as l:
        l.join()
    return capture["img"]


def selection(img, consigne):
    """L'utilisateur encadre une zone de img ; renvoie (x, y, w, h) ou None."""
    print(consigne)
    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    x, y, w, h = cv2.selectROI("Calibration", img, showCrosshair=True)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        print(T("Rien sélectionné, recommence.", "Nothing selected, try again."))
        return None
    return int(x), int(y), int(w), int(h)


def configurer_minicarte():
    """Option minicarte : enregistre l'emplacement de la minicarte à l'écran."""
    print(T("Dans une partie, appuie sur F9 (la minicarte doit être visible).",
            "In a match, press F9 (the minimap must be visible)."))
    img = capture_f9()
    zone = selection(img, T("Encadre exactement le carré de la minicarte, sans le cadre, puis Entrée.",
                            "Select exactly the minimap square, without its frame, then Enter."))
    if not zone:
        return
    x, y, w, h = zone
    DATA.mkdir(exist_ok=True)
    ecrire_json(MINICARTE_ZONE, {"x": x, "y": y, "w": w, "h": h})
    print(T("✔ Minicarte configurée.", "✔ Minimap set up."))


def calibrer():
    print(T("Dans Fortnite, ouvre un coffre et appuie sur F9 pendant que le message « +XP COFFRE » est affiché...",
            "In Fortnite, open a chest and press F9 while the \"+XP CHEST\" message is on screen..."))
    img = capture_f9()

    # A tight box also matches the other chest types: a wide margin keeps only regular chests.
    zone = selection(img, T("Encadre TOUT le mot violet (COFFRE) avec une GRANDE marge tout autour, puis appuie sur "
                            "Entrée (C pour annuler). Un cadre trop serré compte aussi les autres types de coffres.",
                            "Select the WHOLE purple word (CHEST) with a WIDE margin all around it, then press Enter "
                            "(C to cancel). A tight box also counts the other chest types."))
    if not zone:
        return False
    x, y, w, h = zone
    morceau = img[y:y + h, x:x + w]
    if cv2.countNonZero(cv2.inRange(cv2.cvtColor(morceau, cv2.COLOR_BGR2HSV), VIOLET_BAS, VIOLET_HAUT)) < 30:
        print(T("Pas de texte violet dans ta sélection : encadre bien le mot violet.",
                "No purple text in your selection: select the purple word."))
        return False
    DATA.mkdir(exist_ok=True)
    cv2.imwrite(str(MODELE), morceau)
    ecrire_json(CALIBRATION, {"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    print(T(f"✔ Calibrage enregistré ({w}x{h} px).", f"✔ Calibration saved ({w}x{h} px)."))
    return True


# ---------- détection à l'écran ----------
def surveiller(etat, zone, modele):
    with MSS() as sct:
        mon = sct.monitors[ECRAN]
        region = {
            "left": mon["left"] + max(zone["x"] - MARGE, 0),
            "top": mon["top"] + max(zone["y"] - MARGE, 0),
            "width": min(zone["w"] + 2 * MARGE, mon["width"]),
            "height": min(zone["h"] + 2 * MARGE, mon["height"]),
        }
        dernier, etait_visible = 0.0, False
        while not etat.get("fin"):
            masque = masque_violet(cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR))
            score = 0.0
            if cv2.countNonZero(masque) >= 30:  # rien de violet à l'écran : inutile de chercher
                score = float(cv2.matchTemplate(masque, modele, cv2.TM_CCOEFF_NORMED).max())
            if DEBUG and score > 0.2:
                print(f"  {T('ressemblance', 'similarity')} : {score:.2f}")
            visible = score >= SEUIL
            # on compte quand le message APPARAÎT (pas tant qu'il reste affiché)
            if visible and not etait_visible and time.time() - dernier >= DELAI_MIN:
                ajouter_coffre(etat)
                dernier = time.time()
                print(T(f"[{heure()}] Coffre détecté ({score:.2f}) -> {etat['total']}",
                        f"[{heure()}] Chest detected ({score:.2f}) -> {etat['total']}"))
            etait_visible = visible
            time.sleep(0.1)


# ---------- replays ----------
def debut_replay(nom):
    """Heure de début de la partie, lue dans le nom du replay (UnsavedReplay-2026.11.09-22.37.34)."""
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})", nom)
    try:
        return time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1)) if m else None
    except (OverflowError, ValueError):
        # Untrusted file name (downloaded/renamed replay): an out-of-range date must not kill the replay thread.
        return None


def totaux_replays(resultats):
    res = {"esprit": 0, "rare": 0, "casse": 0, "ok": True}
    for r in resultats.values():
        for cle in ("esprit", "rare", "casse"):
            res[cle] += r.get(cle, 0)
    return res


def corriger(etat, r, debut, fin):
    """Recale les coffres ouverts de cette partie sur le replay (fausse détection ou coffre raté)."""
    with VERROU:
        vus = sum(1 for t in etat["detections"] if debut <= t <= fin)
        ecart = r["ouverts"] - vus
        if not ecart:
            return
        etat["total"] += ecart
        if ecart > 0:
            etat["detections"].extend([fin - 5] * ecart)
        else:
            for t in [t for t in etat["detections"] if debut <= t <= fin][ecart:]:
                etat["detections"].remove(t)
        etat["detections"].sort()
        sauver(etat)
    print(T(f"[{heure()}] Correction d'après le replay : {vus} vus à l'écran, {r['ouverts']} dans le replay -> {ecart:+d}",
            f"[{heure()}] Corrected from the replay: {vus} seen on screen, {r['ouverts']} in the replay -> {ecart:+d}"))


def analyser_replays(etat):
    """Lit chaque replay terminé (une seule fois) avec le lecteur, en arrière-plan et sans fenêtre."""
    donnees = lire_json(RESULTATS_REPLAYS) or {}
    if "depuis" not in donnees:
        donnees = {"depuis": time.time(), "replays": {}}
        ecrire_json(RESULTATS_REPLAYS, donnees)
    # les replays en erreur sont réessayés à chaque lancement
    resultats = {k: v for k, v in donnees.get("replays", {}).items() if "erreur" not in v}
    donnees["replays"] = resultats
    depuis = donnees["depuis"]
    etat["replays"] = totaux_replays(resultats)
    print(T(f"Suivi esprit / rares / cassés démarré le {time.strftime('%d/%m à %H:%M', time.localtime(depuis))} "
            f"({etat['replays']['esprit']} esprit, {etat['replays']['rare']} rares, {etat['replays']['casse']} cassés). "
            f"Pour repartir de zéro : supprime data\\replays.json",
            f"Sprite / rare / broken tracking started on {time.strftime('%m/%d at %H:%M', time.localtime(depuis))} "
            f"({etat['replays']['esprit']} sprite, {etat['replays']['rare']} rare, {etat['replays']['casse']} broken). "
            f"To start over: delete data\\replays.json"))

    dotnet = verifier_replays()
    if not dotnet:
        return
    options = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0

    while not etat.get("fin"):
        try:
            replays = sorted(DOSSIER_DEMOS.glob("*.replay"), key=lambda f: f.stat().st_mtime)
        except OSError:
            replays = []
        # partie en cours = le replay le plus récent (Fortnite le crée au début de la partie)
        if replays:
            etat["debut_partie"] = debut_replay(replays[-1].name) or etat.get("debut_partie")

        for f in replays:
            if etat.get("fin"):
                break
            try:
                st = f.stat()
            except OSError:
                continue
            cle = f"{f.name}|{st.st_size}"
            # ignoré : terminé avant le début du suivi, déjà lu, ou encore en train de s'écrire
            if st.st_mtime < depuis or cle in resultats or time.time() - st.st_mtime < 6:
                continue
            try:
                sortie = subprocess.run([dotnet, str(LECTEUR), str(f)], capture_output=True, text=True,
                                        stdin=subprocess.DEVNULL, creationflags=options, timeout=600)
                r = json.loads(sortie.stdout.strip().splitlines()[-1])
            except Exception as e:
                r = {"fichier": f.name, "erreur": str(e)}
            r.pop("details", None)
            if r.pop("en_cours", False):
                continue  # partie pas finie (tu regardes encore tes coéquipiers...) : on réessaiera
            if "erreur" in r and time.time() - st.st_mtime < 600:
                continue  # peut-être pas fini d'écrire : on réessaiera
            if "erreur" not in r and CORRIGER_AVEC_REPLAY and debut_replay(f.name):
                corriger(etat, r, debut_replay(f.name), st.st_mtime + 5)
            resultats[cle] = r
            ecrire_json(RESULTATS_REPLAYS, donnees)
            etat["replays"] = totaux_replays(resultats)
            if "erreur" in r:
                print(T(f"[{heure()}] Replay {f.name} illisible : {r['erreur'][:150]}",
                        f"[{heure()}] Replay {f.name} unreadable: {r['erreur'][:150]}"))
            else:
                print(T(f"[{heure()}] Partie : {r['ouverts']} ouverts, {r['esprit']} esprit, "
                        f"{r['rare']} rares, {r['casse']} cassés",
                        f"[{heure()}] Match: {r['ouverts']} opened, {r['esprit']} sprite, "
                        f"{r['rare']} rare, {r['casse']} broken"))
        time.sleep(3)


# ---------- option carte ----------
TYPES_CARTE = {"normal": 0, "rare": 1, "esprit": 2}  # 3 = autre ou cassé


def lire_positions(dotnet, positions):
    """Lit (une seule fois) les positions des replays terminés : ton trajet, tes coffres et ceux de tous les
    joueurs visibles dans le replay, en mètres."""
    a_lire = []
    for f in DOSSIER_DEMOS.glob("*.replay") if DOSSIER_DEMOS.exists() else []:
        try:
            st = f.stat()
        except OSError:  # Fortnite supprime les vieux replays : le fichier a pu disparaître entre-temps
            continue
        # "tous" absent : lu par une version qui ne gardait que tes coffres -> on relit
        if "tous" not in positions.get(f"{f.name}|{st.st_size}", {}) and time.time() - st.st_mtime > 6:
            a_lire.append((st.st_mtime, f, f"{f.name}|{st.st_size}"))
    a_lire = [(f, cle) for _, f, cle in sorted(a_lire)]  # du plus ancien au plus récent : la dernière partie à la fin
    if a_lire:
        print(T(f"Lecture des positions dans {len(a_lire)} replay(s)...", f"Reading positions from {len(a_lire)} replay(s)..."))
    for i in range(0, len(a_lire), 20):  # par lots : un seul lancement de dotnet pour 20 replays
        lot = dict(a_lire[i:i + 20])
        try:
            sortie = subprocess.run([dotnet, str(LECTEUR), "--positions", *map(str, lot)], capture_output=True,
                                    text=True, stdin=subprocess.DEVNULL, timeout=600).stdout
        except subprocess.TimeoutExpired:
            continue
        cles = {f.name: cle for f, cle in lot.items()}
        for ligne in sortie.splitlines():
            try:  # sortie du lecteur = donnée externe : une ligne illisible est ignorée, pas fatale
                r = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            pos = r.get("positions")
            if r.get("fichier") not in cles or r.get("en_cours") or not pos:
                continue
            joueur = [[round(p["x"] / 100), round(p["y"] / 100)] for p in pos["joueur"][::2]]
            # avant le saut : île d'attente puis bus, à des kilomètres de là -> on garde après le premier grand saut
            saut = next((j for j in range(1, len(joueur)) if abs(joueur[j][0] - joueur[j - 1][0]) + abs(joueur[j][1] - joueur[j - 1][1]) > 500), 0)
            fouilles = [(c["moi"], [round(c["x"] / 100), round(c["y"] / 100), 3 if c["casse"] else TYPES_CARTE.get(c["type"], 3)])
                        for c in pos["fouilles"]]
            positions[cles[r["fichier"]]] = {
                "debut": r.get("debut"),
                "coffres": [c for moi, c in fouilles if moi],
                "tous": [c for _, c in fouilles],
                "joueur": joueur[saut:],
            }
        ecrire_json(POSITIONS, positions)
    return positions


def spots_carte(positions):
    """Emplacements de coffres [x, y, type le plus fréquent, nombre d'ouvertures] : ouvertures à moins de 6 m
    l'une de l'autre (position du joueur à l'ouverture, donc à quelques mètres du coffre)."""
    spots = []  # [x, y, compteurs par type]
    for p in positions.values():
        for x, y, t in p["tous"]:
            s = next((s for s in spots if (s[0] - x) ** 2 + (s[1] - y) ** 2 <= 36), None)
            if not s:
                spots.append(s := [x, y, [0, 0, 0, 0]])
            s[2][t] += 1
    return [[x, y, n.index(max(n)), sum(n)] for x, y, n in spots]


def vers_carte(x, y, cal=CALAGE_CARTE):
    """Mètres du replay -> pixels de l'image de la carte."""
    a, b, c, d = ORIENT[cal["o"]]
    return cal["s"] * (a * x + b * y) + cal["tx"], cal["s"] * (c * x + d * y) + cal["ty"]


def prochains(pos, spots, ouverts, n=3):
    """Les n prochains coffres à faire depuis pos, du plus proche en plus proche, sans ceux déjà ouverts
    cette partie (à moins de 6 m d'une de tes ouvertures)."""
    reste = [s[:2] for s in spots if all((s[0] - o[0]) ** 2 + (s[1] - o[1]) ** 2 > 36 for o in ouverts)]
    chemin = []
    while reste and len(chemin) < n:
        pos = min(reste, key=lambda s: (s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2)
        reste.remove(pos)
        chemin.append(pos)
    return chemin


def vers_metres(X, Y, cal=CALAGE_CARTE):
    """Pixels de l'image de la carte -> mètres du replay (inverse de vers_carte)."""
    a, b, c, d = ORIENT[cal["o"]]
    u, v = (X - cal["tx"]) / cal["s"], (Y - cal["ty"]) / cal["s"]
    return a * u + c * v, b * u + d * v  # matrices d'orientation orthogonales : inverse = transposée


def localiser(mini, carte, avant=None):
    """Cherche la minicarte du jeu dans l'image de la carte (même dessin). Renvoie (ressemblance, échelle,
    centre en pixels de la carte). avant = résultat précédent : on ne cherche qu'autour, bien plus vite."""
    if avant:
        _, f0, (cx, cy) = avant
        echelles, marge = np.arange(f0 - 0.02, f0 + 0.021, 0.01), 60
    else:  # recherche grossière sur toute la carte réduite 4 fois, puis fine autour du meilleur endroit
        petite = cv2.resize(carte, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
        grossier = None
        for f in np.arange(0.20, 1.60, 0.03):
            tpl = cv2.resize(mini, None, fx=f / 4, fy=f / 4, interpolation=cv2.INTER_AREA)
            if min(tpl.shape[:2]) < 12 or tpl.shape[0] >= petite.shape[0] or tpl.shape[1] >= petite.shape[1]:
                continue
            r = cv2.matchTemplate(petite, tpl, cv2.TM_CCOEFF_NORMED)
            _, mx, _, (x, y) = cv2.minMaxLoc(r)
            if not grossier or mx > grossier[0]:
                grossier = (mx, f, ((x + tpl.shape[1] / 2) * 4, (y + tpl.shape[0] / 2) * 4))
        if not grossier:
            return None
        _, f0, (cx, cy) = grossier
        echelles, marge = np.arange(f0 - 0.03, f0 + 0.031, 0.01), 24
    best = None
    for f in echelles:
        tpl = cv2.resize(mini, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        h, w = tpl.shape[:2]
        x0, y0 = int(max(0, cx - w / 2 - marge)), int(max(0, cy - h / 2 - marge))
        zone = carte[y0:y0 + h + 2 * marge, x0:x0 + w + 2 * marge]
        if zone.shape[0] < h or zone.shape[1] < w:
            continue
        r = cv2.matchTemplate(zone, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, (x, y) = cv2.minMaxLoc(r)
        if not best or mx > best[0]:
            best = (mx, f, (x0 + x + w / 2, y0 + y + h / 2))
    return best


def contraste(img):
    """Gris à contraste local égalisé : garde les formes (côtes, cratère, routes) quand la tempête teinte tout en violet."""
    return cv2.createCLAHE(2.0, (8, 8)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))


def trouver(mini, cartes, avant):
    """Position de la minicarte : en couleur d'abord, puis en contraste (tempête) ; autour de la position précédente,
    puis partout si on l'a perdue (téléportation, carte ouverte...). None si rien ne ressemble assez."""
    images = ((mini, cartes[0]), (contraste(mini), cartes[1]))
    for precedent in ((avant, None) if avant else (None,)):  # les recherches rapides d'abord
        for image, carte in images:
            r = localiser(image, carte, precedent)
            if r and r[0] >= 0.5:
                return r
    return None


def suivre_minicarte(etat):
    """Option minicarte : ta position vient de la minicarte du jeu, lue à l'écran (comme le message « +XP COFFRE ») et
    retrouvée dans l'image de la carte. Les coffres ouverts cette partie sont ceux comptés à l'écran, à ta position."""
    zone = lire_json(MINICARTE_ZONE)
    image = next((f for f in sorted(DATA.glob("carte.*")) if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")), None)
    etat["spots"] = spots_carte(lire_json(POSITIONS, {}) or {})
    if not zone or not image or not etat["spots"]:
        print(T("Minicarte : lance d'abord  py compteur_coffres.py carte  puis  py compteur_coffres.py minicarte-config",
                "Minimap: first run  py compteur_coffres.py map  then  py compteur_coffres.py minimap-setup"))
        return
    carte_img = cv2.imread(str(image))
    cartes = (carte_img, contraste(carte_img))
    avant, ouverts, partie, vus = None, [], None, len(etat["detections"])
    with MSS() as sct:
        mon = sct.monitors[ECRAN]
        region = {"left": mon["left"] + zone["x"], "top": mon["top"] + zone["y"], "width": zone["w"], "height": zone["h"]}
        while not etat.get("fin"):
            mini = cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)
            avant = trouver(mini, cartes, avant)
            if etat.get("debut_partie") != partie:  # nouvelle partie : plus aucun coffre ouvert
                partie, ouverts = etat.get("debut_partie"), []
            pos = vers_metres(*avant[2]) if avant else None
            if pos and len(etat["detections"]) > vus:  # coffre compté à l'écran : ouvert ici
                ouverts.append(pos)
            vus = len(etat["detections"])
            etat["minimap"] = {"pos": pos, "ouverts": list(ouverts)} if pos else None
            if DEBUG and avant:
                print(f"  minicarte : {pos[0]:.0f}, {pos[1]:.0f} m (ressemblance {avant[0]:.2f}, échelle {avant[1]:.2f})")
            time.sleep(0.5)


def carte():
    """Option carte : génère data/carte.html (spots de coffres, dernière partie, chemin conseillé) et l'ouvre.
    Un spot vient de n'importe quel joueur visible dans tes replays, pas seulement de toi."""
    import webbrowser

    dotnet = verifier_replays()
    if not dotnet:
        return
    positions = lire_positions(dotnet, lire_json(POSITIONS, {}) or {})
    if not positions:
        print(T("Aucune partie avec positions. Le lecteur est peut-être ancien : recompile-le (lecteur_src\\build.bat).",
                "No match with positions. The reader may be outdated: rebuild it (lecteur_src\\build.bat)."))
        return
    spots = spots_carte(positions)
    derniere = list(positions.values())[-1]
    image = next((f.name for f in sorted(DATA.glob("carte.*")) if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")), None)
    donnees = {
        "image": image,
        "parties": len(positions),
        "ouvertures": sum(len(p["tous"]) for p in positions.values()),
        "spots": spots,
        "partie": {"joueur": derniere["joueur"], "coffres": derniere["coffres"]},
        "calage": CALAGE_CARTE,
    }
    # "<" échappé : les données ne peuvent pas fermer la balise <script> de la page
    modele = (DOSSIER / "carte_modele.html").read_text(encoding="utf-8")
    CARTE.write_text(modele.replace("/*DONNEES*/null", json.dumps(donnees).replace("<", "\\u003c")), encoding="utf-8")
    print(T(f"✔ Carte : {CARTE}", f"✔ Map: {CARTE}"))
    webbrowser.open(CARTE.as_uri())


# ---------- compteur à l'écran ----------
def lancer_overlay(etat):
    """Fenêtre toujours au-dessus du jeu, que les clics traversent."""
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.88)
    root.configure(bg=FOND)
    root.geometry(f"+{OVERLAY_X}+{OVERLAY_Y}")
    images = []

    def icone(nom):
        try:
            images.append(tk.PhotoImage(file=str(ASSETS / nom)))
            return images[-1]
        except Exception as e:
            print(T(f"Icône {nom} introuvable : {e}", f"Icon {nom} not found: {e}"))
            return None

    cadre = tk.Frame(root, bg=FOND, padx=10, pady=6)
    cadre.pack()

    # 1) coffres ouverts (en direct) + partie en cours
    ligne1 = tk.Frame(cadre, bg=FOND)
    ligne1.pack(anchor="w")
    tk.Label(ligne1, image=icone("coffre.png"), bg=FOND).pack(side="left")
    ouverts = tk.Label(ligne1, fg="white", bg=FOND, font=("Segoe UI", 22, "bold"), padx=6)
    ouverts.pack(side="left")
    partie = tk.Label(ligne1, fg=GRIS, bg=FOND, font=("Segoe UI", 12, "bold"))
    partie.pack(side="left", padx=(4, 0))

    # 2) esprit / rares / cassés (replays)
    ligne2 = tk.Frame(cadre, bg=FOND)
    ligne2.pack(anchor="w", pady=(4, 0))
    details = {}
    for cle, fichier in (("esprit", "esprit.png"), ("rare", "rare.png"), ("casse", "casse.png")):
        tk.Label(ligne2, image=icone(fichier), bg=FOND).pack(side="left")
        details[cle] = tk.Label(ligne2, fg="white", bg=FOND, font=("Segoe UI", 14, "bold"), padx=4)
        details[cle].pack(side="left", padx=(0, 8))

    # 3) total + chance d'avoir le token
    tk.Frame(cadre, bg="#3a3a4e", height=1).pack(fill="x", pady=(6, 3))
    ligne3 = tk.Frame(cadre, bg=FOND)
    ligne3.pack(anchor="w")
    tk.Label(ligne3, text="TOTAL", fg=GRIS, bg=FOND, font=("Segoe UI", 11, "bold")).pack(side="left")
    total = tk.Label(ligne3, fg=DORE, bg=FOND, font=("Segoe UI", 18, "bold"), padx=8)
    total.pack(side="left")
    token = tk.Label(ligne3, fg=GRIS, bg=FOND, font=("Segoe UI", 11, "bold"))
    token.pack(side="left")

    # 4) option minicarte : carte autour de toi et les 3 prochains coffres
    if MINICARTE:
        import base64
        taille = 240
        fond_carte = next((cv2.imread(str(f)) for f in sorted(DATA.glob("carte.*"))
                           if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")), None)
        tk.Frame(cadre, bg="#3a3a4e", height=1).pack(fill="x", pady=(6, 3))
        mini = tk.Canvas(cadre, width=taille, height=taille, bg="#12121a", highlightthickness=0)
        mini.pack()
        etapes = tk.Label(cadre, fg="white", bg=FOND, font=("Consolas", 11, "bold"), justify="left")
        etapes.pack(anchor="w")

    def dessiner_minicarte(m):
        mini.delete("all")
        if not m:
            etapes.config(text=T("Minicarte : position introuvable", "Minimap: position not found"))
            return
        cx, cy = vers_carte(*m["pos"])
        demi = MINIMAP_METRES / 2 * CALAGE_CARTE["s"]
        k = taille / (2 * demi)

        def ecran(x, y):
            X, Y = vers_carte(x, y)
            return (X - cx) * k + taille / 2, (Y - cy) * k + taille / 2

        if fond_carte is not None:
            d = int(2 * demi)  # bordure noire : la zone peut dépasser du bord de l'image
            x0, y0 = int(cx - demi) + d, int(cy - demi) + d
            zone = cv2.copyMakeBorder(fond_carte, d, d, d, d, cv2.BORDER_CONSTANT)[y0:y0 + d, x0:x0 + d]
            if zone.size:
                png = cv2.imencode(".png", cv2.resize(zone, (taille, taille)))[1]
                vu["image"] = tk.PhotoImage(data=base64.b64encode(png.tobytes()))
                mini.create_image(0, 0, image=vu["image"], anchor="nw")
        for x, y, *_ in etat["spots"]:
            X, Y = ecran(x, y)
            if 0 <= X <= taille and 0 <= Y <= taille:
                mini.create_oval(X - 3, Y - 3, X + 3, Y + 3, fill="#ffb020", outline="#000")
        for x, y in m["ouverts"]:
            X, Y = ecran(x, y)
            mini.create_line(X - 4, Y - 4, X + 4, Y + 4, fill="#ff4040", width=2)
            mini.create_line(X - 4, Y + 4, X + 4, Y - 4, fill="#ff4040", width=2)
        route = prochains(m["pos"], etat["spots"], m["ouverts"])
        points = [m["pos"]] + route
        if len(points) > 1:
            mini.create_line(*[v for q in points for v in ecran(*q)], fill="#3fa9ff", width=3)
        for i, q in enumerate(route, 1):
            X, Y = ecran(*q)
            mini.create_text(X + 9, Y - 9, text=str(i), fill="white", font=("Segoe UI", 11, "bold"))
        mini.create_oval(taille / 2 - 6, taille / 2 - 6, taille / 2 + 6, taille / 2 + 6, fill="#3fa9ff", outline="white", width=2)
        dist = [math.dist(points[i], points[i + 1]) for i in range(len(route))]
        texte = "  ".join(f"{i + 1}:{'+' if i else ''}{round(v)}m" for i, v in enumerate(dist))
        etapes.config(text=texte)

    # Clics à travers la fenêtre (Windows)
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80)
    except Exception:
        pass

    vu = {"ouverts": None, "flash": 0}

    def rafraichir():
        if etat.get("fin"):
            root.destroy()
            return
        rep = etat.get("replays") or {}
        n = etat["total"]
        if vu["ouverts"] is not None and n > vu["ouverts"]:
            vu["flash"] = 8
        vu["ouverts"] = n
        ouverts.config(text=str(n))
        debut = etat.get("debut_partie")
        n_partie = sum(1 for t in etat["detections"] if debut and t >= debut)
        partie.config(text=T(f"+{n_partie} cette partie", f"+{n_partie} this match"))
        for cle, lab in details.items():
            lab.config(text=str(rep[cle]) if rep.get("ok") else "–")
        n_total = n + (rep.get("casse", 0) if AJOUTER_CASSES else 0)
        total.config(text=str(n_total))
        chance = (1 - (1 - CHANCE_TOKEN) ** n_total) * 100  # au moins un token sur n_total coffres
        token.config(text=T(f"Token : {chance:.2f} %".replace(".", ","), f"Token: {chance:.2f}%"))
        if vu["flash"]:
            vu["flash"] -= 1
            ouverts.config(fg=DORE if vu["flash"] else "white")
        if MINICARTE and etat.get("minimap") is not vu.get("mini", 0):  # redessinée seulement quand elle change
            vu["mini"] = etat.get("minimap")
            dessiner_minicarte(vu["mini"])
        root.attributes("-topmost", True)
        root.after(100, rafraichir)

    rafraichir()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


# ---------- programme principal ----------
def compter():
    zone = lire_json(CALIBRATION)
    if not zone or not MODELE.exists():
        print(T("Pas encore calibré : py compteur_coffres.py calibrer",
                "Not calibrated yet: py compteur_coffres.py calibrate"))
        return
    modele = masque_violet(cv2.imread(str(MODELE)))
    # Un seul compteur à la fois : deux compteurs comptent chaque coffre deux fois et écrasent la sauvegarde
    # l'un de l'autre. Le verrou est libéré par Windows quand le programme s'arrête, même s'il plante.
    import msvcrt
    DATA.mkdir(exist_ok=True)
    instance = open(DATA / "compteur.lock", "w")
    try:
        msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(T("Le compteur est déjà lancé dans une autre fenêtre : ferme-la d'abord.",
                "The counter is already running in another window: close it first."))
        return
    etat = charger_etat()
    sauver(etat)

    def touche(k):
        if k == keyboard.Key.f8:
            ajouter_coffre(etat, 1)
            print(f"+1 -> {etat['total']}")
        elif k == keyboard.Key.f7:
            ajouter_coffre(etat, -1)
            print(f"-1 -> {etat['total']}")
        elif k == keyboard.Key.f10:
            etat["fin"] = True

    keyboard.Listener(on_press=touche, daemon=True).start()
    signal.signal(signal.SIGINT, lambda *_: etat.update(fin=True))  # Ctrl+C = arrêt propre

    threading.Thread(target=surveiller, args=(etat, zone, modele), daemon=True).start()
    threading.Thread(target=analyser_replays, args=(etat,), daemon=True).start()
    if MINICARTE:
        etat["spots"] = []
        threading.Thread(target=suivre_minicarte, args=(etat,), daemon=True).start()
    print(T(f"Surveillance en cours... total : {etat['total']}  (F8 +1, F7 -1, F10 quitter)",
            f"Watching... total: {etat['total']}  (F8 +1, F7 -1, F10 quit)"))

    if "sans-overlay" in ARGS or "no-overlay" in ARGS:
        while not etat.get("fin"):
            time.sleep(0.2)
    else:
        lancer_overlay(etat)
    etat["fin"] = True
    sauver(etat)
    print(T(f"\nArrêt. Total sauvegardé : {etat['total']}", f"\nStopped. Total saved: {etat['total']}"))


def main():
    global LANGUE
    try:  # coordonnées exactes même si Windows est zoomé à 125 % / 150 %
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    migrer_anciens_fichiers()
    reglages = lire_json(REGLAGES)
    if not reglages or "config" in ARGS or "setup" in ARGS:
        configurer()
    else:
        LANGUE = reglages.get("langue", "fr")

    if "calibrer" in ARGS or "calibrate" in ARGS:
        calibrer()
    elif "minicarte-config" in ARGS or "minimap-setup" in ARGS:
        configurer_minicarte()
    elif "carte" in ARGS or "map" in ARGS:
        carte()
    else:
        compter()


if __name__ == "__main__":
    main()
