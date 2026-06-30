import { useEffect, useRef, useState } from 'react'
import { Bot, MessageSquare, Send, Square } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { type ChatMessage, useAgentChat, useAgentsQuery } from '@/features/chat/api'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

function statusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'archived') return 'warning'
  if (status === 'disabled') return 'secondary'
  return 'success'
}

function MessageBubble({
  content,
  emphasis = 'normal',
  author,
}: {
  content: string
  emphasis?: 'error' | 'normal'
  author: 'assistant' | 'user'
}): JSX.Element {
  const bubbleClass =
    author === 'user'
      ? 'ml-auto bg-primary/15 text-foreground'
      : emphasis === 'error'
        ? 'mr-auto border border-destructive/30 bg-destructive/10 text-destructive'
        : 'mr-auto border border-border bg-card text-foreground'

  return (
    <article className={cn('max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm', bubbleClass)}>
      <p className="mb-1 font-semibold text-[10px] text-muted-foreground uppercase tracking-[0.2em]">{author}</p>
      <p className="whitespace-pre-wrap break-words">{content}</p>
    </article>
  )
}

export function ChatPage(): JSX.Element {
  const t = useT()
  const agents = useAgentsQuery()
  const { abort, error, isStreaming, messages, sendMessage } = useAgentChat()
  const [selectedAgent, setSelectedAgent] = useState<string | null>('')
  const [draft, setDraft] = useState('')
  const previousAgentRef = useRef<string | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!selectedAgent && agents.data && agents.data.length > 0) {
      setSelectedAgent(agents.data[0].agent_name)
    }
  }, [agents.data, selectedAgent])

  useEffect(() => {
    if (previousAgentRef.current && previousAgentRef.current !== selectedAgent) {
      abort()
    }
    previousAgentRef.current = selectedAgent || null
  }, [abort, selectedAgent])

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const canSend = Boolean(selectedAgent) && draft.trim().length > 0 && !isStreaming
  const showEmptyAgents = !agents.isLoading && (agents.data?.length ?? 0) === 0
  const activeAgent = (agents.data ?? []).find((agent) => agent.agent_name === selectedAgent)

  const onSubmit = async (): Promise<void> => {
    if (!selectedAgent || !draft.trim()) {
      return
    }
    const message = draft.trim()
    setDraft('')
    await sendMessage(selectedAgent, message)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      if (canSend) {
        void onSubmit()
      }
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('chat.title')}</h2>
          <Badge variant="secondary">{agents.data?.length ?? 0}</Badge>
        </div>
        {isStreaming ? <Badge variant="success">{t('chat.streaming')}</Badge> : null}
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="shadow-none lg:sticky lg:top-6 lg:self-start">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="size-4 text-primary" /> {t('chat.targetAgent')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="chat-agent">{t('chat.agent')}</Label>
              <SimpleSelect
                disabled={agents.isLoading || showEmptyAgents}
                onValueChange={setSelectedAgent}
                options={(agents.data ?? []).map((agent) => ({ value: agent.agent_name, label: agent.agent_name }))}
                placeholder={t('chat.selectAgent')}
                triggerId="chat-agent"
                value={selectedAgent}
              />
            </div>

            {agents.isLoading ? <p className="text-muted-foreground text-sm">{t('chat.loadingAgents')}</p> : null}
            {showEmptyAgents ? <p className="text-muted-foreground text-sm">{t('chat.noAgentsAvailable')}</p> : null}

            <div className="rounded-lg border border-border bg-secondary/30 p-4 text-sm">
              {activeAgent ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  {t('chat.status')}
                  <Badge variant={statusVariant(activeAgent.status)}>{activeAgent.status}</Badge>
                </span>
              ) : (
                <span className="text-muted-foreground">{t('chat.selectAvailableAgent')}</span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="flex flex-col shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="size-4 text-primary" /> {t('chat.transcript')}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-4">
            <div
              className="flex min-h-[320px] flex-1 flex-col gap-3 overflow-y-auto rounded-xl bg-secondary/30 p-4"
              data-testid="chat-transcript"
            >
              {messages.length === 0 ? (
                <p className="m-auto text-muted-foreground text-sm">{t('chat.noMessagesYet')}</p>
              ) : (
                messages.map((message: ChatMessage) => (
                  <div
                    className={cn('flex flex-col gap-2', message.role === 'user' ? 'items-end' : 'items-start')}
                    key={message.id}
                  >
                    <MessageBubble
                      author={message.role}
                      content={message.content}
                      emphasis={message.state === 'error' ? 'error' : 'normal'}
                    />
                    {message.role === 'assistant' && message.state === 'error' && error && error !== message.content ? (
                      <MessageBubble author="assistant" content={error} emphasis="error" />
                    ) : null}
                  </div>
                ))
              )}
              <div ref={transcriptEndRef} />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="chat-message">{t('chat.message')}</Label>
              <Textarea
                className="min-h-28"
                disabled={showEmptyAgents}
                id="chat-message"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
                placeholder={t('chat.messagePlaceholder')}
                value={draft}
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <p className="text-muted-foreground text-sm">
                {isStreaming ? t('chat.streamingResponse') : t('chat.readyToSend')}
              </p>
              <div className="flex items-center gap-2">
                {isStreaming ? (
                  <Button onClick={() => abort()} variant="outline">
                    <Square className="size-4" /> {t('chat.stop')}
                  </Button>
                ) : null}
                <Button disabled={!canSend} onClick={() => void onSubmit()}>
                  <Send className="size-4" /> {t('chat.send')}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
