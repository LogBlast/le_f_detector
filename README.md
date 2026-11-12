# le_f_detector — compteur de coffres Fortnite

**Français** · [English](README.en.md)

Compte les coffres que tu ouvres dans Fortnite et les affiche en direct, par-dessus le jeu.

- **Coffres ouverts, en direct** : détectés à l'écran au moment où le message « +XP COFFRE » apparaît.
- **Coffres de la partie en cours** : « +N cette partie ».
- **Coffres à esprit, rares et cassés** : lus dans le replay quelques secondes après chaque partie.
- **Correction automatique** : en fin de partie, le nombre de coffres ouverts est recalé sur le replay (fausse détection ou coffre raté).
- **Total et chance d'avoir obtenu Pirate Shop Access** avec ton nombre de coffres.

```
[coffre] 1065  +11 cette partie
[esprit] 3  [rare] 4  [cassé] 9
──────────────────────────────
TOTAL 1074   Token : 0,78 %
```

## Comment ça marche (et pourquoi c'est sans risque)

- **Détection à l'écran** : le programme capture une petite zone de l'écran, comme OBS, et y cherche le mot violet du message de coffre. Il ne lit pas la mémoire du jeu et n'injecte rien.
- **Replays** : après chaque partie, un petit lecteur (`lecteur/`) lit en lecture seule le fichier `.replay` que Fortnite enregistre dans `%LOCALAPPDATA%\FortniteGame\Saved\Demos`.
- **Options carte et minicarte** : même principe, les replays après la partie et la minicarte du jeu lue à l'écran. Les positions des autres joueurs ne sont jamais affichées pendant une partie.
- **Aucune donnée envoyée** : tout reste sur ton PC, dans le dossier `data/`.

## Installation

Windows 10 / 11.

1. **Python 3.10+** : <https://www.python.org/downloads/>, puis dans un terminal, dans le dossier du projet :
   ```
   py -m pip install -r requirements.txt
   ```
2. **Runtime .NET 10** (pour lire les replays) :
   ```
   winget install Microsoft.DotNet.Runtime.10
   ```
3. **Le lecteur de replays**, dans un dossier `lecteur/` à côté du script :
   - soit le zip `lecteur.zip` de la page *Releases*, à décompresser dans le dossier du projet ;
   - soit compilé toi-même : installe le SDK .NET 10 (`winget install Microsoft.DotNet.SDK.10`), puis lance `lecteur_src\build.bat`.
