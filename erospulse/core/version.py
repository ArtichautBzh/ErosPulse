"""
version.py
==========
Numéro de version centralisé de l'application, pour suivre son
évolution. À incrémenter à chaque livraison :
    - MAJOR : changement majeur d'architecture ou de fonctionnalités
    - MINOR : nouvelle fonctionnalité (ex: nouvelle page, nouveau module)
    - PATCH : correctif de bug, sans nouvelle fonctionnalité

Historique résumé (voir CHANGELOG.md à la racine pour le détail) :
    0.1.0 — Page d'accueil
    0.2.0 — Connexion au toy (Game Mode) + réorganisation en modules
            à responsabilité unique (core/, ui/pages/)
    0.3.0 — Correctif : la page d'accueil ne s'ouvrait plus si une
            dépendance (requests) manquait ; chargement paresseux
            des pages + messages d'erreur clairs
    0.4.0 — Dépendances embarquées (vendor/) : plus besoin de pip
            install, "python main.py" suffit
    0.4.1 — Le bouton "Tester" se connecte automatiquement s'il n'y a
            pas déjà de connexion active, puis envoie la vibration de
            test (au lieu d'exiger de cliquer d'abord sur "Se connecter")
    0.5.0 — Test par moteur : l'Edge 2 a 2 moteurs indépendants
            (interne + périnée), chacun avec son propre bouton de test
    0.6.0 — Nouvelle page de saisie de texte. Le bouton "Commencer" de
            l'accueil y redirige si un toy est connecté, ou vers la
            page de connexion sinon
    0.7.0 — Format de commande de vibration [Y;D;[A;B]] (moteur, durée,
            intensités) : parsing, validation et exécution réseau
            (core/vibration_command.py)
    0.8.0 — Prompt IA (core/ai_prompt.py) expliquant le format
            [Y;D;[A;B]] à un modèle de langage, pour qu'il génère la
            séquence de commandes à partir du texte de l'utilisateur
    0.9.0 — Le bouton "Générer le modèle de vibration" est branché :
            parse la séquence [Y;D;[A;B]] saisie et la joue réellement
            sur le toy connecté, avec suivi de progression et bouton
            "Arrêter"
    0.10.0 — Rebranding complet en "ErosPulse" (nom d'app, page d'accueil,
             fichiers projet). Le bouton "Arrêter" devient "Pause" /
             "Reprendre" : il coupe le toy immédiatement puis relance
             la commande en cours pour le temps de vibration restant
    0.11.0 — Retrait du libellé "Ton texte" sur la page de séquence.
             Ajout d'un décompte min:sec : durée totale affichée en
             temps réel pendant la saisie, puis compte à rebours du
             temps restant pendant la lecture (figé pendant une pause)
    0.12.0 — 4 correctifs : (1) retrait du texte "Connexion à l'Edge 2"
             sur la page de connexion ; (2) le bouton "← Accueil" met
             la séquence en PAUSE (au lieu de l'arrêter) pendant une
             lecture, reprise possible en revenant sur la page ; (3-4)
             mise en page de la page de texte entièrement revue (pack
             au lieu de place) pour que le décompte, le compteur de
             caractères et le texte d'aide restent toujours visibles
             et correctement dimensionnés quelle que soit la taille de
             la fenêtre
    0.13.0 — Graphique intensité(t) des deux moteurs (ui/widgets/
             sequence_chart.py, Canvas maison sans dépendance externe),
             avec repère de lecture en direct. Le message "Commande
             X/Y — [...]" persiste maintenant à travers pause /
             navigation vers l'accueil / reprise, au lieu d'être
             remplacé par un texte générique "Reprise…"
    0.14.0 — Configuration PyInstaller (ErosPulse.spec) + scripts de
             build (build_exe.bat / build_exe.sh) pour générer un
             exécutable autonome (.exe sur Windows, binaire natif sur
             macOS/Linux) à partir des sources
    0.15.0 — Extension de syntaxe : blocs LOOP(N){...} pour répéter un
             groupe de commandes [Y;D;[A;B]] N fois, sans avoir à le
             retaper (imbrication de boucles supportée). Reste
             totalement rétrocompatible : parse_sequence() développe
             les boucles et continue de renvoyer une liste plate de
             commandes, donc aucune autre partie de l'app n'a besoin
             de connaître cette notion
    0.16.0 — Import de modèles de séquence (.txt) depuis un dossier
             configurable (par défaut Import/ à la racine du projet),
             listés dans un menu déroulant sur la page de séquence.
             Bouton pour masquer/afficher la zone de texte
"""

APP_NAME = "ErosPulse"
APP_VERSION = "0.16.0"


def version_label() -> str:
    return f"{APP_NAME} — v{APP_VERSION}"
