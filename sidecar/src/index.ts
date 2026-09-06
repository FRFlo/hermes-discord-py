import http from "node:http";
import { URL } from "node:url";
import { DiscordBridgeClient } from "./discord.js";
import {
  InboundEvent,
  OutboundSendRequest,
  OutboundSendResponse,
  ToolProgressRequest,
  ToolProgressResponse,
  ReactionRequest,
  ClarifyRequest,
  ExecApprovalRequest,
  ArchiveThreadRequest,
  AlertRequest,
  QuestionRequest,
  CronJobItem,
} from "./types.js";

const PORT = parseInt(process.env.HERMES_SIDECAR_PORT || "8790", 10);
const HOST = "127.0.0.1";
const TOKEN = process.env.HERMES_SIDECAR_TOKEN || "";
const DISCORD_BOT_TOKEN = process.env.DISCORD_BOT_TOKEN || "";

const discord = new DiscordBridgeClient();
const inboundSubscribers = new Set<http.ServerResponse>();

discord.setInboundHandler((event: InboundEvent) => {
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

  // 1. Contrôle de santé (Healthcheck)
  if (pathname === "/healthz" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", discordReady: discord.isReady }));
    return;
  }

  if (!verifyAuth(req, res)) return;

  // 2. Flux SSE des événements entrants
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

  // 3. Envoi de message sortant (avec formatage Thinking, découpage Markdown et pièces jointes)
  if (pathname === "/send" && req.method === "POST") {
    try {
      const body = await readJsonBody<OutboundSendRequest>(req);
      const withButtons = body.with_action_buttons !== false;
      const result = await discord.sendMessage(body.chat_id, body.content, body.reply_to, body.files, withButtons);

      // Si un trigger_message_id est présent dans les métadonnées, marquer le statut ✅
      const triggerMessageId = body.metadata?.trigger_message_id as string | undefined;
      if (triggerMessageId) {
        await discord.setFinalStatusReaction(body.chat_id, triggerMessageId, true);
      }

      const response: OutboundSendResponse = {
        success: true,
        message_ids: result.messageIds,
        message_id: result.messageIds[0],
      };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(response));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 4. Progression et journal des outils (Live edit -> Spoiler repliable)
  if (pathname === "/tool_progress" && req.method === "POST") {
    try {
      const body = await readJsonBody<ToolProgressRequest>(req);
      const result = await discord.updateToolProgress(
        body.chat_id,
        body.tool_name,
        body.tool_args,
        body.status,
        body.output,
        body.is_final
      );
      const response: ToolProgressResponse = {
        success: true,
        progress_message_id: result.progressMessageId,
      };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(response));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 5. Statut final (remplacement de ⏳ par ✅ ou ❌)
  if (pathname === "/final_status" && req.method === "POST") {
    try {
      const body = await readJsonBody<{ chat_id: string; message_id: string; success: boolean }>(req);
      await discord.setFinalStatusReaction(body.chat_id, body.message_id, body.success);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true }));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false }));
    }
    return;
  }

  // 5b. Démarrage de tour (remplacement de ⏱️ par ⏳)
  if (pathname === "/turn_start" && req.method === "POST") {
    try {
      const body = await readJsonBody<{ chat_id: string; message_id: string }>(req);
      await discord.setTurnStartReaction(body.chat_id, body.message_id);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true }));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false }));
    }
    return;
  }

  // 6. Réactions directes
  if (pathname === "/reaction" && req.method === "POST") {
    try {
      const body = await readJsonBody<ReactionRequest>(req);
      await discord.setReaction(body.chat_id, body.message_id, body.emoji, body.action);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true }));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false }));
    }
    return;
  }

  // 7. Approbation de commande sensible (Boutons Approve / Deny)
  if (pathname === "/exec_approval" && req.method === "POST") {
    try {
      const body = await readJsonBody<ExecApprovalRequest>(req);
      const result = await discord.sendExecApproval(body.chat_id, body.command, body.description, body.reply_to);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, message_id: result.messageId }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 8. Question / Clarification interactive (style pi-bridge avec select menus, modales, etc.)
  if (pathname === "/ask" && req.method === "POST") {
    try {
      const body = await readJsonBody<QuestionRequest>(req);
      const result = await discord.askQuestion(body);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(result));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "cancelled", answers: [], error: msg }));
    }
    return;
  }

  if (pathname === "/clarify" && req.method === "POST") {
    try {
      const body = await readJsonBody<ClarifyRequest>(req);
      const result = await discord.sendClarify(
        body.chat_id,
        body.question,
        body.options,
        body.reply_to,
        body.details,
        body.context,
        body.multiSelect,
        body.timeoutSeconds
      );
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, ...result }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 9. Archivage de fil
  if (pathname === "/archive_thread" && req.method === "POST") {
    try {
      const body = await readJsonBody<ArchiveThreadRequest>(req);
      const success = await discord.archiveThread(body.chat_id, body.reason);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success }));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false }));
    }
    return;
  }

  // 10. Alerte système rouge en DM privé avec boutons d'action
  if (pathname === "/alert" && req.method === "POST") {
    try {
      const body = await readJsonBody<AlertRequest>(req);
      const result = await discord.sendSystemAlert(body.title, body.error_message, body.details, body.task_id);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, message_id: result.messageId }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 11. Suppression de message sur Discord
  if (pathname === "/delete_message" && req.method === "POST") {
    try {
      const body = await readJsonBody<{ chat_id: string; message_id: string }>(req);
      const success = await discord.deleteMessage(body.chat_id, body.message_id);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 11. Indicateur de frappe (typing)
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

  // 12. Synchronisation des tâches Cron depuis Hermes
  if (pathname === "/cron/sync" && req.method === "POST") {
    try {
      const body = await readJsonBody<{ jobs: CronJobItem[] }>(req);
      if (Array.isArray(body.jobs)) {
        discord.cron.setJobs(body.jobs);
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, count: body.jobs?.length || 0 }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, error: msg }));
    }
    return;
  }

  // 11. Informations sur le salon
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
  server.on("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "EADDRINUSE") {
      console.error(`[hermes-discord-js] Erreur : Le port ${PORT} est déjà utilisé (EADDRINUSE).`);
      console.error(`[hermes-discord-js] Un autre processus sidecar ou service écoute déjà sur http://${HOST}:${PORT}.`);
    } else {
      console.error("[hermes-discord-js] Erreur serveur HTTP :", err);
    }
    process.exit(1);
  });

  // Détection de la terminaison du processus parent (Hermes) via le flux stdin
  process.stdin.resume();
  process.stdin.on("end", () => {
    console.log("[hermes-discord-js] Flux stdin fermé (processus parent terminé). Arrêt du sidecar...");
    process.exit(0);
  });
  process.stdin.on("close", () => {
    process.exit(0);
  });

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
