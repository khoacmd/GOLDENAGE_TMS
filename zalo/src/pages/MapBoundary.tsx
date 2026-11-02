import { Component, type ReactNode } from 'react'
import { Text } from 'zmp-ui'

/** Bản đồ lỗi (WebGL, không tải được) không làm hỏng trang chi tiết đơn. */
export class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    console.warn('Bản đồ lỗi', error)
  }

  render() {
    if (this.state.failed) {
      return (
        <Text size="small" className="muted">
          Không hiển thị được bản đồ trên thiết bị này.
        </Text>
      )
    }
    return this.props.children
  }
}
