## ADDED Requirements

### Requirement: KB 自描述并强制 embedding 身份一致

每个 KB SHALL 记录其向量建库时所用的 **embedding 身份**(model 名 + dimensions),并在 ingest 与检索两端**强制一致**,使"用 A 模型建库、用 B 模型检索"这类不一致以**显式错误**暴露,而非静默返回空或噪声。

- KB SHALL 在**首次向量写入**(首次 ingest)时 stamp 当前 embedding 的 `model` 与 `dimensions` 到自身记录(`knowledge_bases`);此后该身份代表该 KB 的向量空间。
- **ingest** SHALL 校验:写入向量的 embedding 身份须与 KB 已记录的一致;不一致 SHALL 拒绝写入并报清晰错误(避免单个 KB 内混入不可比向量)。
- **检索** SHALL 校验:query 向量化所用 embedding 身份须与目标 KB 记录的一致;不一致 SHALL **硬失败并报清晰错误**(指出 KB 建库 embedding 与当前检索 embedding),SHALL NOT 静默返回空结果或不可比向量的噪声召回。
- deterministic(离线/测试)embedding 无真实 model 名时,SHALL 以约定身份(如 `deterministic/<dimensions>`)参与记录与比对。

#### Scenario: 首次 ingest stamp embedding 身份
- **WHEN** 一个尚无向量的 KB 首次被 ingest
- **THEN** 该 KB 记录下当次 embedding 的 model 与 dimensions

#### Scenario: ingest 模型不一致被拒绝
- **WHEN** 对已记录 embedding 身份的 KB 用不同 model/dimensions 再次 ingest
- **THEN** ingest 被拒绝并报清晰错误,KB 内不混入不可比向量

#### Scenario: 检索 embedding 不匹配硬失败
- **WHEN** agent 检索某 KB,而当前检索 embedding 的 model/dimensions ≠ 该 KB 记录的身份
- **THEN** 检索硬失败并报清晰错误,指出建库 embedding 与当前检索 embedding 的差异
- **AND** 不返回静默空结果,也不返回不可比向量的噪声召回

#### Scenario: 一致则正常检索
- **WHEN** 检索 embedding 身份与 KB 记录一致
- **THEN** 检索照常进行,无额外报错

### Requirement: 默认 embedding 配置两端对齐

仓库默认配置 SHALL 使 agent 检索侧 embedding 路由与 standalone KB ingest 侧(`kb-service.yaml`)embedding **指向同一 model + dimensions + endpoint**,使开箱常见场景两端 embedding 天然一致、不触发上面的不匹配错误。

#### Scenario: example 默认两端一致
- **WHEN** 查看仓库默认 example(agent 模板的 embedding 路由 与 `kb-service.yaml.example` 的 embedding 段)
- **THEN** 二者的 model 与 dimensions 一致(endpoint 指向同一约定地址)
