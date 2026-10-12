import { useCallback, useEffect, useRef, useState } from 'react'

// Run an async action on demand and track its loading/result/error state.
export function useAction(fn) {
  const [state, setState] = useState({ loading: false, data: null, error: null })
  const fnRef = useRef(fn)
  useEffect(() => { fnRef.current = fn })
  const run = useCallback(async (...args) => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fnRef.current(...args)
      setState({ loading: false, data, error: null })
      return data
    } catch (e) {
      setState({ loading: false, data: null, error: String(e) })
      return null
    }
  }, [])
  return [run, state]
}

// Poll an async fetcher while the component is mounted.
export function usePolling(fn, ms, deps = []) {
  const [data, setData] = useState(null)
  const fnRef = useRef(fn)
  useEffect(() => { fnRef.current = fn })
  const refresh = useCallback(async () => {
    try {
      setData(await fnRef.current())
    } catch {
      // gateway unreachable — keep the last known data on screen
    }
  }, [])
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, ms)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps])
  return [data, refresh]
}

// Compare two vector clocks: 'before' | 'after' | 'equal' | 'concurrent'
export function compareVC(a = {}, b = {}) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  let aLeB = true
  let bLeA = true
  keys.forEach((k) => {
    if ((a[k] || 0) > (b[k] || 0)) aLeB = false
    if ((b[k] || 0) > (a[k] || 0)) bLeA = false
  })
  if (aLeB && bLeA) return 'equal'
  if (aLeB) return 'before'
  if (bLeA) return 'after'
  return 'concurrent'
}

export function fmtVC(vc = {}) {
  return Object.entries(vc)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k.replace('ZONE_', 'Z').replace('COORD_', 'C')}:${v}`)
    .join(' ')
}

export function fmtClock(epochSeconds) {
  if (epochSeconds == null) return '—'
  const d = new Date(epochSeconds * 1000)
  return d.toLocaleTimeString([], { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}
