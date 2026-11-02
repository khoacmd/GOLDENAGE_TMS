export function StatusTag({ label, color }: { label: string; color: string }) {
  return (
    <span className="tag" style={{ color, borderColor: color }}>
      {label}
    </span>
  )
}
