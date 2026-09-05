import http from "node:http";
import { URL } from "node:url";
import { DiscordBridgeClient } from "./discord.js";
import { InboundMessageEvent, OutboundSendRequest, OutboundSendResponse } from "./types.js";

const PORT = parseInt(process.env.HERMES_SIDECAR_PORT || "8790", 10);
const HOST = "127.0.0.1";
const TOKEN = process.env.HERMES_SIDECAR_TOKEN || "";
const DISCORD_BOT_TOKEN = process.env.DISCORD_BOT_TOKEN || "";

const discord = new DiscordBridgeClient();
const inboundSubscribers = new Set<http.ServerResponse>();

discord.setInboundHandler((event: InboundMessageEvent) => {
  const payload = `data: ${JSON.stringify(event)}\n\n`;
  for (const res of inboundSubscribers) {
    try {
      res.write(payload);
    } catch {
      inboundSubscribers.delete(res);
    }
  }
});

function verifyAuth(req: http.IncomingMessage, res: http.ServerResponse): boolean {
  if (!TOKEN) return true; // mode développement sans token
  const incoming = req.headers["x-hermes-token"] || req.headers["authorization"]?.replace("Bearer ", "");
  if (incoming !== TOKEN) {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "non autorisé" }));
    return false;
  }
  return true;
}

async function readJsonBody<T>(req: http.IncomingMessage): Promise<T> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => {
      data += chunk;
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(data || "{}"));
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const parsedUrl = new URL(req.url || "/", `http://${HOST}:${PORT}`);
  const pathname = parsedUrl.pathname;

  // Vérification de santé (Liveness / Readiness)
  if (pathname === "/healthz" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", discordReady: discord.isReady }));
    return;
  }

  if (!verifyAuth(req, res)) return;

  // Flux SSE des messages et événements entrants
  if (pathname === "/inbound" && req.method === "GET") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write(": battement\n\n");
    inboundSubscribers.add(res);

    req.on("close", () => {
      inboundSubscribers.delete(res);
    });
    return;
  }

  // Envoi de message sortant
  if (pathname === "/send" && req.method === "POST") {
    try {
      const body = await readJsonBody<OutboundSendRequest>(req);
      const result = await discord.sendMessage(body.chat_id, body.content, body.reply_to);
      const response: OutboundSendResponse = { success: true, message_id: result.messageId };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(response));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // Indicateur de frappe (typing)
  if (pathname === "/typing" && req.method === "POST") {
    try {
      const body = await readJsonBody<{ chat_id: string }>(req);
      await discord.sendTyping(body.chat_id);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true }));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false }));
    }
    return;
  }

  // Informations sur le salon
  if (pathname === "/chat_info" && req.method === "GET") {
    const chatId = parsedUrl.searchParams.get("chat_id") || "";
    try {
      const info = await discord.getChatInfo(chatId);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(info));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ name: "inconnu", type: "unknown", chat_id: chatId }));
    }
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "non_trouvé" }));
});

async function main() {
  server.listen(PORT, HOST, () => {
    console.log(`[hermes-discord-js] Pont sidecar à l'écoute sur http://${HOST}:${PORT}`);
  });

  if (DISCORD_BOT_TOKEN) {
    try {
      await discord.start(DISCORD_BOT_TOKEN);
    } catch (err) {
      console.error("[discord.js] Échec de la connexion à Discord :", err);
    }
  }

  const shutdown = async () => {
    console.log("[hermes-discord-js] Arrêt du sidecar...");
    await discord.stop();
    server.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("[hermes-discord-js] Erreur fatale au démarrage du sidecar :", err);
  process.exit(1);
});
