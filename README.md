# A股盘前 · 免费公开资讯雷达（测试版）

**测试版：有限官方信息样本，非完整A股早报。首次验收仅1条许可范围内新闻元数据，明确标记为非08:00快照。当前数量与采集时间以报告为准。**

GitHub Actions采集许可范围内官方元数据 → data/reports/YYYY-MM-DD.json → Git提交持久归档 → GitHub Pages静态网页。只用Python标准库与浏览器HTML/CSS/JS，不使用付费API、AI模型、数据库云服务或自定义收费域名。

这个目录是经过白名单导出的独立公开包，不是完整私人研究系统。没有证券账户、交易记录、SQLite、密钥或个人配置。不要把原本地项目整个上传。

## 本地运行

Python3.13，Node仅用于前端测试（GitHub标准runner已有），没有pip/npm安装步骤。

```sh
python3 -m unittest discover -s tests/public -v
node tests/public/view.test.cjs
python3 -m app.public_digest.package build site --root .
python3 -m http.server 8510 --bind 127.0.0.1 --directory site
```

访问 http://127.0.0.1:8510 。不要直接双击index.html（浏览器file://通常无法fetch JSON）。部署后的GitHub Pages使用仓库相对路径，不要求根域名。

真实采集（手动）：

```sh
python3 -m app.public_digest.pipeline --root . --edition morning
```

本地Python若报CERTIFICATE_VERIFY_FAILED，应安装/配置受信任CA证书（例如Python官方的Install Certificates.command，或给SSL_CERT_FILE指定已安装且可信的CA证书包）。不要关闭TLS验证或把本机证书、绝对路径、环境文件提交仓库。GitHub标准Linux runner使用平台系统证书，云端连通性仍须首次运行实测。

morning模式只纳入当日北京时间07:58之前的24小时消息；08:00前不发布。实际生成时间不回填08:00。当前RSS仅提供近期条目，若任务延迟很久，可能已错过部分盘前信息，不能声称全市场覆盖。

如果需要在盘后验收一次实时数据链路，明确执行：

```sh
python3 -m app.public_digest.pipeline --root . --edition snapshot
```

snapshot是当前时点真实采集验收快照，网页明确标记“非08:00日报”。当天首个成功JSON冻结不覆盖；同日重复采集只更新尝试状态与索引。不要删除旧数据来伪造历史版本。样本不足、来源不可用就保留缺口，不编造新闻或行情。

## 零新增费用部署步骤（用户确认后）

