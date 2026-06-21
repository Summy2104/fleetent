import { expect, test } from '@playwright/test';

test('logs into the hosted admin UI and renders the agents list', async ({ page }) => {
  await page.goto('/admin/ui');

  await page.getByLabel('Email').fill('admin@example.com');
  await page.getByLabel('Password').fill('adminpw');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'alpha', exact: true })).toBeVisible();
});
