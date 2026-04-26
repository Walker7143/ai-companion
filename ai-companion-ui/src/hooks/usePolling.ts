import { useEffect, useRef, useCallback } from 'react';

interface UsePollingOptions {
  interval: number;
  enabled?: boolean;
  onPoll: () => void | Promise<void>;
}

export function usePolling({ interval, enabled = true, onPoll }: UsePollingOptions) {
  const savedCallback = useRef(onPoll);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    savedCallback.current = onPoll;
  }, [onPoll]);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const start = useCallback(() => {
    stop();
    if (enabled) {
      savedCallback.current();
      intervalRef.current = window.setInterval(() => {
        savedCallback.current();
      }, interval);
    }
  }, [enabled, interval, stop]);

  useEffect(() => {
    // Handle visibility change
    const handleVisibilityChange = () => {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    start();

    return () => {
      stop();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled, interval, onPoll, start, stop]);

  return { start, stop };
}
