import {
  Client,
  Collection,
  GatewayIntentBits,
  Partials,
} from "discord.js";
import type {
  InboundEvent,
  ChatInfoResponse,
  ClarifyOption,
  QuestionRequest,
  QuestionResult,
} from "../types.js";
import { ChannelManager, isSendable, type Sendable } from "./channels.js";
import { MessageManager } from "./messages.js";
import { ProgressManager } from "./progress.js";
import { ReactionManager } from "./reactions.js";
import { AlertManager } from "./alerts.js";
import { QuestionManager } from "./questions.js";
import { SessionManager } from "./sessions.js";
import { CronManager } from "./cron.js";
import loadCommands from "../handlers/command.js";
import loadButtons from "../handlers/button.js";
import loadEvents from "../handlers/event.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";
const DEFAULT_FORUM_CHANNEL = "1544452203207589938";

export { isSendable, type Sendable };

export class DiscordBridgeClient {
  public client: Client;
  private onInboundEvent: ((event: InboundEvent) => void) | null = null;
  public isReady = false;
  public allowedUserId: string;
  public forumChannelId: string;
  public enableReactions: boolean;

  // Sous-services modulaires
  public channels: ChannelManager;
  public messages: MessageManager;
  public progress: ProgressManager;
  public reactions: ReactionManager;
  public alerts: AlertManager;
  public questions: QuestionManager;
  public sessions: SessionManager;
  public cron: CronManager;

  constructor() {
    this.allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;
    this.forumChannelId = process.env.DISCORD_FORUM_CHANNEL_ID || DEFAULT_FORUM_CHANNEL;
    this.enableReactions = process.env.DISCORD_REACTIONS !== "false";

    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages,
      ],
      partials: [Partials.Channel, Partials.Message, Partials.User],
    });

    // Initialisation des collections modulaires
    this.client.commands = new Collection();
    this.client.buttons = new Collection();
    this.client.cooldowns = new Collection();
    this.client.bridge = this;

    // Instanciation des sous-services modulaires
    this.channels = new ChannelManager(this);
    this.messages = new MessageManager(this);
    this.progress = new ProgressManager(this);
    this.reactions = new ReactionManager(this);
    this.alerts = new AlertManager(this);
    this.questions = new QuestionManager(this);
    this.sessions = new SessionManager(this);
    this.cron = new CronManager(this);
  }

  public async init(): Promise<void> {
    // Chargement dynamique des handlers (events, buttons, commands)
    await loadEvents(this.client);
    await loadButtons(this.client);
    await loadCommands(this.client);
  }

  public setInboundHandler(handler: (event: InboundEvent) => void) {
    this.onInboundEvent = handler;
  }

  public emitInboundEvent(event: InboundEvent) {
    if (this.onInboundEvent) {
      this.onInboundEvent(event);
    }
  }

  public async start(token: string): Promise<void> {
    if (!token) {
      console.warn("[discord.js] Aucun DISCORD_BOT_TOKEN renseigné, connexion ignorée.");
      return;
    }
    await this.init();
    await this.client.login(token);
  }

  public async stop(): Promise<void> {
    this.isReady = false;
    await this.client.destroy();
  }

  // --- Délégations vers ChannelManager ---
  public isChannelAllowed(channel: unknown): boolean {
    return this.channels.isChannelAllowed(channel);
  }

  public async deleteMessage(chatId: string, messageId: string): Promise<boolean> {
    return this.channels.deleteMessage(chatId, messageId);
  }

  public async archiveThread(chatId: string, reason?: string): Promise<boolean> {
    return this.channels.archiveThread(chatId, reason);
  }

  public async sendTyping(chatId: string): Promise<void> {
    return this.channels.sendTyping(chatId);
  }

  public async getChatInfo(chatId: string): Promise<ChatInfoResponse> {
    return this.channels.getChatInfo(chatId);
  }

  // --- Délégations vers MessageManager ---
  public async sendMessage(
    chatId: string,
    content: string,
    replyTo?: string,
    extraFiles?: string[],
    withActionButtons: boolean = true
  ): Promise<{ messageIds: string[] }> {
    return this.messages.sendMessage(chatId, content, replyTo, extraFiles, withActionButtons);
  }

  // --- Délégations vers ProgressManager ---
  public async updateToolProgress(
    chatId: string,
    toolName: string,
    toolArgs?: string,
    status: "start" | "running" | "done" | "error" = "running",
    output?: string,
    isFinal: boolean = false
  ): Promise<{ progressMessageId?: string }> {
    return this.progress.updateToolProgress(chatId, toolName, toolArgs, status, output, isFinal);
  }

  public async cancelActiveProgress(chatId: string): Promise<void> {
    return this.progress.cancelActiveProgress(chatId);
  }

  // --- Délégations vers ReactionManager ---
  public isChatBusy(chatId: string): boolean {
    return this.reactions.isChatBusy(chatId);
  }

  public setChatBusy(chatId: string, busy: boolean): void {
    this.reactions.setChatBusy(chatId, busy);
  }

  public async setReaction(chatId: string, messageId: string, emoji: string, action: "add" | "remove"): Promise<void> {
    return this.reactions.setReaction(chatId, messageId, emoji, action);
  }

  public async setTurnStartReaction(chatId: string, triggerMessageId: string): Promise<void> {
    return this.reactions.setTurnStartReaction(chatId, triggerMessageId);
  }

  public async setFinalStatusReaction(chatId: string, triggerMessageId: string, success: boolean): Promise<void> {
    return this.reactions.setFinalStatusReaction(chatId, triggerMessageId, success);
  }

  // --- Délégations vers AlertManager ---
  public async sendSystemAlert(
    title: string,
    errorMessage: string,
    details?: string,
    taskId: string = "default"
  ): Promise<{ messageId?: string }> {
    return this.alerts.sendSystemAlert(title, errorMessage, details, taskId);
  }

  public async sendExecApproval(
    chatId: string,
    command: string,
    description?: string,
    replyTo?: string
  ): Promise<{ messageId: string }> {
    return this.alerts.sendExecApproval(chatId, command, description, replyTo);
  }

  // --- Délégations vers QuestionManager ---
  public async askQuestion(req: QuestionRequest): Promise<QuestionResult> {
    return this.questions.askQuestion(req);
  }

  public async sendClarify(
    chatId: string,
    question: string,
    options: ClarifyOption[],
    replyTo?: string,
    details?: string,
    context?: string,
    multiSelect?: boolean,
    timeoutSeconds?: number
  ): Promise<{ messageId?: string; result?: QuestionResult }> {
    const questionReq: QuestionRequest = {
      chat_id: chatId,
      question,
      options: options.map((opt) => ({
        label: opt.label,
        value: opt.value || opt.label,
        description: opt.description,
      })),
      reply_to: replyTo,
      details,
      context,
      multiSelect,
      timeoutSeconds,
    };
    const res = await this.questions.askQuestion(questionReq);
    return { result: res };
  }
}
