# hermes-discord-py (discord.py fine-tuned)

Adaptateur de plateforme Discord 100% natif en **Python** propulsé par **discord.py 2.x**, optimisé et fine-tuné pour [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Conçu sans aucun processus sidecar ni dépendance Node.js externe : tout tourne directement dans le processus Python du plugin Hermes Agent avec une latence minimale, une stabilité totale et une intégration native approfondie avec l'écosystème Hermes (`SessionDB`, crons, commandes, interactions UI).

---

## 🏛️ Architecture Modulaire

L'adaptateur a été découpé et structuré en modules thématiques clairs pour une maintenabilité et une lisibilité optimales :

```
hermes-discord-py/
├── adapter.py              # Classe DiscordPyAdapter principale & point d'entrée register(ctx)
├── splitter.py             # Découpage Markdown intelligent, sous-texte thinking & log files
├── downloader.py           # Téléchargement et mise en cache d'attachements Discord
├── views/                  # Composants graphiques interactifs Discord UI (discord.ui)
│   ├── actions.py          # Boutons sous la réponse finale (Régénérer, Clôturer)
│   ├── alert.py            # Embeds d'alertes en DM avec boutons Relancer et Logs
│   ├── approval.py         # Approbation interactive de commandes sensibles
│   ├── common.py           # Utilitaires d'affichage communs (truncate, etc.)
│   ├── cron.py             # Gestionnaire interactif complet des crons (/cron)
│   ├── model.py            # Sélecteur de modèles LLM (/model)
│   ├── progress.py         # Suivi en temps réel des outils avec bouton Interrompre
│   ├── questions.py        # Questions interactives style pi-bridge (menus, modales)
│   └── sessions.py         # Gestionnaire interactif des sessions de forum (/sessions)
├── commands/               # Commandes Slash natives Discord (app_commands.CommandTree)
│   ├── control_cmds.py     # /stop (interruption immédiate)
│   ├── cron_cmds.py        # /cron (gestionnaire de crons)
│   ├── model_cmds.py       # /model (sélecteur et autocomplétion)
│   └── session_cmds.py     # /close, /reset, /status, /context, /sessions
├── services/               # Services métier et intégration avec les modules Hermes
│   ├── cron_service.py     # Synchronisation avec cron.jobs Hermes
│   └── session_service.py  # SessionDB, SessionStore et forum threads
└── events/                 # Gestionnaires d'événements Discord avancés
    └── lifecycle.py        # Événements on_message_delete et on_message_edit
```

---

## ✨ Fonctionnalités & Spécificités Fine-Tunées

### 1. Organisation des Salons & Routage
- **Salon Forum dédié aux Sessions (`DISCORD_FORUM_CHANNEL_ID`)** :
  - Chaque post de forum correspond à une session de travail avec Hermes.
  - **Réponse libre** : Hermes répond directement sans mention `@Hermes` obligatoire dans le fil.
  - Clôture explicite de session via la commande slash `/close` ou le bouton d'action `📁 Clôturer` (archive automatiquement le fil).
- **Canal Privé (DM)** :
  - Réception directe de toutes les communications système, notifications de crons et alertes d'erreurs critiques.
  - Discussion bidirectionnelle complète possible en DM pour des requêtes directes ou de maintenance.
- **Sécurité Mono-Utilisateur Stricte** :
  - Seul l'utilisateur configuré (`DISCORD_ALLOWED_USERS`, par défaut `544862774002581504`) est autorisé. Tout autre utilisateur ou bot est silencieusement ignoré.

### 2. Contrôle d'Exécution & Boutons d'Action
- **Bouton Stop / Interruption immédiate (`⏹️ Interrompre` & commande `/stop`)** :
  - Pendant l'exécution des outils, un bouton rouge `⏹️ Interrompre` est affiché sur le message de progression.
  - Un clic interrompt instantanément la tâche en cours et passe le statut en `⚠️ Interrompu par l'utilisateur`.
- **Boutons sous la Réponse Finale** :
  - `🔄 Régénérer` : relance la dernière requête en un clic.
  - `📁 Clôturer` : clôture et archive immédiatement le post de forum.

### 3. Expérience Visuelle & Moteur de Rendu
- **Rendu du Raisonnement IA (*Thinking / Chain of Thought*)** :
  - Conversion automatique des blocs de réflexion `<thinking>...</thinking>` en **sous-texte natif Discord** (`-# `).
- **Suivi d'Outils & Spoiler Repliable** :
  - Les étapes d'outils sont mises à jour en direct (`• tool (args) : ⏳` puis `✅` ou `❌`).
  - À la fin du tour, le bloc est automatiquement replié dans un spoiler (`||...||`).
- **Sauvegarde des Sorties Volumineuses** :
  - Si un outil renvoie plus de 1 500 caractères, la sortie est automatiquement extraite, sauvegardée sous forme de fichier `.log` ou `.diff` joint, et résumée dans le message.
- **Transitions d'Émojis & File d'Attente** :
  - Si une requête arrive alors que le salon est occupé, elle reçoit immédiatement la réaction `⏱️`.
  - Au démarrage du tour : transition `⏱️` ➔ `⏳`.
  - En fin de tour : transition `⏳` ➔ `✅` (succès) ou `❌` (échec).

### 4. Questions & Clarifications Interactives (style `pi-bridge`)
- L'agent peut solliciter l'utilisateur de manière interactive (`ask_question` / `send_clarify`).
- Affichage d'un Embed soigné avec les détails et le contexte.
- Menus déroulants (`Select`) pour les choix prédéfinis.
- Modale de saisie textuelle libre (`✏️ Autre (texte)`).
- Gestion de compte à rebours et d'expiration propre (`on_timeout`).

### 5. Cycle de Vie Avancé des Messages
- **Suppression d'un message utilisateur** (`on_message_delete`) :
  - Interrompt immédiatement Hermes avec `/stop`.
  - Supprime les réponses du bot associées sur Discord.
  - Nettoie le tour de parole dans `SessionDB` pour conserver un historique cohérent.
- **Modification d'un message utilisateur** (`on_message_edit`) :
  - Interrompt le tour en cours avec `/stop`.
  - Supprime la réponse précédente du bot sur Discord.
  - Tronque l'historique de session Hermes à ce message et relance la génération avec le nouveau texte.

---

## 🚀 Installation & Démarrage

### Prérequis
- Python 3.10+ (testé avec Python 3.14)
- Dépendance Python requise :
  ```bash
  pip install discord.py
  ```

### Variables d'Environnement
| Variable | Description | Valeur par défaut |
| :--- | :--- | :--- |
| `DISCORD_BOT_TOKEN` | Jeton d'authentification du bot Discord | *(Requis)* |
| `DISCORD_ALLOWED_USERS` | Liste des IDs utilisateurs autorisés (séparés par virgule) | `544862774002581504` |
| `DISCORD_ALLOW_ALL_USERS` | Autoriser tous les utilisateurs | `false` |
| `DISCORD_FORUM_CHANNEL_ID` | Salon Forum dédié aux sessions | `1544452203207589938` |
| `DISCORD_HOME_CHANNEL` | Salon par défaut pour les crons | `""` |
| `DISCORD_REACTIONS` | Activer les réactions de statut | `true` |
| `HERMES_UPLOADS_DIR` | Dossier de cache des pièces jointes | `./uploads` |
