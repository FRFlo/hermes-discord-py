import {
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ActionRowBuilder,
} from "discord.js";
import type { ButtonCommand } from "../types.js";

const button: ButtonCommand = {
  prefix: "session:",
  execute: async (interaction) => {
    const bridge = interaction.client.bridge;
    if (!bridge) {
      await interaction.reply({ content: "❌ Pont non disponible.", ephemeral: true });
      return;
    }

    const parts = interaction.customId.split(":");
    const action = parts[1];
    const threadId = parts[2];

    switch (action) {
      case "refresh":
      case "list": {
        const sessions = await bridge.sessions.fetchSessions(25);
        const currentThreadId = interaction.channel?.isThread() ? interaction.channel.id : undefined;
        const embed = bridge.sessions.buildSessionListEmbed(sessions, currentThreadId);
        const components = bridge.sessions.buildSessionListComponents(sessions);
        await interaction.update({ content: null, embeds: [embed], components });
        break;
      }

      case "dismiss": {
        await interaction.update({ content: "📂 Gestionnaire de sessions fermé.", embeds: [], components: [] });
        break;
      }

      case "detail": {
        if (!threadId) return;
        const session = await bridge.sessions.getSession(threadId);
        if (!session) {
          await interaction.reply({ content: "❌ Session introuvable.", ephemeral: true });
          return;
        }
        const embed = bridge.sessions.buildSessionDetailEmbed(session);
        const components = bridge.sessions.buildSessionDetailComponents(session);
        await interaction.update({ content: null, embeds: [embed], components });
        break;
      }

      case "rename": {
        if (!threadId) return;
        const session = await bridge.sessions.getSession(threadId);
        const modal = new ModalBuilder()
          .setCustomId(`session_rename_modal:${threadId}`)
          .setTitle("Renommer la session");

        const textInput = new TextInputBuilder()
          .setCustomId("session_new_name")
          .setLabel("Nouveau nom du fil de session")
          .setStyle(TextInputStyle.Short)
          .setValue(session?.name || "")
          .setMaxLength(100)
          .setRequired(true);

        const modalRow = new ActionRowBuilder<TextInputBuilder>().addComponents(textInput);
        modal.addComponents(modalRow);
        await interaction.showModal(modal);
        break;
      }

      case "toggle_archive": {
        if (!threadId) return;
        const res = await bridge.sessions.toggleArchiveSession(threadId);
        const session = await bridge.sessions.getSession(threadId);
        if (session) {
          const embed = bridge.sessions.buildSessionDetailEmbed(session);
          const components = bridge.sessions.buildSessionDetailComponents(session);
          await interaction.update({
            content: res.archived ? "🔒 Fil archivé." : "🔓 Fil désarchivé.",
            embeds: [embed],
            components,
          });
        }
        break;
      }

      case "delete_prompt": {
        if (!threadId) return;
        const session = await bridge.sessions.getSession(threadId);
        if (!session) {
          await interaction.reply({ content: "❌ Session introuvable.", ephemeral: true });
          return;
        }
        const components = bridge.sessions.buildDeleteConfirmationComponents(threadId);
        await interaction.update({
          content: `⚠️ **Attention** : Voulez-vous vraiment supprimer définitivement le fil **"${session.name}"** et son historique Hermes ?`,
          embeds: [],
          components,
        });
        break;
      }

      case "delete_confirm": {
        if (!threadId) return;
        const ok = await bridge.sessions.deleteSession(threadId, interaction.user.id);
        if (ok) {
          await interaction.update({
            content: "🗑️ **Session et fil Discord supprimés avec succès.**",
            embeds: [],
            components: [],
          });
        } else {
          await interaction.reply({ content: "❌ Échec de la suppression du fil.", ephemeral: true });
        }
        break;
      }

      default:
        console.warn(`[session.ts] Action session inconnue : ${action}`);
        break;
    }
  },
};

export default button;
