import { describe, expect, it } from 'vitest'
import { api, ApiError } from './api'

describe('API client', () => {
  it('keeps actionable problem details on API errors', () => {
    const detail = { problem: 'Invalid operation', cause: 'Run is already running', fix: 'Refresh first' }
    const error = new ApiError(detail, 409)

    expect(error.message).toBe(detail.cause)
    expect(error.detail.fix).toBe('Refresh first')
    expect(error.status).toBe(409)
  })

  it('scopes export URLs to a run ID and format', () => {
    expect(api.exportUrl('run-123', 'csv')).toContain('/runs/run-123/export?format=csv')
  })
})
