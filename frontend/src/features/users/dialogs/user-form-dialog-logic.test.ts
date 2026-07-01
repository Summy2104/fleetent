import { describe, expect, it } from 'vitest'

import type { UserListItem } from '@/features/users/api'
import { canSubmitUser, initialUserForm, type UserFormState } from '@/features/users/dialogs/user-form-dialog-logic'

function user(over: Partial<UserListItem> = {}): UserListItem {
  return {
    email: 'a@b.test',
    id: 'u1',
    must_reset: false,
    name: 'Alice',
    role: 'admin',
    status: 'active',
    ...over,
  }
}

function form(over: Partial<UserFormState> = {}): UserFormState {
  return { email: '', name: '', password: '', resetPassword: '', role: 'viewer', mustReset: false, ...over }
}

describe('initialUserForm', () => {
  it('returns viewer defaults for create', () => {
    expect(initialUserForm('create', null)).toEqual(form())
  })

  it('returns viewer defaults for edit with no user', () => {
    expect(initialUserForm('edit', null)).toEqual(form())
  })

  it('maps an existing user into the form for edit, blanking secrets', () => {
    expect(initialUserForm('edit', user({ role: 'operator', must_reset: true }))).toEqual(
      form({ email: 'a@b.test', name: 'Alice', role: 'operator', mustReset: true })
    )
  })

  it('coerces a null email to an empty string', () => {
    expect(initialUserForm('edit', user({ email: null })).email).toBe('')
  })
})

describe('canSubmitUser', () => {
  it('always requires a name', () => {
    expect(canSubmitUser('create', form({ name: '' }))).toBe(false)
    expect(canSubmitUser('edit', form({ name: '' }))).toBe(false)
  })

  it('create requires both email and password', () => {
    expect(canSubmitUser('create', form({ name: 'A', email: '', password: 'pw' }))).toBe(false)
    expect(canSubmitUser('create', form({ name: 'A', email: '  ', password: 'pw' }))).toBe(false)
    expect(canSubmitUser('create', form({ name: 'A', email: 'a@b.test', password: '' }))).toBe(false)
    expect(canSubmitUser('create', form({ name: 'A', email: 'a@b.test', password: 'pw' }))).toBe(true)
  })

  it('edit only requires a name', () => {
    expect(canSubmitUser('edit', form({ name: 'A', email: '', password: '' }))).toBe(true)
  })
})
