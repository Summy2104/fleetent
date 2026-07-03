import { Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ApprovalRuleForm } from '@/features/mcp/dialogs/server-dialog-logic'
import { useT } from '@/i18n'

// Nested editor for a server's approval_rules. A rule = a tool name + optional when-conditions
// (arg name + allowed values). No conditions on a rule means "every call to this tool needs
// approval". Purely controlled: all state lives in the parent form via value/onChange.
export function ApprovalRulesEditor({
  value,
  onChange,
}: {
  value: ApprovalRuleForm[]
  onChange: (next: ApprovalRuleForm[]) => void
}): JSX.Element {
  const t = useT()

  const patchRule = (index: number, patch: Partial<ApprovalRuleForm>): void =>
    onChange(value.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)))

  const patchConditions = (
    ruleIndex: number,
    map: (conditions: ApprovalRuleForm['conditions']) => ApprovalRuleForm['conditions']
  ): void => patchRule(ruleIndex, { conditions: map(value[ruleIndex].conditions) })

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs">{t('mcp.approvalRulesHelp')}</p>
      {value.map((rule, ruleIndex) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: controlled rows added/removed by index
        <div className="space-y-2 rounded-md border p-3" key={ruleIndex}>
          <div className="flex items-center gap-2">
            <Input
              aria-label={t('mcp.approvalToolAria')}
              className="flex-1"
              onChange={(event) => patchRule(ruleIndex, { tool: event.target.value })}
              placeholder={t('mcp.approvalToolPlaceholder')}
              value={rule.tool}
            />
            <Button
              aria-label={t('mcp.removeApprovalRule')}
              onClick={() => onChange(value.filter((_, i) => i !== ruleIndex))}
              size="icon"
              variant="ghost"
            >
              <X className="size-4" />
            </Button>
          </div>

          {rule.conditions.length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('mcp.approvalWholeToolHint')}</p>
          ) : null}

          {rule.conditions.map((condition, condIndex) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: controlled rows added/removed by index
            <div className="flex items-start gap-2 pl-4" key={condIndex}>
              <Input
                aria-label={t('mcp.approvalArgAria')}
                className="w-40"
                onChange={(event) =>
                  patchConditions(ruleIndex, (conds) =>
                    conds.map((c, i) => (i === condIndex ? { ...c, arg: event.target.value } : c))
                  )
                }
                placeholder={t('mcp.approvalArgPlaceholder')}
                value={condition.arg}
              />
              <div className="flex-1 space-y-2">
                {condition.values.map((allowed, valueIndex) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: controlled rows added/removed by index
                  <div className="flex items-center gap-2" key={valueIndex}>
                    <Input
                      aria-label={t('mcp.approvalValueAria')}
                      className="flex-1"
                      onChange={(event) =>
                        patchConditions(ruleIndex, (conds) =>
                          conds.map((c, i) =>
                            i === condIndex
                              ? {
                                  ...c,
                                  values: c.values.map((v, k) =>
                                    k === valueIndex ? event.target.value : v
                                  ),
                                }
                              : c
                          )
                        )
                      }
                      placeholder={t('mcp.approvalValuePlaceholder')}
                      value={allowed}
                    />
                    <Button
                      aria-label={t('mcp.removeAllowedValue')}
                      onClick={() =>
                        patchConditions(ruleIndex, (conds) =>
                          conds.map((c, i) =>
                            i === condIndex
                              ? { ...c, values: c.values.filter((_, k) => k !== valueIndex) }
                              : c
                          )
                        )
                      }
                      size="icon"
                      variant="ghost"
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
                <Button
                  className="w-full border-dashed"
                  onClick={() =>
                    patchConditions(ruleIndex, (conds) =>
                      conds.map((c, i) =>
                        i === condIndex ? { ...c, values: [...c.values, ''] } : c
                      )
                    )
                  }
                  variant="outline"
                >
                  <Plus className="size-4" /> {t('mcp.addAllowedValue')}
                </Button>
              </div>
              <Button
                aria-label={t('mcp.removeCondition')}
                onClick={() =>
                  patchConditions(ruleIndex, (conds) => conds.filter((_, i) => i !== condIndex))
                }
                size="icon"
                variant="ghost"
              >
                <X className="size-4" />
              </Button>
            </div>
          ))}

          <Button
            className="border-dashed"
            onClick={() =>
              patchConditions(ruleIndex, (conds) => [...conds, { arg: '', values: [''] }])
            }
            size="sm"
            variant="outline"
          >
            <Plus className="size-4" /> {t('mcp.addCondition')}
          </Button>
        </div>
      ))}
      <Button
        className="w-full border-dashed"
        onClick={() => onChange([...value, { tool: '', conditions: [] }])}
        variant="outline"
      >
        <Plus className="size-4" /> {t('mcp.addApprovalRule')}
      </Button>
    </div>
  )
}
