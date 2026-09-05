import { SlashCommandBuilder } from "discord.js";
import type { SlashCommand } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("sessions")
    .setDescription("Gestionnaire interactif des sessions (sélectionner, renommer, archiver, supprimer)"),
  execute: async (interaction) => {
    const bridge = interaction.client.bridge;
    if (!bridge) {
      await interaction.reply({ content: "❌ Pont Discord non initialisé.", ephemeral: true });
      return;
    }

    await interaction.deferReply({ ephemeral: true });

    const sessions = await bridge.sessions.fetchSessions(25);
    const currentThreadId = interaction.channel?.isThread() ? interaction.channel.id : undefined;

    const embed = bridge.sessions.buildSessionListEmbed(sessions, currentThreadId);
    const components = bridge.sessions.buildSessionListComponents(sessions);

    await interaction.editReply({
      embeds: [embed],
      components,
    });
  },
};

export default command;
