'use client';

import { useEffect, useReducer, useState } from 'react';
import type { PriceMap } from '@/types/api';
import { initialPriceState, priceReducer } from '@/lib/sseReducer';

export type ConnectionStatus = 'connecting' | 'open' | 'closed';

export function usePriceStream(url = '/api/stream/prices') {
  const [state, dispatch] = useReducer(priceReducer, initialPriceState);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');

  useEffect(() => {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return;
    }
    const es = new EventSource(url);
    setStatus('connecting');

    es.onopen = () => setStatus('open');
    es.onerror = () => {
      // EventSource auto-reconnects; reflect the transitional state.
      if (es.readyState === EventSource.CLOSED) {
        setStatus('closed');
      } else {
        setStatus('connecting');
      }
    };
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data) as PriceMap;
        dispatch({ type: 'sse', payload });
      } catch (err) {
        // Malformed payload — ignore.
        console.warn('SSE parse failed', err);
      }
    };

    return () => {
      es.close();
    };
  }, [url]);

  return { ...state, status };
}
