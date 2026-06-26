import { Languages } from 'lucide-react';

import { LOCALES, useI18n } from '@/i18n';
import { Button } from '@/components/ui/button';

export function LanguageSwitcher(): JSX.Element {
  const { locale, toggleLocale, t } = useI18n();
  const next = locale === 'en' ? LOCALES.zh : LOCALES.en;
  const label = t('shell.switchToLanguage', { lang: next.label });

  return (
    <Button variant="ghost" size="icon" aria-label={label} title={label} onClick={toggleLocale}>
      <Languages className="size-4" />
      <span className="sr-only">{next.short}</span>
    </Button>
  );
}
