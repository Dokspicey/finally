'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { ChatMessage as ChatMessageType } from '@/types/api';
import { ChatMessage } from './ChatMessage';

interface Props {
  onActionsExecuted: () => void;
}

export function ChatPanel({ onActionsExecuted }: Props) {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.chatHistory(50);
        if (!cancelled) setMessages(res.messages);
      } catch {
        // History endpoint may not exist yet — chat panel still works for new turns.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    const userMsg: ChatMessageType = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput('');
    setBusy(true);
    setError(null);
    try {
      const res = await api.chat(text);
      const assistant: ChatMessageType = {
        ...res.message,
        action_results: res.action_results,
      };
      setMessages((m) => [...m, assistant]);
      if (res.action_results.some((r) => r.success)) {
        onActionsExecuted();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'chat failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>FinAlly Assistant</span>
        <span className="text-flat normal-case tracking-normal">{messages.length} msgs</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.length === 0 && (
          <div className="text-sm text-flat text-center py-8 leading-relaxed">
            Ask about your portfolio or place a trade.
            <br />
            <span className="text-xs">Try: "buy 1 AAPL" or "what's my exposure?"</span>
          </div>
        )}
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        {busy && (
          <div className="flex justify-start" data-testid="chat-loading">
            <div className="bg-bg-elevated border border-border-subtle rounded-lg px-3 py-2 text-sm text-flat">
              <span className="inline-block animate-pulse">FinAlly is thinking…</span>
            </div>
          </div>
        )}
      </div>
      {error && (
        <div className="px-3 py-1 text-xs text-down border-t border-border-subtle">{error}</div>
      )}
      <form onSubmit={submit} className="flex gap-2 px-3 py-3 border-t border-border-subtle">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message FinAlly…"
          disabled={busy}
          aria-label="Chat message"
          className="flex-1 bg-bg-base border border-border-subtle rounded px-2 py-1.5 text-sm focus:outline-none focus:border-primary"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="bg-submit hover:bg-submit/85 text-white font-semibold px-4 py-1.5 rounded disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </form>
    </div>
  );
}
