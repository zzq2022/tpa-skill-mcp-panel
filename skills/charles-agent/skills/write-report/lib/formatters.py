# -*- coding: utf-8 -*-
"""
研报产物格式化与交互式 HTML 生成工具
包含脚注双向跳转、悬浮气泡预览 (Tooltip)、侧边栏目录导航与文件协议穿透。
"""
from pathlib import Path
from typing import Dict, List, Tuple
import hashlib
import html
import re


def _parse_footnotes(markdown_text: str) -> Tuple[str, Dict[str, str]]:
    """提取文末脚注定义 [^n]: ...，返回 (清洗后的正文, 脚注字典)"""
    footnotes = {}
    lines = []
    for line in markdown_text.splitlines():
        match = re.match(r"^\[\^([a-zA-Z0-9_-]+)\]:\s*(.+)$", line.strip())
        if match:
            fn_id = match.group(1)
            fn_content = match.group(2).strip()
            footnotes[fn_id] = fn_content
        else:
            lines.append(line)
    return "\n".join(lines), footnotes


def _render_markdown_table(table_text: str) -> str:
    """简易渲染 Markdown 表格为 HTML table"""
    rows = [r.strip() for r in table_text.strip().splitlines() if r.strip()]
    if len(rows) < 2:
        return f"<pre>{html.escape(table_text)}</pre>"

    header_cols = [c.strip() for c in rows[0].strip("|").split("|")]
    # 第二行通常是分隔符 |---|---|
    data_rows = rows[2:] if len(rows) > 2 and re.match(r"^\|?[\s\-:|]+\|?$", rows[1]) else rows[1:]

    out = ['<div class="table-wrapper"><table>']
    out.append("<thead><tr>")
    for col in header_cols:
        out.append(f"<th>{col}</th>")
    out.append("</tr></thead>")

    out.append("<tbody>")
    for r in data_rows:
        cols = [c.strip() for c in r.strip("|").split("|")]
        out.append("<tr>")
        for i, col in enumerate(cols):
            out.append(f"<td>{col}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def convert_markdown_to_interactive_html(markdown_text: str, title: str = "投研报告") -> str:
    """将 Markdown 转换为带悬浮气泡预览、浮动目录和双向锚点的专业交互式 HTML 研报。"""
    body_text, footnotes = _parse_footnotes(markdown_text)

    # 1. 替换链接 [text](url)
    def link_repl(match):
        label = match.group(1)
        url = match.group(2)
        if url.startswith("file:///"):
            return f'<a href="{html.escape(url)}" class="file-link" title="点击打开本地源文件" target="_blank">📄 {label}</a>'
        return f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'

    # 2. 替换正文中的脚注引用 [^n]
    def fn_repl(match):
        fn_id = match.group(1)
        tooltip_text = html.escape(footnotes.get(fn_id, "来源详情见文末数据源清单"))
        return f'<sup class="footnote-wrapper"><a href="#fn-{fn_id}" id="fnref-{fn_id}" class="footnote-ref" data-tooltip="{tooltip_text}">[{fn_id}]</a></sup>'

    # 先处理粗体、斜体、代码、引用
    processed_text = re.sub(r"\[\^([a-zA-Z0-9_-]+)\]", fn_repl, body_text)
    processed_text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, processed_text)

    # 提取目录结构 (TOC)
    toc_items = []
    html_blocks = []
    lines = processed_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # 标题处理
        h_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if h_match:
            level = len(h_match.group(1))
            h_text = h_match.group(2).strip()
            # 生成安全的锚点 id
            anchor_id = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fa5]+", "-", h_text).strip("-").lower()
            if not anchor_id:
                anchor_id = f"heading-{i}"

            if level in (2, 3):
                toc_items.append((level, h_text, anchor_id))

            html_blocks.append(f'<h{level} id="{anchor_id}">{h_text}</h{level}>')
            i += 1
            continue

        # Markdown 表格检测
        if line.strip().startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            html_blocks.append(_render_markdown_table("\n".join(table_lines)))
            continue

        # 代码块 / Mermaid
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束 ```
            code_content = html.escape("\n".join(code_lines))
            if lang == "mermaid":
                html_blocks.append(f'<div class="mermaid-diagram"><pre class="mermaid">{code_content}</pre></div>')
            else:
                html_blocks.append(f'<pre class="code-block"><code>{code_content}</code></pre>')
            continue

        # 引用块
        if line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            quote_html = "<br>".join([_format_inline(q) for q in quote_lines])
            html_blocks.append(f'<blockquote class="alert-box">{quote_html}</blockquote>')
            continue

        # 列表项
        if re.match(r"^(\*|-|\d+\.)\s+", line.strip()):
            list_tag = "ol" if re.match(r"^\d+\.", line.strip()) else "ul"
            list_items = []
            while i < len(lines) and re.match(r"^(\*|-|\d+\.)\s+", lines[i].strip()):
                item_text = re.sub(r"^(\*|-|\d+\.)\s+", "", lines[i].strip())
                list_items.append(f"<li>{_format_inline(item_text)}</li>")
                i += 1
            html_blocks.append(f"<{list_tag}>{''.join(list_items)}</{list_tag}>")
            continue

        # 分割线
        if re.match(r"^(-{3,}|\*{3,})$", line.strip()):
            html_blocks.append("<hr>")
            i += 1
            continue

        # 普通段落
        if line.strip():
            html_blocks.append(f"<p>{_format_inline(line)}</p>")
        i += 1

    # 组装文末脚注清单
    if footnotes:
        fn_section = ['<div class="footnotes-section" id="footnotes-appendix">', '<h3>📌 脚注索引与数据源快速定位</h3>', '<div class="footnotes-list">']
        for fn_id, fn_text in footnotes.items():
            # 允许脚注文本中的 Markdown 链接生效
            rendered_fn_text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, fn_text)
            fn_section.append(
                f'<div class="footnote-item" id="fn-{fn_id}">'
                f'<span class="fn-num">[{fn_id}]</span> '
                f'<span class="fn-text">{rendered_fn_text}</span> '
                f'<a href="#fnref-{fn_id}" class="fn-backlink" title="返回刚才阅读的正文位置">↩ 返回正文</a>'
                f'</div>'
            )
        fn_section.append('</div></div>')
        html_blocks.append("\n".join(fn_section))

    # 构建侧边栏 TOC
    toc_html = ['<nav class="toc-nav">', '<h4>📑 报告大纲目录</h4>', '<ul>']
    for level, h_text, anchor_id in toc_items:
        indent_cls = f"toc-level-{level}"
        # 清除标题内的 Markdown 格式符号用于目录展示
        clean_text = re.sub(r"\[\^[^\]]+\]", "", h_text).replace("**", "").replace("`", "")
        toc_html.append(f'<li class="{indent_cls}"><a href="#{anchor_id}">{clean_text}</a></li>')
    toc_html.append('</ul></nav>')

    # 完整 HTML 模板
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
:root {{
  --bg-primary: #f8fafc;
  --bg-card: #ffffff;
  --text-main: #1e293b;
  --text-muted: #64748b;
  --accent-primary: #2563eb;
  --accent-hover: #1d4ed8;
  --accent-light: #eff6ff;
  --border-color: #e2e8f0;
  --border-focus: #93c5fd;
  --tag-bg: #f1f5f9;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-main);
  line-height: 1.75;
  font-size: 15px;
}}

