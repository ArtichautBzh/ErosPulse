# Changelog — ErosPulse

Toutes les versions notables du projet sont documentées ici. Le
projet s'appelait "Lovense Text-to-Vibe" jusqu'à la v0.10.0.

## v0.16.0

**Import de modèles de séquence**
- Nouveau module `core/settings.py` : réglages persistés sur disque
  (fichier `settings.json` à la racine du projet), pour l'instant
  limités au dossier configuré pour les modèles importables — mais
  conçu pour accueillir d'autres préférences à l'avenir.
- Nouveau module `core/template_library.py` : découverte des fichiers
  `.txt` dans un dossier donné, et lecture de leur contenu. Aucune
  validation du contenu ici : un modèle chargé est traité exactement
  comme du texte tapé à la main (même parsing, mêmes erreurs possibles).
- Page de séquence : nouveau menu déroulant listant les fichiers `.txt`
  du dossier configuré (par défaut `Import/` à la racine du projet,
  créé automatiquement s'il n'existe pas encore). Sélectionner un
  modèle remplace le contenu de l'éditeur et met à jour
  immédiatement la durée totale et le graphique.
- Bouton **"Dossier…"** pour choisir un autre dossier via le sélecteur
  natif du système ; le choix est mémorisé pour les prochains
  lancements. Bouton **⟳** pour rafraîchir manuellement la liste ; elle
  se rafraîchit aussi automatiquement à chaque retour sur la page.
- Bouton **"Masquer le texte" / "Afficher le texte"** : replie ou
  déplie la zone d'édition (le contenu est conservé même masqué,
  seul l'affichage change).
- Un exemple (`Import/Exemple - vague.txt`, utilisant `LOOP`) est
  fourni avec le projet pour que la fonctionnalité soit visible dès le
  premier lancement.

## v0.15.0

**Boucles LOOP(N){...}**
- Nouvelle syntaxe dans `core/vibration_command.py` : un bloc
  `LOOP(N){ Z }` répète N fois le contenu `Z` (une ou plusieurs
  commandes `[Y;D;[A;B]]`), sans avoir à le retaper. Exemple :
  `LOOP(3){[1;2;[10;0]] [2;2;[0;15]]}` équivaut à écrire la paire de
  commandes 3 fois de suite.
- Les boucles peuvent être imbriquées (`LOOP(2){... LOOP(3){...}}`)
  et mélangées librement avec des commandes normales avant/après.
- `parse_sequence()` a été réécrit en un vrai parseur récursif (les
  accolades imbriquées ne sont pas gérables de façon fiable avec une
  simple regex), mais continue de renvoyer une **liste plate** de
  `VibrationCommand`, boucles entièrement développées : la lecture, le
  graphique et le calcul de durée totale fonctionnent donc avec `LOOP`
  sans la moindre modification.
- `LOOP(0){...}` est accepté et ignore simplement son contenu ; un
  bloc `LOOP(...)` non refermé lève une erreur claire
  (`SequenceSyntaxError`, une sous-classe de `ValueError`, déjà gérée
  par l'interface).
- `core/ai_prompt.py` mis à jour pour que l'IA sache utiliser `LOOP`
  quand c'est pertinent (motif qui se répète à l'identique), sans
  l'imposer pour des séquences qui évoluent (montée d'intensité, etc.).

## v0.14.0

**Génération d'un exécutable autonome**
- Ajout de `ErosPulse.spec`, une configuration PyInstaller prête à
  l'emploi (mode fenêtré sans console, exécutable en un seul fichier,
  toutes les dépendances embarquées via `vendor/`).
- Ajout de `build_exe.bat` (Windows) et `build_exe.sh` (macOS/Linux) :
  scripts qui installent PyInstaller puis lancent la génération de
  l'exécutable en une seule commande / double-clic. Le résultat est
  déposé dans `dist/ErosPulse.exe` (Windows) ou `dist/ErosPulse`
  (macOS/Linux).
- **Important : PyInstaller ne fait pas de compilation croisée.** Un
  `.exe` Windows doit être généré en exécutant le script *sur
  Windows* (idem : un `.app` macOS se génère sur macOS, un binaire
  Linux se génère sur Linux). Ces scripts doivent donc être exécutés
  par l'utilisateur final sur sa propre machine — ils ne peuvent pas
  être pré-générés depuis un environnement de développement Linux
  pour produire un `.exe` Windows valide.

