import { useState } from 'react'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useTenantsQuery } from '@/features/tenancy/api'
import { AssignmentsTable } from '@/features/tenancy/assignments-table'
import { CreateTenantDialog } from '@/features/tenancy/dialogs/create-tenant-dialog'
import { useAdminMeQuery, useTenancyUsersQuery } from '@/features/tenancy/shared'
import { TenantsTable } from '@/features/tenancy/tenants-table'
import { useT } from '@/i18n'

export function TenancyPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const users = useTenancyUsersQuery()
  const tenants = useTenantsQuery()
  const [createOpen, setCreateOpen] = useState(false)

  const canWrite = me.data ? me.data.role !== 'viewer' : false
  const isViewer = me.data?.role === 'viewer'

  const userList = users.data ?? []
  const tenantList = tenants.data ?? []

  const tenantActions = canWrite ? (
    <Button onClick={() => setCreateOpen(true)}>
      <Plus className="size-4" /> {t('tenancy.createTenant')}
    </Button>
  ) : undefined

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-semibold text-xl tracking-tight">{t('tenancy.title')}</h1>
        <p className="text-muted-foreground text-sm">{t('tenancy.subtitle')}</p>
        {isViewer ? <p className="text-muted-foreground text-xs">{t('tenancy.viewerReadOnly')}</p> : null}
      </header>

      <Tabs defaultValue="tenants">
        <TabsList>
          <TabsTrigger value="tenants">{t('tenancy.tenants')}</TabsTrigger>
          <TabsTrigger value="assignment">{t('tenancy.tabAssignment')}</TabsTrigger>
        </TabsList>

        <TabsContent value="tenants">
          <TenantsTable
            actions={tenantActions}
            canWrite={canWrite}
            isLoading={tenants.isPending}
            tenants={tenantList}
            title={t('tenancy.tenants')}
            users={userList}
          />
        </TabsContent>

        <TabsContent value="assignment">
          <AssignmentsTable
            canWrite={canWrite}
            isLoading={users.isPending}
            tenants={tenantList}
            title={t('tenancy.tabAssignment')}
            users={userList}
          />
        </TabsContent>
      </Tabs>

      {canWrite ? <CreateTenantDialog onOpenChange={setCreateOpen} open={createOpen} /> : null}
    </section>
  )
}
