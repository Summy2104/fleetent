import type { McpApprovalRule } from '@/features/connectors/api'

// Edit-friendly shape for one approval rule: the API's `when` (an arg→values map) is flattened
// into an ordered condition list so the editor can add/remove rows. An empty `conditions` list
// means "whole-tool rule" (builds back to when: null).
export type ApprovalRuleForm = {
  tool: string
  conditions: Array<{ arg: string; values: string[] }>
}

// API rules -> editor form: expand each rule's when-map into ordered condition rows.
export function rulesToForm(rules: McpApprovalRule[] | undefined): ApprovalRuleForm[] {
  return (rules ?? []).map((rule) => ({
    tool: rule.tool,
    conditions: rule.when
      ? Object.entries(rule.when).map(([arg, values]) => ({ arg, values: [...values] }))
      : [],
  }))
}

function conditionsToWhen(conditions: ApprovalRuleForm['conditions']): McpApprovalRule['when'] {
  const when: Record<string, string[]> = {}
  for (const { arg, values } of conditions) {
    const name = arg.trim()
    const cleaned = values.map((value) => value.trim()).filter(Boolean)
    if (name && cleaned.length > 0) when[name] = cleaned
  }
  return Object.keys(when).length > 0 ? when : null
}

// Editor form -> API rules: drop rules with a blank tool name; blank args/values are dropped,
// leaving `when: null` (a whole-tool rule) when no condition survives.
export function formToRules(form: ApprovalRuleForm[]): McpApprovalRule[] {
  return form
    .filter((rule) => rule.tool.trim().length > 0)
    .map((rule) => ({ tool: rule.tool.trim(), when: conditionsToWhen(rule.conditions) }))
}

// Every rule needs a non-blank tool name before it can be saved.
export function approvalRulesComplete(form: ApprovalRuleForm[]): boolean {
  return form.every((rule) => rule.tool.trim().length > 0)
}
