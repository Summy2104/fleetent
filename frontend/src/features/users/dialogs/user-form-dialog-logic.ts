import type { UserListItem } from '@/features/users/api'

export type UserFormState = {
  email: string
  name: string
  password: string
  resetPassword: string
  role: string
  mustReset: boolean
}

// Initial form values: an existing user's fields for edit, defaults for create.
export function initialUserForm(mode: 'create' | 'edit', user: UserListItem | null): UserFormState {
  if (mode === 'edit' && user) {
    return {
      email: user.email ?? '',
      name: user.name,
      password: '',
      resetPassword: '',
      role: user.role,
      mustReset: user.must_reset,
    }
  }
  return { email: '', name: '', password: '', resetPassword: '', role: 'viewer', mustReset: false }
}

// Whether the form can be submitted. A platform user logs in by email + password,
// so create requires both; edit only requires a name (email/password edits are optional).
export function canSubmitUser(mode: 'create' | 'edit', state: UserFormState): boolean {
  if (!state.name) return false
  if (mode === 'create') return state.email.trim().length > 0 && state.password.length > 0
  return true
}
