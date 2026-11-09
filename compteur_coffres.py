"""
le_f_detector — compteur de coffres Fortnite / Fortnite chest counter.

Compte les coffres ouverts en direct (détection à l'écran) et lit les replays après chaque partie
pour les coffres à esprit, rares et cassés. Ne touche jamais au jeu : il regarde l'écran, comme OBS,
et lit les fichiers .replay que Fortnite enregistre.

Commandes :
    py compteur_coffres.py              lancer le compteur (configuration au premier lancement)
    py compteur_coffres.py calibrer     refaire le calibrage de la détection
    py compteur_coffres.py config       refaire la configuration (langue, nombre de départ, calibrage)
Options : debug (affiche la ressemblance en direct), sans-overlay (pas de compteur à l'écran)
Raccourcis : F8 = +1   F7 = -1   F10 / Ctrl+C = quitter

Voir README.md pour l'installation.
"""

import json
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

ARGS = [a.lower() for a in sys.argv[1:]]
DEBUG = "debug" in ARGS

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
    tmp = Path(str(chemin) + ".tmp")
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
VERROU = threading.Lock()  # la détection écran et la correction replay modifient le compteur en parallèle


def charger_etat():
    d = lire_json(SAUVEGARDE, {}) or {}
    return {"total": d.get("total", 0), "detections": d.get("detections", [])}


def sauver(etat):
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


def calibrer():
    print(T("Dans Fortnite, ouvre un coffre et appuie sur F9 pendant que le message « +XP COFFRE » est affiché...",
            "In Fortnite, open a chest and press F9 while the \"+XP CHEST\" message is on screen..."))
    capture = {}

    def touche(k):
        if k == keyboard.Key.f9:
            with MSS() as sct:
                capture["img"] = cv2.cvtColor(np.array(sct.grab(sct.monitors[ECRAN])), cv2.COLOR_BGRA2BGR)
            return False

    with keyboard.Listener(on_press=touche) as l:
        l.join()

    # A tight box also matches the other chest types: a wide margin keeps only regular chests.
    print(T("Encadre TOUT le mot violet (COFFRE) avec une GRANDE marge tout autour, puis appuie sur Entrée "
            "(C pour annuler). Un cadre trop serré compte aussi les autres types de coffres.",
            "Select the WHOLE purple word (CHEST) with a WIDE margin all around it, then press Enter "
            "(C to cancel). A tight box also counts the other chest types."))
    titre = "Calibration"
    cv2.namedWindow(titre, cv2.WINDOW_NORMAL)
    x, y, w, h = cv2.selectROI(titre, capture["img"], showCrosshair=True)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        print(T("Rien sélectionné, recommence.", "Nothing selected, try again."))
        return False

    morceau = capture["img"][y:y + h, x:x + w]
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
    else:
        compter()


if __name__ == "__main__":
    main()
