import { SlashCommandBuilder } from "discord.js";
import type { SlashCommand, InboundCommandEvent } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("context")
    .setDescription("Affiche l'état détaillé du contexte, tokens utilisés et saturation de la fenêtre"),
  execute: async (interaction) => {
    await interaction.reply({ content: "📊 *Analyse du contexte de la session en cours...*", ephemeral: false });

    const event: InboundCommandEvent = {
      type: "command",
      platform: "discord",
      command: "context",
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
