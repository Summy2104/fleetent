#!/bin/bash
# 解析项目扩展详情的 ext_type 并打印对应的 ARMADA_CALL（fleetent 两步交互）
#
# fleetent 适配说明：
#   沙箱内没有 mcpfast，无法在脚本内部直接拿到 armada JSON。本脚本只负责：
#     1. 按 business_line_name 解析 ext_type（resolve_extension）
#     2. 打印 agent 应发起的 ARMADA_CALL 行（GET 扩展详情）
#   agent 据此发起 armada__armada_get 工具调用拿到 JSON 后，
#   再用 run_code 跑下方 §format 段的 Python 把 JSON 格式化成中文 label 输出。
#
# 用法：
#   resolve（默认）：fetch-project-extensions.sh <uid> <project_id> <business_line_name>
#       → 打印 EXT_TYPE / EXT_NAME / ARMADA_CALL 三行（或「无对应扩展详情」）
#   format：cat armada.json | fetch-project-extensions.sh --format <ext_name>
#       → 读 stdin 的 armada JSON，按 LABELS 输出中文字段（供 run_code 调用）
set -euo pipefail

MODE="${1:-resolve}"

# ── §format：把 armada 返回的扩展详情 JSON 格式化成中文 label 列表 ──
if [ "$MODE" = "--format" ]; then
  EXT_NAME="${2:-扩展详情}"
  echo "=== 扩展详情（${EXT_NAME}）==="
  python3 -c "
import sys, json

LABELS = {
    'annual_interest_rate':     '年化利率',
    'collateral_account':       '质押金所在账户',
    'collateral_platform':      '质押金所在平台',
    'initial_ltv':              '初始LTV',
    'liquidation_ltv':          '强平LTV',
    'supplementary_ltv':        '补保LTV',
    'supplementary_time_limit': '补保时限',
    'maturity_date':            '到期日',
    'value_date':               '起息日',
    'period':                   '周期',
    'settlement_method':        '结算方式',
    'prime_order_no':           'Prime订单号',
    'prime_fee_rate':           'Prime手续费率',
    'channel_party':            '渠道方',
    'related_project_no':       '关联项目号',
    'withdrawal_limit':         '可提保上限',
    'type':                     '类型',
    'preferred_sharing_ratio':  '优先分润比例',
    'secondary_sharing_ratio':  '劣后分润比例',
    'strategy_description':     '策略说明',
    'strategy_type':            '策略类型',
    'settlement_period':        '结算周期',
    'observer_link':            '观察者链接',
    'mining_pool':              '质押金所属矿池',
    'mining_pool_subaccount':   '矿池子账户',
    'venue':                    '对应场地',
    'miner_model':              '矿机型号',
    'miner_number':             '矿机数量',
    'theoretical_miner_number': '理论矿机数量',
    'mining_income_coin':       '挖矿收益币种',
}

raw = sys.stdin.read().strip()
try:
    data = json.loads(raw)
except Exception:
    print(raw)
    sys.exit(0)

found = False
for k, v in data.items():
    if k in ('id', 'project_id'):
        continue
    if v is None or v == '' or v == [] or v == 0:
        continue
    label = LABELS.get(k, k)
    print('  ' + label + '：' + str(v))
    found = True
if not found:
    print('  （暂无扩展数据）')
"
  exit 0
fi

# ── §resolve：解析 ext_type 并打印 ARMADA_CALL ──
UID_VAL="$1"
PROJECT_ID="$2"
BIZ_LINE="${3:-}"

resolve_extension() {
  local biz="$1"
  case "$biz" in
    *信誉借贷*FDL*|*credit*loan*fdl*)          echo "credit_loans_fdl|信誉借贷FDL" ;;
    *信誉借贷*|*credit*loan*)                   echo "credit_loans|信誉借贷" ;;
    *委托配资*|*entrust*)                        echo "entrusted_margins|委托配资" ;;
    *质押借贷*内*prime5005*)                     echo "prime5005_internal_pledge_loans|质押借贷内(prime5005)" ;;
    *质押借贷*内*test*)                          echo "test_internal_pledge_loans|质押借贷内(test)" ;;
    *质押借贷*内*prime*)                         echo "internal_pledge_loans_prime|质押借贷内(prime)" ;;
    *质押借贷*内*other*)                         echo "internal_pledge_loans_other|质押借贷内(other)" ;;
    *质押借贷*内*)                               echo "internal_pledge_loans|质押借贷内" ;;
    *质押借贷*外*黄金*|*gold*pledge*)            echo "gold_external_pledge_loans|黄金质押借贷外" ;;
    *质押借贷*外*)                               echo "external_pledge_loans|质押借贷外" ;;
    *交易贷*|*loan*trading*)                     echo "loan_trading|借贷-交易贷" ;;
    *机构拆借*|*interbank*)                      echo "interbank_loans|机构拆借" ;;
    *配资*test*)                                 echo "test_margins|配资(test)" ;;
    *配资*)                                      echo "margins|配资" ;;
    *量化*|*quant*)                              echo "quantities|量化" ;;
    *DeFi*|*defi*)                               echo "defi|DeFi" ;;
    *Mining*BTC*托管*|*btc*custody*)             echo "mining_btc_custody_fee|Mining-BTC托管费" ;;
    *Mining*BTC*采购*|*btc*purchase*)            echo "mining_btc_miner_purchase|Mining-BTC矿机采购" ;;
    *Mining*算力*|*mining*computing*)            echo "mining_computing|Mining-算力" ;;
    *Mining*其他*|*mining*other*)                echo "mining_other_coins|Mining-其他币种" ;;
    *其他投资*|*other*invest*)                   echo "other_investment|其他投资" ;;
    *)                                           echo "" ;;
  esac
}

EXT_INFO=$(resolve_extension "$BIZ_LINE")

if [ -z "$EXT_INFO" ]; then
  echo "（无对应扩展详情）"
  exit 0
fi

EXT_PATH="${EXT_INFO%%|*}"
EXT_NAME="${EXT_INFO##*|}"

# uid 校验复用 ns-call.sh（同时构造 _meta），把 GET 扩展详情的 ARMADA_CALL 打印出来。
# agent 收到 ARMADA_CALL 行后发起 armada__armada_get；拿到 JSON 再以
#   bash_exec: ... ns-call 结果 | fetch-project-extensions.sh --format "$EXT_NAME"
# （或直接 run_code 跑 §format 段）格式化。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "EXT_TYPE=${EXT_PATH}"
echo "EXT_NAME=${EXT_NAME}"
bash "$SCRIPT_DIR/ns-call.sh" "$UID_VAL" \
  get "/v1/projects/{id}/extensions/${EXT_PATH}" \
  "path_params={\"id\": \"${PROJECT_ID}\"}"