## v0.13.0

**Graphique intensité(t)**
- Nouveau widget `ui/widgets/sequence_chart.py` (`SequenceChart`,
  sous-classe de `tk.Canvas`) : dessine l'intensité de chaque moteur
  au cours du temps sous forme de deux courbes en "escalier" (une par
  moteur), échelle 0-20, avec grille et légende. Aucune dépendance
  externe (pas de matplotlib) : tout est dessiné à la main sur le
  Canvas, cohérent avec le principe "zéro dépendance" du projet.
- Le graphique se met à jour en direct pendant la saisie du texte, et
  affiche un repère vertical ("playhead") indiquant la position de
  lecture actuelle pendant l'exécution — figé pendant une pause,
  masqué à la fin de la lecture.
- Une commande à durée infinie (D=0) est représentée par un segment
  symbolique avec une annotation ; le graphique s'arrête à ce point
  comme le fait réellement `play_sequence()`.
- Placé en bas de la page de texte (hauteur fixe, toujours visible),
  entre la zone de texte et la barre de statut.

**Persistance du message "commande en cours"**
- Le message `"Commande X/Y — [Y;D;[A;B]]"` est maintenant conservé
  (`self._current_command_text`) et restauré après une pause, un
  aller-retour vers l'accueil, ou une reprise — au lieu d'être
  remplacé par un texte générique "Reprise…" qui faisait perdre cette
  information.

## v0.12.0

**Correctifs**

1. Retrait du texte "Connexion à l'Edge 2" à côté du bouton "← Accueil"
   sur la page de connexion.

2. Le bouton "← Accueil" de la page de séquence **met en pause** une
   lecture en cours (coupure physique immédiate du toy) au lieu de
   l'arrêter définitivement. Comme `AppWindow` garde toutes les pages
   construites en mémoire (elles ne sont jamais détruites en changeant
   de page), le thread de lecture reste en pause en arrière-plan : en
   revenant sur la page, le bouton affiche "Reprendre" et permet de
   relancer la séquence exactement là où elle s'était arrêtée (même
   mécanisme de reprise avec temps restant qu'en v0.10.0).

3. et 4. Mise en page de la page de séquence entièrement revue :
   remplacement des positionnements relatifs (`place(relx=..., rely=...)`)
   par un empilement `pack()` ancré aux bords (header en haut, décompte
   + compteur de caractères + boutons + message de progression ancrés
   en bas). Ces éléments restent donc toujours visibles quelle que soit
   la taille de la fenêtre ; seule la zone de texte s'agrandit ou se
   réduit. Le texte d'aide au-dessus de la zone de saisie recalcule
   désormais dynamiquement son retour à la ligne (`wraplength`) à
   chaque redimensionnement (`<Configure>`), au lieu d'une largeur
   fixe qui débordait sur les petites fenêtres.

## v0.11.0

