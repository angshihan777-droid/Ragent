// 轻量 Markdown 渲染：支持代码块、列表、标题、引用、链接与行内标记。
// 决策：仍然不引 marked/dompurify，但从"只有行内"升级为"块级 + 行内"，
// 因为知识库回答里代码块和列表极常见，当纯文本渲染可读性很差。
//
// 安全：唯一的 HTML 来源是本文件生成的标签。所有文本先经 escapeHtml 再套标签；
// 链接只放行 http/https/mailto，杜绝 javascript: 协议注入。
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

// 行内处理顺序很关键：先把行内代码抽成占位符，
// 否则代码里的 * 会被强调规则吃掉（原实现就有这个 bug）。
function renderSpans(raw) {
  const codes = [];
  let s = escapeHtml(raw).replace(/`([^`]+?)`/g, (_, code) => {
    codes.push(code);
    return `\u0000${codes.length - 1}\u0000`;
  });

  s = s.replace(/\[([^\]]+?)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, (m, label, href) =>
    SAFE_URL.test(href)
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : label
  );
  s = s.replace(/\*\*(?=\S)([\s\S]+?\S)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*(?=\S)([^*\n]+?\S)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/~~(?=\S)([\s\S]+?\S)~~/g, "<del>$1</del>");

  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[i]}</code>`);
}

export function renderInline(text) {
  if (!text) return "";
  const lines = String(text).split("\n");
  const out = [];
  let list = null;   // "ul" | "ol"
  let para = [];
  let fence = null;  // { lang, body[] }

  const flushPara = () => {
    if (para.length) { out.push(`<p>${para.map(renderSpans).join("<br>")}</p>`); para = []; }
  };
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const openList = (kind) => { if (list !== kind) { closeList(); out.push(`<${kind}>`); list = kind; } };

  for (const line of lines) {
    const fenceMark = line.match(/^\s*```(\w*)\s*$/);
    if (fenceMark) {
      if (fence) {
        const lang = fence.lang ? ` data-lang="${escapeHtml(fence.lang)}"` : "";
        out.push(`<pre${lang}><code>${escapeHtml(fence.body.join("\n"))}</code></pre>`);
        fence = null;
      } else {
        flushPara(); closeList();
        fence = { lang: fenceMark[1], body: [] };
      }
      continue;
    }
    if (fence) { fence.body.push(line); continue; }
    if (!line.trim()) { flushPara(); closeList(); continue; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushPara(); closeList();
      out.push(`<h${Math.min(4, heading[1].length + 2)}>${renderSpans(heading[2])}</h${Math.min(4, heading[1].length + 2)}>`);
      continue;
    }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushPara(); closeList(); out.push("<hr>"); continue;
    }
    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushPara(); closeList();
      out.push(`<blockquote>${renderSpans(quote[1])}</blockquote>`);
      continue;
    }
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    if (ul) { flushPara(); openList("ul"); out.push(`<li>${renderSpans(ul[1])}</li>`); continue; }
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ol) { flushPara(); openList("ol"); out.push(`<li>${renderSpans(ol[1])}</li>`); continue; }

    closeList();
    para.push(line);
  }

  if (fence) out.push(`<pre><code>${escapeHtml(fence.body.join("\n"))}</code></pre>`);
  flushPara();
  closeList();
  return out.join("");
}
