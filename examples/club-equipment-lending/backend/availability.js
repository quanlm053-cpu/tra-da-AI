const timestamp = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/;

export function utcTime(value) {
  if (typeof value !== 'string') return;
  const match = timestamp.exec(value);
  if (!match || match[0] !== value || match[1].startsWith('0000')) return;
  const [, wallTime, fraction = '', offset] = match;
  const localIso = wallTime + '.' + fraction.padEnd(3, '0') + 'Z';
  const localTime = new Date(localIso);
  // Date normalizes some invalid dates, so verify the original calendar fields.
  if (!Number.isFinite(+localTime) || localTime.toISOString() !== localIso) return;
  const utc = new Date(wallTime + '.' + fraction.padEnd(3, '0') + offset);
  if (Number.isFinite(+utc) && utc.getUTCFullYear() >= 1 && utc.getUTCFullYear() <= 9999) return utc;
}

export function availabilityInput(id, query) {
  const equipmentId = Number(id);
  if (!/^\d+$/.test(id) || equipmentId < 1 || equipmentId > 2147483647) return;
  if (query.getAll('from').length !== 1 || query.getAll('to').length !== 1) return;
  const from = utcTime(query.get('from'));
  const to = utcTime(query.get('to'));
  if (from && to && from < to) return { equipmentId, from, to };
}

export function availableSlots(from, to, rows) {
  const available = [];
  let cursor = +from;
  const addSlot = (end) => available.push({
    start_at: new Date(cursor).toISOString(),
    end_at: new Date(end).toISOString(),
  });
  for (const { start_at, end_at } of rows) {
    if (start_at === null) continue;
    const start = Math.max(+from, +start_at);
    const end = Math.min(+to, +end_at);
    if (start > cursor) addSlot(start);
    cursor = Math.max(cursor, end);
  }
  if (cursor < +to) addSlot(+to);
  return available;
}
