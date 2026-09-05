import {
  Client,
  GatewayIntentBits,
  Partials,
  TextBasedChannel,
  Message,
} from "discord.js";
import { InboundMessageEvent, ChatInfoResponse } from "./types.js";

export class DiscordBridgeClient {
  public client: Client;
  private onInboundEvent: ((event: InboundMessageEvent) => void) | null = null;
  public isReady = false;

  constructor() {
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages,
      ],
      partials: [Partials.Channel, Partials.Message],
    });

    this.setupListeners();
  }

  public setInboundHandler(handler: (event: InboundMessageEvent) => void) {
    this.onInboundEvent = handler;
  }

  private setupListeners() {
    this.client.once("ready", () => {
      this.isReady = true;
      console.log(`[discord.js] Connecté avec succès en tant que ${this.client.user?.tag}`);
    });

    this.client.on("messageCreate", async (message: Message) => {
      // Ignorer ses propres messages pour éviter les boucles infinies
      if (message.author.id === this.client.user?.id) return;
      if (!this.onInboundEvent) return;

      const isDm = message.channel.isDMBased();
      const channelName = "name" in message.channel ? (message.channel.name as string) : "DM";

      const event: InboundMessageEvent = {
        platform: "discord",
        chat_id: message.channelId,
        sender_id: message.author.id,
        sender_name: message.author.username,
        message_id: message.id,
        content: message.content,
        is_dm: isDm,
        channel_name: channelName,
        guild_id: message.guildId ?? undefined,
        reply_to_id: message.reference?.messageId,
      };

      this.onInboundEvent(event);
    });
  }

  public async start(token: string): Promise<void> {
    if (!token) {
      console.warn("[discord.js] Aucun DISCORD_BOT_TOKEN renseigné, connexion ignorée.");
      return;
    }
    await this.client.login(token);
  }

  public async stop(): Promise<void> {
    this.isReady = false;
    await this.client.destroy();
  }

  public async sendMessage(
    chatId: string,
    content: string,
    replyTo?: string
  ): Promise<{ messageId: string }> {
    const channel = await this.client.channels.fetch(chatId);
    if (!channel || !channel.isTextBased()) {
      throw new Error(`Le salon ${chatId} est introuvable ou n'est pas un salon textuel.`);
    }

    const textChannel = channel as TextBasedChannel;
    const sendOptions: Record<string, unknown> = { content };
    if (replyTo) {
      sendOptions.reply = { messageReference: replyTo };
    }

    const sent = await textChannel.send(sendOptions);
    return { messageId: sent.id };
  }

  public async sendTyping(chatId: string): Promise<void> {
    const channel = await this.client.channels.fetch(chatId);
    if (channel && channel.isTextBased()) {
      await (channel as TextBasedChannel).sendTyping();
    }
  }

  public async getChatInfo(chatId: string): Promise<ChatInfoResponse> {
    const channel = await this.client.channels.fetch(chatId);
    if (!channel) {
      return { name: "inconnu", type: "unknown", chat_id: chatId };
    }

    let type: ChatInfoResponse["type"] = "channel";
    let name = "salon";

    if (channel.isDMBased()) {
      type = "dm";
      name = "DM";
    } else if (channel.isThread()) {
      type = "thread";
      name = channel.name;
    } else if ("name" in channel) {
      name = channel.name as string;
    }

    return { name, type, chat_id: chatId };
  }
}
