import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuthSession } from '@/app/auth';
import { type AgentListItem, useAgentsQuery } from '@/features/agents/api';

export { useAgentsQuery };
export type { AgentListItem };

type ChatRole = 'assistant' | 'user';
type ChatMessageState = 'aborted' | 'done' | 'error' | 'streaming';

export type ChatMessage = {
  content: string;
  id: string;
  role: ChatRole;
  state: ChatMessageState;
};

type ChatStreamEvent = {
  content: string;
  type: 'done' | 'error' | 'text_delta';
};

type UseAgentChatResult = {
  abort: () => void;
  error: string | null;
  isStreaming: boolean;
  messages: ChatMessage[];
  sendMessage: (agentName: string, message: string) => Promise<void>;
};

type IngressErrorBody = {
  detail?: unknown;
};

async function readIngressErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as IngressErrorBody;
    return typeof body.detail === 'string' && body.detail.length > 0 ? body.detail : null;
  } catch {
    return null;
  }
}

function toIngressError(agentName: string, status: number, detail: string | null): string {
  if (detail) {
    return `Agent "${agentName}": ${detail}`;
  }
  if (status === 404) {
    return `Agent "${agentName}" was not found.`;
  }
  if (status === 503) {
    return `Agent "${agentName}" is currently unavailable.`;
  }
  return `Agent "${agentName}" request failed with status ${status}.`;
}

function parseSseBuffer(buffer: string): { events: ChatStreamEvent[]; remainder: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const parts = normalized.split('\n\n');

  if (!normalized.endsWith('\n\n')) {
    const remainder = parts.pop() ?? '';
    return {
      events: parts.flatMap(parseSseEventBlock),
      remainder,
    };
  }

  return {
    events: parts.flatMap(parseSseEventBlock),
    remainder: '',
  };
}

function parseSseEventBlock(block: string): ChatStreamEvent[] {
  const dataLines = block
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .filter(Boolean);

  if (dataLines.length === 0) {
    return [];
  }

  try {
    return [JSON.parse(dataLines.join('\n')) as ChatStreamEvent];
  } catch {
    return [];
  }
}

function updateMessage(
  messages: ChatMessage[],
  messageId: string,
  updater: (message: ChatMessage) => ChatMessage
): ChatMessage[] {
  return messages.map((message) => (message.id === messageId ? updater(message) : message));
}

export function useAgentChat(): UseAgentChatResult {
  const auth = useAuthSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const activeRequestIdRef = useRef(0);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const streamingAssistantIdRef = useRef<string | null>(null);

  const abort = useCallback((): void => {
    activeRequestIdRef.current += 1;
    void readerRef.current?.cancel();
    readerRef.current = null;
    const assistantId = streamingAssistantIdRef.current;
    streamingAssistantIdRef.current = null;
    setIsStreaming(false);
    if (assistantId) {
      setMessages((current) =>
        updateMessage(current, assistantId, (message) => ({ ...message, state: 'aborted' }))
      );
    }
  }, []);

  useEffect(() => {
    return () => {
      activeRequestIdRef.current += 1;
      void readerRef.current?.cancel();
      readerRef.current = null;
    };
  }, []);

  const sendMessage = useCallback(
    async (agentName: string, message: string): Promise<void> => {
      abort();
      setError(null);

      const requestId = activeRequestIdRef.current + 1;
      activeRequestIdRef.current = requestId;
      const assistantId = `assistant-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      streamingAssistantIdRef.current = assistantId;
      setMessages((current) => [
        ...current,
        { content: message, id: `user-${assistantId}`, role: 'user', state: 'done' },
        { content: '', id: assistantId, role: 'assistant', state: 'streaming' },
      ]);

      setIsStreaming(true);

      try {
        const headers = new Headers({ 'content-type': 'application/json' });
        if (auth.token) {
          headers.set('authorization', `Session ${auth.token}`);
        }

        const response = await fetch(`${auth.baseUrl}/admin/agents/${agentName}/chat`, {
          body: JSON.stringify({ message }),
          headers,
          method: 'POST',
        });

        if (activeRequestIdRef.current !== requestId) {
          return;
        }

        if (response.status === 401) {
          auth.clearToken();
        }

        if (!response.ok) {
          const detail = await readIngressErrorDetail(response);
          const ingressError = toIngressError(agentName, response.status, detail);
          setError(ingressError);
          setMessages((current) =>
            updateMessage(current, assistantId, (currentMessage) => ({
              ...currentMessage,
              content: ingressError,
              state: 'error',
            }))
          );
          return;
        }

        if (!response.body) {
          throw new Error('Missing stream body');
        }

        const reader = response.body.getReader();
        readerRef.current = reader;
        const decoder = new TextDecoder();
        let buffer = '';
        let sawDone = false;

        while (true) {
          const { done, value } = await reader.read();
          if (activeRequestIdRef.current !== requestId) {
            return;
          }
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSseBuffer(buffer);
          buffer = parsed.remainder;

          for (const event of parsed.events) {
            if (event.type === 'text_delta') {
              setMessages((current) =>
                updateMessage(current, assistantId, (currentMessage) => ({
                  ...currentMessage,
                  content: `${currentMessage.content}${event.content}`,
                  state: 'streaming',
                }))
              );
            }
            if (event.type === 'error') {
              setError(event.content);
              setMessages((current) =>
                updateMessage(current, assistantId, (currentMessage) => ({
                  ...currentMessage,
                  state: 'error',
                }))
              );
              return;
            }
            if (event.type === 'done') {
              sawDone = true;
              setMessages((current) =>
                updateMessage(current, assistantId, (currentMessage) => ({
                  ...currentMessage,
                  state: 'done',
                }))
              );
              return;
            }
          }
        }

        if (!sawDone && activeRequestIdRef.current === requestId) {
          setMessages((current) =>
            updateMessage(current, assistantId, (currentMessage) => ({
              ...currentMessage,
              state: currentMessage.content ? 'done' : 'error',
            }))
          );
        }
      } catch (caught) {
        if (activeRequestIdRef.current !== requestId) {
          setMessages((current) =>
            updateMessage(current, assistantId, (currentMessage) => ({
              ...currentMessage,
              state: 'aborted',
            }))
          );
          return;
        }

        const failure =
          caught instanceof Error ? caught.message : `Agent "${agentName}" stream failed.`;
        setError(failure);
        setMessages((current) =>
          updateMessage(current, assistantId, (currentMessage) => ({
            ...currentMessage,
            content: currentMessage.content || failure,
            state: 'error',
          }))
        );
      } finally {
        if (readerRef.current !== null && activeRequestIdRef.current === requestId) {
          readerRef.current = null;
          if (streamingAssistantIdRef.current === assistantId) {
            streamingAssistantIdRef.current = null;
          }
        }
        setIsStreaming(false);
      }
    },
    [abort, auth]
  );

  return {
    abort,
    error,
    isStreaming,
    messages,
    sendMessage,
  };
}
