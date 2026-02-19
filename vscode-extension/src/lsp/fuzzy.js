function levenshteinDistance(a, b) {
  if (a === b) {
    return 0;
  }
  if (a.length === 0) {
    return b.length;
  }
  if (b.length === 0) {
    return a.length;
  }

  const rows = b.length + 1;
  const cols = a.length + 1;
  const dp = Array.from({ length: rows }, () => new Array(cols).fill(0));

  for (let i = 0; i < cols; i += 1) {
    dp[0][i] = i;
  }
  for (let j = 0; j < rows; j += 1) {
    dp[j][0] = j;
  }

  for (let j = 1; j < rows; j += 1) {
    for (let i = 1; i < cols; i += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[j][i] = Math.min(
        dp[j][i - 1] + 1,
        dp[j - 1][i] + 1,
        dp[j - 1][i - 1] + cost,
      );
    }
  }

  return dp[rows - 1][cols - 1];
}

function rankKeywordSuggestions(prefix, keywords, maxEditDistance) {
  const normalized = (prefix || "").trim().toLowerCase();
  if (!normalized) {
    return [];
  }

  const out = [];
  for (const keyword of keywords) {
    const lowerKeyword = keyword.toLowerCase();
    const startsWith = lowerKeyword.startsWith(normalized);
    const distance = levenshteinDistance(normalized, lowerKeyword);
    if (!startsWith && distance > maxEditDistance) {
      continue;
    }
    out.push({
      keyword,
      startsWith,
      distance,
      sameFirst: normalized[0] === lowerKeyword[0],
    });
  }

  out.sort((a, b) => {
    if (a.startsWith !== b.startsWith) {
      return a.startsWith ? -1 : 1;
    }
    if (a.sameFirst !== b.sameFirst) {
      return a.sameFirst ? -1 : 1;
    }
    if (a.distance !== b.distance) {
      return a.distance - b.distance;
    }
    if (a.keyword.length !== b.keyword.length) {
      return a.keyword.length - b.keyword.length;
    }
    return a.keyword.localeCompare(b.keyword);
  });

  return out;
}

module.exports = {
  levenshteinDistance,
  rankKeywordSuggestions,
};