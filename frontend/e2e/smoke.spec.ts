import { expect, test } from '@playwright/test';

test('renders the frontend shell', async ({ page }) => {
  await page.goto('/admin/ui');

  await expect(page.getByRole('heading', { name: 'Admin Login' })).toBeVisible();
});
