import { useEffect, useRef, useState } from 'react'

type CropEvidence = { page: number; bbox: [number, number, number, number] }

export function SourceCrop({ evidence, documentUrl }: { evidence: CropEvidence; documentUrl: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    setReady(false); setFailed(false)
    if (evidence.page !== 1) return
    const image = new Image()
    image.onload = () => {
      if (cancelled || !canvas.current) return
      const [x, y, right, bottom] = evidence.bbox
      const width = right - x; const height = bottom - y
      if (width <= 0 || height <= 0) return
      canvas.current.width = width; canvas.current.height = height
      canvas.current.getContext('2d')?.drawImage(image, x, y, width, height, 0, 0, width, height)
      setReady(true)
    }
    image.onerror = () => { if (!cancelled) setFailed(true) }
    image.src = documentUrl
    return () => { cancelled = true }
  }, [documentUrl, evidence.page, evidence.bbox.join(',')])
  return (
    <div className="source-crop">
      <strong>Source crop</strong>
      <canvas ref={canvas} hidden={!ready} aria-label="Selected source evidence crop" />
      {!ready && <span>{failed ? 'The source image could not be loaded for this crop.' : 'Loading source crop…'}</span>}
      <span>Page {evidence.page} · x{evidence.bbox[0]}–{evidence.bbox[2]}, y{evidence.bbox[1]}–{evidence.bbox[3]}</span>
    </div>
  )
}
