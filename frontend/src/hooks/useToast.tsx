import { createContext, useCallback, useContext, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { CheckCircle2, XCircle, X } from "lucide-react"

interface Toast {
  id: number
  message: string
  type: "succes" | "erreur"
}

interface ToastState {
  notifier: (message: string, type?: Toast["type"]) => void
}

const ToastContext = createContext<ToastState | null>(null)

let compteur = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const notifier = useCallback((message: string, type: Toast["type"] = "succes") => {
    const id = ++compteur
    setToasts((t) => [...t, { id, message, type }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000)
  }, [])

  return (
    <ToastContext.Provider value={{ notifier }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "flex items-start gap-2 rounded-lg border p-3 shadow-haute text-menu bg-surface animate-entree-toast",
              t.type === "succes" ? "border-vert-pale" : "border-rouge-pale",
            )}
          >
            {t.type === "succes" ? <CheckCircle2 className="size-5 text-vert shrink-0" /> : <XCircle className="size-5 text-rouge shrink-0" />}
            <span className="flex-1">{t.message}</span>
            <button onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))} className="text-texte-faible hover:text-texte">
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastState {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error("useToast doit être utilisé sous <ToastProvider>")
  return ctx
}
