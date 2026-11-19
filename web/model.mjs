export function selectCells(rows, month, day, period) {
  return rows.filter(row => (!month || row.month === month) &&
    (!day || row.day === Number(day)) && (!period || row.period === period));
}
export function summarize(rows) {
  let absolute = 0, signed = 0, matched = 0, eligible = 0, revision = null;
  for (const row of rows) {
    matched += row.matched;
    eligible += row.eligible;
    signed += row.sum_error;
    absolute += row.sum_absolute;
    const next = row.largest_revision;
    if (next && (!revision || Math.abs(next.change) > Math.abs(revision.change))) revision = next;
  }
  return { matched, eligible, mae: matched ? absolute / matched : null,
    bias: matched ? signed / matched : null, revision };
}
export const utc = value => value.replace('T', ' ').replace(/:\d\dZ$/, ' UTC');
export const temp = value => Number.isFinite(value) ? value.toFixed(1) + ' °C' : '—';
export const signed = value => Number.isFinite(value) ? (value > 0 ? '+' : '') + temp(value) : '—';
export function statusFor(valid, observed, checked) {
  if (Date.parse(valid) > Date.parse(checked)) return 'Future';
  if (!observed || observed[0] === null) return 'Awaiting reading';
  return observed[1] ? 'Flagged · ' + observed[1] : 'Matched';
}
