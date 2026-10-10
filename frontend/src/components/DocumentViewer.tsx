import type { Evidence } from '../types/prescription'
import { useEffect, useRef, useState } from 'react'

export function DocumentViewer({ documentPath, evidence }: { documentPath: string; evidence?: Evidence | null }) {
  const [failed, setFailed] = useState(false)
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragStart = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)

  useEffect(() => {
    setFailed(false); setSize(null); setZoom(1); setPan({ x: 0, y: 0 })
  }, [documentPath])

  function beginPan(event: React.PointerEvent<HTMLDivElement>) {
    if (zoom === 1) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragStart.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y }
  }

  function movePan(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart.current) return
    setPan({ x: dragStart.current.panX + event.clientX - dragStart.current.x, y: dragStart.current.panY + event.clientY - dragStart.current.y })
  }

  function endPan() { dragStart.current = null }

  return (
    <section className="panel document-viewer">
      <div className="panel__heading"><span>Original fax</span><small>Source evidence</small></div>
      {failed ? <div className="document-placeholder"><strong>Source image unavailable</strong><p>The prescription service must serve the original image.</p></div> :
        <>
          <div className={`document-image-viewport${zoom > 1 ? ' document-image-viewport--zoomed' : ''}`} onPointerDown={beginPan} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan}>
            <div className="document-image" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
              <img src={documentPath} alt="Original prescription fax" draggable={false} onError={() => setFailed(true)} onLoad={(event) => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
              {size && evidence?.bbox && (evidence.page ?? 1) === 1 && <div className="evidence-highlight" aria-label="Highlighted selected evidence" style={{ left: `${100 * evidence.bbox[0] / size.width}%`, top: `${100 * evidence.bbox[1] / size.height}%`, width: `${100 * (evidence.bbox[2] - evidence.bbox[0]) / size.width}%`, height: `${100 * (evidence.bbox[3] - evidence.bbox[1]) / size.height}%` }} />}
            </div>
          </div>
          <div className="document-controls" aria-label="Document zoom controls">
            <button type="button" onClick={() => setZoom((value) => Math.max(1, Number((value - 0.25).toFixed(2))))} disabled={zoom === 1}>−</button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => setZoom((value) => Math.min(3, Number((value + 0.25).toFixed(2))))} disabled={zoom === 3}>+</button>
            <button type="button" className="button--quiet" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} disabled={zoom === 1 && pan.x === 0 && pan.y === 0}>Reset view</button>
          </div>
        </>}
      {evidence?.bbox && <p className="evidence-note">Selected evidence: page {evidence.page ?? 1} · region {evidence.bbox.join(', ')}</p>}
    </section>
  )
}
