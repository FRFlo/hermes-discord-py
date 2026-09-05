export interface InboundAttachment {
  name: string;
  url: string;
  size: number;
  contentType?: string;
  localPath?: string;
  isText?: boolean;
  textContent?: string;
}

export type InboundEventType = "message" | "command" | "button" | "message_delete" | "message_edit";

export interface InboundMessageEvent {
  type: "message";
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
  attachments?: InboundAttachment[];
  raw?: Record<string, unknown>;
}

export interface InboundCommandEvent {
  type: "command";
  platform: "discord";
  command: "close" | "reset" | "status" | "model" | "stop" | "context" | string;
  args?: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  interaction_id: string;
  is_dm: boolean;
}

export interface InboundButtonEvent {
  type: "button";
  platform: "discord";
  custom_id: string;
  action: "approval" | "clarify" | "cancel" | "regenerate" | "close" | "view_logs" | "retry_task" | string;
  payload?: string;
  chat_id: string;
  sender_id: string;
  message_id: string;
}

export interface InboundDeleteEvent {
  type: "message_delete";
  platform: "discord";
  message_id: string;
  chat_id: string;
  sender_id: string;
  sender_name?: string;
  is_dm: boolean;
}

export interface InboundEditEvent {
  type: "message_edit";
  platform: "discord";
  message_id: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  content: string;
  old_content?: string;
  is_dm: boolean;
  reply_to_id?: string;
}

export interface InboundSessionDeleteEvent {
  type: "session_delete";
  platform: "discord";
  session_id: string;
  sender_id: string;
}

export interface SessionItem {
  id: string;
  name: string;
  archived: boolean;
  messageCount: number;
  createdAt: number;
  url: string;
}

export interface CronJobItem {
  id: string;
  name: string;
  schedule: string;
  schedule_display?: string;
  prompt: string;
  enabled: boolean;
  last_run?: string | number | null;
  last_status?: "success" | "error" | "running" | string;
  next_run?: string | number | null;
  deliver?: string;
  last_output?: string;
}

export interface InboundCronEvent {
  type: "cron";
  platform: "discord";
  action: "list" | "pause" | "resume" | "trigger" | "delete" | "create" | "view_output";
  job_id?: string;
  name?: string;
  schedule?: string;
  prompt?: string;
  deliver?: string;
  chat_id: string;
  sender_id: string;
  interaction_id?: string;
}

export type InboundEvent =
  | InboundMessageEvent
  | InboundCommandEvent
  | InboundButtonEvent
  | InboundDeleteEvent
  | InboundEditEvent
  | InboundSessionDeleteEvent
  | InboundCronEvent;

export interface OutboundSendRequest {
  chat_id: string;
  content: string;
  reply_to?: string;
  files?: string[];
  with_action_buttons?: boolean;
  metadata?: Record<string, unknown>;
}

export interface OutboundSendResponse {
  success: boolean;
  message_ids?: string[];
  message_id?: string;
  error?: string;
}

export interface ToolProgressRequest {
  chat_id: string;
  trigger_message_id?: string;
  tool_name: string;
  tool_args?: string;
  status: "start" | "running" | "done" | "error";
  output?: string;
  is_final?: boolean;
}

export interface ToolProgressResponse {
  success: boolean;
  progress_message_id?: string;
  error?: string;
}

export interface ReactionRequest {
  chat_id: string;
  message_id: string;
  emoji: string;
  action: "add" | "remove";
}

export interface ClarifyOption {
  label: string;
  value: string;
  description?: string;
}

export interface QuestionOption {
  label: string;
  value?: string;
  description?: string;
}

export interface QuestionRecentMessage {
  role: string;
  content: string;
}

export interface QuestionRequest {
  id?: string;
  chat_id?: string;
  channelId?: string;
  question: string;
  details?: string;
  context?: string;
  recentMessages?: QuestionRecentMessage[];
  options?: QuestionOption[];
  multiSelect?: boolean;
  timeoutSeconds?: number;
  reply_to?: string;
}

export interface AnswerItem {
  type: "option" | "other" | "text";
  label: string;
  value: string;
  index?: number;
}

export interface QuestionResult {
  status: "answered" | "timeout" | "cancelled" | "retry";
  answers: AnswerItem[];
  message?: string;
  user?: {
    id: string;
    username: string;
  };
}

export interface ClarifyRequest {
  chat_id: string;
  question: string;
  options: ClarifyOption[];
  reply_to?: string;
  details?: string;
  context?: string;
  multiSelect?: boolean;
  timeoutSeconds?: number;
}

export interface ExecApprovalRequest {
  chat_id: string;
  command: string;
  description?: string;
  reply_to?: string;
}

export interface AlertRequest {
  chat_id?: string;
  title: string;
  error_message: string;
  details?: string;
  task_id?: string;
}

export interface ArchiveThreadRequest {
  chat_id: string;
  reason?: string;
}

export interface ChatInfoResponse {
  name: string;
  type: "channel" | "dm" | "thread" | "forum_thread" | "unknown";
  chat_id: string;
  is_forum_thread?: boolean;
}

import type {
  ChatInputCommandInteraction,
  AutocompleteInteraction,
  ButtonInteraction,
  ClientEvents,
  Collection,
  SlashCommandBuilder,
  SlashCommandOptionsOnlyBuilder,
  SlashCommandSubcommandsOnlyBuilder,
} from "discord.js";
import type { DiscordBridgeClient } from "./discord.js";

export interface SlashCommand {
  command:
    | SlashCommandBuilder
    | SlashCommandOptionsOnlyBuilder
    | SlashCommandSubcommandsOnlyBuilder;
  execute: (interaction: ChatInputCommandInteraction) => Promise<void> | void;
  autocomplete?: (interaction: AutocompleteInteraction) => Promise<void> | void;
  cooldown?: number;
}

export interface ButtonCommand {
  prefix: string;
  execute: (interaction: ButtonInteraction) => Promise<void> | void;
  cooldown?: number;
}

export interface BotEvent<Name extends keyof ClientEvents = keyof ClientEvents> {
  name: Name;
  once?: boolean;
  execute: (...args: ClientEvents[Name]) => Promise<void> | void;
}

declare module "discord.js" {
  export interface Client {
    commands: Collection<string, SlashCommand>;
    buttons: Collection<string, ButtonCommand>;
    cooldowns: Collection<string, number>;
    bridge: DiscordBridgeClient;
  }
}

