import {
  SlashCommandBuilder,
  ActionRowBuilder,
  StringSelectMenuBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
} from "discord.js";
import type { SlashCommand, InboundCommandEvent } from "../types.js";

export const AVAILABLE_MODELS = [
  { label: "Gemini Pro Agent (Défaut)", value: "gemini-pro-agent", description: "Modèle principal configuré via cliproxyapi" },
  { label: "Gemini 2.5 Pro", value: "gemini-2.5-pro", description: "Raisonnement approfondi et immense fenêtre de contexte" },
  { label: "Gemini 2.5 Flash", value: "gemini-2.5-flash", description: "Ultra rapide et économique" },
  { label: "Claude 3.5 Sonnet", value: "claude-3-5-sonnet", description: "Excellence en programmation et architecture" },
  { label: "GPT-4o", value: "gpt-4o", description: "Modèle polyvalent et multimodal d'OpenAI" },
  { label: "DeepSeek Chat", value: "deepseek-chat", description: "Haute performance et coût minimal" },
  { label: "o3-mini", value: "o3-mini", description: "Raisonnement logique et mathématique" },
];

export function buildModelSelectorComponents(): ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] {
  const selectMenu = new StringSelectMenuBuilder()
    .setCustomId("model:select")
    .setPlaceholder("🔍 Choisissez un modèle LLM...")
    .setMinValues(1)
    .setMaxValues(1)
    .addOptions(
      AVAILABLE_MODELS.map((m) => ({
        label: m.label.slice(0, 100),
        value: m.value,
        description: m.description.slice(0, 100),
        emoji: "🧠",
      }))
    );

  const buttonRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId("model:custom_modal")
      .setLabel("Saisir un autre modèle")
      .setStyle(ButtonStyle.Primary)
      .setEmoji("✏️"),
    new ButtonBuilder()
      .setCustomId("model:reset_default")
      .setLabel("Défaut (gemini-pro-agent)")
      .setStyle(ButtonStyle.Secondary)
      .setEmoji("🔄"),
    new ButtonBuilder()
      .setCustomId("model:dismiss")
      .setLabel("Fermer")
      .setStyle(ButtonStyle.Secondary)
      .setEmoji("✖️")
  );

  return [
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu),
    buttonRow,
  ];
}

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("model")
    .setDescription("Consulte ou modifie le modèle LLM actif avec autocomplétion et sélecteur interactif")
    .addStringOption((opt) =>
      opt
        .setName("name")
        .setDescription("Nom du modèle LLM (avec autocomplétion)")
        .setAutocomplete(true)
        .setRequired(false)
    ),
  autocomplete: async (interaction) => {
    const focused = interaction.options.getFocused().toLowerCase();
    const filtered = AVAILABLE_MODELS.filter(
      (m) => m.value.toLowerCase().includes(focused) || m.label.toLowerCase().includes(focused)
    ).slice(0, 25);

    await interaction.respond(
      filtered.map((m) => ({
        name: `${m.label} (${m.value})`.slice(0, 100),
        value: m.value,
      }))
    );
  },
  execute: async (interaction) => {
    const modelArg = interaction.options.getString("name");

    // Si un argument direct est fourni, on applique directement
    if (modelArg) {
      await interaction.reply({
        content: `🔄 **Bascule demandée vers le modèle :** \`${modelArg}\`...`,
        ephemeral: false,
      });

      const event: InboundCommandEvent = {
        type: "command",
        platform: "discord",
        command: "model",
        args: modelArg,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        sender_name: interaction.user.username,
        interaction_id: interaction.id,
        is_dm: interaction.channel?.isDMBased() ?? false,
      };
      interaction.client.bridge?.emitInboundEvent(event);
      return;
    }

    // Sinon, on ouvre le sélecteur moderne interactif
    const embed = new EmbedBuilder()
      .setTitle("🧠 Gestionnaire & Sélecteur de Modèle LLM")
      .setColor(0x5865f2)
      .setDescription(
        "Choisissez un modèle parmi les options optimisées ci-dessous, ou cliquez sur **Saisir un autre modèle** pour spécifier n'importe quel identifiant sur-mesure."
      )
      .addFields(
        { name: "🌟 Modèle recommandé", value: "`gemini-pro-agent` (cliproxyapi)", inline: true },
        { name: "⚡ Bascule rapide", value: "Sélectionnez une option dans le menu", inline: true }
      )
      .setFooter({ text: "La modification s'applique immédiatement à cette session" })
      .setTimestamp();

    const components = buildModelSelectorComponents();
    await interaction.reply({
      embeds: [embed],
      components,
      ephemeral: true,
    });
  },
};

export default command;
