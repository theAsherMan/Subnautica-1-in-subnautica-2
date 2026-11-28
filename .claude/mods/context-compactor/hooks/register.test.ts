import { expect, test } from 'claude-code/testing'

// Hooks below stand for the engine. `tokens` is what $.session.usage() reports.
function engine(on: any, tokens: number, log: string[]) {
  on('session.usage', () => ({ value: { startedAt: 0, rateLimits: [], context: { tokens, window: 1_000_000 } } }))
  on('clock.after', () => ({ value: undefined }))
  on('session.compact', () => (log.push('compact'), { messages: [{ role: 'user', text: 'summary', toolUses: [] }] }))
  on('turn.abort', (_: unknown, e: any) => (log.push(`abort ${e.turnId}`), { value: undefined }))
  on('prompt.submit', (_: unknown, e: any) => (log.push(`submit ${e.text.slice(0, 20)}`), { text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.log', () => ({ value: undefined }))
}

const end = (over: object = {}) => ({
  answer: 'done', durationMs: 1, isAborted: false, turnId: 't1', reason: 'end_turn', ...over,
})

test('turn end over 150k compacts', async ($, on) => {
  const log: string[] = []
  engine(on, 160_000, log)
  await $.turn.complete(end() as any)
  await new Promise(r => setTimeout(r, 50))
  expect(log).toEqual(['compact'])
})

test('turn end under 150k does nothing', async ($, on) => {
  const log: string[] = []
  engine(on, 140_000, log)
  await $.turn.complete(end() as any)
  await new Promise(r => setTimeout(r, 50))
  expect(log).toEqual([])
})

test('a subagent turn end is ignored', async ($, on) => {
  const log: string[] = []
  engine(on, 400_000, log)
  await $.turn.complete(end({ agentId: 'a1' }) as any)
  await new Promise(r => setTimeout(r, 50))
  expect(log).toEqual([])
})

test('200k mid-turn ends the turn, compacts, then continues', async ($, on) => {
  const log: string[] = []
  engine(on, 205_000, log)
  on('turn.step', async function* (_: unknown, e: any) { return { turnId: e.turnId, index: e.index, answer: '', toolUses: [] } as any })
  const s = $.turn.step({ turnId: 't1', index: 3, model: 'opus', messageCount: 40 } as any); for await (const _ of s) void _
  await $.turn.complete(end({ isAborted: true, reason: 'aborted' }) as any)
  await new Promise(r => setTimeout(r, 50))
  expect(log).toEqual(['abort t1', 'compact', 'submit The context reached '])
})

test('a subagent at 200k mid-turn is left alone', async ($, on) => {
  const log: string[] = []
  engine(on, 300_000, log)
  on('turn.step', async function* (_: unknown, e: any) { return { turnId: e.turnId, index: e.index, answer: '', toolUses: [] } as any })
  const s = $.turn.step({ turnId: 't2', index: 3, model: 'opus', messageCount: 40, agentId: 'a1' } as any); for await (const _ of s) void _
  expect(log).toEqual([])
})

test('an interrupted turn is not compacted', async ($, on) => {
  const log: string[] = []
  engine(on, 160_000, log)
  await $.turn.complete(end({ isAborted: true, reason: 'aborted' }) as any)
  await new Promise(r => setTimeout(r, 50))
  expect(log).toEqual([])
})
