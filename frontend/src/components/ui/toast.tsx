"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle, XCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  message: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastProps extends ToastItem {
  onDismiss: (id: string) => void;
}

const variantConfig: Record<ToastVariant, { icon: React.ReactNode; className: string }> = {
  success: {
    icon: <CheckCircle className="h-5 w-5 text-green-500 shrink-0" />,
    className: "border-green-100 bg-white",
  },
  error: {
    icon: <XCircle className="h-5 w-5 text-red-500 shrink-0" />,
    className: "border-red-100 bg-white",
  },
  info: {
    icon: <Info className="h-5 w-5 text-primary shrink-0" />,
    className: "border-blue-100 bg-white",
  },
};

const Toast = React.forwardRef<HTMLDivElement, ToastProps>(
  ({ id, message, variant = "info", duration = 5000, onDismiss }, ref) => {
    const config = variantConfig[variant];

    React.useEffect(() => {
      const timer = setTimeout(() => onDismiss(id), duration);
      return () => clearTimeout(timer);
    }, [id, duration, onDismiss]);

    return (
      <motion.div
        ref={ref}
        layout
        initial={{ opacity: 0, x: 64, scale: 0.95 }}
        animate={{ opacity: 1, x: 0, scale: 1 }}
        exit={{ opacity: 0, x: 64, scale: 0.95 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className={cn(
          "flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg w-80 max-w-sm",
          config.className
        )}
      >
        {config.icon}
        <p className="flex-1 text-sm text-text-primary leading-snug">{message}</p>
        <button
          onClick={() => onDismiss(id)}
          className="shrink-0 rounded-md p-0.5 text-text-secondary hover:text-text-primary hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </motion.div>
    );
  }
);
Toast.displayName = "Toast";

// ─── Toast Container ─────────────────────────────────────────────────────────

interface ToastContainerProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

const ToastContainer = ({ toasts, onDismiss }: ToastContainerProps) => {
  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="sync">
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto">
            <Toast {...toast} onDismiss={onDismiss} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
};
ToastContainer.displayName = "ToastContainer";

// ─── useToast hook ────────────────────────────────────────────────────────────

export function useToast() {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);

  const dismiss = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback(
    (message: string, variant: ToastVariant = "info", duration = 5000) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [...prev, { id, message, variant, duration }]);
    },
    []
  );

  return { toasts, toast, dismiss, ToastContainer };
}

export { Toast, ToastContainer };
