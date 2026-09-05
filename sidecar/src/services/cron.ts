import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  StringSelectMenuBuilder,
  EmbedBuilder,
} from "discord.js";
import type { DiscordBridgeClient } from "./bridge.js";
import type { CronJobItem, InboundCronEvent } from "../types.js";

function truncate(str: string, maxLen: number): string {
  if (!str) return "";
  return str.length > maxLen ? `${str.slice(0, maxLen - 3)}...` : str;
}

export class CronManager {
  private jobsCache = new Map<string, CronJobItem>();

  constructor(private bridge: DiscordBridgeClient) {}

  public setJobs(jobs: CronJobItem[]): void {
    this.jobsCache.clear();
    for (const job of jobs) {
      this.jobsCache.set(job.id, job);
    }
  }

  public getJobs(): CronJobItem[] {
    return Array.from(this.jobsCache.values());
  }

  public getJob(id: string): CronJobItem | undefined {
    return this.jobsCache.get(id);
  }

  public updateJob(job: CronJobItem): void {
    this.jobsCache.set(job.id, job);
  }

  public removeJob(id: string): void {
    this.jobsCache.delete(id);
  }

  public requestList(chatId: string, senderId: string, interactionId?: string): void {
    const event: InboundCronEvent = {
      type: "cron",
      platform: "discord",
      action: "list",
      chat_id: chatId,
      sender_id: senderId,
      interaction_id: interactionId,
    };
    this.bridge.emitInboundEvent(event);
  }

  public requestAction(
    action: "pause" | "resume" | "trigger" | "delete" | "view_output",
    jobId: string,
    chatId: string,
    senderId: string,
    interactionId?: string
  ): void {
    const event: InboundCronEvent = {
      type: "cron",
      platform: "discord",
      action,
      job_id: jobId,
      chat_id: chatId,
      sender_id: senderId,
      interaction_id: interactionId,
    };
    this.bridge.emitInboundEvent(event);
  }

  public requestCreate(
    name: string,
    schedule: string,
    prompt: string,
    deliver: string,
    chatId: string,
    senderId: string,
    interactionId?: string
  ): void {
    const event: InboundCronEvent = {
      type: "cron",
      platform: "discord",
      action: "create",
      name,
      schedule,
      prompt,
      deliver,
      chat_id: chatId,
      sender_id: senderId,
      interaction_id: interactionId,
    };
    this.bridge.emitInboundEvent(event);
  }

  /**
   * Construction de l'Embed de liste des tâches cron.
   */
  public buildJobListEmbed(jobs: CronJobItem[]): EmbedBuilder {
    const embed = new EmbedBuilder()
      .setTitle("⏰ Gestionnaire des Tâches Cron Hermes")
      .setColor(0x5865f2)
      .setDescription(
        `Consultez et pilotez vos tâches planifiées ci-dessous.\nUtilisez le menu pour inspecter une tâche, ou cliquez sur **➕ Planifier une tâche** pour en ajouter une nouvelle.\n\n` +
          (jobs.length === 0
            ? "*Aucune tâche cron configurée pour le moment.*"
            : jobs
                .slice(0, 10)
                .map((j, idx) => {
                  const icon = j.enabled ? "🟢" : "⏸️";
                  const sched = j.schedule_display || j.schedule;
                  const nextStr = j.next_run
                    ? typeof j.next_run === "number"
                      ? `<t:${Math.floor(j.next_run / 1000)}:R>`
                      : j.next_run
                    : "Non planifié";
                  return `**${idx + 1}.** ${icon} **${truncate(j.name, 35)}** (\`${sched}\`)\n↳ Prochaine : ${nextStr}`;
                })
                .join("\n\n"))
      )
      .setFooter({ text: `${jobs.length} tâche(s) enregistrée(s)` })
      .setTimestamp();

    return embed;
  }

