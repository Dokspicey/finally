import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage } from '@/components/ChatMessage';
import type { ChatMessage as ChatMessageType } from '@/types/api';

function msg(over: Partial<ChatMessageType>): ChatMessageType {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'hello',
    created_at: '2026-05-18T00:00:00Z',
    ...over,
  };
}

describe('ChatMessage', () => {
  it('renders plain assistant content', () => {
    render(<ChatMessage message={msg({ content: 'how can I help?' })} />);
    expect(screen.getByText('how can I help?')).toBeInTheDocument();
  });

  it('renders user messages with the user role testid', () => {
    render(<ChatMessage message={msg({ role: 'user', content: 'buy 1 AAPL' })} />);
    expect(screen.getByTestId('chat-message-user')).toBeInTheDocument();
  });

  it('renders a successful trade action with checkmark', () => {
    render(
      <ChatMessage
        message={msg({
          action_results: [
            { kind: 'trade', success: true, note: 'filled', ticker: 'AAPL', side: 'buy', quantity: 10 },
          ],
        })}
      />,
    );
    const line = screen.getByTestId('chat-action-ok');
    expect(line.textContent).toMatch(/Bought/);
    expect(line.textContent).toMatch(/AAPL/);
    expect(line.textContent).toMatch(/10/);
    expect(line.textContent?.startsWith('✓')).toBe(true);
  });

  it('renders a failed trade action with reason', () => {
    render(
      <ChatMessage
        message={msg({
          action_results: [
            {
              kind: 'trade',
              success: false,
              note: 'insufficient cash',
              ticker: 'AAPL',
              side: 'buy',
              quantity: 50,
            },
          ],
        })}
      />,
    );
    const line = screen.getByTestId('chat-action-fail');
    expect(line.textContent).toMatch(/Tried to buy/);
    expect(line.textContent).toMatch(/insufficient cash/);
    expect(line.textContent?.startsWith('✗')).toBe(true);
  });

  it('renders watchlist add success', () => {
    render(
      <ChatMessage
        message={msg({
          action_results: [
            { kind: 'watchlist', success: true, note: 'added', ticker: 'PYPL', action: 'add' },
          ],
        })}
      />,
    );
    expect(screen.getByTestId('chat-action-ok').textContent).toMatch(/Added.*PYPL/);
  });

  it('omits the action list when no actions provided', () => {
    render(<ChatMessage message={msg({ content: 'no actions' })} />);
    expect(screen.queryByTestId('chat-action-ok')).toBeNull();
    expect(screen.queryByTestId('chat-action-fail')).toBeNull();
  });
});
