import { Languages } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { LOCALES, useI18n } from '@/i18n'

export function LanguageSwitcher(): JSX.Element {
  const { locale, toggleLocale, t } = useI18n()
  const next = locale === 'en' ? LOCALES.zh : LOCALES.en
  const label = t('shell.switchToLanguage', { lang: next.label })

  return (
    <Button aria-label={label} onClick={toggleLocale} size="icon" title={label} variant="ghost">
      <Languages className="size-4" />
      <span className="sr-only">{next.short}</span>
    </Button>
  )
}
