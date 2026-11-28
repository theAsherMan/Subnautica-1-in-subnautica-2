import type { EngineInterface, Register } from 'claude-code'

// Main loop only (subagents keep their own autoCompactWindow from their frontmatter).
//  - Mid-turn: before a model request, if the context holds >= MID_TURN_LIMIT tokens,
//    end the turn, compact, then submit a prompt that tells the agent to carry on.
//  - Turn end: if the turn ended normally with > END_TURN_LIMIT tokens, compact.
export const MID_TURN_LIMIT = 200_000
export const END_TURN_LIMIT = 150_000

export const CONTINUE_PROMPT =
  'The context reached 200k tokens mid-turn, so the conversation was compacted. ' +
  'Continue the task you were working on from where you left off.'

const RETRY_MS = 1_000
const MAX_TRIES = 30

async function contextTokens($: EngineInterface): Promise<number> {
  return (await $.session.usage()).context.tokens ?? 0
}

// `$.session.compact()` rejects while a turn runs, so it is retried on a timer
// until the turn that asked for it has fully ended.
function compactSoon($: EngineInterface, reason: string, then?: () => Promise<unknown>, tries = 0): void {
  $.clock.after(RETRY_MS, () => {
    void (async () => {
      let r
      try {
        r = await $.session.compact()
      } catch (err) {
        // Only a rejected compact (turn still running) is retried.
        if (tries + 1 < MAX_TRIES) compactSoon($, reason, then, tries + 1)
        else $.ui.log(`context-compactor: gave up compacting: ${String(err)}`)
        return
      }
      if (r?.skip !== undefined) {
        $.ui.log(`context-compactor: compaction skipped (${r.skip})`)
        return
      }
      $.ui.log(`context-compactor: compacted (${reason})`)
      if (then) await then().catch(err => $.ui.log(`context-compactor: follow-up failed: ${String(err)}`))
    })()
  })
}

export const register: Register = on => {
  let midTurnAbort: string | undefined // turnId this mod ended to compact

  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined && e.index > 0 && midTurnAbort === undefined) {
      const tokens = await contextTokens($)
      if (tokens >= MID_TURN_LIMIT) {
        midTurnAbort = e.turnId
        $.ui.log(`context-compactor: ${tokens} tokens mid-turn, ending the turn to compact`)
        await $.turn.abort({ turnId: e.turnId })
      }
    }
    return yield* next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result

    if (midTurnAbort === e.turnId) {
      midTurnAbort = undefined
      compactSoon($, `>= ${MID_TURN_LIMIT} mid-turn`, () => $.prompt.submit({ text: CONTINUE_PROMPT }))
      return result
    }
    midTurnAbort = undefined
    if (e.isAborted || e.reason === 'refusal') return result

    const tokens = await contextTokens($)
    if (tokens > END_TURN_LIMIT) compactSoon($, `${tokens} > ${END_TURN_LIMIT} at turn end`)
    return result
  })
}
