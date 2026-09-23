// Cosine similarity is not a calibrated probability; preserve its [-1, 1] range.
export function validSimilarity(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
}
export function formatSimilarity(value) {
  return validSimilarity(value) ? `${(value * 100).toFixed(1)}%` : "暂未提供";
}
// 进度条量程：文字仍显示真实余弦值，但条形图裁到 [0,1]。
// 理由：重排后的命中相似度实际落在 0.3~0.9，用 [-1,1] 画会永远只填一半，
// 让用户误以为匹配很差。负值（几乎不出现）裁到 0。
export function meterValue(value) {
  return validSimilarity(value) ? Math.max(0, value) : 0;
}
