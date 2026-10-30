import type { ReactNode } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native'

export const colors = { primary: '#1677ff', danger: '#cf1322', success: '#389e0d', muted: '#8c8c8c', border: '#e5e5e5' }

export function Button({
  title,
  onPress,
  kind = 'primary',
  disabled,
  loading,
  style,
}: {
  title: string
  onPress: () => void
  kind?: 'primary' | 'danger' | 'success' | 'outline'
  disabled?: boolean
  loading?: boolean
  style?: ViewStyle
}) {
  const bg = kind === 'outline' ? '#fff' : colors[kind === 'primary' ? 'primary' : kind]
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={[styles.button, { backgroundColor: bg, opacity: disabled ? 0.5 : 1 }, kind === 'outline' && styles.outline, style]}
    >
      {loading ? (
        <ActivityIndicator color={kind === 'outline' ? colors.primary : '#fff'} />
      ) : (
        <Text style={[styles.buttonText, kind === 'outline' && { color: colors.primary }]}>{title}</Text>
      )}
    </Pressable>
  )
}

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={{ color, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  )
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>
}

export function Header({ title, onBack, right }: { title: string; onBack?: () => void; right?: ReactNode }) {
  return (
    <View style={styles.header}>
      {onBack && (
        <Pressable onPress={onBack} hitSlop={12} style={{ marginRight: 12 }}>
          <Text style={{ fontSize: 22, color: colors.primary }}>‹</Text>
        </Pressable>
      )}
      <Text style={styles.headerTitle} numberOfLines={1}>
        {title}
      </Text>
      {right}
    </View>
  )
}

const styles = StyleSheet.create({
  button: { borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center' },
  outline: { borderWidth: 1, borderColor: colors.primary },
  buttonText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  badge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2, alignSelf: 'flex-start' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, marginHorizontal: 12, marginTop: 10, gap: 6 },
  header: {
    paddingTop: 48,
    paddingBottom: 12,
    paddingHorizontal: 16,
    backgroundColor: '#fff',
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '600' },
})