1. 在GitHub Free账户手动新建**公开**空仓库，仅上传当前导出包内容。保留.github/workflows/daily.yml，不上传本地私人项目。公开站点里所有内容都可被其他人读取。
2. Settings → Actions → General：允许本仓库使用GitHub官方Actions；Workflow permissions允许工作流按声明写入内容。工作流collector只提交data/index.json、data/status.json及data/reports/*.json，不使用git add .，不会提交工作区其他文件。默认分支若受保护，应先确认允许bot提交的合规配置，不使用force push或隐藏PAT。
3. Settings → Pages → Build and deployment → Source选择**GitHub Actions**。使用免费的github.io项目域名，无需购买域名。
4. Actions → Free A-share morning briefing → Run workflow，选择默认分支。这会在确认后执行真实网络采集，并发布公开站点。本轮交付未替你执行这些步骤。
5. 查看两个job：collect提交JSON，publish生成仅包含HTML/CSS/JS/JSON的site artifact并调用Pages部署。打开部署输出的Pages链接。若采集失败但状态JSON可生成，仍发布诚实的失败标记，publish最后会将workflow标红；以前成功日报保留。
6. 定时：`0 0 * * *`对应北京时间08:00，`15 0 * * *`对应08:15补偿检查。GitHub可能延迟或丢弃任务，公开仓库长期无活动还可能停用计划任务，不能保证精确08:00。来源请求最多重试2次；手动重采请Run workflow或Re-run all jobs，单独重跑publish不会重新采集。
7. Git提交是长期JSON存储，runner临时盘和短期Pages artifact不是主数据库。默认单写并发组防止两个采集任务同时提交；push冲突会报错，不强推旧数据。
8. 只用`ubuntu-latest`标准公开runner；不启用larger runner、自托管收费资源、付费API或模型。artifact保留1天，不开依赖缓存；构建前设置64MiB公共数据预算，超出即停止，不删历史、不自动升级。不要为此开通任何新的付费功能，账户若已有付费方式，应将相关可计费超额预算设为0/停止；达限选择停用或归档调整。

官方依据：[公开仓库标准Actions runner免费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)、[GitHub Free公开仓库可用Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)、[定时执行的延迟限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[Pages容量与流量限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。平台规则可能变化，费用不满足0新增时应停用，不切换付费方案。

## 来源和研究边界

许可检查日期：2026-11-18。逐源许可依据、范围和限制在config/public_sources.json的public_reuse字段；每条报告和页面同步显示依据及检查日期。仅公开可访问、RSS可用，均不代表获得再发布许可。

- Federal Reserve Board：[官方声明](https://www.federalreserve.gov/disclaimer.htm)允许未另行声明的Board自身资料公有领域使用，须署名；仅采集自身新闻稿标题及元数据，排除第三方、图片、标识、模型及另有限制内容。
- European Central Bank：[版权声明](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)允许准确署名使用、修改需说明；只采集机构/press/pr/新闻稿标题及元数据，排除署名演讲、采访、研究、第三方及图片标识。
- 商务部网站：[网站声明](https://www.mofcom.gov.cn/fzlm/wzsm/index.html)对明确标注原创的作品要求注明“文章来源：商务部网站”。最多检查4个指定栏目详情页，逐条要求原创标记与可见发布时间；排除转载、编译、摘编。不保存新闻正文、图片或来源摘要。
- 中新网：没有公开再发布授权，完全禁用。原30条本地验收快照不进入索引、公开导出或Pages构建，不因为只留标题/链接就假定可公开。

标题仅在上述许可范围内保留。所谓summary字段现存放系统独立编写的核查模板，明确标记“系统独立核查提示”，不是新闻内容摘要；不复制报道表达、不推断个股表现。不存在许可明确且在时间窗口内的内容时允许零条，不为十大热点/三主题/三风险补造。网页当前只是有限官方信息雷达，不代表已完整覆盖国内热点。条款可能变化，维护者应定期复核；来源提出更严格限制时先停用，再人工审查。

香港金管局列为候选但未启用：原格式限制与RSS日期精度不足尚未满足盘前窗口核验，不采集发布。其他浏览型媒体暂不使用。

分类、板块、风险使用透明关键词规则。股票只取原始标题显式“六位代码.SH/SZ/BJ”，没有则待核实，不猜公司名称和代码。三主题、三风险不足不补。并非全市场新闻、公告或风险数据库；没有实时行情、涨幅预测、回测或交易功能。

## 故障与旧数据保护

网页使用北京时间判断今天；今日缺文件即显示“今日早报暂未更新”，明确最近成功日期。昨日内容只在手动选择归档后展示。源全部失败、日期缺失或时间窗口没有有效新闻时不写空报告覆盖旧文件，仅更新status。访问不到索引时显示无法确认状态，不拿浏览器旧内容冒充当天。成功日报按日期不可变；确需订正时另行设计版本化流程，本MVP不提供强制覆盖。

## 安全维护

导出白名单之外的文件一律不上传。.gitignore只是辅助，不是隐私保证。上传前再核对：没有.env、私人数据库、API Key/PAT、账户截图、账号、交易CSV、绝对个人路径等。工作流使用GitHub自动提供的短期GITHUB_TOKEN，不需要购买API或自行创建PAT。官方Actions已固定为经核对的完整commit SHA，尚未在你的GitHub账号运行。
