export const MIN_GRAPH_ZOOM = 0.4
export const MAX_GRAPH_ZOOM = 4

// Preserve the graph point under the cursor when its displayed scale changes.
export function zoomGraphAt(viewport, requestedScale, anchor) {
  const scale = Math.min(MAX_GRAPH_ZOOM, Math.max(MIN_GRAPH_ZOOM, requestedScale))
  const ratio = scale / viewport.scale
  return {
    scale,
    x: anchor.x - (anchor.x - viewport.x) * ratio,
    y: anchor.y - (anchor.y - viewport.y) * ratio
  }
}
