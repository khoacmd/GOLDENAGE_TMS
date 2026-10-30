import { useSyncExternalStore } from 'react'

import { getQueue, subscribe, type QueueEntry } from '../queue'

let snapshot: QueueEntry[] = getQueue()
subscribe(() => {
  snapshot = getQueue()
})

export function useQueue(): QueueEntry[] {
  return useSyncExternalStore(subscribe, () => snapshot)
}
