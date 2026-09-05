import { SlashCommandBuilder } from "discord.js";
import type { SlashCommand } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("cron")
    .setDescription("Gestionnaire interactif des tâches planifiées Cron Hermes"),
  execute: async (interaction) => {
    const bridge = interaction.client.bridge;
    if (!bridge) {
      await interaction.reply({ content: "❌ Pont Discord non initialisé.", ephemeral: true });
      return;
    }

    await interaction.deferReply({ ephemeral: true });

    // Émettre une demande de synchronisation fraîche des tâches cron vers Hermes
    bridge.cron.requestList(interaction.channelId, interaction.user.id, interaction.id);

    // Attendre 200ms pour laisser le temps au sync immédiat si l'adaptateur répond vite
    await new Promise((r) => setTimeout(r, 200));

    const jobs = bridge.cron.getJobs();
    const embed = bridge.cron.buildJobListEmbed(jobs);
    const components = bridge.cron.buildJobListComponents(jobs);

    await interaction.editReply({
      embeds: [embed],
      components,
    });
  },
};

export default command;
