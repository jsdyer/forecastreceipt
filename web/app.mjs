import {selectCells, summarize, utc, temp, signed, statusFor} from './model.mjs';
const el = id => document.getElementById(id);
const text = (id, value) => { el(id).textContent = value; };
const option = (label, value) => new Option(label, value);
async function json(path) {
  const response = await fetch('./data/' + path);
  if (!response.ok) throw Error('Unavailable file');
  return response.json();
}
let catalog, series, selection = 0, version = 0, hourRequest = 0;
const receiptCache = new Map();
function savedReceipt(path) {
  if (!receiptCache.has(path)) {
    // A chosen valid hour can occur only in the preceding five days of receipts.
    if (receiptCache.size >= 40) receiptCache.delete(receiptCache.keys().next().value);
    const request = json(path).catch(error => {receiptCache.delete(path); throw error;});
    receiptCache.set(path, request);
  }
  return receiptCache.get(path);
}

async function showHour() {
  const request = ++hourRequest;
  const valid = el('valid-hour').value, rows = el('hour-rows');
  rows.replaceChildren();
  if (!valid) return;
  text('history-result', 'Reading the saved forecasts for this hour…');
  const at = Date.parse(valid);
  const candidates = series.receipts.filter(r => {
    const lead = at - Date.parse(r.capture);
    return lead > 0 && lead <= 5 * 86400000;
  }).slice().reverse();
  const replies = await Promise.allSettled(candidates.map(r => savedReceipt(r.path)));
  if (request !== hourRequest) return;
  const obs = series.observed[valid], status = statusFor(valid, obs, catalog.checked);
  const points = [];
  let missing = 0;
  for (const [i, reply] of replies.entries()) {
    if (reply.status === 'rejected') { missing++; continue; }
    const found = reply.value.points.find(([stamp]) => stamp === valid);
    if (!found) continue;
    const record = candidates[i];
    points.push(found[1]);
    const row = rows.insertRow(), link = document.createElement('a');
    link.href = './data/' + record.path; link.textContent = utc(record.capture);
    row.insertCell().append(link);
    row.insertCell().textContent = ((at - Date.parse(record.capture)) / 3600000).toFixed(1);
    row.insertCell().textContent = temp(found[1]);
    row.insertCell().textContent = status === 'Matched' ? signed(found[1] - obs[0]) : '—';
  }
  const summary = points.length > 1
    ? points.length + ' saved forecasts. The earliest predicted ' + temp(points[0]) + ' and the latest ' + temp(points.at(-1)) + '.'
    : points.length ? 'One saved forecast predicted ' + temp(points[0]) + '.' : 'No forecast points available for this hour.';
  const outcome = status === 'Matched' ? 'The airport measured ' + temp(obs[0]) + '. A positive error means a warm forecast.'
    : status === 'Future' ? 'This hour was still in the future when the archive was checked.'
    : status === 'Awaiting reading' ? 'The archive is waiting for the station reading.' : 'The station reading is flagged and excluded from scores.';
  text('history-result', summary + ' ' + outcome + (missing ? ' Some receipt files could not be loaded.' : ''));
}

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

async function receipt(exampleHour = '') {
  const mine = ++version;
  const chosen = el('receipt').value, info = el('receipt-info'), link = el('download'), body = el('rows');
  ++hourRequest;
  el('hour-panel').hidden = true;
  body.replaceChildren(); link.hidden = true;
  if (!chosen) { info.textContent = 'This provider has no saved receipt at this station.'; return; }
  info.textContent = 'Loading receipt…';
  try {
    const doc = await savedReceipt(chosen);
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
    const previous = el('valid-hour').value;
    el('valid-hour').replaceChildren(...doc.points.map(([valid]) => option(fmt.format(new Date(valid)), valid)));
    const firstMatched = doc.points.find(([valid]) => statusFor(valid, series.observed[valid], catalog.checked) === 'Matched');
    if (exampleHour && doc.points.some(([valid]) => valid === exampleHour)) el('valid-hour').value = exampleHour;
    else if (doc.points.some(([valid]) => valid === previous)) el('valid-hour').value = previous;
    else if (firstMatched) el('valid-hour').value = firstMatched[0];
    el('hour-panel').hidden = false;
    showHour();
    info.textContent = `${doc.points.length} forecast hours sampled at three-hour intervals. Captured ${utc(doc.capture_utc)}. ` +
      (doc.model_initialization_utc ? `Model initialized ${utc(doc.model_initialization_utc)}.` : 'OpenWeather does not publish an issue timestamp in this response.');
    link.href = './data/' + chosen; link.download = chosen.split('/').at(-1); link.hidden = false;
  } catch { if (mine === version) info.textContent = 'The receipt file could not be loaded. Reload to retry.'; }
}

