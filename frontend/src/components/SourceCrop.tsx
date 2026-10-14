import { useEffect, useRef, useState } from 'react'

// Context around the evidence box, so the reviewer sees the neighbouring words too.
const MARGIN = 48

export function SourceCrop({ bbox, documentUrl }: { bbox: [number, number, number, number]; documentUrl: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  useEffect(() => {
    let cancelled = false
    setState('loading')
    const image = new Image()
    image.onload = () => {
      const target = canvas.current
      if (cancelled || !target) return
      const [x0, y0, x1, y1] = bbox
      const left = Math.max(0, x0 - MARGIN), top = Math.max(0, y0 - MARGIN)
      const width = Math.min(image.naturalWidth, x1 + MARGIN) - left
      const height = Math.min(image.naturalHeight, y1 + MARGIN) - top
      if (width <= 0 || height <= 0) { setState('failed'); return }
      target.width = width; target.height = height
      const context = target.getContext('2d')
      if (!context) return
      context.drawImage(image, left, top, width, height, 0, 0, width, height)
      context.strokeStyle = '#e8590c'; context.lineWidth = 3
      context.strokeRect(x0 - left - 4, y0 - top - 4, x1 - x0 + 8, y1 - y0 + 8)
      setState('ready')
    }
    image.onerror = () => { if (!cancelled) setState('failed') }
    image.src = documentUrl
    return () => { cancelled = true }
  }, [documentUrl, bbox.join(',')])
  return (
    <figure className="crop">
      <canvas ref={canvas} hidden={state !== 'ready'} aria-label="Close-up of the fax where this value is written" />
      {state !== 'ready' && <span className="crop__placeholder">{state === 'failed' ? 'Close-up unavailable' : 'Loading close-up…'}</span>}
    </figure>
  )
}
