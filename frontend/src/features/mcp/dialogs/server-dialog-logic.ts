import type {
  McpApiKeyPerUserAuthConfig,
  McpApprovalRule,
  McpAuthType,
  McpOAuthAuthorizationCodeAuthConfig,
  McpOAuthClientCredentialsAuthConfig,
  McpServerInput,
  McpServerRecord,
} from '@/features/connectors/api'
import { type EnvPair, GLOBAL_SCOPE, toPairs } from '@/features/mcp/shared'

// Edit-friendly shape for one approval rule: `when` (an arg→values map) is flattened into
// an ordered condition list so the form can add/remove rows. An empty `conditions` list
// means "whole-tool rule" (builds to when: null). Converted back by buildApprovalRules.
export type ApprovalRuleForm = {
  tool: string
  conditions: Array<{ arg: string; values: string[] }>
}

// Plain form state for the MCP server dialog, extracted from the component so the
// branch-heavy derive/build/validate logic can be unit-tested without rendering the
// dialog (no jsdom, no Base UI, no userEvent — fast and flake-free).
export type ServerFormFields = {
  id: string
  transport: string | null
  command: string
  url: string
  agentScope: string | null
  authType: McpAuthType
  apiKeyEnv: string
  oauthTokenUrl: string
  oauthClientId: string
  oauthClientSecretEnv: string
  oauthScope: string
  oauthAuthorizationEndpoint: string
  oauthRedirectPath: string
  oauthTokenEnv: string
  headerStyle: 'bearer' | 'x_api_key'
  credentialInput: 'form' | 'tool' | 'both'
  env: EnvPair[]
  args: string[]
  headers: EnvPair[]
  degradeMode: string
  fileRoot: string
  fileIsolation: string
  approvalRules: ApprovalRuleForm[]
}

// when-map (arg -> allowed values) into ordered, editable condition rows.
function whenToConditions(when: McpApprovalRule['when']): ApprovalRuleForm['conditions'] {
  if (!when) return []
  return Object.entries(when).map(([arg, values]) => ({ arg, values: [...values] }))
}

// Ordered condition rows back into a when-map, dropping blank arg names and blank values.
// No surviving condition -> null (a whole-tool rule).
function conditionsToWhen(conditions: ApprovalRuleForm['conditions']): McpApprovalRule['when'] {
  const when: Record<string, string[]> = {}
  for (const { arg, values } of conditions) {
    const name = arg.trim()
    const cleaned = values.map((value) => value.trim()).filter(Boolean)
    if (name && cleaned.length > 0) when[name] = cleaned
  }
  return Object.keys(when).length > 0 ? when : null
}

// Build the API-shaped approval_rules, dropping rules with a blank tool name.
export function buildApprovalRules(rules: ApprovalRuleForm[]): McpApprovalRule[] {
  return rules
    .filter((rule) => rule.tool.trim().length > 0)
    .map((rule) => ({ tool: rule.tool.trim(), when: conditionsToWhen(rule.conditions) }))
}

// Initial form values: an existing record's fields for edit, or defaults for create.
export function serverFormFromEditing(editing: McpServerRecord | null): ServerFormFields {
  const authConfig = editing?.auth_config ?? {}
  const oauthConfig = authConfig as Partial<McpOAuthClientCredentialsAuthConfig>
  const authzCodeConfig = authConfig as Partial<McpOAuthAuthorizationCodeAuthConfig>
  const perUserConfig = authConfig as Partial<McpApiKeyPerUserAuthConfig>
  return {
    id: editing?.id ?? '',
    transport: editing?.transport ?? 'stdio',
    command: editing?.command ?? '',
    url: editing?.url ?? '',
    agentScope: editing?.agent_id == null ? GLOBAL_SCOPE : String(editing.agent_id),
    authType: editing?.auth_type ?? 'none',
    apiKeyEnv: 'key_env' in authConfig && typeof authConfig.key_env === 'string' ? authConfig.key_env : '',
    oauthTokenUrl: oauthConfig.token_url ?? '',
    oauthClientId: oauthConfig.client_id ?? '',
    oauthClientSecretEnv: oauthConfig.client_secret_env ?? '',
    oauthScope: oauthConfig.scope ?? '',
    oauthAuthorizationEndpoint: authzCodeConfig.authorization_endpoint ?? '',
    oauthRedirectPath: authzCodeConfig.redirect_path ?? '',
    oauthTokenEnv: authzCodeConfig.token_env ?? '',
    headerStyle: perUserConfig.header_style ?? 'bearer',
    credentialInput: perUserConfig.credential_input ?? 'form',
    env: toPairs(editing?.env),
    args: editing?.args ?? [],
    headers: toPairs(editing?.headers),
    degradeMode: editing?.degrade_mode ?? 'degrade',
    fileRoot: editing?.file_root ?? '',
    fileIsolation: editing?.file_isolation ?? 'on',
    approvalRules: (editing?.approval_rules ?? []).map((rule) => ({
      tool: rule.tool,
      conditions: whenToConditions(rule.when),
    })),
  }
}

