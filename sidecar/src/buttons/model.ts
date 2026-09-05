import {
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ActionRowBuilder,
  EmbedBuilder,
} from "discord.js";
import type { ButtonCommand, InboundCommandEvent } from "../types.js";

const button: ButtonCommand = {
  prefix: "model:",
  execute: async (interaction) => {
    const bridge = interaction.client.bridge;
    const parts = interaction.customId.split(":");
    const action = parts[1];

    if (action === "dismiss") {
      await interaction.update({ content: "🧠 Sélecteur de modèle fermé.", embeds: [], components: [] });
      return;
    }

    if (action === "reset_default") {
      const defaultModel = "gemini-pro-agent";
      const embed = new EmbedBuilder()
        .setTitle("🧠 Modèle LLM Réinitialisé")
        .setColor(0x57f287)
        .setDescription(`Le modèle de la session a été basculé vers le modèle par défaut : **\`${defaultModel}\`**.`)
        .setTimestamp();

      await interaction.update({ embeds: [embed], components: [] });

      const event: InboundCommandEvent = {
        type: "command",
        platform: "discord",
        command: "model",
        args: defaultModel,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        sender_name: interaction.user.username,
        interaction_id: interaction.id,
        is_dm: interaction.channel?.isDMBased() ?? false,
      };
      bridge?.emitInboundEvent(event);
      return;
    }

    if (action === "custom_modal") {
      const modal = new ModalBuilder()
        .setCustomId("model_custom_modal")
        .setTitle("Définir un Modèle LLM");

      const input = new TextInputBuilder()
        .setCustomId("model_name")
        .setLabel("Identifiant du modèle")
        .setPlaceholder("Ex: gpt-4o, claude-3-5-sonnet, etc.")
        .setStyle(TextInputStyle.Short)
        .setMaxLength(100)
        .setRequired(true);

      const row = new ActionRowBuilder<TextInputBuilder>().addComponents(input);
      modal.addComponents(row);

      await interaction.showModal(modal);
      return;
    }
  },
};

export default button;
