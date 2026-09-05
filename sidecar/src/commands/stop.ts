import { SlashCommandBuilder } from "discord.js";
import type { SlashCommand, InboundCommandEvent } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("stop")
    .setDescription("Interrompt immédiatement la commande ou tâche en cours"),
  execute: async (interaction) => {
    await interaction.reply({ content: "⏹️ Signal d'interruption immédiat transmis à l'agent.", ephemeral: true });
    const event: InboundCommandEvent = {
      type: "command",
      platform: "discord",
      command: "stop",
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
