import {selectCells, summarize, utc, temp, signed, statusFor} from './model.mjs';
const el = id => document.getElementById(id);
const text = (id, value) => { el(id).textContent = value; };
const option = (label, value) => new Option(label, value);
async function json(path) {
  const response = await fetch('./data/' + path);
  if (!response.ok) throw Error('Unavailable file');
  return response.json();
}
let catalog, series, selection = 0, version = 0;

function metrics() {
  const rows = selectCells(series.cells, el('month').value, el('day').value, el('period').value);
  const {matched, eligible, mae, bias, revision} = summarize(rows);
  text('matched', String(matched));
  text('mae', temp(mae)); text('bias', signed(bias));
  text('score-note', matched ? `${matched} of ${eligible} past forecast points have an unflagged ECCC reading. Positive bias means forecasts ran warm.` :
    eligible ? `Awaiting station observations for ${eligible} past forecast points in this selection.` :
    'No verified pairs yet for this selection. Scores begin after a saved forecast reaches its valid hour and ECCC publishes a reading.');
  const target = el('revision');
  target.replaceChildren();
  if (!revision) {
    target.textContent = 'A revision requires two saved forecasts for the same valid hour.';
    return;
  }
  const detail = document.createElement('span');
  detail.textContent = `${signed(revision.change)} for ${utc(revision.valid)}. `;
  target.append(detail);
  for (const [i, point] of [revision.before, revision.after].entries()) {
    const a = document.createElement('a');
    a.href = './data/' + point.path;
    a.textContent = `${temp(point.forecast)} captured ${utc(point.capture)}`;
    if (i) target.append(' → ');
    target.append(a);
  }
}

async function receipt() {
  const mine = ++version;
  const chosen = el('receipt').value, info = el('receipt-info'), link = el('download'), body = el('rows');
  body.replaceChildren(); link.hidden = true;
  if (!chosen) { info.textContent = 'This provider has no saved receipt at this station.'; return; }
  info.textContent = 'Loading receipt…';
  try {
    const doc = await json(chosen);
    if (mine !== version) return;
    const zone = catalog.stations[series.station].zone;
    const fmt = new Intl.DateTimeFormat('en-CA',{timeZone:zone,month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'short'});
    const frag = document.createDocumentFragment();
    for (const [valid, forecast] of doc.points) {
      const obs = series.observed[valid], status = statusFor(valid, obs, catalog.checked);
      const row = document.createElement('tr');
      for (const value of [utc(valid), fmt.format(new Date(valid)), temp(forecast), temp(obs?.[0]),
        status === 'Matched' ? signed(forecast - obs[0]) : '—', status]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      frag.append(row);
    }
    body.append(frag);
    info.textContent = `${doc.points.length} forecast hours sampled at three-hour intervals. Captured ${utc(doc.capture_utc)}. ` +
      (doc.model_initialization_utc ? `Model initialized ${utc(doc.model_initialization_utc)}.` : 'OpenWeather does not publish an issue timestamp in this response.');
    link.href = './data/' + chosen; link.download = chosen.split('/').at(-1); link.hidden = false;
  } catch { if (mine === version) info.textContent = 'The receipt file could not be loaded. Reload to retry.'; }
}

async function changeSeries() {
  const mine = ++selection; ++version;
  const station = el('station').value, provider = el('provider').value;
  try {
    const [cells, observed] = await Promise.all([json(`scores/${station}-${provider}.json`), json(`observed/${station}.json`)]);
    if (mine !== selection) return;
    const receipts = catalog.receipts.filter(x => x.station === station && x.provider === provider).sort((a,b) => b.capture.localeCompare(a.capture));
    series = {station, provider, cells, observed};
    el('gfs-credit').hidden = provider !== 'noaa-gfs';
    el('ow-credit').hidden = provider !== 'openweather';
    const months = [...new Set(cells.map(c => c.month))].sort().reverse();
    const oldMonth = el('month').value;
    el('month').replaceChildren(option('All months',''), ...months.map(m => option(m,m)));
    el('month').value = months.includes(oldMonth) ? oldMonth : '';
    el('receipt').replaceChildren(...receipts.map(r => option(utc(r.capture),r.path)));
    el('receipt').disabled = !receipts.length;
    const state = catalog.status[station];
    const measured = Object.entries(observed).filter(([,o])=> Number.isFinite(o[0]) && !o[1]).sort(([a],[b])=>b.localeCompare(a));
    const last = measured[0];
    const st = catalog.stations[station];
    text('availability', `${receipts.length} saved ${receipts.length === 1 ? 'receipt' : 'receipts'}. ${state[provider]} ` +
      (receipts.length ? 'First capture ' + utc(receipts.at(-1).capture) + '.' : ''));
    text('station-note', `ECCC climate ID ${st.climate_id} · ${st.zone}. ` +
      (last ? `Latest saved station reading: ${temp(last[1][0])} at ${utc(last[0])}. ` : 'No station readings available. ') +
      (state.observed === 'Retrieved' ? '' : state.observed));
    metrics(); await receipt();
  } catch {
    if (mine === selection) text('status','A data file could not be loaded. Reload to retry.');
  }
}

async function start() {
  try {
    catalog = await json('index.json');
    el('station').replaceChildren(...Object.entries(catalog.stations).map(([k,s]) => option(s.name,k)));
    el('provider').replaceChildren(...Object.entries(catalog.providers).map(([k,name]) => option(name,k)));
    if (catalog.receipts.some(r => r.provider === 'openweather')) el('provider').value = 'openweather';
    text('status', `Archive checked ${utc(catalog.checked)} · Captures scheduled every six hours.`);
    for (const id of ['station','provider']) el(id).addEventListener('change', changeSeries);
    for (const id of ['month','day','period']) el(id).addEventListener('change', () => { if (series) metrics(); });
    el('receipt').addEventListener('change', receipt);
    await changeSeries();
  } catch { text('status','The archive could not be loaded. Reload to retry.'); }
}
start();
