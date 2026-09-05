# Inventaire Exhaustif des Fonctionnalités de l'Adaptateur Discord par Défaut

Ce document recense l'intégralité des fonctionnalités implémentées dans l'adaptateur Discord officiel de Hermes Agent (`plugins/platforms/discord/` et son fichier monolithique `adapter.py` de 7 376 lignes). Il sert de cahier des charges et de référence fonctionnelle pour la réimplémentation du plugin avec **discord.js**.

---

## Sommaire

1. [Transport, Cycle de Vie & Santé Réseau](#1-transport-cycle-de-vie--santé-réseau)
2. [Authentification, Autorisations & Sécurité](#2-authentification-autorisations--sécurité)
3. [Règles de Déclenchement & Routage des Salons](#3-règles-de-déclenchement--routage-des-salons)
4. [Gestion de Contexte, Historique & Rattrapage](#4-gestion-de-contexte-historique--rattrapage)
5. [Formatage, Rendu des Réponses & Découpage](#5-formatage-rendu-des-réponses--découpage)
6. [Composants d'Interface Graphique (UI & Boutons)](#6-composants-dinterface-graphique-ui--boutons)
7. [Slash Commands Natives & Synchronisation](#7-slash-commands-natives--synchronisation)
8. [Gestion des Pièces Jointes & Fichiers Médias](#8-gestion-des-pièces-jointes--fichiers-médias)
9. [Mode Vocal & Salons Audio](#9-mode-vocal--salons-audio)
10. [Canal Principal (Home Channel) & Tâches Cron](#10-canal-principal-home-channel--tâches-cron)

---

## 1. Transport, Cycle de Vie & Santé Réseau

- **Client Discord WebSocket & REST** : Basé sur `discord.py` avec écoute des événements de Gateway en continu.
- **Intents Privilégiés** :
  - `MessageContent` : Obligatoire pour lire le contenu textuel des messages.
  - `GuildMembers` : Résolution des pseudonymes, rôles et identifiants.
  - `Guilds`, `DirectMessages` : Réception des messages de serveurs et messages privés.
- **Contrôle de Santé WebSocket (Liveness Probe)** :
  - Vérification combinée de l'état du socket, de l'âge du dernier acquittement (Heartbeat ACK) et de la latence Discord (`websocket_liveness_interval_seconds`, `websocket_heartbeat_ack_max_age_seconds`, `websocket_max_latency_seconds`).
  - Après plusieurs échecs consécutifs (`websocket_liveness_failure_threshold`), émission d'une erreur fatale contrôlée déclenchant la recréation propre de l'adaptateur par le watcher Hermes.
- **Support Proxy Réseau** : Prise en charge de `DISCORD_PROXY` (protocoles `http://`, `https://`, et `socks5://`).
- **Arrêt Gracieux (Graceful Shutdown)** :
  - Vidage des messages texte en attente de traitement (`_flush_text_batch`).
  - Annulation des tâches de fond et fermeture propre des connexions actives.

---

## 2. Authentification, Autorisations & Sécurité

- **Liste d'utilisateurs autorisés (`DISCORD_ALLOWED_USERS`)** : Filtrage strict par User IDs (et résolution automatique des noms d'utilisateurs).
- **Rôles autorisés (`DISCORD_ALLOWED_ROLES`)** : Autorisation basée sur les rôles Discord (relation OU avec la liste des utilisateurs autorisés).
- **Switches de développement** :
  - `DISCORD_ALLOW_ALL_USERS` : Ouvre l'accès à tous les utilisateurs Discord pour le bot.
  - `GATEWAY_ALLOW_ALL_USERS` : Ouvre l'accès globalement sur toutes les plateformes de la passerelle.
- **Filtrage des salons autorisés et interdits** :
  - `DISCORD_ALLOWED_CHANNELS` : Restreint l'écoute du bot à une liste blanche de salons.
  - `DISCORD_IGNORED_CHANNELS` : Liste noire prioritaire (le bot ne répond jamais dans ces salons, même mentionné).
- **Contrôle d'accès granulaire aux Slash Commands** :
  - Distinction Administrateurs (`allow_admin_from` / `group_allow_admin_from`) ayant accès à toutes les commandes slash.
  - Utilisateurs restreints (`user_allowed_commands`) limités aux commandes spécifiées (avec accès par défaut garanti à `/help` et `/whoami`).
- **Filtrage des interactions entre bots (`DISCORD_ALLOW_BOTS`)** :
  - Valeurs : `"none"` (ignore tous les bots - valeur par défaut sûre), `"mentions"` (accepte les bots qui mentionnent expressément Hermes), `"all"` (accepte tous les messages de bots).
- **Système de pairage interactif (`pairing.py`)** : Prise en charge des flux d'approbation pour les utilisateurs inconnus.

---

## 3. Règles de Déclenchement & Routage des Salons

- **Obligation de Mention (`DISCORD_REQUIRE_MENTION`)** :
  - En salons de serveurs : Le bot ne répond que lorsqu'il est explicitement mentionné (`@Hermes`).
  - En DMs : Répond à tous les messages sans mention.
- **Salons en Réponse Libre (`DISCORD_FREE_RESPONSE_CHANNELS`)** :
  - Salons désignés où le bot répond sans mention obligatoire (style salon d'assistance/chat direct).
- **Filtrage des conversations entre tiers (`DISCORD_IGNORE_NO_MENTION`)** :
  - Si un message mentionne un autre utilisateur du serveur mais ne mentionne pas Hermes, le bot s'abstient pour ne pas interrompre les conversations humaines.
- **Création Automatique de Fils (`DISCORD_AUTO_THREAD`)** :
  - Crée automatiquement un fil Discord dédié lors d'une mention dans un salon textuel pour isoler la session de travail.
  - Salons sans fil forcé (`DISCORD_NO_THREAD_CHANNELS`) : Répond directement dans le salon principal sans créer de thread.
- **Gestion des Mentions dans les Fils (`DISCORD_THREAD_REQUIRE_MENTION`)** :
  - Par défaut `false` : Dès que le bot est dans un fil, il répond sans mention.
  - Activé à `true` : Requiert la mention même dans les fils (indispensable pour les fils partagés entre plusieurs bots concurrents).
- **Support des Canaux Forum Discord** :
  - Détection des posts de forum et gestion appropriée des fils de discussion associés.

---

## 4. Gestion de Contexte, Historique & Rattrapage

- **Rattrapage du Contexte de Salon (`DISCORD_HISTORY_BACKFILL`)** :
  - Lors d'une mention, scanne les messages récents du salon (`DISCORD_HISTORY_BACKFILL_LIMIT`, par défaut 50) jusqu'au dernier message du bot pour reconstituer l'échange et fournir le contexte immédiat à l'agent.
- **Rattrapage des Messages Manqués Hors-ligne (`DISCORD_MISSED_MESSAGE_BACKFILL`)** :
  - Base SQLite locale dédiée (`gateway/discord_message_recovery.db`).
  - À la reconnexion après une panne ou un redémarrage, scanne l'historique des salons configurés pour récupérer les messages manqués pendant la coupure sans doubler les réponses.
- **Isolation des Sessions par Utilisateur (`group_sessions_per_user`)** :
  - Gère l'isolation ou le partage d'historique entre plusieurs participants dans un même salon.

---

## 5. Formatage, Rendu des Réponses & Découpage

- **Découpage Intelligent des Messages (> 2 000 caractères)** :
  - Respect de la limite stricte de Discord avec découpage propre (`_cap_split_chunks`).
  - Préservation des blocs de code Markdown (fermeture et réouverture automatique des balises de code ` ``` ` entre les blocs découpés).
  - Gestion du débordement lors de l'édition de messages (`_edit_overflow_split`).
- **Modes de Réponse par Citation (`DISCORD_REPLY_TO_MODE`)** :
  - `"first"` : Ajoute la référence Discord (reply) sur le premier fragment uniquement.
  - `"all"` : Ajoute la référence sur tous les fragments.
  - `"off"` : Envoie les messages sans citation.
- **Contrôle Strict des Pings Sortants (`allow_mentions`)** :
  - `everyone: false` : Empêche le bot de notifier `@everyone` ou `@here`.
  - `roles: false` : Bloque les pings de rôles.
  - `users: true` : Autorise le ping des utilisateurs ciblés.
  - `replied_user: true` : Notifie ou non l'auteur du message cité.
- **Rendu du Raisonnement IA (Thinking/Reasoning Blocks)** :
  - Mode natif Discord : Utilisation du préfixe de sous-texte `-# ` (texte petit et grisé).
  - Modes alternatifs : Citation (`> `) ou bloc de code Markdown (` ``` `).
- **Indicateurs de Frappe & Temporisation** :
  - Envoi continu de l'indicateur d'écriture (`send_typing`) pendant la réflexion de l'agent.
  - Lissage des flux de texte par fenêtres tampon (`HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS`).
- **Réactions Émojis de Statut (`DISCORD_REACTIONS`)** :
  - Ajout d'émojis sur le message utilisateur selon l'état du traitement :
    - 👀 : Traitement en cours (processing start).
    - ✅ : Traitement terminé avec succès.
    - ❌ : Échec ou erreur survenue.

---

## 6. Composants d'Interface Graphique (UI & Boutons)

- **Clarification Interactive (`send_clarify`)** :
  - Rendu des questions de l'outil `clarify` sous forme de boutons d'action cliquables par choix.
  - Bouton spécial "Autre" pour saisir une réponse libre au clavier.
  - Désactivation automatique des boutons après sélection pour éviter les doubles résolutions.
- **Approbation de Commandes Dangereuses (`send_exec_approval`)** :
  - Boutons d'action `Approve` / `Deny` pour valider ou rejeter l'exécution de commandes système sensibles demandées par l'agent.
- **Confirmation de Slash Commands (`send_slash_confirm`)** :
  - Boutons de validation `Once` / `Always` / `Cancel` (par exemple pour `/reload-mcp`).
- **Sélecteur de Modèles Interactif (`send_model_picker`)** :
  - Interface interactive pour la commande `/model` avec menus déroulants (Select Menus) à deux niveaux : Fournisseur -> Modèle.
  - Gestion d'expiration de l'interaction (timeout de 120 secondes).
- **Sélecteurs à Choix Uniques (`send_choice_picker`)** :
  - Menus déroulants pour les commandes à choix fini (`/reasoning`, `/fast`).

---

## 7. Slash Commands Natives & Synchronisation

- **Enregistrement des Commandes Applicatives (`app_commands`)** :
  - Transformation automatique des compétences installées (`skills`) en commandes slash natives Discord avec autocomplétion des arguments.
  - Prise en charge des commandes système intégrées : `/help`, `/whoami`, `/model`, `/status`, `/reset`, `/bg`, `/sethome`, etc.
- **Politique de Synchronisation Sûre (`DISCORD_COMMAND_SYNC_POLICY`)** :
  - `"safe"` : Calcule l'empreinte (diff) des commandes enregistrées et n'applique que les modifications nécessaires pour éviter les blocages de rate-limit de Discord.
  - `"bulk"` : Synchronisation globale forcée.
  - `"off"` : Désactive la synchronisation au démarrage.
- **Désactivation pour Topologies Multi-Bots** :
  - Option `slash_commands: false` pour les passerelles secondaires (staging/prod sur le même bot).

---

## 8. Gestion des Pièces Jointes & Fichiers Médias

- **Réception et Téléchargement de Fichiers** :
  - Accepte tout type de fichier sans restriction d'extension.
  - Téléchargement et mise en cache locale sous `~/.hermes/cache/documents/`.
  - Injection automatique du contenu textuel des fichiers légers (code, config, JSON, etc. jusqu'à 100 Ko) dans le prompt de l'agent.
  - Plafond de taille configurable (`DISCORD_MAX_ATTACHMENT_BYTES`, défaut 32 Mo).
- **Envoi de Médias Sortants (Balises `MEDIA:`)** :
  - Remplacement automatique des balises `MEDIA:/chemin` émises par l'agent par de véritables pièces jointes Discord :
    - **Images** : Prévisualisation intégrée dans le salon.
    - **GIFs Animés** (`send_animation`) : Envoi sous `animation.gif` garantissant la lecture en boucle automatique.
    - **Vidéos** (`send_video`) : Lecteur vidéo natif Discord.
    - **Messages Vocaux** (`send_voice`) : Fichier audio / bulle vocale.
    - **Documents** (`send_document`) : Fichier téléchargeable.
  - Gestion du dépassement de taille HTTP 413 avec repli vers un lien de téléchargement local.

---

## 9. Mode Vocal & Salons Audio

- **Transcription des Messages Vocaux Entrants** :
  - Prise en charge des messages vocaux Discord avec transcription automatique via les fournisseurs STT (Groq Whisper, OpenAI Whisper ou faster-whisper local).
- **Synthèse Vocale Sortante (TTS)** :
  - Commande `/voice tts` pour accompagner les réponses textuelles d'une piste vocale générée.
- **Connexion aux Salons Vocaux Discord (Voice Channels)** :
  - Capacité pour le bot de rejoindre un salon vocal (`join_voice_channel`, `leave_voice_channel`).
  - Réception du flux audio des participants avec décodage Opus / PCM (`VoiceReceiver`).
  - Diffusion audio en direct dans le salon avec mixage logiciel (`voice_mixer.py`), son d'ambiance et gestion des silences d'amorce.
  - Détection d'inactivité et déconnexion automatique (`voice_channel_inactivity_timeout_seconds`).

---

## 10. Canal Principal (Home Channel) & Tâches Cron

- **Désignation du Salon Principal** :
  - Configuration via `DISCORD_HOME_CHANNEL` ou via la commande slash `/sethome`.
  - Sert de canal par défaut pour les messages proactifs de l'agent (sorties de cron jobs, rappels, alertes système).
- **Module d'Envoi Autonome (`_standalone_send`)** :
  - Fonction d'expédition REST directe permettant aux tâches planifiées cron de publier sur Discord même si l'adaptateur complet de la passerelle n'est pas instancié dans le processus d'exécution.
