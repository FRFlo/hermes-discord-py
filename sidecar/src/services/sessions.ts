import {
  ChannelType,
  ForumChannel,
  ThreadChannel,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  StringSelectMenuBuilder,
  EmbedBuilder,
} from "discord.js";
import type { DiscordBridgeClient } from "./bridge.js";
import type { SessionItem } from "../types.js";

function truncate(str: string, maxLen: number): string {
  if (!str) return "";
  return str.length > maxLen ? `${str.slice(0, maxLen - 3)}...` : str;
}

export class SessionManager {
  constructor(private bridge: DiscordBridgeClient) {}

  /**
   * Récupère la liste des sessions (fils du forum actifs et archivés récents).
   */
  public async fetchSessions(limit: number = 25): Promise<SessionItem[]> {
    try {
      const channel = await this.bridge.client.channels.fetch(this.bridge.forumChannelId);
      if (!channel || channel.type !== ChannelType.GuildForum) {
        return [];
      }
      const forum = channel as ForumChannel;

      const activeThreads = await forum.threads.fetchActive();
      const archivedThreads = await forum.threads.fetchArchived({ limit: 20 });

      const allThreads: ThreadChannel[] = [
        ...Array.from(activeThreads.threads.values()),
        ...Array.from(archivedThreads.threads.values()),
      ];

      // Trier par date de création / activité décroissante
      allThreads.sort((a, b) => {
        const timeA = a.createdTimestamp || 0;
        const timeB = b.createdTimestamp || 0;
        return timeB - timeA;
      });

      return allThreads.slice(0, limit).map((t) => ({
        id: t.id,
        name: t.name,
        archived: Boolean(t.archived),
        messageCount: t.totalMessageSent ?? t.messageCount ?? 0,
        createdAt: t.createdTimestamp || Date.now(),
        url: `https://discord.com/channels/${t.guildId}/${t.id}`,
      }));
    } catch (err) {
      console.error("[SessionManager] Erreur récupération sessions :", err);
      return [];
    }
  }

  /**
   * Récupère les métadonnées d'une session / fil spécifique.
   */
  public async getSession(threadId: string): Promise<SessionItem | null> {
    try {
      const channel = await this.bridge.client.channels.fetch(threadId);
      if (!channel || !channel.isThread()) return null;
      const t = channel as ThreadChannel;
      return {
        id: t.id,
        name: t.name,
        archived: Boolean(t.archived),
        messageCount: t.totalMessageSent ?? t.messageCount ?? 0,
        createdAt: t.createdTimestamp || Date.now(),
        url: `https://discord.com/channels/${t.guildId}/${t.id}`,
      };
    } catch {
      return null;
    }
  }

  /**
   * Renomme une session / fil forum.
   */
  public async renameSession(threadId: string, newName: string): Promise<boolean> {
    try {
      const channel = await this.bridge.client.channels.fetch(threadId);
      if (!channel || !channel.isThread()) return false;
      const t = channel as ThreadChannel;
      await t.setName(truncate(newName, 100));
      return true;
    } catch (err) {
      console.error(`[SessionManager] Erreur renommage fil ${threadId} :`, err);
      return false;
    }
  }

  /**
   * Archive ou désarchive une session.
   */
  public async toggleArchiveSession(threadId: string, forceArchive?: boolean): Promise<{ success: boolean; archived: boolean }> {
    try {
      const channel = await this.bridge.client.channels.fetch(threadId);
      if (!channel || !channel.isThread()) return { success: false, archived: false };
      const t = channel as ThreadChannel;
      const targetState = forceArchive !== undefined ? forceArchive : !t.archived;
      await t.setArchived(targetState);
      return { success: true, archived: targetState };
    } catch (err) {
      console.error(`[SessionManager] Erreur archivage fil ${threadId} :`, err);
      return { success: false, archived: false };
    }
  }

  /**
   * Supprime une session Discord et émet un événement de purge vers Hermes.
   */
  public async deleteSession(threadId: string, userId: string): Promise<boolean> {
    try {
      const channel = await this.bridge.client.channels.fetch(threadId);
      if (channel && channel.isThread()) {
        const t = channel as ThreadChannel;
        await t.delete("Suppression de la session demandée par l'utilisateur via /sessions");
      }

      // Notifier Hermes pour purger l'historique de la session en base
      this.bridge.emitInboundEvent({
        type: "session_delete",
        platform: "discord",
        session_id: threadId,
        sender_id: userId,
      });

      return true;
    } catch (err) {
      console.error(`[SessionManager] Erreur suppression fil ${threadId} :`, err);
      return false;
    }
  }

