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
