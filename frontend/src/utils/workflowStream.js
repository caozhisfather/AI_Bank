export async function readWorkflowStream(body, onEvent) {
  if (!body) throw new Error('浏览器未能接收计算进度，请重新运行')
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  const dispatch = line => {
    if (!line.trim()) return
    const event = JSON.parse(line)
    onEvent(event)
    if (event.type === 'error') throw new Error(event.message || '计算失败')
    if (event.type === 'completed') completed = true
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let newline
      while ((newline = buffer.indexOf('\n')) >= 0) {
        dispatch(buffer.slice(0, newline))
        buffer = buffer.slice(newline + 1)
      }
    }
    buffer += decoder.decode()
    dispatch(buffer)
    if (!completed) throw new Error('计算连接已中断，未收到完成结果，请重新运行')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