.report-container {{
  display: flex;
  max-width: 1380px;
  margin: 30px auto;
  padding: 0 20px;
  gap: 32px;
}}

/* 侧边栏目录 */
.toc-sidebar {{
  width: 280px;
  flex-shrink: 0;
  position: sticky;
  top: 30px;
  max-height: calc(100vh - 60px);
  overflow-y: auto;
  background: var(--bg-card);
  padding: 24px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}}

.toc-nav h4 {{
  font-size: 15px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--border-color);
}}

.toc-nav ul {{ list-style: none; }}
.toc-nav li {{ margin-bottom: 8px; }}
.toc-nav li.toc-level-3 {{ padding-left: 14px; font-size: 13.5px; }}
.toc-nav a {{
  color: var(--text-muted);
  text-decoration: none;
  transition: color 0.15s ease;
  display: block;
  line-height: 1.4;
}}
.toc-nav a:hover {{ color: var(--accent-primary); font-weight: 600; }}

/* 报告主体 */
.report-content {{
  flex: 1;
  min-width: 0;
  background: var(--bg-card);
  padding: 40px 48px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}}

h1 {{ font-size: 26px; font-weight: 800; color: #0f172a; margin-bottom: 20px; line-height: 1.3; }}
h2 {{ font-size: 20px; font-weight: 700; color: #1e293b; margin: 36px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border-color); }}
h3 {{ font-size: 16.5px; font-weight: 600; color: #334155; margin: 24px 0 12px; }}
p {{ margin-bottom: 16px; }}
hr {{ border: none; height: 1px; background: var(--border-color); margin: 32px 0; }}

/* 表格样式 */
.table-wrapper {{
  overflow-x: auto;
  margin: 20px 0;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}}
th, td {{
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}}
th {{
  background-color: #f1f5f9;
  font-weight: 700;
  color: #334155;
}}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background-color: #f8fafc; }}

/* 引用块 */
blockquote.alert-box {{
  background: #f8fafc;
  border-left: 4px solid var(--accent-primary);
  padding: 14px 18px;
  border-radius: 0 8px 8px 0;
  color: #475569;
  margin: 18px 0;
  font-size: 14px;
}}

/* 列表 */
ul, ol {{ margin: 12px 0 18px 24px; }}
li {{ margin-bottom: 6px; }}

/* 代码块 */
pre.code-block {{
  background: #0f172a;
  color: #f8fafc;
  padding: 18px;
  border-radius: 8px;
  overflow-x: auto;
  font-family: Consolas, Monaco, "Courier New", monospace;
  font-size: 13.5px;
  margin: 18px 0;
}}

/* 交互式脚注引用与气泡预览 Tooltip */
.footnote-wrapper {{
  position: relative;
  display: inline-block;
  margin: 0 2px;
}}
.footnote-ref {{
  color: var(--accent-primary);
  font-weight: 700;
  text-decoration: none;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--accent-light);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}}
.footnote-ref:hover {{
  background: var(--accent-primary);
  color: #ffffff;
}}

/* 鼠标悬停显示气泡 Tooltip */
.footnote-wrapper:hover::after {{
  content: attr(data-tooltip);
  position: absolute;
  bottom: 130%;
  left: 50%;
  transform: translateX(-50%);
  background: #0f172a;
  color: #f8fafc;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: normal;
  line-height: 1.5;
  white-space: normal;
  width: max-content;
  max-width: 320px;
  z-index: 1000;
  box-shadow: 0 10px 25px rgba(0,0,0,0.25);
  pointer-events: none;
}}
.footnote-wrapper:hover::before {{
  content: "";
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #0f172a;
  z-index: 1000;
}}

/* 文件协议链接样式 */
a.file-link {{
  color: #0d9488;
  font-weight: 600;
  text-decoration: none;
  background: #f0fdfa;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #ccfbf1;
  transition: all 0.15s ease;
}}
a.file-link:hover {{
  background: #0d9488;
  color: #ffffff;
}}

/* 文末脚注区 */
.footnotes-section {{
  margin-top: 48px;
  padding-top: 24px;
  border-top: 2px dashed var(--border-color);
}}
.footnotes-section h3 {{
  font-size: 16px;
  color: #1e293b;
  margin-bottom: 16px;
}}
.footnotes-list {{
  display: flex;
  flex-direction: column;
  gap: 12px;
}}
.footnote-item {{
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13.5px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}}
.fn-num {{
  font-weight: 700;
  color: var(--accent-primary);
  flex-shrink: 0;
}}
.fn-text {{
  flex: 1;
  color: #334155;
}}
.fn-backlink {{
  color: var(--accent-primary);
  text-decoration: none;
  font-weight: 600;
  font-size: 12px;
  flex-shrink: 0;
}}
.fn-backlink:hover {{ text-decoration: underline; }}

@media (max-width: 992px) {{
  .report-container {{ flex-direction: column; }}
  .toc-sidebar {{ width: 100%; position: static; max-height: none; }}
  .report-content {{ padding: 24px; }}
}}
</style>
</head>
<body>
<div class="report-container">
  <aside class="toc-sidebar">
    {toc_html}
  </aside>
  <main class="report-content">
    {chr(10).join(html_blocks)}
  </main>
</div>
</body>
</html>"""


def _format_inline(text: str) -> str:
    """行内粗体、斜体、行内代码格式化"""
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text


def write_report_bundle(output_dir: Path, report_markdown: str, title: str) -> Dict[str, str]:
    """保存 Markdown 研报，并生成专业交互式 HTML 版本。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 规范文件名
    safe_title = re.sub(r'[\\/:*?"<>|]+', '_', str(title)).strip("_-")
    if not safe_title:
        safe_title = f"report_{hashlib.sha256(str(title).encode('utf-8')).hexdigest()[:12]}"

    md_path = output_dir / f"{safe_title}.md"
    html_path = output_dir / f"{safe_title}.html"

    # 保存 Markdown 研报
    md_path.write_text(report_markdown, encoding="utf-8")

    # 生成并保存专业交互式 HTML 研报
    html_content = convert_markdown_to_interactive_html(report_markdown, title=title)
    html_path.write_text(html_content, encoding="utf-8")

    return {"markdown": str(md_path), "html": str(html_path)}
