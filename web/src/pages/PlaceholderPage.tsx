import { Result } from 'antd'

export function PlaceholderPage({ title, milestone }: { title: string; milestone: string }) {
  return <Result status="info" title={title} subTitle={`Chức năng sẽ được phát triển ở ${milestone}.`} />
}
