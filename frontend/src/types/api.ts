export type Direction = 'up' | 'down' | 'flat';

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  direction: Direction;
}

export type PriceMap = Record<string, PriceUpdate>;

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  updated_at: string;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  positions: Position[];
}

export interface TradeRequest {
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
}

export interface Trade {
  id: string;
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResponse {
  trade: Trade;
  cash_balance: number;
  position: {
    ticker: string;
    quantity: number;
    avg_cost: number;
    updated_at: string;
  } | null;
}

export interface WatchlistEntry {
  ticker: string;
  added_at: string;
  price: number | null;
  previous_price: number | null;
  change: number | null;
  change_percent: number | null;
  direction: Direction | null;
}

export interface WatchlistResponse {
  watchlist: WatchlistEntry[];
}

export interface PortfolioSnapshot {
  id: string;
  total_value: number;
  recorded_at: string;
}

export interface PortfolioHistoryResponse {
  snapshots: PortfolioSnapshot[];
}

export interface TradesResponse {
  trades: Trade[];
}

export interface ActionResult {
  kind: 'trade' | 'watchlist';
  success: boolean;
  note: string;
  ticker?: string;
  side?: 'buy' | 'sell';
  quantity?: number;
  action?: 'add' | 'remove';
}

export interface ChatActions {
  trades?: Array<{ ticker: string; side: 'buy' | 'sell'; quantity: number }>;
  watchlist_changes?: Array<{ ticker: string; action: 'add' | 'remove' }>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  actions?: ChatActions | null;
  action_results?: ActionResult[] | null;
  created_at: string;
}

export interface ChatResponse {
  message: ChatMessage;
  action_results: ActionResult[];
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
}
