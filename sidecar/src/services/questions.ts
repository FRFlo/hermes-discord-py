import { randomUUID } from "node:crypto";
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  StringSelectMenuBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  Message,
  ThreadChannel,
  TextChannel,
  DMChannel,
  type ButtonInteraction,
  type StringSelectMenuInteraction,
  type ModalSubmitInteraction,
  ThreadAutoArchiveDuration,
} from "discord.js";
import type { DiscordBridgeClient } from "./bridge.js";
import type {
  QuestionRequest,
  QuestionResult,
  QuestionOption,
  AnswerItem,
} from "../types.js";

type Sendable = TextChannel | DMChannel | ThreadChannel;

function isSendable(channel: unknown): channel is Sendable {
  return Boolean(channel && typeof (channel as { send?: unknown }).send === "function");
}

function truncate(str: string, maxLength: number): string {
  if (!str) return "";
  return str.length > maxLength ? `${str.slice(0, maxLength - 3)}...` : str;
}

interface PendingQuestion {
  id: string;
  req: QuestionRequest;
  message: Message;
  thread?: ThreadChannel;
  timer?: NodeJS.Timeout;
  reminderTimer?: NodeJS.Timeout;
  reminderMessage?: Message;
  selectedOptionIndices: Set<number>;
  customText?: string;
  resolve: (result: QuestionResult) => void;
}

export class QuestionManager {
  private pendingQuestions = new Map<string, PendingQuestion>();
  private bridge: DiscordBridgeClient;

  constructor(bridge: DiscordBridgeClient) {
    this.bridge = bridge;
  }

  public getPending(questionId: string): PendingQuestion | undefined {
    return this.pendingQuestions.get(questionId);
  }

  public async askQuestion(req: QuestionRequest): Promise<QuestionResult> {
    const targetChatId = req.chat_id || req.channelId;
    if (!targetChatId) {
      return {
        status: "cancelled",
        answers: [],
        message: "Identifiant de salon manquant pour poser la question",
      };
    }

    const channel = await this.bridge.client.channels.fetch(targetChatId);
    if (!isSendable(channel)) {
      return {
        status: "cancelled",
        answers: [],
        message: `Salon Discord ${targetChatId} introuvable ou non sendable`,
      };
    }

    const questionId = req.id || randomUUID().slice(0, 8);
    const timeoutSec = typeof req.timeoutSeconds === "number" ? req.timeoutSeconds : 0;
    const nowSec = Math.floor(Date.now() / 1000);
    const expireTimestamp = timeoutSec > 0 ? nowSec + timeoutSec : undefined;

    const mainEmbed = this.buildMainQuestionEmbed(req, expireTimestamp);
    const components = this.buildQuestionComponents(questionId, req);

    const sendOptions: Record<string, unknown> = {
      embeds: [mainEmbed],
      components,
    };
    if (req.reply_to) {
      sendOptions.reply = { messageReference: req.reply_to };
    }

    const sentMessage = await channel.send(sendOptions);

    // Contexte attaché : créer un fil si supporté (dans un TextChannel normal hors Forum/DM)
    let thread: ThreadChannel | undefined;
    if ("threads" in channel && !channel.isThread() && !channel.isDMBased()) {
      try {
        const threadName = `❓ ${truncate(req.question.replace(/[\n\r]+/g, " "), 95)}`;
        thread = await sentMessage.startThread({
          name: threadName,
          autoArchiveDuration: ThreadAutoArchiveDuration.OneHour,
        });

        if (req.context) {
          await thread.send(`📋 **Contexte de la tâche :**\n\`\`\`\n${truncate(req.context, 1900)}\n\`\`\``);
        }
        if (req.recentMessages && req.recentMessages.length > 0) {
          for (const msg of req.recentMessages.slice(-5)) {
            const roleName = msg.role === "user" ? "👤 **Utilisateur :**" : "🤖 **Hermes :**";
            await thread.send(`${roleName}\n${truncate(msg.content, 1900)}`);
          }
        }
      } catch (err) {
        console.warn("[discord.js] Impossible de créer le fil de contexte attaché:", err);
      }
    }

    return new Promise<QuestionResult>((resolve) => {
      let timer: NodeJS.Timeout | undefined;
      if (timeoutSec > 0) {
        timer = setTimeout(async () => {
          const pending = this.pendingQuestions.get(questionId);
          if (!pending) return;
          this.pendingQuestions.delete(questionId);

          await this.updateMessageStatus(
            sentMessage,
            req,
            "⌛ **Question expirée (délai d'attente dépassé)**",
            0xed4245,
            thread
          );

          resolve({
            status: "timeout",
            answers: [],
            message: "Délai d'attente Discord dépassé",
          });
        }, timeoutSec * 1000);
      }

      this.pendingQuestions.set(questionId, {
        id: questionId,
        req,
        message: sentMessage,
        thread,
        timer,
        selectedOptionIndices: new Set<number>(),
        resolve,
      });
    });
  }

