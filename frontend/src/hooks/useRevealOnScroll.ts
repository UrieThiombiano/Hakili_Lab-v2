import { useEffect, useRef, useState } from "react"

/** Fait apparaître un élément (fondu + léger glissement) la première fois qu'il
 * entre dans le viewport, plutôt qu'au montage — donne un défilement vivant sur
 * les listes et grilles de cartes sans rien configurer par page. Se désactive
 * si l'utilisateur préfère moins d'animations (cohérent avec `prefers-reduced-motion`
 * déjà respecté par `.animate-entree-*` dans index.css). */
export function useRevealOnScroll<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -10% 0px" },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return { ref, visible }
}
