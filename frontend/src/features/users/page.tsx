import { useState } from 'react'
import { KeyRound, Plus, UserPlus } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  type UserListItem,
  useCreateUserMutation,
  useResetPasswordMutation,
  useSetRoleMutation,
  useUpdateUserMutation,
  useUsersQuery,
} from '@/features/users/api'
import { AddImMappingDialog } from '@/features/users/dialogs/add-im-mapping-dialog'
import { CreateServicePrincipalDialog } from '@/features/users/dialogs/create-service-principal-dialog'
import { KeysDialog } from '@/features/users/dialogs/keys-dialog'
import { SecretDialog } from '@/features/users/dialogs/secret-dialog'
import { UserFormDialog, type UserFormState } from '@/features/users/dialogs/user-form-dialog'
import { ImIdentitiesTable } from '@/features/users/im-identities-table'
import { useAdminMeQuery } from '@/features/users/shared'
import { UsersTable } from '@/features/users/users-table'
import { useT } from '@/i18n'

export function UsersPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const users = useUsersQuery()
  const canWrite = me.data?.role !== 'viewer'

  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [formOpen, setFormOpen] = useState(false)
  const [editUser, setEditUser] = useState<UserListItem | null>(null)
  const [servicePrincipalOpen, setServicePrincipalOpen] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [keysUser, setKeysUser] = useState<UserListItem | null>(null)
  const [addImMappingOpen, setAddImMappingOpen] = useState(false)

  const editUserId = editUser?.id ?? ''
  const updateUser = useUpdateUserMutation(editUserId)
  const setRole = useSetRoleMutation(editUserId)
  const resetPassword = useResetPasswordMutation(editUserId)
  const createUser = useCreateUserMutation()

  const submitForm = async (state: UserFormState): Promise<void> => {
    if (formMode === 'create') {
      await createUser.mutateAsync({
        email: state.email,
        must_reset: state.mustReset,
        name: state.name,
        password: state.password,
        role: state.role,
      })
      setFormOpen(false)
      return
    }
    if (!editUser) return
    if (editUser.name !== state.name || (editUser.email ?? '') !== state.email) {
      await updateUser.mutateAsync({ email: state.email, name: state.name })
    }
    if (editUser.role !== state.role) {
      await setRole.mutateAsync({ role: state.role })
    }
    if (state.resetPassword.trim()) {
      await resetPassword.mutateAsync({ new_password: state.resetPassword })
    }
    setFormOpen(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('users.title')}</h2>
          <Badge variant="secondary">{users.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setServicePrincipalOpen(true)} variant="secondary">
              <KeyRound className="size-4" /> {t('users.createServicePrincipal')}
            </Button>
            <Button
              onClick={() => {
                setEditUser(null)
                setFormMode('create')
                setFormOpen(true)
              }}
            >
              <UserPlus className="size-4" /> {t('users.createUser')}
            </Button>
          </div>
        ) : null}
      </div>

      <p className="max-w-2xl text-muted-foreground text-sm">{t('users.pageDescription')}</p>

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">{t('users.tabUsers')}</TabsTrigger>
          <TabsTrigger value="im">{t('users.tabImIdentities')}</TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <UsersTable
            canWrite={canWrite}
            onEdit={(user) => {
              setEditUser(user)
              setFormMode('edit')
              setFormOpen(true)
            }}
            onManageKeys={setKeysUser}
          />
        </TabsContent>

        <TabsContent value="im">
          <div className="space-y-4">
            {canWrite ? (
              <div className="flex justify-end">
                <Button onClick={() => setAddImMappingOpen(true)}>
                  <Plus className="size-4" /> {t('users.addImMapping')}
                </Button>
              </div>
            ) : null}
            <ImIdentitiesTable canWrite={canWrite} users={users.data ?? []} />
          </div>
        </TabsContent>
      </Tabs>

      {canWrite ? (
        <UserFormDialog
          busy={createUser.isPending || updateUser.isPending}
          mode={formMode}
          onOpenChange={setFormOpen}
          onSubmit={submitForm}
          open={formOpen}
          user={formMode === 'edit' ? editUser : null}
        />
      ) : null}

      {canWrite ? (
        <CreateServicePrincipalDialog
          onOpenChange={setServicePrincipalOpen}
          onSecret={setSecret}
          open={servicePrincipalOpen}
        />
      ) : null}

      {keysUser ? (
        <KeysDialog
          canWrite={canWrite}
          onOpenChange={(open) => !open && setKeysUser(null)}
          onSecret={setSecret}
          open
          user={keysUser}
        />
      ) : null}

      {canWrite ? (
        <AddImMappingDialog onOpenChange={setAddImMappingOpen} open={addImMappingOpen} users={users.data ?? []} />
      ) : null}

      <SecretDialog onDismiss={() => setSecret(null)} secret={secret} />
    </div>
  )
}
