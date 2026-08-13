# ErosPulse

**ErosPulse** est une application Python dédiée au contrôle interactif et à l'automatisation d'appareils haptiques / de bien-être connectés (notamment la gamme Lovense) via une interface graphique moderne et des générateurs de motifs de vibration dynamiques.

---

## 🚀 Fonctionnalités Principales

- **Interface Graphique Moderne (PyQt / Custom UI)** : Navigation fluide par onglets (Accueil, Connexion, Contrôle Textuel / Motifs).
- **Intégration Lovense (API / Local Network)** : Communication directe avec les appareils Lovense via le client dédié (`LovenseClient`).
- **Générateur de Motifs de Vibration** : Création et envoi de séquences, rythmes et variations d'intensité adaptées (`pattern_generator.py`, `vibration_command.py`).
- **Mode Déconnecté / Vendor Embed** : Gestion des dépendances intégrées (`requests`, `urllib3`, `certifi`, `charset_normalizer`, `idna`) dans le répertoire `vendor/` pour garantir une exécution autonome sans conflit d'environnement.
- **Support Multiplateforme & IDE** : Projet structuré pour Python standard, Visual Studio (`.sln`), et PyCharm / VS Code (`.pyproj`).

---

## 📁 Structure du Projet

```text
erospulse_v0.11/
├── main.py                     # Point d'entrée principal de l'application
├── requirements.txt            # Dépendances requises
├── CHANGELOG.md                # Historique des versions et modifications
├── ErosPulse.sln / .pyproj     # Fichiers de projet Visual Studio
│
├── core/                       # Logique métier et communication
│   ├── app_state.py            # Gestion de l'état global de l'application
│   ├── ai_prompt.py            # Modules de génération / interprétation intelligente
│   ├── constants.py            # Constantes et configurations globales
│   ├── lovense_client.py       # Client d'interaction avec l'API / appareils Lovense
│   ├── pattern_generator.py    # Générateur de motifs et rythmes de vibration
│   ├── vibration_command.py    # Modélisation des commandes de vibration
│   └── version.py              # Informations de version du projet
│
├── ui/                         # Interface Utilisateur (GUI)
│   ├── app_window.py           # Fenêtre principale et navigation
│   ├── theme.py                # Thème visuel et styles CSS/QSS
│   └── pages/                  # Pages de l'interface
│       ├── home_page.py        # Tableau de bord / Accueil
│       ├── connection_page.py  # Gestion de la connexion aux appareils
│       └── text_page.py        # Contrôle par texte / commandes
│
└── vendor/                     # Bibliothèques tierces embarquées
    ├── certifi/
    ├── charset_normalizer/
    ├── idna/
    ├── requests/
    └── urllib3/
```

---

## 🛠️ Configuration et Installation

### Prérequis
- **Python 3.8+** recommandé.

### Installation

1. **Cloner ou extraire le projet** dans le dossier de votre choix.
2. *(Optionnel mais conseillé)* Créer et activer un environnement virtuel :
   ```bash
   python -m venv venv
   # Sur Windows :
   venv\Scripts\activate
   # Sur Linux / macOS :
   source venv/bin/activate
   ```
3. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 Utilisation

Pour lancer l'application, exécutez le fichier `main.py` depuis la racine du projet :

```bash
python main.py
```

### Étapes d'utilisation :
1. **Connexion** : Rendez-vous sur l'onglet **Connection** pour détecter et appairer votre appareil Lovense (via le réseau local / Lovense Connect App).
2. **Contrôle & Motifs** : Utilisez la page d'accueil ou la page textuelle pour appliquer des motifs de vibration ou générer des variations d'intensité en temps réel.

---

## 📦 Dépendances & Vendorisation

Le projet inclut un répertoire `vendor/` contenant des copies autonomes de bibliothèques courantes (`requests`, `urllib3`, etc.), permettant au projet d'être distribué sous forme de package autonome sans dépendre obligatoirement d'une connexion Internet pour récupérer des packages externes.

---

## 📄 Licence & Crédits

- **Version** : 0.15
- **Projet** : ErosPulse
