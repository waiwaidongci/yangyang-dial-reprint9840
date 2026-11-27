# 钟表字盘返印编码册

小型传统机器学习后端。分组折外平滑目标编码、未知类别回退。提供台账校验与导入、参数校验与同步计算、结果复核和 CSV 导出。完整业务口径见 [BUSINESS.md](BUSINESS.md)。

## 本地运行

```sh
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:19340/api/health
curl -fsS http://127.0.0.1:19340/api/spec
```

API 默认监听 `127.0.0.1:19340`。接口文档在 `/api/docs`，机器可读规范在 `/api/openapi.json`。数据保存在 SQLite 具名卷中，`docker compose down` 后仍可使用。服务首次启动会装载模拟业务数据。

| 本地演示账号 | 口令 | 权限 |
|---|---|---|
| `analyst@demo.local` | `Demo-2611!` | 导入数据、运行计算、核对结果 |
| `admin@demo.local` | `Demo-2611!` | 分析员权限及结果复核 |
| `viewer@demo.local` | `Demo-2611!` | 查阅来源、已批准的结果并导出 CSV |

## API 工作流

1. `POST /api/auth/login` 接收带 `email`、`password` 的 JSON。后续业务请求通过 `Authorization: Bearer <access_token>` 鉴权。
2. `GET /api/spec` 查看 CSV 列、参数和结果口径。`GET /api/datasets` 查找演示台账，或用 `POST /api/datasets` 提交带 `name`、`csv` 的 JSON。
3. `POST /api/runs` 提交 `dataset_id`、`label` 和可选的 `settings`。响应包含运行 ID 及最终状态。`GET /api/runs/{id}` 返回业务指标、表格或失败原因。
4. 负责人调用 `POST /api/runs/{id}/review`，提交 `decision`（`approved` 或 `rejected`）和 `note`。批准后可通过 `GET /api/runs/{id}/export/{table_key}` 下载业务表。表名和字段从运行结果取得。

### 两车间合册

同一生产批可能分到两个车间做，每个车间逐件保留自己的台账，只交换封账合计：各生产批次的件数、返印件数，以及每个印版、每个油墨在批次内的件数和返印件数。合册时把两边的封账合计相加，整批扣除后重算分组折外编码，跨车间批次按合并后的整批扣除；历史未见类别回退到本折参考返印率。

1. `POST /api/merge/seals` 交一份封账数。可提交本车间台账 `csv`（`shop` 必填，只收 `split=train` 的已确认历史件），也可直接提交 `payload` 聚合对象（含 `shop`、`batches`，各批 `rows`、`reprints` 及 `plate_code`、`ink_code` 计数）。`version` 省略时自动递增；再次提交相同 `version` 完全相同的内容是幂等的，内容不同则返回 409，应改用新版次补报。
2. `GET /api/merge/seals` 与 `GET /api/merge/seals/{shop}` 查看已交封账合计。封账数只含聚合，不含逐件记录。
3. `POST /api/merge/books` 提交 `label` 和可选的 `seals`（`[{shop, version}]`，省略时取各车间最新版次）。两边封账数交齐后才开算；开算即固定两份封账版次，之后即使补报新版本也不影响本册。计算成功前不进入复核。响应中的 `versions` 标明本册所用版次。
4. 计算中断时册子停在计算中状态，`POST /api/merge/books/{id}/retry` 或再次以同一版次组合提交都会按原版次恢复，且不会新增同版编码册。
5. 负责人调用 `POST /api/merge/books/{id}/review` 复核。批准后 `GET /api/merge/books/{id}/export/{table_key}` 下载冻结编码表、逐批折外、跨车间批次、封账合计等业务表；`POST /api/merge/books/{id}/encode` 可用已批准的册子在本地给留出或待检首件编码并生成交班名单，逐件记录不必上传。

## 代码与配置

- `backend/src/domain` 实现数据规范、模拟样本和业务算法。
- `backend/src/services` 与 `backend/src/models` 实现台账、计算、用户权限和复核记录。
- `backend/src/routes`、`schemas` 和 `controllers` 提供 FastAPI 接口与输入输出约束。
- `backend/migrations` 和 `backend/scripts` 提供 SQLite 初始化和可重复执行的演示数据装载。

可在 `.env` 中配置 `BACKEND_PORT`、`SEED_DEMO` 和 `JWT_SECRET`。演示账号、默认签名密钥及模拟台账用于本地验证。启用演示数据也可执行 `docker compose exec -T backend python -m scripts.seed_demo`。
