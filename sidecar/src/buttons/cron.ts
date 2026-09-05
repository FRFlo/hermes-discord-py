import {
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ActionRowBuilder,
} from "discord.js";
import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "cron:",
  execute: async (interaction) => {
    const bridge = interaction.client.bridge;
    if (!bridge) {
      await interaction.reply({ content: "❌ Pont non disponible.", ephemeral: true });
      return;
    }

    const parts = interaction.customId.split(":");
    const action = parts[1];
    const jobId = parts[2];

    switch (action) {
      case "refresh":
      case "list": {
        bridge.cron.requestList(interaction.channelId, interaction.user.id, interaction.id);
        await new Promise((r) => setTimeout(r, 150));
        const jobs = bridge.cron.getJobs();
        const embed = bridge.cron.buildJobListEmbed(jobs);
        const components = bridge.cron.buildJobListComponents(jobs);
        await interaction.update({ content: null, embeds: [embed], components });
        break;
      }

      case "dismiss": {
        await interaction.update({ content: "⏰ Gestionnaire cron fermé.", embeds: [], components: [] });
        break;
      }

      case "detail": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        if (!job) {
          await interaction.reply({ content: "❌ Tâche cron introuvable.", ephemeral: true });
          return;
        }
        const embed = bridge.cron.buildJobDetailEmbed(job);
        const components = bridge.cron.buildJobDetailComponents(job);
        await interaction.update({ content: null, embeds: [embed], components });
        break;
      }

      case "create_modal": {
        const modal = new ModalBuilder()
          .setCustomId("cron_create_modal")
          .setTitle("Planifier une tâche Cron");

        const nameInput = new TextInputBuilder()
          .setCustomId("cron_name")
          .setLabel("Nom de la tâche")
          .setPlaceholder("Ex: Rapport matinal Docker")
          .setStyle(TextInputStyle.Short)
          .setMaxLength(80)
          .setRequired(true);

        const schedInput = new TextInputBuilder()
          .setCustomId("cron_schedule")
          .setLabel("Fréquence (Cron ou intervalle)")
          .setPlaceholder("Ex: 0 9 * * * ou every 2 hours")
          .setStyle(TextInputStyle.Short)
          .setMaxLength(100)
          .setRequired(true);

        const promptInput = new TextInputBuilder()
          .setCustomId("cron_prompt")
          .setLabel("Prompt / Instruction à exécuter")
          .setPlaceholder("Ex: Vérifie l'état des conteneurs docker et préviens si incident.")
          .setStyle(TextInputStyle.Paragraph)
          .setMaxLength(2000)
          .setRequired(true);

        const deliverInput = new TextInputBuilder()
          .setCustomId("cron_deliver")
          .setLabel("Destination (optionnel)")
          .setPlaceholder("Laissez vide pour ce salon ou 'dm'")
          .setStyle(TextInputStyle.Short)
          .setMaxLength(100)
          .setRequired(false);

        modal.addComponents(
          new ActionRowBuilder<TextInputBuilder>().addComponents(nameInput),
          new ActionRowBuilder<TextInputBuilder>().addComponents(schedInput),
          new ActionRowBuilder<TextInputBuilder>().addComponents(promptInput),
          new ActionRowBuilder<TextInputBuilder>().addComponents(deliverInput)
        );

        await interaction.showModal(modal);
        break;
      }

      case "toggle_pause": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        if (!job) {
          await interaction.reply({ content: "❌ Tâche cron introuvable.", ephemeral: true });
          return;
        }
        const targetAction = job.enabled ? "pause" : "resume";
        bridge.cron.requestAction(targetAction, jobId, interaction.channelId, interaction.user.id, interaction.id);

        // Optimistic update
        job.enabled = !job.enabled;
        bridge.cron.updateJob(job);

        const embed = bridge.cron.buildJobDetailEmbed(job);
        const components = bridge.cron.buildJobDetailComponents(job);
        await interaction.update({
          content: job.enabled ? "▶️ Tâche cron réactivée." : "⏸️ Tâche cron mise en pause.",
          embeds: [embed],
          components,
        });
        break;
      }

      case "trigger": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        if (!job) {
          await interaction.reply({ content: "❌ Tâche cron introuvable.", ephemeral: true });
          return;
        }
        bridge.cron.requestAction("trigger", jobId, interaction.channelId, interaction.user.id, interaction.id);
        await interaction.reply({
          content: `⚡ **Déclenchement immédiat lancé pour "${job.name}".**\nL'agent Hermes va traiter la tâche en arrière-plan.`,
          ephemeral: true,
        });
        break;
      }

      case "view_output": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        if (!job) {
          await interaction.reply({ content: "❌ Tâche cron introuvable.", ephemeral: true });
          return;
        }
        bridge.cron.requestAction("view_output", jobId, interaction.channelId, interaction.user.id, interaction.id);
        if (job.last_output) {
          await interaction.reply({
            content: `📜 **Dernier output de "${job.name}" :**\n\`\`\`text\n${job.last_output.slice(0, 1900)}\n\`\`\``,
            ephemeral: true,
          });
        } else {
          await interaction.reply({
            content: `📜 Requête envoyée pour récupérer le dernier rapport d'exécution de **"${job.name}"**.`,
            ephemeral: true,
          });
        }
        break;
      }

      case "delete_prompt": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        if (!job) {
          await interaction.reply({ content: "❌ Tâche cron introuvable.", ephemeral: true });
          return;
        }
        const components = bridge.cron.buildDeleteConfirmationComponents(jobId);
        await interaction.update({
          content: `⚠️ **Attention** : Voulez-vous vraiment supprimer définitivement la tâche cron **"${job.name}"** ?`,
          embeds: [],
          components,
        });
        break;
      }

      case "delete_confirm": {
        if (!jobId) return;
        const job = bridge.cron.getJob(jobId);
        bridge.cron.requestAction("delete", jobId, interaction.channelId, interaction.user.id, interaction.id);
        bridge.cron.removeJob(jobId);
        await interaction.update({
          content: `🗑️ **Tâche cron "${job?.name || jobId}" supprimée avec succès.**`,
          embeds: [],
          components: [],
        });
        break;
      }

      default:
        console.warn(`[cron.ts] Action cron inconnue : ${action}`);
        break;
    }
  },
};

export default button;
