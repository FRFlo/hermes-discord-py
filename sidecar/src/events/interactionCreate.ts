import { type Interaction, EmbedBuilder } from "discord.js";
import type { BotEvent } from "../types.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";

const event: BotEvent<"interactionCreate"> = {
  name: "interactionCreate",
  execute: async (interaction: Interaction) => {
    const allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;

    if (interaction.user.id !== allowedUserId) {
      if (interaction.isRepliable()) {
        await interaction.reply({ content: "⛔ Accès non autorisé.", ephemeral: true });
      }
      return;
    }

    const bridge = interaction.client.bridge;

    // 1. Commandes Slash
    if (interaction.isChatInputCommand()) {
      const command = interaction.client.commands.get(interaction.commandName);
      if (!command) {
        console.warn(`[discord.js] Commande slash introuvable : ${interaction.commandName}`);
        return;
      }
      try {
        await command.execute(interaction);
      } catch (err) {
        console.error(`[discord.js] Erreur exécution commande ${interaction.commandName} :`, err);
        if (interaction.isRepliable() && !interaction.replied && !interaction.deferred) {
          await interaction.reply({ content: "Une erreur est survenue lors de l'exécution.", ephemeral: true });
        }
      }
      return;
    }

    // 1b. Autocomplétion dynamique des commandes Slash
    if (interaction.isAutocomplete()) {
      const command = interaction.client.commands.get(interaction.commandName);
      if (command?.autocomplete) {
        try {
          await command.autocomplete(interaction);
        } catch (err) {
          console.error(`[discord.js] Erreur autocomplétion ${interaction.commandName} :`, err);
        }
      }
      return;
    }

    // 2. Menus déroulants de sélection (pi-bridge style, sessions & cron)
    if (interaction.isStringSelectMenu()) {
      if (interaction.customId.startsWith("session:")) {
        const threadId = interaction.values[0];
        const session = await bridge?.sessions.getSession(threadId);
        if (session && bridge?.sessions) {
          const embed = bridge.sessions.buildSessionDetailEmbed(session);
          const components = bridge.sessions.buildSessionDetailComponents(session);
          await interaction.update({ embeds: [embed], components });
          return;
        }
      }
      if (interaction.customId.startsWith("cron:")) {
        const jobId = interaction.values[0];
        const job = bridge?.cron.getJob(jobId);
        if (job && bridge?.cron) {
          const embed = bridge.cron.buildJobDetailEmbed(job);
          const components = bridge.cron.buildJobDetailComponents(job);
          await interaction.update({ embeds: [embed], components });
          return;
        }
      }
      if (interaction.customId === "model:select") {
        const selectedModel = interaction.values[0];
        const embed = new EmbedBuilder()
          .setTitle("🧠 Modèle LLM Modifié")
          .setColor(0x57f287)
          .setDescription(`Le modèle de cette session a été configuré sur : **\`${selectedModel}\`**.`)
          .setTimestamp();
        await interaction.update({ embeds: [embed], components: [] });

        bridge?.emitInboundEvent({
          type: "command",
          platform: "discord",
          command: "model",
          args: selectedModel,
          chat_id: interaction.channelId,
          sender_id: interaction.user.id,
          sender_name: interaction.user.username,
          interaction_id: interaction.id,
          is_dm: interaction.channel?.isDMBased() ?? false,
        });
        return;
      }
      if (bridge?.questions) {
        const handled = await bridge.questions.handleSelectMenuInteraction(interaction);
        if (handled) return;
      }
      console.warn(`[discord.js] Menu déroulant non géré : ${interaction.customId}`);
      return;
    }

    // 3. Soumission de fenêtres modales (pi-bridge style, sessions & cron)
    if (interaction.isModalSubmit()) {
      if (interaction.customId === "cron_create_modal") {
        const name = interaction.fields.getTextInputValue("cron_name")?.trim();
        const schedule = interaction.fields.getTextInputValue("cron_schedule")?.trim();
        const prompt = interaction.fields.getTextInputValue("cron_prompt")?.trim();
        const deliver = interaction.fields.getTextInputValue("cron_deliver")?.trim() || "";
        if (name && schedule && prompt && bridge?.cron) {
          bridge.cron.requestCreate(name, schedule, prompt, deliver, interaction.channelId || "", interaction.user.id, interaction.id);
          await interaction.reply({
            content: `⏳ **Création de la tâche cron "${name}" en cours...**\nFréquence : \`${schedule}\``,
            ephemeral: true,
          });
          return;
        }
        await interaction.reply({ content: "❌ Paramètres manquants pour la création de la tâche cron.", ephemeral: true });
        return;
      }
      if (interaction.customId === "model_custom_modal") {
        const customModel = interaction.fields.getTextInputValue("model_name")?.trim();
        if (customModel) {
          const embed = new EmbedBuilder()
            .setTitle("🧠 Modèle LLM Personnalisé")
            .setColor(0x57f287)
            .setDescription(`Le modèle de cette session a été configuré sur : **\`${customModel}\`**.`)
            .setTimestamp();
          await interaction.reply({ embeds: [embed], ephemeral: true });

          bridge?.emitInboundEvent({
            type: "command",
            platform: "discord",
            command: "model",
            args: customModel,
            chat_id: interaction.channelId || "",
            sender_id: interaction.user.id,
            sender_name: interaction.user.username,
            interaction_id: interaction.id,
            is_dm: interaction.channel?.isDMBased() ?? false,
          });
          return;
        }
      }
      if (interaction.customId.startsWith("session_rename_modal:")) {
        const threadId = interaction.customId.split(":")[1];
        const newName = interaction.fields.getTextInputValue("session_new_name")?.trim();
        if (newName && bridge?.sessions) {
          await bridge.sessions.renameSession(threadId, newName);
          const session = await bridge.sessions.getSession(threadId);
          if (session) {
            const embed = bridge.sessions.buildSessionDetailEmbed(session);
            const components = bridge.sessions.buildSessionDetailComponents(session);
            await interaction.reply({
              content: `✏️ Le fil a été renommé avec succès en **${newName}**.`,
              embeds: [embed],
              components,
              ephemeral: true,
            });
            return;
          }
        }
        await interaction.reply({ content: "❌ Impossible de renommer ce fil.", ephemeral: true });
        return;
      }
      if (bridge?.questions) {
        const handled = await bridge.questions.handleModalSubmitInteraction(interaction);
        if (handled) return;
      }
      console.warn(`[discord.js] Modale non gérée : ${interaction.customId}`);
      return;
    }

    // 4. Boutons interactifs
    if (interaction.isButton()) {
      // Vérification prioritaire si c'est un bouton du système de questions (pi-bridge)
      if (bridge?.questions) {
        const handled = await bridge.questions.handleButtonInteraction(interaction);
        if (handled) return;
      }

      // Routage vers les handlers de boutons standard
      const buttonCmd = Array.from(interaction.client.buttons.values()).find((cmd) =>
        interaction.customId.startsWith(cmd.prefix)
      );
      if (!buttonCmd) {
        console.warn(`[discord.js] Bouton non géré : ${interaction.customId}`);
        return;
      }
      try {
        await buttonCmd.execute(interaction);
      } catch (err) {
        console.error(`[discord.js] Erreur exécution bouton ${interaction.customId} :`, err);
      }
      return;
    }
  },
};

export default event;
