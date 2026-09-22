// Cosine similarity is not a calibrated probability; preserve its [-1, 1] range.
export function validSimilarity(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
}
export function formatSimilarity(value) {
  return validSimilarity(value) ? `${(value * 100).toFixed(1)}%` : "暂未提供";
}
