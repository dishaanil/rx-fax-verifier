import { useEffect, useState } from 'react'
import { getPrescription, getPrescriptions, intakePrescription } from './api/prescriptions'
import { callInProgress, fieldValue } from './lib/review'
import { IntakeQueuePage } from './pages/IntakeQueuePage'
import { PrescriptionReviewPage } from './pages/PrescriptionReviewPage'
import type { Prescription } from './types/prescription'
import brandIcon from './assets/rxbridge-icon.png'

// Each prescription has its own address (#/rx/<id>), so links and the browser's back button work.
const routeId = () => decodeURIComponent(window.location.hash.match(/^#\/rx\/(.+)$/)?.[1] ?? '') || null
const go = (id: string | null) => { window.location.hash = id ? `#/rx/${encodeURIComponent(id)}` : '#/' }

export default function App() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([])
  const [active, setActive] = useState<Prescription | null>(null)
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState<Prescription | null>(null)  // a fax read while the pharmacist was elsewhere

  useEffect(() => {
    getPrescriptions().then(({ data, live }) => { setPrescriptions(data); setLive(live) }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [])

  function update(item: Prescription) {
    setActive(item)
    setPrescriptions((old) => [item, ...old.filter((p) => p.prescription_id !== item.prescription_id)])
  }

  useEffect(() => {
    if (loading) return
    async function show() {
      const id = routeId()
      setError(null)
      if (!id) { setActive(null); return }
      try { setActive(live ? await getPrescription(id) : prescriptions.find((p) => p.prescription_id === id) ?? null) }
      catch (e) { setError(e instanceof Error ? e.message : 'Unable to open prescription.'); go(null) }
    }
    void show()
    window.addEventListener('hashchange', show)
    return () => window.removeEventListener('hashchange', show)
  }, [loading, live])

  useEffect(() => { if (ready && active?.prescription_id === ready.prescription_id) setReady(null) }, [active, ready])

  // Poll while the fax is being read or a prescriber call is in progress.
  const waiting = active?.status === 'PROCESSING' || callInProgress(active)
  useEffect(() => {
    if (!live || !waiting) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await getPrescription(active!.prescription_id)
        if (cancelled) return
        update(next)
        if (next.status === 'PROCESSING' || callInProgress(next)) timer = setTimeout(poll, 2000)
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to refresh processing status.') }
    }
    timer = setTimeout(poll, 2000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [active?.prescription_id, waiting, live])

  async function upload(file: File) {
    setBusy(true); setError(null)
    try {
      const item = await intakePrescription(file)
      if (!live) setPrescriptions([])
      setLive(true)
      // Reading takes a while; only open the new fax if the pharmacist is still on the queue.
      if (routeId()) {
        setPrescriptions((old) => [item, ...old.filter((p) => p.prescription_id !== item.prescription_id)])
        setReady(item)
      } else { update(item); go(item.prescription_id) }
    } catch (e) { setError(e instanceof Error ? e.message : 'Upload failed.') }
    finally { setBusy(false) }
  }

  if (loading) return <main className="loading"><span className="spinner" aria-hidden="true" /> Loading prescriptions…</main>
  return <>
    <nav className="nav" aria-label="Main navigation">
      <a className="brand" href="#/"><img src={brandIcon} alt="" /><span>RxBridge</span></a>
      <span className={`connection${live ? ' connection--live' : ''}`}>{live ? 'Connected' : 'Preview'}</span>
    </nav>
    {error && <p className="banner banner--error page-banner" role="alert">{error}</p>}
    {ready && <p className="banner page-banner banner--action" role="status">
      <span>{(ready.fields.patient && fieldValue(ready.fields.patient)) ?? 'A new'} fax has been read.</span>
      <button type="button" className="link-button" onClick={() => { go(ready.prescription_id); setReady(null) }}>Open</button>
      <button type="button" className="link-button" onClick={() => setReady(null)}>Dismiss</button>
    </p>}
    {active ? <PrescriptionReviewPage key={active.prescription_id} prescription={active} apiReady={live} onRefresh={update} onBack={() => go(null)} />
      : <IntakeQueuePage prescriptions={prescriptions} onOpen={go} onUpload={upload} busy={busy} live={live} />}
  </>
}
