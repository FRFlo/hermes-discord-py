import { ThreadChannel } from "discord.js";
import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "action",
  execute: async (interaction) => {
    const parts = interaction.customId.split(":");
    const subAction = parts[1] || "";

    if (subAction === "regenerate") {
      await interaction.reply({ content: "🔄 Régénération de la réponse demandée...", ephemeral: true });
      interaction.client.bridge?.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "regenerate",
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return;
    }

    if (subAction === "close") {
      const channel = interaction.channel;
      if (channel && channel.isThread()) {
        await interaction.reply({ content: "🔒 Clôture de la session...", ephemeral: false });
        await (channel as ThreadChannel).setArchived(true, "Clôturé via bouton");
      } else {
        await interaction.reply({ content: "Session fermée.", ephemeral: true });
      }
      interaction.client.bridge?.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "close",
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return;
    }
  },
};

export default button;