// Assemble the API payload from form state. auth_config shape depends on authType;
// transport picks command+args (stdio) vs url+headers (http/ws); empty entries drop.
export function buildServerPayload(
  fields: ServerFormFields,
  opts: { isEdit: boolean; editingEnabled: boolean | undefined }
): McpServerInput {
  const payload: McpServerInput = {
    id: fields.id.trim(),
    transport: fields.transport ?? '',
    enabled: opts.editingEnabled ?? true,
    degrade_mode: fields.degradeMode,
    file_root: fields.fileRoot.trim(),
    file_isolation: fields.fileIsolation,
    approval_rules: buildApprovalRules(fields.approvalRules),
    auth_type: fields.authType,
    auth_config:
      fields.authType === 'api_key'
        ? { key_env: fields.apiKeyEnv.trim() }
        : fields.authType === 'oauth_client_credentials'
          ? {
              token_url: fields.oauthTokenUrl.trim(),
              client_id: fields.oauthClientId.trim(),
              client_secret_env: fields.oauthClientSecretEnv.trim(),
              scope: fields.oauthScope.trim(),
            }
          : fields.authType === 'oauth_authorization_code'
            ? {
                authorization_endpoint: fields.oauthAuthorizationEndpoint.trim(),
                token_url: fields.oauthTokenUrl.trim(),
                client_id: fields.oauthClientId.trim(),
                client_secret_env: fields.oauthClientSecretEnv.trim(),
                scope: fields.oauthScope.trim(),
                redirect_path: fields.oauthRedirectPath.trim(),
                token_env: fields.oauthTokenEnv.trim(),
              }
            : fields.authType === 'api_key_per_user'
              ? { header_style: fields.headerStyle, credential_input: fields.credentialInput }
              : {},
  }
  if (!opts.isEdit && fields.agentScope !== GLOBAL_SCOPE) payload.agent_id = Number(fields.agentScope)
  if (fields.transport === 'stdio') {
    payload.command = fields.command.trim() || undefined
    const cleanArgs = fields.args.map((arg) => arg.trim()).filter(Boolean)
    if (cleanArgs.length > 0) payload.args = cleanArgs
  } else {
    payload.url = fields.url.trim() || undefined
    const headerMap: Record<string, string> = {}
    fields.headers.forEach((pair) => {
      if (pair.key.trim()) headerMap[pair.key.trim()] = pair.value
    })
    if (Object.keys(headerMap).length > 0) payload.headers = headerMap
  }
  const envMap: Record<string, string> = {}
  fields.env.forEach((pair) => {
    if (pair.key.trim()) envMap[pair.key.trim()] = pair.value
  })
  if (Object.keys(envMap).length > 0) payload.env = envMap
  return payload
}

// Whether the form is complete enough to submit: id + transport target + the fields
// each auth type requires (authorization_code allows an empty client_secret for PKCE).
export function canSubmitServer(fields: ServerFormFields): boolean {
  return (
    fields.id.trim().length > 0 &&
    (fields.transport === 'stdio' ? fields.command.trim().length > 0 : fields.url.trim().length > 0) &&
    fields.approvalRules.every((rule) => rule.tool.trim().length > 0) &&
    (fields.authType === 'none' ||
      fields.authType === 'api_key_per_user' ||
      (fields.authType === 'api_key' && fields.apiKeyEnv.trim().length > 0) ||
      (fields.authType === 'oauth_client_credentials' &&
        fields.oauthTokenUrl.trim().length > 0 &&
        fields.oauthClientId.trim().length > 0 &&
        fields.oauthClientSecretEnv.trim().length > 0) ||
      (fields.authType === 'oauth_authorization_code' &&
        fields.oauthAuthorizationEndpoint.trim().length > 0 &&
        fields.oauthTokenUrl.trim().length > 0 &&
        fields.oauthClientId.trim().length > 0))
  )
}
