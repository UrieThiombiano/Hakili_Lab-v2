import { useEffect, useState } from "react"

export function useDebounce<T>(valeur: T, delaiMs: number): T {
  const [debattue, setDebattue] = useState(valeur)
  useEffect(() => {
    const minuteur = setTimeout(() => setDebattue(valeur), delaiMs)
    return () => clearTimeout(minuteur)
  }, [valeur, delaiMs])
  return debattue
}
