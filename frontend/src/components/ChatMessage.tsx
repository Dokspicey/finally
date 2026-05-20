'use client';

import type { ActionResult, ChatMessage as ChatMessageType } from '@/types/api';
import { formatQty } from '@/lib/format';

interface Props {
  message: ChatMessageType;
}

function describeResult(r: ActionResult): string {
  if (r.kind === 'trade') {
    const side = r.side ?? 'trade';
    const qty = r.quantity != null ? formatQty(r.quantity) : '';
    const verb = side === 'buy' ? (r.success ? 'Bought' : 'Tried to buy') : r.success ? 'Sold' : 'Tried to sell';
    const tail = r.success ? '' : ` — ${r.note}`;
    return `${verb} ${qty} ${r.ticker ?? ''}${tail}`.trim();
  }
  if (r.kind === 'watchlist') {
    const verb =
      r.action === 'add'
        ? r.success
          ? 'Added'
          : 'Tried to add'
        : r.success
        ? 'Removed'
        : 'Tried to remove';
    const tail = r.success ? '' : ` — ${r.note}`;
    return `${verb} ${r.ticker ?? ''}${tail}`.trim();
  }
  return r.note;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user';
  const results = message.action_results ?? [];

  return (
    <div
      data-testid={`chat-message-${message.role}`}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-primary/20 border border-primary/40 text-zinc-100'
            : 'bg-bg-elevated border border-border-subtle text-zinc-100'
        }`}
      >
        <div>{message.content}</div>
        {results.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs font-mono">
            {results.map((r, i) => (
              <li
                key={i}
                className={r.success ? 'text-up' : 'text-down'}
                data-testid={`chat-action-${r.success ? 'ok' : 'fail'}`}
              >
                {r.success ? '✓' : '✗'} {describeResult(r)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