  /**
   * Construction de l'Embed de liste des sessions.
   */
  public buildSessionListEmbed(sessions: SessionItem[], currentThreadId?: string): EmbedBuilder {
    const embed = new EmbedBuilder()
      .setTitle("📂 Gestionnaire des Sessions Hermes")
      .setColor(0x5865f2)
      .setDescription(
        `Sélectionnez une session ci-dessous pour la gérer (**renommer**, **archiver**, **supprimer** ou **consulter**).\n\n` +
          (sessions.length === 0
            ? "*Aucune session trouvée dans le forum.*"
            : sessions
                .slice(0, 10)
                .map((s, idx) => {
                  const isCurrent = s.id === currentThreadId ? " 📍 *(actuelle)*" : "";
                  const icon = s.archived ? "🔒" : "💬";
                  const dateStr = `<t:${Math.floor(s.createdAt / 1000)}:R>`;
                  return `**${idx + 1}.** ${icon} [${truncate(s.name, 40)}](${s.url})${isCurrent}\n↳ ${s.messageCount} msg • Créée ${dateStr}`;
                })
                .join("\n\n"))
      )
      .setFooter({ text: `${sessions.length} session(s) répertoriée(s)` })
      .setTimestamp();

    return embed;
  }

  /**
   * Construction des composants (Select Menu + Boutons) pour la liste des sessions.
   */
  public buildSessionListComponents(sessions: SessionItem[]): ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] {
    const rows: ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>[] = [];

    if (sessions.length > 0) {
      const selectMenu = new StringSelectMenuBuilder()
        .setCustomId("session:select")
        .setPlaceholder("🔍 Choisissez une session à administrer...")
        .setMinValues(1)
        .setMaxValues(1)
        .addOptions(
          sessions.slice(0, 25).map((s) => ({
            label: truncate(s.name, 90),
            value: s.id,
            description: truncate(
              `${s.archived ? "🔒 Archivée" : "💬 Active"} • ${s.messageCount} messages`,
              100
            ),
            emoji: s.archived ? "🔒" : "💬",
          }))
        );
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(selectMenu));
    }

    const controlRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId("session:refresh")
        .setLabel("Rafraîchir la liste")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("🔄"),
      new ButtonBuilder()
        .setCustomId("session:dismiss")
        .setLabel("Fermer le menu")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("✖️")
    );
    rows.push(controlRow);

    return rows;
  }

  /**
   * Construction de l'Embed détaillé pour une session sélectionnée.
   */
  public buildSessionDetailEmbed(session: SessionItem): EmbedBuilder {
    const statusEmoji = session.archived ? "🔒" : "🟢";
    const statusText = session.archived ? "Archivée / Clôturée" : "Active / Ouverte";
    const createdStr = `<t:${Math.floor(session.createdAt / 1000)}:F> (<t:${Math.floor(session.createdAt / 1000)}:R>)`;

    const embed = new EmbedBuilder()
      .setTitle(`🛠️ Session : ${truncate(session.name, 60)}`)
      .setColor(session.archived ? 0x95a5a6 : 0x57f287)
      .setDescription(`[Accéder au fil Discord de la session 🔗](${session.url})`)
      .addFields(
        { name: "📋 Statut", value: `${statusEmoji} **${statusText}**`, inline: true },
        { name: "💬 Messages échangés", value: `${session.messageCount} message(s)`, inline: true },
        { name: "🆔 Identifiant unique", value: `\`${session.id}\``, inline: false },
        { name: "⏱️ Date de création", value: createdStr, inline: false }
      )
      .setFooter({ text: "Actions disponibles ci-dessous" })
      .setTimestamp();

    return embed;
  }

  /**
   * Construction des boutons d'actions pour une session sélectionnée.
   */
  public buildSessionDetailComponents(session: SessionItem): ActionRowBuilder<ButtonBuilder>[] {
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`session:rename:${session.id}`)
        .setLabel("Renommer")
        .setStyle(ButtonStyle.Primary)
        .setEmoji("✏️"),
      new ButtonBuilder()
        .setCustomId(`session:toggle_archive:${session.id}`)
        .setLabel(session.archived ? "Désarchiver" : "Archiver")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji(session.archived ? "🔓" : "🔒"),
      new ButtonBuilder()
        .setCustomId(`session:delete_prompt:${session.id}`)
        .setLabel("Supprimer")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("🗑️"),
      new ButtonBuilder()
        .setCustomId("session:list")
        .setLabel("Retour à la liste")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("⬅️")
    );

    return [row];
  }

  /**
   * Construction des boutons de confirmation de suppression.
   */
  public buildDeleteConfirmationComponents(sessionId: string): ActionRowBuilder<ButtonBuilder>[] {
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`session:delete_confirm:${sessionId}`)
        .setLabel("Confirmer la suppression définitive")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("💥"),
      new ButtonBuilder()
        .setCustomId(`session:detail:${sessionId}`)
        .setLabel("Annuler")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("↩️")
    );
    return [row];
  }
}
