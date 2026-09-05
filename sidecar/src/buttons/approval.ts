import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "approval",
  execute: async (interaction) => {
    try {
      await interaction.update({ components: [] });
    } catch {
      // ignore
    }

    const parts = interaction.customId.split(":");
    interaction.client.bridge?.emitInboundEvent({
      type: "button",
      platform: "discord",
      custom_id: interaction.customId,
      action: "approval",
      payload: parts.slice(1).join(":"),
      chat_id: interaction.channelId,
      sender_id: interaction.user.id,
      message_id: interaction.message.id,
    });
  },
};

export default button;
