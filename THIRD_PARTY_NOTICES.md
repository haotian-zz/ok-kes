# Third-Party Notices

本文件只做说明，不替代各上游的许可证原文。

## YES-BD2 界面框架（GPL-3.0）

新主窗口 `src/ui/shell/` 里下列文件取自 YES-BD2（https://github.com/nobell001/YES-BD2 ，
它本身是 GodRaymond233/ok-bd2 的修改版），许可证 GPL-3.0；每个文件开头有来源说明，按 ok-kes 的需要做了改动
（去掉 BD2 专用逻辑、改成卡厄思梦境的页面）：

- `theme.py`、`widgets.py`、`motion.py`、`icons.py`、`nav_history.py`、`safe.py`、`page.py`
- `config_form.py`、`sidebar.py`、`install.py`

`src/ui/shell/` 下其他文件（首页、卡厄思页、运行记录、设置、关于、使用说明、标签列表、数据读取）是为 ok-kes 新写的，
和上面这些文件一起按 GPL-3.0 发布。GPL-3.0 全文见 https://www.gnu.org/licenses/gpl-3.0.txt 。

给上游 ok-kes 提交这部分代码前，需要先和上游作者确认许可证。

## 随仓库附带的其他文件

| 内容 | 位置 | 许可证 | 来源 |
|---|---|---|---|
| Lucide 图标 | `assets/ui/icons/` | ISC，见 `assets/ui/icons/LICENSE` | https://github.com/lucide-icons/lucide |
