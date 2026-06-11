## ADDED Requirements

### Requirement: 基础设施错误不得谎报为路径状态

文件工具的容器后端在解析 exec 输出前 SHALL 先判定执行是否为基础设施失败（容器失踪、daemon 错误等）；此类失败 MUST 以明确的沙箱不可用错误返回给模型，MUST NOT 解析为「路径不存在」「无匹配文件」等路径状态。`probe` 的 `missing` 判定 MUST 仅来源于容器内命令对路径的真实检查结果。

#### Scenario: 死容器下 read_file 报沙箱错误而非路径不存在
- **WHEN** 会话容器已死且未被自愈（极端情形），read_file 的容器内探测命令执行失败
- **THEN** 工具返回指明沙箱基础设施不可用的错误文案，不返回「路径不存在」

#### Scenario: 死容器下 search_files 报错而非"无匹配"
- **WHEN** 容器失踪导致 find 命令未真正执行
- **THEN** 工具返回沙箱错误，不返回「(无匹配文件)」

#### Scenario: 真实缺失路径仍如实报告
- **WHEN** 容器存活，read_file 探测一个确实不存在的路径
- **THEN** 工具返回「路径不存在」（既有语义不变）
