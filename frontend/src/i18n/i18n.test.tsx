import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { I18nProvider, useI18n, useT } from '@/i18n'
import { CATALOGS } from '@/i18n/messages'

function Probe(): JSX.Element {
  const { locale, setLocale, toggleLocale } = useI18n()
  const t = useT()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="title">{t('login.title')}</span>
      <span data-testid="interp">{t('shell.switchToLanguage', { lang: 'X' })}</span>
      <button onClick={toggleLocale} type="button">
        toggle
      </button>
      <button onClick={() => setLocale('zh')} type="button">
        to-zh
      </button>
    </div>
  )
}

describe('i18n package', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })
  afterEach(() => {
    window.localStorage.clear()
  })

  it('每个 zh 词条都覆盖了 en 的全部 key（无漏翻）', () => {
    expect(Object.keys(CATALOGS.zh).sort()).toEqual(Object.keys(CATALOGS.en).sort())
  })

  it('默认 en（jsdom navigator.language 非 zh）并按 key 翻译', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('title')).toHaveTextContent('Admin Login')
  })

  it('toggle 切到中文后词条更新', async () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    await userEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('locale')).toHaveTextContent('zh')
    expect(screen.getByTestId('title')).toHaveTextContent('管理员登录')
  })

  it('{var} 占位符按 vars 插值', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('interp')).toHaveTextContent('Switch to X')
  })

  it('选择持久化到 localStorage 并在重新挂载后恢复', async () => {
    const first = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    await userEvent.click(screen.getByText('to-zh'))
    expect(window.localStorage.getItem('fleetent.admin.locale')).toBe('zh')
    first.unmount()

    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('locale')).toHaveTextContent('zh')
  })
})
