import { useEffect, useState } from 'react'
import { getPrescription, getPrescriptions, intakePrescription } from './api/prescriptions'
import { IntakeQueuePage } from './pages/IntakeQueuePage'
import { PrescriptionReviewPage } from './pages/PrescriptionReviewPage'
import type { Prescription } from './types/prescription'
import brandIcon from './assets/rxbridge-icon.png'
export default function App() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([])
  const [active, setActive] = useState<Prescription | null>(null)
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    getPrescriptions().then(({ data, live }) => { setPrescriptions(data); setLive(live) }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [])
  function update(item: Prescription) {
    setActive(item)
    setPrescriptions((old) => [item, ...old.filter((p) => p.prescription_id !== item.prescription_id)])
  }
  useEffect(() => {
    if (!live || active?.status !== 'PROCESSING') return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await getPrescription(active!.prescription_id)
        if (cancelled) return
        update(next)
        if (next.status === 'PROCESSING') timer = setTimeout(poll, 2000)
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to refresh processing status.') }
    }
    timer = setTimeout(poll, 2000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [active?.prescription_id, active?.status, live])
  async function upload(file: File) {
    setBusy(true); setError(null); setNotice('Uploading prescription and extracting fields…')
    try {
      const item = await intakePrescription(file)
      if (!live) setPrescriptions([])
      setLive(true); update(item)
      setNotice(item.status === 'PROCESSING' ? 'Upload received. Extraction is processing…' : 'Prescription uploaded. Extracted result is ready to review.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Upload failed.'); setNotice(null) }
    finally { setBusy(false) }
  }
  async function open(id: string) {
    setError(null)
    try { setActive(live ? await getPrescription(id) : prescriptions.find((p) => p.prescription_id === id) ?? null) }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to open prescription.') }
  }
  if (loading) return <main className="loading">Loading prescriptions…</main>
  return <>
    <nav className="app-nav" aria-label="Main navigation"><button type="button" className="brand" onClick={() => { setActive(null); setNotice(null) }}><span className="brand-icon"><img src={brandIcon} alt="" /></span><span>RxBridge</span></button><span className="nav-caption">Evidence first. Pharmacist approved.</span><span className={`connection-label${live ? ' connection-label--live' : ''}`}>{live ? 'Service connected' : 'Preview workspace'}</span></nav>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {notice && <p className="notice-banner" role="status">{notice}</p>}
    {active ? <PrescriptionReviewPage key={active.prescription_id} prescription={active} apiReady={live} onRefresh={update} onBack={() => { setActive(null); setNotice(null) }} />
      : <IntakeQueuePage prescriptions={prescriptions} onOpen={open} onUpload={upload} busy={busy} live={live} />}
  </>
}
