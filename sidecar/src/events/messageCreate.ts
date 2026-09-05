import type { Message } from "discord.js";
import type { BotEvent, InboundAttachment, InboundMessageEvent } from "../types.js";
import { downloadAndCacheAttachment } from "../downloader.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";
const DEFAULT_FORUM_CHANNEL = "1544452203207589938";

const event: BotEvent<"messageCreate"> = {
  name: "messageCreate",
  execute: async (message: Message) => {
    if (message.author.bot || message.author.id === message.client.user?.id) return;

    const allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;
    const forumChannelId = process.env.DISCORD_FORUM_CHANNEL_ID || DEFAULT_FORUM_CHANNEL;
    const enableReactions = process.env.DISCORD_REACTIONS !== "false";

    // Filtrage strict : seul l'utilisateur autorisé est accepté
    if (message.author.id !== allowedUserId) {
      return;
    }

    const bridge = message.client.bridge;
    // Filtrage des salons (DMs ou Forum / Fils de forum)
    if (bridge && !bridge.isChannelAllowed(message.channel)) {
      return;
    }

    // Réaction de statut immédiate (⏱️ si une tâche tourne déjà dans ce salon, sinon ⏳)
    if (enableReactions && bridge) {
      try {
        if (bridge.isChatBusy(message.channelId)) {
          await message.react("⏱️");
        } else {
          await message.react("⏳");
          bridge.setChatBusy(message.channelId, true);
        }
      } catch (err) {
        console.warn("[discord.js] Impossible d'ajouter la réaction de statut :", err);
      }
    }

    const isDm = message.channel.isDMBased();
    const channelName = "name" in message.channel ? (message.channel.name as string) : "DM";

    // Téléchargement, cache local et extraction de texte des pièces jointes entrantes
    const attachments: InboundAttachment[] = [];
    let injectedTextExtra = "";

    for (const [, att] of message.attachments) {
      try {
        const cached = await downloadAndCacheAttachment(att.url, att.name, att.size, att.contentType || undefined);
        attachments.push({
          name: att.name,
          url: att.url,
          size: att.size,
          contentType: att.contentType || undefined,
          localPath: cached.localPath,
          isText: cached.isText,
          textContent: cached.textContent,
        });

        if (cached.textContent) {
          injectedTextExtra += `\n\n[Fichier joint: "${att.name}" - Chemin local: ${cached.localPath}]\n\`\`\`\n${cached.textContent}\n\`\`\``;
        } else {
          injectedTextExtra += `\n\n[Fichier joint disponible localement: ${cached.localPath}]`;
        }
      } catch (err) {
        console.warn(`[discord.js] Échec du cache pour ${att.name}:`, err);
      }
    }

    const fullContent = (message.content + injectedTextExtra).trim();

    const inboundEvent: InboundMessageEvent = {
      type: "message",
      platform: "discord",
      chat_id: message.channelId,
      sender_id: message.author.id,
      sender_name: message.author.username,
      message_id: message.id,
      content: fullContent,
      is_dm: isDm,
      channel_name: channelName,
      guild_id: message.guildId ?? undefined,
      reply_to_id: message.reference?.messageId,
      attachments: attachments.length > 0 ? attachments : undefined,
    };

    bridge?.emitInboundEvent(inboundEvent);
  },
};

export default event;
