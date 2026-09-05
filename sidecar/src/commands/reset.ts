import { SlashCommandBuilder } from "discord.js";
import type { SlashCommand, InboundCommandEvent } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("reset")
    .setDescription("Réinitialise le contexte de la conversation active"),
  execute: async (interaction) => {
    await interaction.reply({ content: "🔄 Contexte réinitialisé pour cette session." });
    const event: InboundCommandEvent = {
      type: "command",
      platform: "discord",
      command: "reset",
      chat_id: interaction.channelId,
      sender_id: interaction.user.id,
      sender_name: interaction.user.username,
      interaction_id: interaction.id,
      is_dm: interaction.channel?.isDMBased() ?? false,
    };
    interaction.client.bridge?.emitInboundEvent(event);
  },
};

export default command;
