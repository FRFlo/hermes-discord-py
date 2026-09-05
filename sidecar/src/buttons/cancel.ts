import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "cancel",
  execute: async (interaction) => {
    await interaction.reply({ content: "⏹️ Tâche interrompue immédiatement.", ephemeral: true });

    const bridge = interaction.client.bridge;
    if (bridge) {
      await bridge.cancelActiveProgress(interaction.channelId);
      bridge.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "cancel",
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
    }
  },
};

export default button;
