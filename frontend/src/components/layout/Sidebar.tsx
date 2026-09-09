import { NavLink, useNavigate } from "react-router-dom"
import { cn } from "@/lib/utils"
import { Info, FileStack, Route as RouteIcon, BookOpen, ShieldCheck, Settings, X, ChevronsLeft, ChevronsRight, LogOut } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"

const LIENS = [
  { to: "/", label: "À propos", icon: Info, exact: true },
  { to: "/analyse-de-copie", label: "Analyse de copie", icon: FileStack },
  { to: "/parcours", label: "Parcours", icon: RouteIcon },
  { to: "/sujets", label: "Sujets tests", icon: BookOpen },
]

/** Visible seulement casquette administrateur — miroir de
 * `templates_django/base.html` (`{% if casquette == 'administrateur' %}`). */
const LIEN_ADMIN = { to: "/administration", label: "Administration", icon: ShieldCheck, exact: false }

const LIEN_PARAMETRES = { to: "/parametres", label: "Paramètres", icon: Settings, exact: false }

export function Sidebar({
  ouvert,
  fermer,
  reduite,
  basculerReduite,
}: {
  ouvert: boolean
  fermer: () => void
  reduite: boolean
  basculerReduite: () => void
}) {
  const { logout, casquette } = useAuth()
  const navigate = useNavigate()
  const liens = casquette === "administrateur"
    ? [...LIENS, LIEN_ADMIN, LIEN_PARAMETRES]
    : [...LIENS, LIEN_PARAMETRES]

  return (
    <>
      {ouvert && <div className="fixed inset-0 bg-black/30 z-40 lg:hidden" onClick={fermer} />}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 h-screen shrink-0 flex flex-col gap-4 overflow-y-auto overflow-x-hidden py-6 transition-[width,transform] duration-300",
          "bg-gradient-to-b from-marine/85 to-[#001636]/85 backdrop-blur-md border-r border-white/10 text-white",
          reduite ? "w-[76px]" : "w-[260px]",
          ouvert ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        <div className={cn("flex items-center px-5", reduite ? "justify-center px-0" : "justify-between")}>
          {reduite ? (
            <img src="/hakili_logo.png" alt="Maïya" className="size-9 rounded-full object-cover bg-white" />
          ) : (
            <span className="flex items-center gap-2.5 min-w-0">
              <img src="/hakili_logo.png" alt="Maïya" className="size-9 rounded-full object-cover bg-white shrink-0" />
              <span className="text-h3 font-bold tracking-tight leading-tight truncate">Prof. Maïya</span>
            </span>
          )}
          <button onClick={fermer} className="lg:hidden text-white/70 hover:text-white">
            <X className="size-5" />
          </button>
        </div>

        <nav className="flex flex-col gap-1 px-3 mt-2">
          {liens.map(({ to, label, icon: Icon, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              onClick={fermer}
              title={reduite ? label : undefined}
              className={({ isActive }) =>
                cn(
                  "relative flex items-center gap-3 rounded px-3 py-2.5 text-menu transition-all duration-150",
                  reduite && "justify-center px-0",
                  isActive
                    ? "bg-white/15 text-white font-medium before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-rond before:bg-orange"
                    : "text-white/70 hover:bg-white/10 hover:text-white",
                  !reduite && !isActive && "hover:translate-x-0.5",
                )
              }
            >
              <Icon className="size-5 shrink-0" />
              {!reduite && label}
            </NavLink>
          ))}
        </nav>

        <div className={cn("mt-auto flex flex-col gap-1 px-3", reduite && "items-center px-0")}>
          <button
            onClick={basculerReduite}
            title={reduite ? "Déplier le menu" : "Réduire le menu"}
            className={cn(
              "hidden lg:flex items-center gap-2 px-3 py-2 rounded text-petit text-white/60 hover:bg-white/10 hover:text-white transition-colors duration-150",
              reduite && "justify-center px-0",
            )}
          >
            {reduite ? <ChevronsRight className="size-4 shrink-0" /> : <ChevronsLeft className="size-4 shrink-0" />}
            {!reduite && "Réduire"}
          </button>

          <button
            onClick={async () => {
              await logout()
              navigate("/connexion")
            }}
            title="Déconnexion"
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded text-petit text-white/60 hover:bg-rouge-pale hover:text-rouge transition-colors duration-150",
              reduite && "justify-center px-0",
            )}
          >
            <LogOut className="size-4 shrink-0" />
            {!reduite && "Déconnexion"}
          </button>
        </div>
      </aside>
    </>
  )
}
