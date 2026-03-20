import { useState, useRef, useLayoutEffect, useEffect } from 'react'
import { createPortal } from 'react-dom'

const GAP = 8
const HIDE_MS = 150
const DEFAULT_MAX_W = 520
const DEFAULT_MAX_H = 360

/**
 * 鼠标悬停在子元素上时，在视口内以浮层展示全文；移开触发区或浮层后消失。
 * 使用 Portal 避免被表格 overflow 裁剪。
 */
export default function HoverFullText({ fullText, children, className, style, disabled }) {
  const [open, setOpen] = useState(false)
  const popRef = useRef(null)
  const anchorRectRef = useRef(null)
  const hideTimerRef = useRef(null)

  const cancelHide = () => {
    if (hideTimerRef.current != null) {
      window.clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
  }

  const scheduleHide = () => {
    cancelHide()
    hideTimerRef.current = window.setTimeout(() => {
      setOpen(false)
      hideTimerRef.current = null
    }, HIDE_MS)
  }

  const handleAnchorEnter = (e) => {
    if (disabled) return
    const t = String(fullText ?? '').trim()
    if (!t) return
    anchorRectRef.current = e.currentTarget.getBoundingClientRect()
    cancelHide()
    setOpen(true)
  }

  const handlePopEnter = () => {
    cancelHide()
  }

  useLayoutEffect(() => {
    if (!open || !popRef.current || !anchorRectRef.current) return
    const pop = popRef.current
    const anchor = anchorRectRef.current
    const margin = 8
    const maxW = Math.min(DEFAULT_MAX_W, window.innerWidth - 2 * margin)
    const maxH = Math.min(DEFAULT_MAX_H, window.innerHeight - 2 * margin)
    pop.style.boxSizing = 'border-box'
    pop.style.width = `${maxW}px`
    pop.style.maxHeight = `${maxH}px`

    const ph = pop.getBoundingClientRect().height
    const pw = pop.getBoundingClientRect().width
    let top = anchor.bottom + GAP
    if (top + ph > window.innerHeight - margin) {
      top = anchor.top - ph - GAP
    }
    top = Math.max(margin, Math.min(top, window.innerHeight - ph - margin))

    let left = anchor.left
    if (left + pw > window.innerWidth - margin) {
      left = window.innerWidth - pw - margin
    }
    left = Math.max(margin, left)

    pop.style.position = 'fixed'
    pop.style.top = `${top}px`
    pop.style.left = `${left}px`
    pop.style.zIndex = '10050'
  }, [open, fullText])

  useEffect(() => {
    if (!open) return
    const onScroll = (e) => {
      const pop = popRef.current
      if (pop && e.target instanceof Node && pop.contains(e.target)) return
      setOpen(false)
    }
    const onResize = () => setOpen(false)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onResize)
    }
  }, [open])

  const text = String(fullText ?? '').trim()
  if (disabled || !text) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    )
  }

  return (
    <>
      <div
        className={className}
        style={style}
        onMouseEnter={handleAnchorEnter}
        onMouseLeave={scheduleHide}
      >
        {children}
      </div>
      {open &&
        createPortal(
          <div
            ref={popRef}
            role="tooltip"
            className="hover-fulltext-popover"
            onMouseEnter={handlePopEnter}
            onMouseLeave={scheduleHide}
          >
            {fullText}
          </div>,
          document.body,
        )}
    </>
  )
}
