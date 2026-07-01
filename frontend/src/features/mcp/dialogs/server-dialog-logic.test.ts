import { describe, expect, it } from 'vitest'

import type { McpServerRecord } from '@/features/connectors/api'
import {
  buildServerPayload,
  canSubmitServer,
  type ServerFormFields,
  serverFormFromEditing,
} from '@/features/mcp/dialogs/server-dialog-logic'
import { GLOBAL_SCOPE } from '@/features/mcp/shared'

function baseFields(over: Partial<ServerFormFields> = {}): ServerFormFields {
  return {
    id: 'srv',
    transport: 'stdio',
    command: 'run',
    url: '',
    agentScope: GLOBAL_SCOPE,
    authType: 'none',
    apiKeyEnv: '',
    oauthTokenUrl: '',
    oauthClientId: '',
    oauthClientSecretEnv: '',
    oauthScope: '',
    oauthAuthorizationEndpoint: '',
    oauthRedirectPath: '',
    oauthTokenEnv: '',
    headerStyle: 'bearer',
    credentialInput: 'form',
    env: [],
    args: [],
    headers: [],
    ...over,
  }
}

function record(over: Partial<McpServerRecord> = {}): McpServerRecord {
  return {
    id: 'srv',
    transport: 'stdio',
    auth_type: 'none',
    auth_config: {},
    status: 'connected',
    tool_count: 0,
    agent_id: null,
    ...over,
  }
}

describe('serverFormFromEditing', () => {
  it('returns create defaults when editing is null', () => {
    expect(serverFormFromEditing(null)).toEqual(baseFields({ id: '', command: '', transport: 'stdio' }))
  })

  it('maps a null agent_id to the global scope and a number to its string', () => {
    expect(serverFormFromEditing(record({ agent_id: null })).agentScope).toBe(GLOBAL_SCOPE)
    expect(serverFormFromEditing(record({ agent_id: 42 })).agentScope).toBe('42')
  })

  it('reads the api_key env name from auth_config', () => {
    const f = serverFormFromEditing(record({ auth_type: 'api_key', auth_config: { key_env: 'TOKEN' } }))
    expect(f.authType).toBe('api_key')
    expect(f.apiKeyEnv).toBe('TOKEN')
  })

  it('reads oauth_client_credentials fields', () => {
    const f = serverFormFromEditing(
      record({
        auth_type: 'oauth_client_credentials',
        auth_config: { token_url: 'https://t', client_id: 'cid', client_secret_env: 'SECRET', scope: 'read' },
      })
    )
    expect(f).toMatchObject({
      oauthTokenUrl: 'https://t',
      oauthClientId: 'cid',
      oauthClientSecretEnv: 'SECRET',
      oauthScope: 'read',
    })
  })

  it('reads oauth_authorization_code-only fields', () => {
    const f = serverFormFromEditing(
      record({
        auth_type: 'oauth_authorization_code',
        auth_config: {
          authorization_endpoint: 'https://auth',
          token_url: 'https://t',
          client_id: 'cid',
          client_secret_env: '',
          scope: '',
          redirect_path: '/cb',
          token_env: 'TOK',
        },
      })
    )
    expect(f).toMatchObject({
      oauthAuthorizationEndpoint: 'https://auth',
      oauthRedirectPath: '/cb',
      oauthTokenEnv: 'TOK',
    })
  })

  it('reads api_key_per_user style + credential input', () => {
    const f = serverFormFromEditing(
      record({ auth_type: 'api_key_per_user', auth_config: { header_style: 'x_api_key', credential_input: 'tool' } })
    )
    expect(f).toMatchObject({ headerStyle: 'x_api_key', credentialInput: 'tool' })
  })

  it('expands env/args/headers into editable pairs', () => {
    const f = serverFormFromEditing(
      record({ env: { A: '1' }, args: ['--flag'], headers: { 'X-Key': 'v' }, command: 'cmd', url: 'u' })
    )
    expect(f.env).toEqual([{ key: 'A', value: '1' }])
    expect(f.headers).toEqual([{ key: 'X-Key', value: 'v' }])
    expect(f.args).toEqual(['--flag'])
  })
})