**Page de séquence**
- Retrait du libellé "Ton texte" à côté du bouton "← Accueil".
- Ajout d'un décompte au format `min:sec` :
  - pendant la saisie, affiche la **durée totale** de la séquence
    tapée (`Durée totale : 0:12`), recalculée à chaque modification
    du texte ;
  - pendant la lecture, devient un **compte à rebours du temps
    restant** (`Temps restant : 0:08`), rafraîchi chaque seconde ;
  - se **fige pendant une pause** (le temps ne défile pas tant que la
    lecture n'a pas repris) ;
  - affiche "indéterminée (boucle infinie)" si la séquence contient
    une commande à durée 0 (impossible à borner).

## v0.10.0

**Rebranding**
- L'application s'appelle désormais **ErosPulse** (au lieu de
  "Lovense Text-to-Vibe"). Nom mis à jour dans `core/version.py`
  (source unique de vérité, propagée au titre de la fenêtre et à la
  page d'accueil), sur la page d'accueil (bandeau + titre principal),
  et dans les fichiers projet Visual Studio (`ErosPulse.pyproj`,
  `ErosPulse.sln`, remplaçant `LovenseTextToVibe.*`).
- Texte de la page d'accueil mis à jour pour refléter le fonctionnement
  actuel (séquence `[Y;D;[A;B]]` plutôt que texte libre pour l'instant).

**Pause / Reprendre**
- Le bouton "Arrêter" de la page de texte devient **Pause** /
  **Reprendre**. En pause, le toy est immédiatement coupé
  (`client.stop()`) ; à la reprise, la commande en cours est relancée
  pour le temps de vibration qu'il restait à jouer (et non depuis le
  début), avant de continuer normalement la séquence.
- `core/vibration_command.play_sequence()` accepte un nouveau paramètre
  `pause_event`, avec suivi du temps restant par polling (toutes les
  0.2s) pour rester réactif à un clic sur Pause/Reprendre.
- Quitter la page de texte pendant une lecture (bouton "← Accueil")
  arrête désormais proprement la séquence en cours, plutôt que de
  laisser le thread continuer à piloter le toy en arrière-plan.

## v0.9.0

**Exécution réelle de la séquence saisie**
- Le bouton **Générer le modèle de vibration** de la page de texte est
  maintenant branché : il parse le texte saisi avec
  `core.vibration_command.parse_sequence()`, puis joue la séquence
  obtenue sur le toy connecté via `play_sequence()`, dans un thread
  séparé pour ne pas geler l'interface.
- Affichage de la progression en direct : "Commande 2/5 —
  [2;1;[0;12]]", etc.
- Nouveau bouton **Arrêter**, qui interrompt la séquence en cours
  (via le `stop_event` de `play_sequence()`).
- Gestion propre des cas limites :
  - texte vide → message d'invite,
  - texte sans commande `[Y;D;[A;B]]` valide → message d'erreur clair,
  - toy non connecté → redirection automatique vers la page de
    connexion (comme le fait déjà le bouton "Commencer" de l'accueil).
- `core/vibration_command.play_sequence()` accepte désormais un
  callback `on_command_start(index, total, command)` pour permettre
  cet affichage de progression.

## v0.8.0

**Prompt IA pour la génération de séquences**
- Nouveau fichier `core/ai_prompt.py`, contenant `TEXT_TO_VIBRATION_PROMPT` :
  un prompt système complet expliquant à une IA (LLM) le format
  `[Y;D;[A;B]]` défini en v0.7.0, avec :
  - la spécification stricte du format et des bornes de chaque champ,
  - les règles de conversion texte → vibration (ponctuation, emphase,
    rythme, montée en intensité, transitions),
  - un exemple d'entrée/sortie complet.
- L'exemple de sortie fourni dans le prompt a été vérifié comme étant
  réellement parsable par `core/vibration_command.parse_sequence()`,
  pour garantir la cohérence entre ce que l'IA est invitée à produire
  et ce que l'application sait effectivement interpréter.
- Ce prompt sera utilisé par un futur module d'appel à une IA (ex: API
  Anthropic) pour générer automatiquement la séquence de vibration à
  partir du texte saisi sur la page de saisie.

## v0.7.0

**Format de commande de vibration**
- Nouveau module `core/vibration_command.py` implémentant le format
  `[Y;D;[A;B]]` :
  - `Y` : moteur ciblé (1 = interne, 2 = périnée, 3 = les deux)
  - `D` : durée en secondes (0 = boucle indéfinie, comme le reste de
    l'API Lovense)
  - `[A;B]` : intensités des moteurs 1 et 2 (0-20, bornées automatiquement)
- `VibrationCommand.from_string()` / `.to_string()` pour parser et
  sérialiser une commande unique ; `parse_sequence()` pour extraire
  toutes les commandes présentes dans un texte plus large.
- `send_command()` envoie une commande au toy. Pour `Y=3` (les deux
  moteurs), deux requêtes sont envoyées automatiquement avec le bon
  réglage `stopPrevious` pour que les deux moteurs vibrent en même
  temps avec des intensités différentes sans se couper l'un l'autre.
- `play_sequence()` enchaîne plusieurs commandes en respectant la
  durée de chacune, avec un `stop_event` optionnel pour interrompre la
  lecture en cours de route.
- `core/lovense_client.py` : ajout du paramètre `stop_previous` à
  `vibrate()` et `vibrate_motor()` (correspond à `stopPrevious` dans
  l'API Lovense).

## v0.6.0

**Navigation conditionnelle + page de texte**
- Nouvelle page `ui/pages/text_page.py` : zone de saisie de texte
  (avec compteur de caractères, limite de 2000 caractères), point
  d'entrée pour la future génération de modèle de vibration.
- Le bouton **Commencer** de la page d'accueil :
  - redirige vers la page de connexion si aucun toy n'est connecté ;
  - redirige vers la nouvelle page de texte si un toy est connecté.
- La page de texte affiche le statut de connexion en temps réel et
  prévient si la connexion est perdue entre-temps.
- Le bouton "Générer le modèle de vibration" est en place mais pas
  encore branché : l'algorithme texte → vibration
  (`core/text_to_pattern.py`) arrive à l'étape suivante.

## v0.5.0

**Contrôle par moteur (Edge 2 = 2 moteurs)**
- Nouvelle méthode `LovenseClient.vibrate_motor(motor, strength, ...)`
  dans `core/lovense_client.py`, qui envoie les actions `Vibrate1:X` /
  `Vibrate2:X` du protocole Lovense pour piloter un moteur précis,
  plutôt que `Vibrate:X` qui agit sur tous les moteurs à la fois.
- La page de connexion propose désormais **deux boutons de test** :
  « Tester Moteur 1 (interne) » et « Tester Moteur 2 (périnée) ».
  Chacun se connecte automatiquement si besoin (comme en v0.4.1), puis
  envoie une courte vibration sur le moteur choisi uniquement.
- Le bouton "Se connecter" reste disponible séparément pour une
  simple vérification de connexion sans déclencher de vibration.

## v0.4.1

**Correctif de comportement**
- Le bouton **Tester** de la page de connexion se connecte désormais
  automatiquement (s'il n'y a pas déjà de connexion active) puis
  enchaîne directement sur l'envoi d'une courte vibration. Avant, il
  fallait obligatoirement cliquer sur "Se connecter" au préalable — le
  bouton "Tester" ne faisait rien tant que ce n'était pas fait.
- Si une connexion est déjà active, "Tester" ne refait pas d'appel
  `GetToys` inutile : il envoie directement la vibration.
- Le bouton "Se connecter" reste disponible séparément pour ceux qui
  veulent juste vérifier la connexion sans déclencher de vibration.

## v0.4.0

**Dépendances embarquées**
- Ajout d'un dossier `vendor/` contenant directement le code source de
  `requests` et de ses dépendances (`urllib3`, `certifi`, `idna`,
  `charset_normalizer`). Plus besoin de `pip install -r requirements.txt` :
  `python main.py` (ou double-clic) suffit désormais, même sur une
  machine sans aucun paquet Python tiers installé.
- `main.py` ajoute automatiquement `vendor/` en tête de `sys.path` avant
  tout import, de façon relative à l'emplacement du projet (fonctionne
  quel que soit le dossier depuis lequel on lance le script).
- Les binaires compilés spécifiques à Linux (`.so` de
  `charset_normalizer`) ont été retirés du vendoring pour garantir la
  portabilité (notamment vers Windows/Visual Studio) : la bibliothèque
  utilise automatiquement son repli 100% Python.
- `requirements.txt` est conservé à titre indicatif/documentaire, mais
  n'est plus nécessaire pour lancer l'application.

## v0.3.0

**Correctif critique**
- La page d'accueil ne s'affichait plus si une dépendance (`requests`)
  n'était pas installée : toutes les pages étaient construites (et donc
  importées) au démarrage, y compris la page de connexion qui dépend de
  `requests`/`urllib3`. Une dépendance manquante faisait planter
  l'application avant même l'affichage de la fenêtre.
- **Fix** : chargement paresseux des pages. Seule la page d'accueil
  (aucune dépendance externe) est construite au démarrage. Les autres
  pages sont importées/construites uniquement quand on y accède, avec un
  message d'erreur clair si une dépendance manque.

**Autres changements**
- Ajout d'un système de version centralisé (`core/version.py`), affiché
  dans le titre de la fenêtre et en pied de page d'accueil.
- Ajout de `requirements.txt`.
- Ajout de ce changelog.

## v0.2.0

- Ajout de la connexion au toy via le "Game Mode" de l'app Lovense
  Remote (LAN, IP + port, sans compte développeur).
- Nouvelle page `connection_page.py` (formulaire IP/port/HTTPS, test de
  vibration, statut de connexion synchronisé avec la page d'accueil).
- Réorganisation du code en modules à responsabilité unique :
  - `core/constants.py` — limites partagées
  - `core/lovense_client.py` — communication réseau avec le toy
  - `core/pattern_generator.py` — génération des modèles de vibration
  - `core/app_state.py` — état de connexion partagé entre les pages

## v0.1.0

- Première version : application de bureau (Tkinter) avec une page
  d'accueil présentant le projet.
