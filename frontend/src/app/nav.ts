import {
  BarChart3,
  Bot,
  Boxes,
  Building2,
  BookOpen,
  Cpu,
  History,
  MessagesSquare,
  Plug,
  Server,
  Sparkles,
  Users,
  UserCog,
  type LucideIcon,
} from 'lucide-react';

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
};

export type NavGroup = {
  label: string | null;
  items: NavItem[];
};

/** Keep the existing 11 features; only regroup them for the new visual shell. */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [
      { to: '/agents', label: 'Agents', icon: Bot },
      { to: '/chat', label: 'Chat', icon: MessagesSquare },
      { to: '/sessions', label: 'Sessions', icon: History },
    ],
  },
  {
    label: 'Knowledge & Skills',
    items: [
      { to: '/skills', label: 'Skills', icon: Sparkles },
      { to: '/kb', label: 'Knowledge Base', icon: BookOpen },
    ],
  },
  {
    label: 'Integrations',
    items: [
      { to: '/providers', label: 'Providers', icon: Cpu },
      { to: '/connectors', label: 'Connector', icon: Plug },
      { to: '/mcp', label: 'MCP Servers', icon: Boxes },
      { to: '/nodes', label: 'Nodes', icon: Server },
    ],
  },
  {
    label: 'Admin',
    items: [
      { to: '/users', label: 'Users', icon: Users },
      { to: '/im-identities', label: 'IM Identities', icon: UserCog },
      { to: '/tenancy', label: 'Tenancy', icon: Building2 },
      { to: '/stats', label: 'Statistics', icon: BarChart3 },
    ],
  },
];

export const NAV_TITLES: Record<string, string> = Object.fromEntries(
  NAV_GROUPS.flatMap((group) => group.items).map((item) => [item.to, item.label])
);
