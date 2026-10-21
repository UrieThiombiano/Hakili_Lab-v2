export function StatRow({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-6">{children}</div>
}

export function Stat({ label, value, unite }: { label: string; value: string | number; unite?: string }) {
  return (
    <div>
      <div className="text-chiffre font-bold text-marine leading-none">
        {value}
        {unite && <span className="text-h3 font-normal text-texte-doux ml-1">{unite}</span>}
      </div>
      <div className="text-petit text-texte-doux mt-1">{label}</div>
    </div>
  )
}
