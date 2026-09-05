# hermes-discord-js

Adaptateur de plateforme Discord fine-tuné et optimisé pour [Hermes Agent](https://github.com/NousResearch/hermes-agent), propulsé par un pont sidecar moderne en **discord.js v14** (Node.js / TypeScript).

Conçu pour remplacer le fichier monolithique officiel `discord.py` par un adaptateur ultra-léger, ergonomique et configuré sur-mesure pour un usage personnel de haute productivité (sessions par Forum, communications système en DM, contrôle d'exécution d'urgence et rendu soigné).

---

## 🏗️ Architecture

```
Utilisateur ↔ Discord Gateway (discord.js v14) ↔ Loopback local (HTTP/SSE : 8790) ↔ Adaptateur Python ↔ Gateway Hermes Agent
```

- **Sidecar (`sidecar/`)** : Processus modulaire en TypeScript compilé inspiré de l'architecture de [`aio-discordbot`](https://github.com/FRFlo/aio-discordbot) :
  - `commands/` : Définitions individuelles des commandes slash (`/close`, `/stop`, `/reset`, `/status`, `/model`).
  - `buttons/` : Gestionnaires d'interactions de boutons (`cancel`, `action`, `alert`, `approval`, `clarify`).
  - `events/` : Écouteurs d'événements Gateway (`ready`, `messageCreate`, `interactionCreate`).
  - `handlers/` : Chargeurs dynamiques automatiques des commandes, boutons et événements.
  - `services/` : Service pont Hermes (`bridge.ts`) et clients d'envoi.
- **Adaptateur (`adapter.py`)** : Sous-classe Python de `BasePlatformAdapter` qui supervise le cycle de vie du sidecar, reçoit les événements via SSE (`/inbound`), transmet les actions sortantes via HTTP REST et gère les alertes système en DM.

---

## ✨ Fonctionnalités & Spécificités Fine-Tunées

### 1. Organisation des Salons & Routage
- **Salon Forum dédié aux Sessions (`DISCORD_FORUM_CHANNEL_ID`)** :
  - Chaque post de forum correspond à une session de travail avec Hermes.
  - **Réponse libre** : Hermes répond directement sans mention `@Hermes` obligatoire dans le fil.
  - Clôture explicite de session via la commande slash `/close` ou le bouton d'action `🔒 Clôturer` (archive automatiquement le fil).
- **Canal Privé (DM)** :
  - Réception directe de toutes les communications système, notifications de crons et alertes d'erreurs critiques.
  - Discussion bidirectionnelle complète possible en DM pour des requêtes directes ou de maintenance.
- **Sécurité Mono-Utilisateur Stricte** :
  - Seul l'utilisateur configuré (`DISCORD_ALLOWED_USERS`, par défaut `544862774002581504`) est autorisé. Tout autre utilisateur ou bot est silencieusement ignoré.

### 2. Contrôle d'Exécution & Boutons d'Action
- **Bouton Stop / Interruption immédiate (`⏹️ Interrompre` & commande `/stop`)** :
  - Pendant l'exécution des outils, un bouton rouge `⏹️ Interrompre` est affiché sur le message de progression.
  - Un clic interrompt instantanément la tâche en cours et passe le statut en `⚠️ Interrompu par l'utilisateur` sans délai ni confirmation bloquante.
- **Boutons sous la Réponse Finale** :
  - `🔄 Régénérer` : relance la dernière requête en un clic.
  - `🔒 Clôturer` : clôture et archive immédiatement le post de forum.

### 3. Expérience Visuelle & Moteur de Rendu
- **Rendu du Raisonnement IA (*Thinking / Chain of Thought*)** :
  - Conversion automatique des blocs de réflexion en **sous-texte natif Discord** (`-# `). Le texte s'affiche grisé et compact, garantissant une distinction visuelle immédiate et fluide avec la réponse finale.
- **Suivi d'Outils & Spoiler Repliable** :
  - Pendant l'exécution : affichage et mise à jour en direct des étapes et outils appelés (`bash`, lecture de fichiers, etc.).
  - À la finalisation : le journal d'exécution est automatiquement replié dans un **bloc spoiler** (`|| ... ||`) pour garder la discussion impeccable tout en préservant l'historique complet consultable d'un clic.
- **Fichiers Logs Automatiques pour Grosses Sorties (> 1 500 car.)** :
  - Dès qu'une sortie de commande (ex: `docker compose logs`, `git diff`) dépasse 1 500 caractères, elle est automatiquement enregistrée et attachée sous forme de fichier `.log` ou `.diff` horodaté joint au message au lieu d'inonder le fil.
- **Réactions Émojis de Statut & Transitions Dynamiques (Mode Queue)** :
  - **Prise en charge immédiate** : ⏳ est ajoutée directement si l'agent est libre.
  - **Mise en file d'attente intelligente** : si l'agent est déjà en cours de génération ou d'exécution d'un outil, le message reçoit immédiatement l'émoji **⏱️** (en attente dans la file).
  - **Transition au tour suivant** : dès que le tour précédent se termine, l'émoji ⏱️ est remplacé par **⏳** (traitement actif).
  - **Clôture** : remplacé par **✅** dès que la réponse est achevée avec succès (ou ❌ en cas d'erreur).
- **Découpage Markdown Intelligent (> 2 000 caractères)** :
  - Découpage automatique respectant la limite de Discord sans jamais casser les blocs de code (fermeture et réouverture propre des balises ` ```lang ` entre les fragments).
  - La citation (reply) n'est attachée qu'au premier fragment.

### 4. Téléchargement & Cache Local des Pièces Jointes
- **Sauvegarde locale automatique** :
  - Tout document, image, script ou archive déposé dans Discord est automatiquement téléchargé dans `/workspace/uploads/` (volume partagé).
- **Auto-injection de texte** :
  - Les fichiers texte/code/config légers (< 50 Ko) voient leur contenu automatiquement injecté dans le contexte du prompt de l'agent.
  - Le chemin local absolu sur le disque est toujours communiqué à l'agent.

### 5. Alertes d'Erreurs Système en DM
- **Embed d'alerte rouge en DM** en cas d'erreur critique ou d'échec de tâche planifiée.
- **Boutons interactifs sous l'alerte** :
  - `🔄 Relancer la tâche` : déclenche une nouvelle tentative immédiate.
  - `🔍 Voir les logs` : demande l'affichage des dernières lignes de log système.

### 6. Questions & Clarifications Interactives (Architecture pi-bridge)
Inspiré directement de `pi-bridge`, le système de clarification et de questions interactives offre une ergonomie riche :
- **Embeds riches** : Embeds bleus avec timing dynamique (`<t:...:R>`), affichage des options numérotées avec leurs descriptions détaillées, et instructions contextuelles.
- **Menus déroulants (StringSelectMenu)** :
  - Sélection simple (`select_single`) ou multi-sélection (`select`) jusqu'à 25 options.
- **Modales Discord (ModalBuilder)** :
  - Bouton `✏️ Autre (texte)` ou `💬 Saisir une réponse` ouvrant une invite modale native avec champ multi-lignes pour saisir une précision ou une réponse personnalisée.
- **Boutons d'action & Contrôle** :
  - `✅ Valider la sélection` : valide le choix multiple.
  - `🔄 Réessayer / Fork` : interrompt et relance la tâche.
  - `❌ Annuler` : annule la question.
- **Résolution visuelle en direct** :
  - Dès validation, l'embed passe en vert (`✅ Choix validé`), le résumé des choix s'affiche avec la mention du validateur, et les composants interactifs sont nettoyés.
  - En cas d'annulation, l'embed passe en rouge (`❌ Question annulée`).

### 7. Cycle de Vie des Messages : Suppression & Modification Dynamique
- **Suppression de Message (`messageDelete`)** :
  - **Message Utilisateur** : supprime le tour complet dans la session Hermes (`SessionDB` / `SessionStore`) : le message de l'utilisateur ainsi que les réponses et appels d'outils associés de l'agent. Supprime également le message de réponse du bot sur Discord.
  - **Message Assistant** : si l'utilisateur supprime directement un message envoyé par le bot sur Discord, ce message de réponse est retiré de la session.
  - **Interruption automatique** : si une exécution est en cours lors de la suppression, elle est immédiatement interrompue via `/stop` avant le nettoyage.
- **Modification de Message (`messageUpdate`)** :
  - **Régénération intelligente** : lorsqu'un message utilisateur antérieur ou récent est modifié sur Discord, l'historique de la session est tronqué à partir de ce point (façon ChatGPT / Claude).
  - **Nettoyage Discord** : l'ancien message de réponse du bot est automatiquement supprimé sur Discord.
  - **Nouveau cycle de réponse** : l'agent déclenche immédiatement une nouvelle génération avec le texte édité, publiant la réponse fraîche dans le fil.
  - **Filtrage anti-bruit** : les modifications de métadonnées Discord sans changement de texte (comme le déploiement d'aperçus de liens) sont ignorées.

### 8. Commandes Slash Natives
- `/cron` : **Gestionnaire interactif des tâches planifiées Cron Hermes** :
  - Liste de toutes les tâches enregistrées avec leur fréquence/expression cron, état (🟢 Actif / ⏸️ En pause) et prochaine exécution (`<t:...:R>`).
  - Menu déroulant pour inspecter les détails complets d'une tâche (prompt, destination, statut du dernier run).
  - ⚡ **Exécuter maintenant** : déclenchement immédiat de la tâche en arrière-plan sans attendre son heure programmée.
  - ⏸️/▶️ **Mettre en pause / Reprendre** : activation ou désactivation d'un clic avec mise à jour visuelle instantanée.
  - 📜 **Dernier output** : consultation du dernier rapport d'exécution sauvegardé dans `~/.hermes/cron/output/`.
  - 🗑️ **Supprimer la tâche** : suppression sécurisée avec confirmation.
  - ➕ **Planifier une tâche** : ouverture d'une modale Discord native pour créer une nouvelle tâche cron (Nom, Expression cron/intervalle, Prompt, Destination).
- `/sessions` : **Gestionnaire interactif des sessions** avec menus déroulants et boutons :
  - Sélection d'une session parmi les fils du forum (actifs et archivés).
  - Détails complets de la session (statut, nombre de messages, date de création, lien direct).
  - ✏️ **Renommer** : ouvre une modale native Discord pour renommer instantanément le fil.
  - 🔒/🔓 **Archiver / Désarchiver** : bascule l'état du fil d'un simple clic.
  - 🗑️ **Supprimer** : suppression sécurisée du fil Discord avec confirmation et purge automatique de l'historique dans Hermes `SessionDB`.
- `/context` : Affiche l'analyse détaillée du contexte de la session active (fenêtre de tokens, jauge d'utilisation, seuil de compression, historique et modèle).
- `/close` : Clôture et archive le fil de discussion de la session de forum courante.
- `/stop` : Interrompt immédiatement la commande ou tâche en cours.
- `/reset` : Réinitialise le contexte de la conversation active.
- `/status` : Affiche l'état de santé du bot, la latence WebSocket, l'uptime et la consommation mémoire.
- `/model [nom]` : Affiche ou modifie le modèle LLM actif.

---

## ⚙️ Variables d'Environnement

| Variable | Description | Valeur par défaut |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Jeton d'authentification du bot Discord (obligatoire) | — |
| `DISCORD_ALLOWED_USERS` | Identifiant Discord de l'utilisateur unique autorisé | `544862774002581504` |
| `DISCORD_FORUM_CHANNEL_ID` | Identifiant du salon Forum pour les sessions | `1544452203207589938` |
| `DISCORD_HOME_CHANNEL` | Canal de notification par défaut (mettre votre ID ou `dm`) | `544862774002581504` |
| `HERMES_UPLOADS_DIR` | Répertoire de stockage des uploads sur le disque | `/workspace/uploads` |
| `DISCORD_REACTIONS` | Activer les réactions de statut (⏳, ✅, ❌) | `true` |
| `HERMES_DISCORD_JS_PORT` | Port d'écoute de la boucle locale HTTP/SSE | `8790` |

---

## 🚀 Installation & Déploiement

### 1. Activer le plugin dans Hermes Agent
Dans votre fichier `config/hermes/config.yaml` :

```yaml
plugins:
  enabled:
    - discord-js
```

### 2. Compilation du sidecar
Le sidecar est automatiquement compilé au démarrage de l'adaptateur si `dist/` est absent. Vous pouvez aussi le compiler manuellement :

```bash
cd config/hermes/plugins/discord-js/sidecar
npm install
npm run build
```