  private buildMainQuestionEmbed(req: QuestionRequest, expireTimestamp?: number): EmbedBuilder {
    const timingInfo = expireTimestamp
      ? `⏳ *Expire <t:${expireTimestamp}:R>*`
      : "♾️ *Sans limite de temps*";

    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle("❓ Question de Hermes Agent")
      .setDescription(`### ${truncate(req.question, 1000)}\n\n${timingInfo}`)
      .setTimestamp();

    if (req.options && req.options.length > 0) {
      const optionsList = req.options
        .map((opt, idx) => {
          let line = `**${idx + 1}. ${opt.label}**`;
          if (opt.description) {
            line += `\n↳ *${opt.description}*`;
          }
          return line;
        })
        .join("\n\n");

      embed.addFields({
        name: "📋 Choix disponibles :",
        value: truncate(optionsList, 1024),
      });
    }

    if (req.details) {
      embed.addFields({
        name: "ℹ️ Détails & Instructions",
        value: truncate(req.details, 1024),
      });
    }

    return embed;
  }

  private buildQuestionComponents(
    questionId: string,
    req: QuestionRequest
  ): ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] {
    const rows: ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] = [];
    const options = (req.options || []).slice(0, 25);
    const isMulti = Boolean(req.multiSelect);

    if (options.length > 0) {
      if (isMulti) {
        // Multi-select menu
        const selectMenu = new StringSelectMenuBuilder()
          .setCustomId(`select:${questionId}`)
          .setPlaceholder(truncate("Sélectionnez une ou plusieurs options...", 150))
          .setMinValues(1)
          .setMaxValues(options.length)
          .addOptions(
            options.map((opt, idx) => ({
              label: truncate(`${idx + 1}. ${opt.label}`, 100),
              value: String(idx),
              description: opt.description ? truncate(opt.description, 100) : undefined,
            }))
          );

        rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu));

        const actionRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder()
            .setCustomId(`submit_multi:${questionId}`)
            .setLabel("Valider la sélection")
            .setStyle(ButtonStyle.Success)
            .setEmoji("✅"),
          new ButtonBuilder()
            .setCustomId(`other:${questionId}`)
            .setLabel("Autre (texte)")
            .setStyle(ButtonStyle.Secondary)
            .setEmoji("✏️"),
          new ButtonBuilder()
            .setCustomId(`retry:${questionId}`)
            .setLabel("Réessayer / Fork")
            .setStyle(ButtonStyle.Primary)
            .setEmoji("🔄"),
          new ButtonBuilder()
            .setCustomId(`cancel:${questionId}`)
            .setLabel("Annuler")
            .setStyle(ButtonStyle.Danger)
            .setEmoji("❌")
        );
        rows.push(actionRow);
      } else {
        // Single-select menu
        const selectMenu = new StringSelectMenuBuilder()
          .setCustomId(`select_single:${questionId}`)
          .setPlaceholder(truncate("Choisissez une option...", 150))
          .setMinValues(1)
          .setMaxValues(1)
          .addOptions(
            options.map((opt, idx) => ({
              label: truncate(`${idx + 1}. ${opt.label}`, 100),
              value: String(idx),
              description: opt.description ? truncate(opt.description, 100) : undefined,
            }))
          );
        rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu));

        const controlRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder()
            .setCustomId(`other:${questionId}`)
            .setLabel("Autre (texte)")
            .setStyle(ButtonStyle.Secondary)
            .setEmoji("✏️"),
          new ButtonBuilder()
            .setCustomId(`retry:${questionId}`)
            .setLabel("Réessayer / Fork")
            .setStyle(ButtonStyle.Primary)
            .setEmoji("🔄"),
          new ButtonBuilder()
            .setCustomId(`cancel:${questionId}`)
            .setLabel("Annuler")
            .setStyle(ButtonStyle.Danger)
            .setEmoji("❌")
        );
        rows.push(controlRow);
      }
    } else {
      // Free text question
      const textRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder()
          .setCustomId(`text_btn:${questionId}`)
          .setLabel("Saisir une réponse")
          .setStyle(ButtonStyle.Success)
          .setEmoji("💬"),
        new ButtonBuilder()
          .setCustomId(`retry:${questionId}`)
          .setLabel("Réessayer / Fork")
          .setStyle(ButtonStyle.Primary)
          .setEmoji("🔄"),
        new ButtonBuilder()
          .setCustomId(`cancel:${questionId}`)
          .setLabel("Annuler")
          .setStyle(ButtonStyle.Danger)
          .setEmoji("❌")
      );
      rows.push(textRow);
    }

    return rows;
  }

  public async updateMessageStatus(
    message: Message,
    req: QuestionRequest,
    statusText: string,
    color = 0x57f287,
    thread?: ThreadChannel
  ): Promise<void> {
    try {
      const embed = new EmbedBuilder()
        .setColor(color)
        .setTitle("❓ Question de Hermes Agent")
        .setDescription(`### ${truncate(req.question, 1000)}\n\n${truncate(statusText, 3000)}`)
        .setTimestamp();

      if (req.details) {
        embed.addFields({ name: "ℹ️ Détails", value: truncate(req.details, 1024) });
      }

      await message.edit({
        embeds: [embed],
        components: [],
      });

      if (thread) {
        await thread
          .send({
            embeds: [
              new EmbedBuilder()
                .setColor(color)
                .setTitle("Statut de la question")
                .setDescription(truncate(statusText, 4000))
                .setTimestamp(),
            ],
          })
          .catch(() => {});
        await thread.setArchived(true).catch(() => {});
      }
    } catch (err) {
      console.error("[discord.js] Erreur mise à jour statut message question:", err);
    }
  }

  public async handleButtonInteraction(interaction: ButtonInteraction): Promise<boolean> {
    const [action, questionId] = interaction.customId.split(":");
    const pending = this.pendingQuestions.get(questionId);
    if (!pending) return false;

    if (action === "cancel") {
      if (pending.timer) clearTimeout(pending.timer);
      this.pendingQuestions.delete(questionId);

      const statusText = `Question annulée par <@${interaction.user.id}>.`;
      await interaction.update({
        embeds: [
          new EmbedBuilder()
            .setColor(0xed4245)
            .setTitle("❌ Question annulée")
            .setDescription(`### ${truncate(pending.req.question, 1000)}\n\n${statusText}`)
            .setTimestamp(),
        ],
        components: [],
      });

      if (pending.thread) {
        await pending.thread.send(`❌ **Question annulée** par <@${interaction.user.id}>.`).catch(() => {});
        await pending.thread.setArchived(true).catch(() => {});
      }

      pending.resolve({
        status: "cancelled",
        answers: [],
        message: "Question annulée depuis Discord",
        user: { id: interaction.user.id, username: interaction.user.username },
      });

      this.bridge.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "cancel",
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return true;
    }

    if (action === "retry") {
      if (pending.timer) clearTimeout(pending.timer);
      this.pendingQuestions.delete(questionId);

      const statusText = `Interruption demandée par <@${interaction.user.id}> pour forker/réessayer la tâche.`;
      await interaction.update({
        embeds: [
          new EmbedBuilder()
            .setColor(0xfee75c)
            .setTitle("🔄 Réessayer / Fork demandé")
            .setDescription(`### ${truncate(pending.req.question, 1000)}\n\n${statusText}`)
            .setTimestamp(),
        ],
        components: [],
      });

      if (pending.thread) {
        await pending.thread.send(`🔄 **Interruption demandée** par <@${interaction.user.id}>.`).catch(() => {});
        await pending.thread.setArchived(true).catch(() => {});
      }

      pending.resolve({
        status: "retry",
        answers: [],
        message: "Réessayer / Fork demandé depuis Discord",
        user: { id: interaction.user.id, username: interaction.user.username },
      });

      this.bridge.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "retry_task",
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return true;
    }

    if (action === "text_btn" || action === "other") {
      const modal = new ModalBuilder()
        .setCustomId(`modal_other:${questionId}`)
        .setTitle(truncate("Saisie de réponse", 45));

      const textInput = new TextInputBuilder()
        .setCustomId("custom_text")
        .setLabel("Votre réponse ou précision :")
        .setStyle(TextInputStyle.Paragraph)
        .setRequired(true)
        .setPlaceholder(truncate("Tapez votre texte ici...", 100));

      modal.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(textInput));
      await interaction.showModal(modal);
      return true;
    }

    if (action === "submit_multi") {
      const options = pending.req.options || [];
      const selectedIndices = Array.from(pending.selectedOptionIndices);

      if (selectedIndices.length === 0 && !pending.customText) {
        await interaction.reply({
          content: "⚠️ Veuillez sélectionner au moins une option avant de valider.",
          ephemeral: true,
        });
        return true;
      }

      if (pending.timer) clearTimeout(pending.timer);
      this.pendingQuestions.delete(questionId);

      const answers: AnswerItem[] = [];
      selectedIndices.forEach((idx) => {
        const opt = options[idx];
        if (opt) {
          answers.push({
            type: "option",
            label: opt.label,
            value: opt.value || opt.label,
            index: idx + 1,
          });
        }
      });

      if (pending.customText) {
        answers.push({
          type: "other",
          label: pending.customText,
          value: pending.customText,
        });
      }

      const summaryList = answers
        .map((a) => (a.type === "option" ? `✓ \`${a.index}. ${a.label}\`` : `✓ \`Autre: ${a.label}\``))
        .join("\n");

      const statusText = `**Options sélectionnées :**\n${summaryList}\n\n*Validé par <@${interaction.user.id}>*`;
      await interaction.update({
        embeds: [
          new EmbedBuilder()
            .setColor(0x57f287)
            .setTitle("✅ Sélection validée")
            .setDescription(`### ${truncate(pending.req.question, 1000)}\n\n${truncate(statusText, 3000)}`)
            .setTimestamp(),
        ],
        components: [],
      });

      if (pending.thread) {
        await pending.thread.send(`✅ **Sélection validée** par <@${interaction.user.id}> :\n${summaryList}`).catch(() => {});
        await pending.thread.setArchived(true).catch(() => {});
      }

      const res: QuestionResult = {
        status: "answered",
        answers,
        user: { id: interaction.user.id, username: interaction.user.username },
      };
      pending.resolve(res);

      // Émission d'événement pour Hermes
      const answerSummary = answers.map((a) => a.value).join(", ");
      this.bridge.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "clarify",
        payload: answerSummary,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return true;
    }

    return false;
  }

  public async handleSelectMenuInteraction(interaction: StringSelectMenuInteraction): Promise<boolean> {
    const [action, questionId] = interaction.customId.split(":");
    const pending = this.pendingQuestions.get(questionId);
    if (!pending) return false;

    if (action === "select") {
      pending.selectedOptionIndices = new Set(interaction.values.map((v) => Number.parseInt(v, 10)));
      await interaction.deferUpdate();
      return true;
    }

    if (action === "select_single") {
      const index = Number.parseInt(interaction.values[0], 10);
      const opt = pending.req.options?.[index];
      if (!opt) return true;

      if (pending.timer) clearTimeout(pending.timer);
      this.pendingQuestions.delete(questionId);

      const statusText = `**Option choisie :**\n✓ \`${index + 1}. ${opt.label}\`\n\n*Validé par <@${interaction.user.id}>*`;
      await interaction.update({
        embeds: [
          new EmbedBuilder()
            .setColor(0x57f287)
            .setTitle("✅ Choix validé")
            .setDescription(`### ${truncate(pending.req.question, 1000)}\n\n${truncate(statusText, 3000)}`)
            .setTimestamp(),
        ],
        components: [],
      });

      if (pending.thread) {
        await pending.thread.send(`✅ **Choix validé** par <@${interaction.user.id}> : \`${index + 1}. ${opt.label}\``).catch(() => {});
        await pending.thread.setArchived(true).catch(() => {});
      }

      const answerVal = opt.value || opt.label;
      const res: QuestionResult = {
        status: "answered",
        answers: [
          {
            type: "option",
            label: opt.label,
            value: answerVal,
            index: index + 1,
          },
        ],
        user: { id: interaction.user.id, username: interaction.user.username },
      };
      pending.resolve(res);

      this.bridge.emitInboundEvent({
        type: "button",
        platform: "discord",
        custom_id: interaction.customId,
        action: "clarify",
        payload: answerVal,
        chat_id: interaction.channelId,
        sender_id: interaction.user.id,
        message_id: interaction.message.id,
      });
      return true;
    }

    return false;
  }

  public async handleModalSubmitInteraction(interaction: ModalSubmitInteraction): Promise<boolean> {
    const [action, questionId] = interaction.customId.split(":");
    const pending = this.pendingQuestions.get(questionId);
    if (!pending) return false;

    if (action === "modal_other") {
      const text = interaction.fields.getTextInputValue("custom_text").trim();
      if (!text) {
        await interaction.reply({
          content: "La réponse ne peut pas être vide.",
          ephemeral: true,
        });
        return true;
      }

      if (!pending.req.multiSelect) {
        if (pending.timer) clearTimeout(pending.timer);
        this.pendingQuestions.delete(questionId);

        const statusText = `**Réponse saisie :**\n\`${text}\`\n\n*Soumis par <@${interaction.user.id}>*`;
        await interaction.deferUpdate().catch(() => {});
        await this.updateMessageStatus(
          pending.message,
          pending.req,
          statusText,
          0x57f287,
          pending.thread
        );

        if (pending.thread) {
          await pending.thread.send(`💬 **Réponse saisie** par <@${interaction.user.id}> :\n\`\`\`\n${text}\n\`\`\``).catch(() => {});
          await pending.thread.setArchived(true).catch(() => {});
        }

        const res: QuestionResult = {
          status: "answered",
          answers: [
            {
              type: pending.req.options && pending.req.options.length > 0 ? "other" : "text",
              label: text,
              value: text,
            },
          ],
          user: { id: interaction.user.id, username: interaction.user.username },
        };
        pending.resolve(res);

        this.bridge.emitInboundEvent({
          type: "button",
          platform: "discord",
          custom_id: interaction.customId,
          action: "clarify",
          payload: text,
          chat_id: interaction.channelId || "",
          sender_id: interaction.user.id,
          message_id: interaction.message?.id || "",
        });
        return true;
      } else {
        pending.customText = text;
        await interaction.reply({
          content: `Remarque/Option ajoutée : \`${text}\`. N'oubliez pas de cliquer sur **Valider la sélection**.`,
          ephemeral: true,
        });
        return true;
      }
    }

    return false;
  }
}
