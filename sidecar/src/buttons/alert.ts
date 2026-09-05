import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "alert",
  execute: async (interaction) => {
    const parts = interaction.customId.split(":");
    const subAction = parts[1] || "";
    const payload = parts.slice(2).join(":");

    if (subAction === "retry") {
      await interaction.reply({ content: "🔄 Relance de la tâche demandée...", ephemeral: true });
      interaction.client.bridge?.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "retry_task",
        payload,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return;
    }

    if (subAction === "logs") {
      await interaction.reply({ content: "🔍 Récupération des logs en cours...", ephemeral: true });
      interaction.client.bridge?.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "view_logs",
        payload,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return;
    }
  },
};

export default button;
