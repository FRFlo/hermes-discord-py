import type { Message, PartialMessage } from "discord.js";
import type { BotEvent, InboundEvent } from "../types.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";

const event: BotEvent<"messageDelete"> = {
  name: "messageDelete",
  execute: async (message: Message | PartialMessage) => {
    const bridge = message.client.bridge;
    if (!bridge) return;

    const allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;
    const authorId = message.author?.id;
    const isBot = message.author?.bot || false;

    // Si l'auteur est connu et que ce n'est ni Flo ni le bot lui-même, on ignore
    if (authorId && authorId !== allowedUserId && authorId !== message.client.user?.id) {
      return;
    }

    const isDm = message.channel.isDMBased();

    // Envoi de l'événement de suppression vers Hermes
    const deleteEvent: InboundEvent = {
      type: "message_delete",
      platform: "discord",
      message_id: message.id,
      chat_id: message.channelId,
      sender_id: authorId || allowedUserId,
      sender_name: message.author?.username || (isBot ? "Hermes" : "Flo"),
      is_dm: isDm,
    };

    bridge.emitInboundEvent(deleteEvent);
  },
};

export default event;
