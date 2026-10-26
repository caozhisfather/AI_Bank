import test from 'node:test'
import assert from 'node:assert/strict'
import { readWorkflowStream } from '../frontend/src/utils/workflowStream.js'

function streamChunks(text, size = 1) {
  const bytes = new TextEncoder().encode(text)
  return new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += size) controller.enqueue(bytes.slice(i, i + size))
    controller.close()
  } })
}

test('reads split UTF-8 progress and completion without inventing events', async () => {
  const events = [{ type: 'stage', stage: 'data', status: 'completed', label: '后台数据' }, { type: 'completed' }]
  const received = []
  await readWorkflowStream(streamChunks('\n' + events.map(event => JSON.stringify(event)).join('\n') + '\n'), event => received.push(event))
  assert.deepEqual(received, events)
})

test('a backend error is propagated and cannot become success', async () => {
  await assert.rejects(readWorkflowStream(streamChunks('{"type":"error","message":"计算失败"}\n'), () => {}), /计算失败/)
})

test('a truncated stream is not reported as completed', async () => {
  await assert.rejects(readWorkflowStream(streamChunks('{"type":"stage","status":"running"}\n'), () => {}), /中断/)
})
