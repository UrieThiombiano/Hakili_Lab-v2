import { useQueryClient, type QueryKey } from "@tanstack/react-query"
import { elevesApi } from "@/lib/api"
import { useConfirm } from "@/hooks/useConfirm"
import { useToast } from "@/hooks/useToast"

/** Suppression d'un document stocké d'une copie (scan, rapport, sujet…),
 * après confirmation — la copie et sa note restent. Rafraîchit les requêtes
 * `aRafraichir` une fois le document retiré du serveur. Partagé par la page
 * de correction, le parcours et le profil élève. */
export function useSupprimerDocument(aRafraichir: QueryKey[]) {
  const queryClient = useQueryClient()
  const { confirmer } = useConfirm()
  const { notifier } = useToast()

  return async (jetonCopie: string, docType: string, titre: string) => {
    const ok = await confirmer({
      titre: `Supprimer « ${titre} » ?`,
      message: "Le fichier sera définitivement supprimé du serveur. La copie et sa note sont conservées.",
      texteConfirmer: "Supprimer",
    })
    if (!ok) return
    try {
      await elevesApi.supprimerDocument(jetonCopie, docType)
      notifier("Document supprimé.")
      await Promise.all(aRafraichir.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
    } catch {
      notifier("Suppression impossible.", "erreur")
    }
  }
}
