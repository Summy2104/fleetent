import { useState } from 'react';

import {
  type ImMapping,
  useBindableUsersQuery,
  useCreateMappingMutation,
  useDeleteMappingMutation,
  useImMappingsQuery,
} from '@/features/im-identities/api';

const PLATFORMS = ['slack', 'telegram', 'whatsapp'];

function MappingCard({ mapping }: { mapping: ImMapping }): JSX.Element {
  const deleteMapping = useDeleteMappingMutation();

  return (
    <article
      aria-label={`mapping ${mapping.id}`}
      className="rounded-2xl border bg-white/80 p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-secondary px-3 py-1 text-xs font-medium">
              {mapping.platform}
            </span>
            <span className="font-mono text-sm">{mapping.platform_user_id}</span>
          </div>
          <p className="text-sm">
            {`${mapping.user_name} · ${mapping.user_email ?? 'no email'}`}
          </p>
          <p className="text-xs text-muted-foreground">{mapping.user_id}</p>
        </div>
        <button
          className="rounded-md bg-secondary px-3 py-2 text-sm font-medium"
          onClick={() => {
            if (!window.confirm(`Delete mapping ${mapping.platform}:${mapping.platform_user_id}?`)) {
              return;
            }
            deleteMapping.mutate(mapping.id);
          }}
          type="button"
        >
          {`删除 ${mapping.platform_user_id}`}
        </button>
      </div>
      {deleteMapping.isError ? (
        <p
          className="mt-2 text-sm text-red-600"
          role="alert"
        >
          删除失败，请重试。
        </p>
      ) : null}
    </article>
  );
}

export function ImIdentitiesPage(): JSX.Element {
  const mappings = useImMappingsQuery();
  const users = useBindableUsersQuery();
  const createMapping = useCreateMappingMutation();

  const [platform, setPlatform] = useState(PLATFORMS[0]);
  const [platformUserId, setPlatformUserId] = useState('');
  const [userId, setUserId] = useState('');

  const onCreate = (): void => {
    createMapping.mutate(
      {
        platform,
        platform_user_id: platformUserId.trim(),
        user_id: userId,
      },
      {
        onSuccess: () => {
          setPlatformUserId('');
          setUserId('');
        },
      }
    );
  };

  const canSubmit = Boolean(platformUserId.trim()) && Boolean(userId);

  return (
    <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-muted-foreground">
            Native SPA
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">用户-IM 关系</h1>
          <p className="text-sm text-muted-foreground">
            管理"外部 IM 身份 ↔ 内部用户"映射：查看每个渠道身份绑到哪个用户，手动新增或删除绑定。
          </p>
        </header>

        <section className="rounded-2xl border bg-white/75 p-5">
          <h2 className="text-lg font-semibold">新增绑定</h2>
          <div className="mt-4 grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              平台
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setPlatform(event.target.value)}
                value={platform}
              >
                {PLATFORMS.map((option) => (
                  <option
                    key={option}
                    value={option}
                  >
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              外部 ID
              <input
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setPlatformUserId(event.target.value)}
                value={platformUserId}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              内部用户
              <select
                className="rounded-md border bg-white px-3 py-2"
                onChange={(event) => setUserId(event.target.value)}
                value={userId}
              >
                <option value="">选择用户</option>
                {(users.data ?? []).map((user) => (
                  <option
                    key={user.id}
                    value={user.id}
                  >
                    {user.email ? `${user.name} (${user.email})` : user.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!canSubmit || createMapping.isPending}
              onClick={onCreate}
              type="button"
            >
              新增绑定
            </button>
            {createMapping.isError ? (
              <p
                className="text-sm text-red-600"
                role="alert"
              >
                新增绑定失败：该外部身份可能已被绑定，或目标用户不存在。
              </p>
            ) : null}
          </div>
        </section>
      </div>

      <div className="space-y-4">
        {mappings.data?.length ? (
          mappings.data.map((mapping) => (
            <MappingCard
              key={mapping.id}
              mapping={mapping}
            />
          ))
        ) : (
          <p className="text-sm text-muted-foreground">暂无映射。</p>
        )}
      </div>
    </section>
  );
}