4. **Dans Fortnite** :
   - *Paramètres → Jeu → Rediffusions → Enregistrer les rediffusions : Oui* ;
   - *Paramètres → Vidéo → Mode de fenêtre : Plein écran fenêtré* (en plein écran exclusif, rien ne peut s'afficher par-dessus le jeu).

## Premier lancement

```
py compteur_coffres.py
```

La configuration se lance toute seule :

1. **Langue** : français ou anglais.
2. **Nombre de coffres déjà ouverts** : `0` (par défaut), `1000` (maximum du compteur de la quête Fortnite) ou ton propre nombre.
3. **Calibrage** : lance Fortnite, ouvre un coffre et appuie sur **F9** pendant que le message « +XP COFFRE » est affiché. Encadre **tout le mot violet** (COFFRE, ou CHEST en anglais) **avec une grande marge tout autour**, puis appuie sur Entrée.
4. **Vérification** de ce qu'il faut pour lire les replays.

> [!WARNING]
> **Calibrage : prends tout le mot « COFFRE » avec une grande marge tout autour.** C'est ce qui permet de ne compter que les coffres classiques. Un cadre trop serré sur le mot reconnaît aussi les autres types de coffres, qui seront alors comptés en trop.

Les coffres à esprit, rares et cassés sont comptés à partir de ce premier lancement : les parties plus anciennes sont ignorées.

## Utilisation

| Commande | Effet |
|---|---|
| `py compteur_coffres.py` | Lance le compteur |
| `py compteur_coffres.py calibrer` | Refait le calibrage |
| `py compteur_coffres.py config` | Refait la configuration complète (remet le compteur au nombre choisi) |
| `py compteur_coffres.py debug` | Affiche la ressemblance de chaque détection, pour régler `SEUIL` |
| `py compteur_coffres.py sans-overlay` | Compte sans afficher le compteur à l'écran |
| `py compteur_coffres.py carte` | Option : ouvre la carte de tes coffres (voir plus bas) |
| `py compteur_coffres.py minicarte` | Option : ajoute au compteur une carte en direct avec les 3 prochains coffres (voir plus bas) |
| `py compteur_coffres.py minicarte-config` | Option : repère la minicarte du jeu à l'écran (F9) |

| Touche | Effet |
|---|---|
| **F8** | +1 (coffre raté) |
| **F7** | −1 (fausse détection) |
| **F10** ou **Ctrl+C** | Quitter |

Les corrections manuelles sont rarement utiles : en fin de partie, le replay recale le compte de toute façon.

### Délai des chiffres du replay

Fortnite écrit le replay jusqu'à ce que tu quittes la partie, même si tu regardes encore tes coéquipiers. Les chiffres esprit / rares / cassés arrivent environ 6 à 10 secondes après ton retour au lobby.

## Carte des coffres (option)

`py compteur_coffres.py carte` lit tes replays et ouvre `data/carte.html` dans ton navigateur :

- **les spots de coffres** : chaque endroit où un coffre a été ouvert, par toi ou par un joueur près de toi (le replay enregistre aussi les joueurs autour), cumulé partie après partie (plus le point est gros, plus il a été ouvert souvent) ;
- **ta dernière partie** : ton trajet et les coffres ouverts ;
- **un chemin conseillé** : clique là où tu atterris, choisis une distance, et la carte trace l'ordre de passage qui ouvre le plus de coffres.

Molette pour zoomer, glisser pour te déplacer, **Vue entière** pour revenir à toute l'île.

La position d'un coffre est celle du joueur qui l'ouvre (le replay ne donne pas celle des coffres de la carte) : à quelques mètres près. Seules les zones où tu as joué se remplissent, puisque le replay n'enregistre que ce qui se passe près de toi.

L'option ne change rien au compteur et ne tourne que quand tu lances cette commande. La première fois, la lecture prend moins d'une minute pour 100 replays ; ensuite seuls les nouveaux replays sont lus. Elle demande le lecteur de cette version : si tu utilises un ancien `lecteur.zip`, recompile-le avec `lecteur_src\build.bat`.

**Fond de carte** : mets une image de la carte actuelle du jeu dans `data/carte.png` (ou `.jpg` / `.webp`). Elle reste sur ton PC. Le calage fourni (`CALAGE_CARTE`) correspond à l'image officielle de 1920 px de la saison de novembre 2026. Avec une autre image, coche **Caler la carte** et ajuste les points (glisser, molette, Pivoter, Miroir) jusqu'à ce que tes trajets suivent les routes ; ce réglage n'est gardé que dans ton navigateur : pour la minicarte, reporte-le dans `CALAGE_CARTE`. À chaque nouvelle saison, remplace l'image, recale, et supprime `data/positions.json` pour repartir de zéro.

### Minicarte en direct (option)

`py compteur_coffres.py minicarte` ajoute sous le compteur une petite carte de 300 m autour de toi, pendant la partie : les spots de coffres, ceux que tu as ouverts cette partie (croix rouge) et le chemin vers les **3 prochains coffres** (`1:3m  2:+6m  3:+8m`).

Avant la première fois :

1. `py compteur_coffres.py carte` (pour les spots et l'image de fond `data/carte.*`) ;
2. `py compteur_coffres.py minicarte-config` : en partie, appuie sur **F9** et encadre exactement le carré de la minicarte du jeu.

Ta position est lue sur la minicarte du jeu, à l'écran, comme le message « +XP COFFRE » : le script cherche ce bout de carte dans `data/carte.*` (le même dessin que la carte du jeu), deux fois par seconde. Rien n'est lu dans le jeu ni dans sa mémoire. Le replay ne peut pas servir en direct : Fortnite n'y écrit la clé de déchiffrement qu'à la fin de la partie.

Un coffre compté à l'écran est marqué ouvert là où tu es. Si tu changes de résolution ou de place de la minicarte, refais `minicarte-config`.

## Réglages

En haut de `compteur_coffres.py` :

| Réglage | Par défaut | Rôle |
|---|---|---|
| `SEUIL` | `0.70` | Ressemblance minimale. Baisse si des coffres sont ratés, monte en cas de fausses détections. |
| `OVERLAY_X`, `OVERLAY_Y` | `15`, `110` | Position du compteur à l'écran. |
| `ECRAN` | `1` | Écran surveillé (1 = principal). |
| `AJOUTER_CASSES` | `True` | Le total inclut les coffres cassés. |
| `CORRIGER_AVEC_REPLAY` | `True` | Recale les coffres ouverts sur le replay en fin de partie. |
| `CHANCE_TOKEN` | `1 / 137_500` | Chance de Pirate Shop Access par coffre. |
| `CALAGE_CARTE` | image de novembre 2026 | Options carte et minicarte : correspondance entre les positions des replays et l'image de la carte. |
| `MINIMAP_METRES` | `300` | Côté, en mètres, de la zone affichée par la minicarte. |

## Chance d'avoir le token

La probabilité affichée est celle d'avoir obtenu **au moins une fois** Pirate Shop Access avec ton nombre de coffres : `1 − (1 − 1/137 500)^coffres`. Le taux de 1 sur 137 500 par coffre en partie normale vient du compte Fortnite Status (voir aussi <https://fortnite.bot/treasure>). Les *Treasure Hours*, qui augmentent ce taux, ne sont pas prises en compte.

## Données

Tout est dans `data/` (ignoré par git) :

| Fichier | Contenu |
|---|---|
| `reglages.json` | Langue |
| `calibration.json`, `modele_coffre.png` | Calibrage |
| `compteur.json` | Total et heure de chaque coffre compté |
| `compteur.txt` | Total en texte, pour une source texte OBS |
| `replays.json` | Début du suivi et résultat de chaque partie |
| `positions.json`, `carte.html`, `carte.png` | Option carte : positions lues, page générée, image de fond |
| `minicarte.json` | Option minicarte : emplacement de la minicarte du jeu à l'écran |

Pour remettre à zéro les coffres esprit / rares / cassés, supprime `data/replays.json`.

## Problèmes fréquents

- **Le compteur n'apparaît pas par-dessus le jeu** : passe Fortnite en *Plein écran fenêtré*.
- **Des coffres ne sont pas détectés** : lance avec `debug`, regarde la ressemblance affichée, baisse `SEUIL` ou refais le calibrage.
- **Esprit / rares / cassés restent à « – » ou ne bougent pas** : vérifie les messages au lancement (runtime .NET, dossier `lecteur/`, rediffusions activées).
- **Minicarte : « position introuvable »** : normal quand la carte est ouverte ou que tu es mort. Sinon, refais `minicarte-config` (encadre le carré de la minicarte, sans son cadre) et vérifie que `data/carte.*` est la carte de la saison actuelle.
- **« Replay illisible »** : une mise à jour de Fortnite peut changer le format des replays ; ouvre une *issue* avec le message.

## Structure du projet

```
compteur_coffres.py    programme principal
carte_modele.html      modèle de la page de l'option carte
assets/                icônes du compteur
lecteur_src/           code source du lecteur de replays (C#)
lecteur/               lecteur compilé (non versionné)
data/                  données de l'utilisateur (non versionné)
```

## Crédits et licence

- Décodage des replays : [FortniteReplayDecompressor](https://github.com/Shiqan/FortniteReplayDecompressor) (Shiqan, MIT), avec les correctifs de [Fortnite-ChestCounter](https://github.com/LED-N/Fortnite-ChestCounter) (LED-N, MIT). Détails dans [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Calage de la carte : formule de conversion des coordonnées de la carte de [fortnite.gg](https://fortnite.gg/) (aucune de leurs données n'est incluse).
- Code de ce projet : licence [MIT](LICENSE).

Fortnite est une marque d'Epic Games, Inc. Ce projet n'est ni affilié à Epic Games, ni approuvé par Epic Games.
