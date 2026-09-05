export interface InboundMessageEvent {
  platform: "discord";
  chat_id: string;
  sender_id: string;
  sender_name: string;
  message_id: string;
  content: string;
  is_dm: boolean;
  channel_name?: string;
  guild_id?: string;
  reply_to_id?: string;
  raw?: Record<string, unknown>;
}

export interface OutboundSendRequest {
  chat_id: string;
  content: string;
  reply_to?: string;
  metadata?: Record<string, unknown>;
}

export interface OutboundSendResponse {
  success: boolean;
  message_id?: string;
  error?: string;
}

export interface ChatInfoResponse {
  name: string;
  type: "channel" | "dm" | "thread" | "unknown";
  chat_id: string;
}
