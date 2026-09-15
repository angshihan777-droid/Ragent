// 极简 Markdown 行内渲染：只处理模型常用的加粗/斜体/行内代码。
// 决策：不引 marked/dompurify。模型输出基本只用到这几种标记，自己写十几行更可控；
// 关键安全点：先转义 HTML 再套标签，避免把模型输出当 HTML 注入(防 XSS)。
// 换行仍交给 CSS 的 white-space: pre-wrap 处理，这里不动。
function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function renderInline(text) {
  let s = escapeHtml(text);
  // **加粗** 先于 *斜体* 处理，否则 ** 会被斜体规则先吃掉一半
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // `行内代码`
  s = s.replace(/`([^`]+?)`/g, "<code>$1</code>");
  return s;
}
