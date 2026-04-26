import { toast as sonnerToast } from 'sonner';

// Re-export sonner functions with compatible API
export const toast = {
  success: (message: string, duration?: number) =>
    sonnerToast.success(message, { duration: duration || 3000 }),
  error: (message: string, duration?: number) =>
    sonnerToast.error(message, { duration: duration || 5000 }),
  warning: (message: string, duration?: number) =>
    sonnerToast.warning(message, { duration: duration || 4000 }),
  info: (message: string, duration?: number) =>
    sonnerToast.info(message, { duration: duration || 3000 }),
  loading: (message: string) => sonnerToast.loading(message),
};

export function useToast() {
  return toast;
}

// Keep ToastContainer export for backwards compatibility but it's no-op with sonner
export function ToastContainer() {
  return null;
}
