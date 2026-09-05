# hermes-discord-js

Plugin d'adaptation de plateforme Discord pour [Hermes Agent](https://github.com/NousResearch/hermes-agent), propulsé par un pont sidecar en **discord.js** (Node.js / TypeScript).

## Architecture

```
Utilisateur ↔ Discord Gateway (discord.js) ↔ Loopback local (HTTP/SSE) ↔ Adaptateur Python ↔ Gateway Hermes Agent
```

- **Sidecar (`sidecar/`)** : Pont léger et rapide en Node.js/TypeScript exposant des points d'accès HTTP/SSE locaux sur `127.0.0.1:8790`.
- **Adaptateur (`adapter.py`)** : Sous-classe Python de `BasePlatformAdapter` qui supervise le cycle de vie du sidecar, reçoit le flux d'événements entrants et achemine les messages sortants.

## Installation dans Hermes Agent

Placez ce répertoire dans `$HERMES_HOME/plugins/discord-js` ou ajoutez-le en sous-module Git :

```bash
git submodule add https://github.com/FRFlo/hermes-discord-js.git config/hermes/plugins/discord-js
```

Activez ensuite le plugin dans votre fichier `config.yaml` :

```yaml
plugins:
  enabled:
    - discord-js
```

## Prérequis

- Node.js >= 18 (Node 26 recommandé)
- `DISCORD_BOT_TOKEN`