describe('buildServerPayload', () => {
  const opts = { isEdit: false, editingEnabled: undefined }

  it('stdio: keeps the command, trims and drops empty args, no url/headers', () => {
    const payload = buildServerPayload(baseFields({ command: '  run ', args: ['a', ' ', ' b '] }), opts)
    expect(payload.command).toBe('run')
    expect(payload.args).toEqual(['a', 'b'])
    expect(payload.url).toBeUndefined()
    expect(payload.headers).toBeUndefined()
    expect(payload.enabled).toBe(true)
  })

  it('http: keeps the url and a header map, dropping blank keys, no command/args', () => {
    const payload = buildServerPayload(
      baseFields({
        transport: 'http',
        command: '',
        url: ' https://x ',
        headers: [
          { key: ' X-Key ', value: 'v' },
          { key: '  ', value: 'ignored' },
        ],
      }),
      opts
    )
    expect(payload.url).toBe('https://x')
    expect(payload.headers).toEqual({ 'X-Key': 'v' })
    expect(payload.command).toBeUndefined()
    expect(payload.args).toBeUndefined()
  })

  it('builds each auth_config shape from authType', () => {
    expect(buildServerPayload(baseFields({ authType: 'none' }), opts).auth_config).toEqual({})
    expect(buildServerPayload(baseFields({ authType: 'api_key', apiKeyEnv: ' K ' }), opts).auth_config).toEqual({
      key_env: 'K',
    })
    expect(
      buildServerPayload(
        baseFields({
          authType: 'oauth_client_credentials',
          oauthTokenUrl: 't',
          oauthClientId: 'c',
          oauthClientSecretEnv: 's',
          oauthScope: 'r',
        }),
        opts
      ).auth_config
    ).toEqual({ token_url: 't', client_id: 'c', client_secret_env: 's', scope: 'r' })
    expect(
      buildServerPayload(
        baseFields({
          authType: 'oauth_authorization_code',
          oauthAuthorizationEndpoint: 'a',
          oauthTokenUrl: 't',
          oauthClientId: 'c',
          oauthClientSecretEnv: 's',
          oauthScope: 'r',
          oauthRedirectPath: '/cb',
          oauthTokenEnv: 'TOK',
        }),
        opts
      ).auth_config
    ).toEqual({
      authorization_endpoint: 'a',
      token_url: 't',
      client_id: 'c',
      client_secret_env: 's',
      scope: 'r',
      redirect_path: '/cb',
      token_env: 'TOK',
    })
    expect(
      buildServerPayload(
        baseFields({ authType: 'api_key_per_user', headerStyle: 'x_api_key', credentialInput: 'both' }),
        opts
      ).auth_config
    ).toEqual({ header_style: 'x_api_key', credential_input: 'both' })
  })

  it('adds agent_id only for a scoped create, never on edit', () => {
    expect(
      buildServerPayload(baseFields({ agentScope: '7' }), { isEdit: false, editingEnabled: undefined }).agent_id
    ).toBe(7)
    expect(
      buildServerPayload(baseFields({ agentScope: GLOBAL_SCOPE }), { isEdit: false, editingEnabled: undefined })
        .agent_id
    ).toBeUndefined()
    expect(
      buildServerPayload(baseFields({ agentScope: '7' }), { isEdit: true, editingEnabled: true }).agent_id
    ).toBeUndefined()
  })

  it('carries the existing enabled flag through on edit', () => {
    expect(buildServerPayload(baseFields(), { isEdit: true, editingEnabled: false }).enabled).toBe(false)
  })

  it('includes an env map, dropping blank keys', () => {
    const payload = buildServerPayload(
      baseFields({
        env: [
          { key: ' A ', value: '1' },
          { key: '', value: 'skip' },
        ],
      }),
      opts
    )
    expect(payload.env).toEqual({ A: '1' })
  })
})

describe('canSubmitServer', () => {
  it('requires a non-empty id', () => {
    expect(canSubmitServer(baseFields({ id: '  ' }))).toBe(false)
  })

  it('requires a command for stdio and a url for http', () => {
    expect(canSubmitServer(baseFields({ transport: 'stdio', command: '' }))).toBe(false)
    expect(canSubmitServer(baseFields({ transport: 'http', command: '', url: '' }))).toBe(false)
    expect(canSubmitServer(baseFields({ transport: 'http', command: '', url: 'https://x' }))).toBe(true)
  })

  it('treats none and api_key_per_user as always auth-complete', () => {
    expect(canSubmitServer(baseFields({ authType: 'none' }))).toBe(true)
    expect(canSubmitServer(baseFields({ authType: 'api_key_per_user' }))).toBe(true)
  })

  it('requires the env name for api_key', () => {
    expect(canSubmitServer(baseFields({ authType: 'api_key', apiKeyEnv: '' }))).toBe(false)
    expect(canSubmitServer(baseFields({ authType: 'api_key', apiKeyEnv: 'K' }))).toBe(true)
  })

  it('requires all client-credentials fields', () => {
    expect(
      canSubmitServer(baseFields({ authType: 'oauth_client_credentials', oauthTokenUrl: 't', oauthClientId: 'c' }))
    ).toBe(false)
    expect(
      canSubmitServer(
        baseFields({
          authType: 'oauth_client_credentials',
          oauthTokenUrl: 't',
          oauthClientId: 'c',
          oauthClientSecretEnv: 's',
        })
      )
    ).toBe(true)
  })

  it('allows an empty client secret for authorization_code (PKCE)', () => {
    expect(
      canSubmitServer(
        baseFields({
          authType: 'oauth_authorization_code',
          oauthAuthorizationEndpoint: 'a',
          oauthTokenUrl: 't',
          oauthClientId: 'c',
          oauthClientSecretEnv: '',
        })
      )
    ).toBe(true)
  })
})
