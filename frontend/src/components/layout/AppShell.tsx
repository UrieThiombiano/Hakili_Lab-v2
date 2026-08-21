import { useState, type ReactNode } from "react"
import { Sidebar } from "./Sidebar"
import { Topbar } from "./Topbar"
import { cn } from "@/lib/utils"

const CLE_REDUITE = "hakili_sidebar_reduite"

function lireReduite() {
  try {
    return localStorage.getItem(CLE_REDUITE) === "1"
  } catch {
    return false
  }
}

export function AppShell({
  children,
  titre,
}: {
  children: ReactNode
  titre?: string
}) {
  const [sidebarOuverte, setSidebarOuverte] = useState(false)
  const [sidebarReduite, setSidebarReduite] = useState(lireReduite)

  function basculerReduite() {
    setSidebarReduite((v) => {
      const next = !v
      try {
        localStorage.setItem(CLE_REDUITE, next ? "1" : "0")
      } catch {
        /* stockage indisponible (navigation privée…) — la préférence ne survit juste pas à un rechargement */
      }
      return next
    })
  }

  return (
    <div className="flex min-h-screen fond-cahier">
      <Sidebar
        ouvert={sidebarOuverte}
        fermer={() => setSidebarOuverte(false)}
        reduite={sidebarReduite}
        basculerReduite={basculerReduite}
      />
      <div
        className={cn(
          "flex-1 min-w-0 flex flex-col transition-[margin] duration-300 ease-out",
          sidebarReduite ? "lg:ml-[76px]" : "lg:ml-[260px]",
        )}
      >
        <Topbar ouvrirSidebar={() => setSidebarOuverte(true)} titre={titre} />
        <main className="flex-1 px-5 sm:px-8 py-6 w-full animate-entree-page">
          {children}
        </main>
      </div>
    </div>
  )
}
