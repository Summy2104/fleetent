import { useState } from 'react'

import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type UserListItem, useCreateImMappingMutation } from '@/features/users/api'
import { IM_PLATFORMS } from '@/features/users/shared'
import { useT } from '@/i18n'

export function AddImMappingDialog({
  open,
  onOpenChange,
  users,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  users: UserListItem[]
}): JSX.Element {
  const t = useT()
  const createMapping = useCreateImMappingMutation()
  const [platform, setPlatform] = useState<string | null>(IM_PLATFORMS[0])
  const [platformUserId, setPlatformUserId] = useState('')
  const [userId, setUserId] = useState<string | null>('')

  const reset = (): void => {
    setPlatform(IM_PLATFORMS[0])
    setPlatformUserId('')
    setUserId('')
  }

  const submit = async (): Promise<void> => {
    await createMapping.mutateAsync({
      platform: platform ?? '',
      platform_user_id: platformUserId.trim(),
      user_id: userId ?? '',
    })
    reset()
    onOpenChange(false)
  }

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('users.addImMapping')}</DialogTitle>
          <DialogDescription>{t('users.addImMappingDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="im-mapping-platform">{t('users.imPlatform')}</Label>
            <SimpleSelect
              onValueChange={setPlatform}
              options={IM_PLATFORMS.map((option) => ({ value: option, label: option }))}
              triggerAriaLabel={t('users.imPlatform')}
              triggerId="im-mapping-platform"
              value={platform}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="im-mapping-external-id">{t('users.imExternalId')}</Label>
            <Input
              id="im-mapping-external-id"
              onChange={(event) => setPlatformUserId(event.target.value)}
              placeholder={t('users.imExternalIdPlaceholder')}
              value={platformUserId}
            />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="im-mapping-user">{t('users.imInternalUser')}</Label>
            <SimpleSelect
              onValueChange={setUserId}
              options={users.map((user) => ({
                value: user.id,
                label: user.email ? `${user.name} (${user.email})` : user.name,
              }))}
              placeholder={t('users.selectUser')}
              triggerAriaLabel={t('users.imInternalUser')}
              triggerId="im-mapping-user"
              value={userId}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('users.cancel')}
          </Button>
          <Button disabled={!platformUserId.trim() || !userId || createMapping.isPending} onClick={() => void submit()}>
            {t('users.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
