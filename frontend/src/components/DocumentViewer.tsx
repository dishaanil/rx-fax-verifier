import type { Evidence } from '../types/prescription'
import { useEffect, useRef, useState } from 'react'

export function DocumentViewer({ documentPath, evidence, label }: { documentPath: string; evidence?: Evidence | null; label?: string }) {
  const [failed, setFailed] = useState(false)
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragStart = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)
  const highlight = useRef<HTMLDivElement>(null)
  const viewport = useRef<HTMLDivElement>(null)
  const bbox = size && evidence?.bbox && (evidence.page ?? 1) === 1 ? evidence.bbox : null

  useEffect(() => {
    setFailed(false); setSize(null); setZoom(1); setPan({ x: 0, y: 0 })
  }, [documentPath])

  // Bring the highlighted value into view inside the fax panel.
  useEffect(() => {
    const box = highlight.current, frame = viewport.current
    if (zoom === 1 && box && frame) frame.scrollTo({ top: box.offsetTop - frame.clientHeight / 2 + box.offsetHeight / 2, behavior: 'smooth' })
  }, [bbox?.join(','), zoom])

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
    <section className="card viewer" aria-label="Original fax">
      <header className="viewer__bar">
        <span className="viewer__title">Original fax{label && <small> · showing {label}</small>}</span>
        {!failed && <span className="viewer__zoom" aria-label="Zoom">
          <button type="button" className="icon-button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(1, value - 0.5))} disabled={zoom === 1}>−</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button type="button" className="icon-button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(3, value + 0.5))} disabled={zoom === 3}>+</button>
          {(zoom > 1 || pan.x !== 0 || pan.y !== 0) && <button type="button" className="link-button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}>Fit</button>}
        </span>}
      </header>
      {failed ? <div className="viewer__empty"><strong>Fax image unavailable</strong><p>The prescription service did not return the original image.</p></div> :
        <div ref={viewport} className={`viewer__viewport${zoom > 1 ? ' viewer__viewport--zoomed' : ''}`} onPointerDown={beginPan} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan}>
          <div className="viewer__page" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
            <img src={documentPath} alt="Original prescription fax" draggable={false} onError={() => setFailed(true)} onLoad={(event) => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
            {size && bbox && <div ref={highlight} className="viewer__highlight" aria-label={`Highlighted: ${label ?? 'selected value'}`} style={{ left: `${100 * bbox[0] / size.width}%`, top: `${100 * bbox[1] / size.height}%`, width: `${100 * (bbox[2] - bbox[0]) / size.width}%`, height: `${100 * (bbox[3] - bbox[1]) / size.height}%` }} />}
          </div>
        </div>}
    </section>
  )
}