async function changeSeries() {
  const mine = ++selection; ++version; ++hourRequest;
  el('hour-panel').hidden = true;
  const station = el('station').value, provider = el('provider').value;
  text('example', 'Reading the selected airport’s forecasts…');
  el('example-link').hidden = true;
  el('example-link').onclick = null;
  try {
    const [cells, observed] = await Promise.all([json(`scores/${station}-${provider}.json`), json(`observed/${station}.json`)]);
    if (mine !== selection) return;
    const receipts = catalog.receipts.filter(x => x.station === station && x.provider === provider).sort((a,b) => b.capture.localeCompare(a.capture));
    series = {station, provider, cells, observed, receipts};
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
    const example = cells.map(cell => cell.largest_revision)
      .filter(item => item && statusFor(item.valid, observed[item.valid], catalog.checked) === 'Matched')
      .sort((a, b) => b.valid.localeCompare(a.valid) || b.after.capture.localeCompare(a.after.capture))[0];
    if (example) {
      const local = new Intl.DateTimeFormat('en-CA', {timeZone: st.zone, dateStyle: 'medium', timeStyle: 'short'});
      text('example', `For ${local.format(new Date(example.valid))} at ${st.name}, ${catalog.providers[provider]} forecast ${temp(example.after.forecast)}. The airport measured ${temp(observed[example.valid][0])}.`);
      el('receipt').value = example.after.path;
      el('example-link').hidden = false;
      el('example-link').onclick = async event => {
        event.preventDefault();
        el('receipt').value = example.after.path;
        await receipt(example.valid);
        if (mine === selection && !el('hour-panel').hidden) el('valid-hour').focus();
      };
    } else {
      const score = summarize(cells);
      text('example', score.matched
        ? `At ${st.name}, the forecasts differed from the thermometer by ${temp(score.mae)} on average across ${score.matched} matched forecast points.`
        : receipts.length ? `Forecasts for ${st.name} are saved. A comparison appears when a matching airport reading arrives.`
        : `There are no saved forecasts from ${catalog.providers[provider]} at ${st.name}. Choose another forecast source.`);
    }
    metrics(); await receipt(example?.valid);
  } catch {
    if (mine === selection) {
      text('example', 'The selected airport’s data could not be loaded.');
      text('status', 'A data file could not be loaded. Reload to retry.');
    }
  }
}

async function start() {
  try {
    catalog = await json('index.json');
    el('station').replaceChildren(...Object.entries(catalog.stations).map(([k,s]) => option(s.name,k)));
    el('provider').replaceChildren(...Object.entries(catalog.providers).map(([k,name]) => option(name,k)));
    const firstStation = el('station').value;
    const available = catalog.receipts.filter(r => r.station === firstStation);
    const initial = available.find(r => r.provider === 'openweather') ?? available[0] ?? catalog.receipts[0];
    if (initial) {
      el('station').value = initial.station;
      el('provider').value = initial.provider;
    }
    text('status', `Archive checked ${utc(catalog.checked)} · Captures scheduled every six hours.`);
    for (const id of ['station','provider']) el(id).addEventListener('change', changeSeries);
    for (const id of ['month','day','period']) el(id).addEventListener('change', () => { if (series) metrics(); });
    el('receipt').addEventListener('change', () => receipt());
    el('valid-hour').addEventListener('change', showHour);
    await changeSeries();
  } catch { text('status','The archive could not be loaded. Reload to retry.'); }
}
start();
