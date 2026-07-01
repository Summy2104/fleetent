import {
  BarChart3,
  Bot,
  Boxes,
  Building2,
  BookOpen,
  Cpu,
  MessagesSquare,
  ScrollText,
  Server,
  Sparkles,
  Users,
  UsersRound,
  Webhook,
  type LucideIcon,
} from 'lucide-react';

import type { MessageKey } from '@/i18n';

export type NavItem = {
  to: string;
  /** i18n key resolved at render time（见 `src/i18n/messages.ts`）。 */
  labelKey: MessageKey;
  icon: LucideIcon;
};

export type NavGroup = {
  /** 分组标题的 i18n key；无标题分组为 null。 */
  labelKey: MessageKey | null;
  items: NavItem[];
};

/** Keep the existing 11 features; only regroup them for the new visual shell. */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: null,
    items: [
      { to: '/agents', labelKey: 'nav.agents', icon: Bot },
      { to: '/chat', labelKey: 'nav.chat', icon: MessagesSquare },
    ],
  },
  {
    labelKey: 'nav.group.knowledgeSkills',
    items: [
      { to: '/skills', labelKey: 'nav.skills', icon: Sparkles },
      { to: '/kb', labelKey: 'nav.kb', icon: BookOpen },
    ],
  },
  {
    labelKey: 'nav.group.integrations',
    items: [
      { to: '/providers', labelKey: 'nav.providers', icon: Cpu },
      { to: '/mcp', labelKey: 'nav.mcp', icon: Boxes },
      { to: '/webhooks', labelKey: 'nav.webhooks', icon: Webhook },
      { to: '/nodes', labelKey: 'nav.nodes', icon: Server },
    ],
  },
  {
    labelKey: 'nav.group.admin',
    items: [
      { to: '/users', labelKey: 'nav.users', icon: Users },
      { to: '/tenancy', labelKey: 'nav.tenancy', icon: Building2 },
      { to: '/teams', labelKey: 'nav.teams', icon: UsersRound },
      { to: '/stats', labelKey: 'nav.stats', icon: BarChart3 },
      { to: '/audit', labelKey: 'nav.audit', icon: ScrollText },
    ],
  },
];

/** 路由路径 → 页面标题 i18n key（Topbar 标题复用导航词条）。 */
export const NAV_TITLE_KEYS: Record<string, MessageKey> = Object.fromEntries(
  NAV_GROUPS.flatMap((group) => group.items).map((item) => [item.to, item.labelKey])
);
