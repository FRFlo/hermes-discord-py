import type { Message, PartialMessage } from "discord.js";
import type { BotEvent, InboundEvent } from "../types.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";

const event: BotEvent<"messageUpdate"> = {
  name: "messageUpdate",
  execute: async (oldMessage: Message | PartialMessage, newMessage: Message | PartialMessage) => {
    const bridge = newMessage.client.bridge;
    if (!bridge) return;

    const allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;

    // Si le message est partiel, on tente de le récupérer complètement
    let fullNewMessage: Message;
    if (newMessage.partial) {
      try {
        fullNewMessage = await newMessage.fetch();
      } catch {
        return;
      }
    } else {
      fullNewMessage = newMessage;
    }

    // Ignore les bots et tout utilisateur non autorisé
    if (fullNewMessage.author.bot || fullNewMessage.author.id !== allowedUserId) {
      return;
    }

    const newContent = fullNewMessage.content?.trim() || "";
    const oldContent = oldMessage.content?.trim() || "";

    // Filtrage anti-bruit : si le contenu textuel n'a pas changé (ex: unfurl d'embed ou chargement d'image)
    if (newContent === oldContent || newContent === "") {
      return;
    }

    const isDm = fullNewMessage.channel.isDMBased();

    // Émission de l'événement d'édition vers Hermes
    const editEvent: InboundEvent = {
      type: "message_edit",
      platform: "discord",
      message_id: fullNewMessage.id,
      chat_id: fullNewMessage.channelId,
      sender_id: fullNewMessage.author.id,
      sender_name: fullNewMessage.author.username,
      content: newContent,
      old_content: oldContent || undefined,
      is_dm: isDm,
    };

    bridge.emitInboundEvent(editEvent);
  },
};

export default event;