  /**
   * Construction des composants pour la liste des tâches cron.
   */
  public buildJobListComponents(jobs: CronJobItem[]): ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] {
    const rows: ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] = [];

    if (jobs.length > 0) {
      const selectMenu = new StringSelectMenuBuilder()
        .setCustomId("cron:select")
        .setPlaceholder("🔍 Choisissez une tâche cron à piloter...")
        .setMinValues(1)
        .setMaxValues(1)
        .addOptions(
          jobs.slice(0, 25).map((j) => ({
            label: truncate(j.name, 90),
            value: j.id,
            description: truncate(
              `${j.enabled ? "🟢 Active" : "⏸️ En pause"} • Sched: ${j.schedule_display || j.schedule}`,
              100
            ),
            emoji: j.enabled ? "🟢" : "⏸️",
          }))
        );
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu));
    }

    const controlRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId("cron:create_modal")
        .setLabel("Planifier une tâche")
        .setStyle(ButtonStyle.Success)
        .setEmoji("➕"),
      new ButtonBuilder()
        .setCustomId("cron:refresh")
        .setLabel("Rafraîchir")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("🔄"),
      new ButtonBuilder()
        .setCustomId("cron:dismiss")
        .setLabel("Fermer")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("✖️")
    );
    rows.push(controlRow);

    return rows;
  }

  /**
   * Construction de l'Embed détaillé d'une tâche cron.
   */
  public buildJobDetailEmbed(job: CronJobItem): EmbedBuilder {
    const statusText = job.enabled ? "🟢 Active" : "⏸️ En pause";
    const schedText = job.schedule_display || job.schedule;

    const nextStr = job.next_run
      ? typeof job.next_run === "number"
        ? `<t:${Math.floor(job.next_run / 1000)}:F> (<t:${Math.floor(job.next_run / 1000)}:R>)`
        : job.next_run
      : "Non calculé";

    const lastStr = job.last_run
      ? typeof job.last_run === "number"
        ? `<t:${Math.floor(job.last_run / 1000)}:R>`
        : job.last_run
      : "Jamais exécuté";

    const lastStatus = job.last_status === "success"
      ? "✅ Succès"
      : job.last_status === "error"
      ? "❌ Erreur"
      : job.last_status || "N/A";

    const embed = new EmbedBuilder()
      .setTitle(`⏰ Tâche Cron : ${truncate(job.name, 60)}`)
      .setColor(job.enabled ? 0x57f287 : 0xfee75c)
      .setDescription(`**Prompt / Instruction exécutée :**\n\`\`\`text\n${truncate(job.prompt, 1500)}\n\`\`\``)
      .addFields(
        { name: "📋 Statut", value: `**${statusText}**`, inline: true },
        { name: "🗓️ Fréquence / Cron", value: `\`${schedText}\``, inline: true },
        { name: "📍 Destination", value: `\`${job.deliver || "Automatique"}\``, inline: true },
        { name: "⏱️ Prochaine exécution", value: String(nextStr), inline: false },
        { name: "📜 Dernier résultat", value: `${lastStatus} (${lastStr})`, inline: false },
        { name: "🆔 Identifiant unique", value: `\`${job.id}\``, inline: false }
      )
      .setFooter({ text: "Actions disponibles ci-dessous" })
      .setTimestamp();

    return embed;
  }

  /**
   * Construction des boutons d'actions pour une tâche sélectionnée.
   */
  public buildJobDetailComponents(job: CronJobItem): ActionRowBuilder<ButtonBuilder>[] {
    const row1 = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`cron:trigger:${job.id}`)
        .setLabel("Exécuter maintenant")
        .setStyle(ButtonStyle.Primary)
        .setEmoji("⚡"),
      new ButtonBuilder()
        .setCustomId(`cron:toggle_pause:${job.id}`)
        .setLabel(job.enabled ? "Mettre en pause" : "Reprendre")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji(job.enabled ? "⏸️" : "▶️"),
      new ButtonBuilder()
        .setCustomId(`cron:view_output:${job.id}`)
        .setLabel("Dernier output")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("📜")
    );

    const row2 = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`cron:delete_prompt:${job.id}`)
        .setLabel("Supprimer la tâche")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("🗑️"),
      new ButtonBuilder()
        .setCustomId("cron:list")
        .setLabel("Retour à la liste")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("⬅️")
    );

    return [row1, row2];
  }

  /**
   * Construction des boutons de confirmation de suppression d'une tâche.
   */
  public buildDeleteConfirmationComponents(jobId: string): ActionRowBuilder<ButtonBuilder>[] {
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`cron:delete_confirm:${jobId}`)
        .setLabel("Confirmer la suppression")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("💥"),
      new ButtonBuilder()
        .setCustomId(`cron:detail:${jobId}`)
        .setLabel("Annuler")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("↩️")
    );
    return [row];
  }
}
