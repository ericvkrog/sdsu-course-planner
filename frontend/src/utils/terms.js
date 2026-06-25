// Academic term ordering — mirror of backend/engine/terms.py.
// SDSU calendar order within a year: Winter → Spring → Summer → Fall.

export const TERM_RANK = { Winter: 0, Spring: 1, Summer: 2, Fall: 3 };
export const OPTIONAL_TERMS = ["Winter", "Summer"];

export function chronoKey(semester, year) {
  return Number(year) * 10 + (TERM_RANK[semester] ?? 9);
}

export function sortSemesters(semesters) {
  return [...semesters].sort(
    (a, b) => chronoKey(a.semester, a.year) - chronoKey(b.semester, b.year)
  );
}

// Optional (Summer/Winter) terms that could be inserted into the current plan but
// aren't there yet — one suggestion per gap, in chronological position.
// Winter Y sits between Fall (Y-1) and Spring Y; Summer Y between Spring Y and Fall Y.
export function suggestedTerms(semesters) {
  const present = new Set(semesters.map((s) => `${s.semester} ${s.year}`));
  const out = [];
  for (const s of semesters) {
    if (s.semester === "Spring") {
      const k = `Summer ${s.year}`;
      if (!present.has(k)) out.push({ semester: "Summer", year: s.year });
    }
    if (s.semester === "Fall") {
      const k = `Winter ${s.year + 1}`;
      if (!present.has(k)) out.push({ semester: "Winter", year: s.year + 1 });
    }
  }
  // De-dup and order chronologically.
  const seen = new Set();
  return sortSemesters(
    out.filter((t) => {
      const k = `${t.semester} ${t.year}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
  );
}
