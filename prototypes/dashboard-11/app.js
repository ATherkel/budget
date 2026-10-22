/* THROWAWAY rendering only. All totals, categories and trust states are frozen report fields. */
const el = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => value === null || value === undefined ? 'Ukendt' : new Intl.NumberFormat('da-DK', {minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value)).replace('-', '−') + ' kr.';
const date = value => value ? new Intl.DateTimeFormat('da-DK', {day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')) : 'Dato mangler';
const badge = (label, warning=true) => `<span class="badge ${warning?'warning':''}">${esc(label)}</span>`;
const monthName = value => new Intl.DateTimeFormat('da-DK',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(value+'-01T12:00:00Z'));
const monthShort = value => new Intl.DateTimeFormat('da-DK',{month:'short',year:'2-digit',timeZone:'UTC'}).format(new Date(value+'-01T12:00:00Z'));
const countText = (count, one, many) => `${count} ${count === 1 ? one : many}`;

let data = null, publication = null, report = null, activeReports = [];
let mode = 'simple', tab = 'overview', publicationId = '';
let rangeMode = 'rolling', customStart = '', customEnd = '', spendingMode = 'amounts';
let trendCategory = 'all', trendResetNotice = '';

const selectedAccountIds = () => [...document.querySelectorAll('#account-options input:checked')].map(input => input.value).sort();
const accountNames = ids => ids.length
  ? data.availableAccounts.filter(a => ids.includes(a.id)).map(a => a.name).join(' · ')
  : 'Ingen konti valgt';
const currentView = () => publication?.views.find(view => view.accountIds.join('|') === selectedAccountIds().join('|')) ?? null;

function currentBudget() {
  const budget = publication?.budgetExample;
  if (!budget || budget.accountIds.join('|') !== selectedAccountIds().join('|')) return null;
  return budget.reports.find(entry => entry.month === report.period.id) ?? null;
}

/* --- shared blocks ------------------------------------------------------- */

function coverageLine(coverage) {
  return `<p class="coverage-line ${coverage.status === 'complete' ? 'complete' : ''}"><strong>${esc(coverage.label)}</strong></p>`;
}

const hasEvidence = () => report.coverage.status !== 'no_data';

function metricRow() {
  const m = report.measures;
  return `<section class="metrics" aria-label="Månedens samlede beløb">
      <button class="metric" type="button" data-detail="income"><span class="label">Indtægter ↗</span><strong class="value">${money(m.income)}</strong><small>${esc(report.measureNote)} · Se posteringer</small></button>
      <button class="metric" type="button" data-detail="expenses"><span class="label">Udgifter ↘</span><strong class="value">${money(m.expenses)}</strong><small>Efter tilbagebetalinger · ${esc(report.measureNote)}</small></button>
      <button class="metric accent" type="button" data-detail="net"><span class="label">Tilbage efter udgifter</span><strong class="value">${money(m.netCashFlow)}</strong><small>Indtægter minus udgifter · ${esc(report.measureNote)}</small></button>
    </section>`;
}

function summaryFigures() {
  const m = report.measures;
  return `<section class="metrics" aria-label="Månedens samlede beløb">
      <div class="metric"><span class="label">Indtægter ↗</span><strong class="value">${money(m.income)}</strong><small>${esc(report.measureNote)}</small></div>
      <div class="metric"><span class="label">Udgifter ↘</span><strong class="value">${money(m.expenses)}</strong><small>Efter tilbagebetalinger</small></div>
      <div class="metric accent"><span class="label">Tilbage efter udgifter</span><strong class="value">${money(m.netCashFlow)}</strong><small>Indtægter minus udgifter</small></div>
    </section>`;
}

function simpleNotice() {
  if (!hasEvidence()) {
    return 'Der er ingen oplysninger for denne måned. Manglende tal vises som ukendte og er ikke det samme som nul.';
  }
  const parts = [];
  if (report.coverage.status !== 'complete') parts.push('Nogle tal er ufuldstændige.');
  if (report.period.provisional) parts.push('Tallene er foreløbige.');
  parts.push('Beløb uden kategori er ikke med i indtægter og udgifter.');
  return parts.join(' ');
}

function categoryList() {
  return report.categories.map(c => `<button class="category" type="button" data-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}</span><span class="row-amount">${money(c.netSpending)}<span class="arrow">›</span></span></span>${c.netRefund?'<small>Mere tilbagebetalt end brugt denne måned</small>':`<span class="bar-track" aria-hidden="true"><span class="bar" style="display:block;--width:${c.barPercent}%"></span></span>`}</button>`).join('')
    || `<p class="empty">${report.coverage.status === 'no_data' ? 'Der mangler oplysninger om udgifter for de valgte konti.' : 'Ingen udgifter med kategori blandt de viste posteringer.'}</p>`;
}

function categoriesPanel(withBudget) {
  return `<section class="panel" aria-labelledby="spending-title">
      <div class="section-head"><h2 id="spending-title">Hvor blev pengene af?</h2>${badge(report.coverage.shortLabel, report.coverage.status !== 'complete')}</div>
      ${withBudget ? `<div class="spending-switch" role="group" aria-label="Visning af kategorier"><button type="button" data-spending-mode="amounts" aria-pressed="${spendingMode === 'amounts'}">Beløb</button><button type="button" data-spending-mode="budget" aria-pressed="${spendingMode === 'budget'}">Mod budget</button></div>` : ''}
      ${withBudget && spendingMode === 'budget' ? budgetPanel() : `<p class="section-intro">Tryk på en kategori for at se posteringerne bag beløbet. Penge tilbage trækkes fra udgifterne.</p>${categoryList()}`}
    </section>`;
}

function transfersPanel() {
  const t = report.transfers;
  const counts = hasEvidence() && t.count
    ? `<p class="footnote">${t.pairedCount} som parret overførsel, ${t.oneSidedCount} enkeltsidet.</p>`
    : '';
  return `<section class="panel"><h3>Mellem vores konti</h3>
      <p class="transfer-note">${esc(t.label)} ${esc(t.detail)}</p>
      ${counts}
      ${hasEvidence() ? '<button class="text-button" type="button" data-detail="transfers">Se overførsler →</button>' : ''}
    </section>`;
}

function adjustmentsPanel() {
  const a = report.adjustments;
  if (!a.count) return '';
  return `<section class="panel"><h3>Andre rettelser</h3>
      <p class="section-intro">${a.count} posteringer er ikke med i indtægter og udgifter.</p>
      <button class="text-button" type="button" data-detail="adjustments">Se rettelser →</button>
    </section>`;
}

/* --- trend -------------------------------------------------------------- */

function monthOptions(months, selected) {
  return months.map(id => `<option value="${id}" ${id === selected ? 'selected' : ''}>${monthName(id)}</option>`).join('');
}

function shiftMonth(id, delta) {
  const index = Number(id.slice(0, 4)) * 12 + Number(id.slice(5, 7)) - 1 + delta;
  return `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`;
}

function calendarMonths(start, end) {
  const first = Number(start.slice(0, 4)) * 12 + Number(start.slice(5, 7)) - 1;
  const last = Number(end.slice(0, 4)) * 12 + Number(end.slice(5, 7)) - 1;
  if (last < first || last - first > 119) return [];
  return Array.from({length: last - first + 1}, (_value, offset) => `${Math.floor((first + offset) / 12)}-${String((first + offset) % 12 + 1).padStart(2, '0')}`);
}

const BUDGET_COLOR = '#6f57a8';

// The selectable categories are every category the selected accounts show anywhere
// in this publication, not only the newest month's list.
function categoryUniverse() {
  const found = new Map();
  activeReports.forEach(item => (item.categories ?? []).forEach(category => {
    if (!found.has(category.id)) found.set(category.id, category.name);
  }));
  return [...found].map(([id, name]) => ({id, name})).sort((left, right) => left.name.localeCompare(right.name, 'da'));
}

// Budget points exist only for the budget's own publication and account scope.
function trendBudget() {
  const budget = publication?.budgetExample;
  if (!budget || budget.accountIds.join('|') !== selectedAccountIds().join('|')) return null;
  return budget;
}

function trendBudgetBlock(month) {
  return trendBudget()?.reports.find(entry => entry.month === month) ?? null;
}

function trendSeries(category) {
  if (!category) {
    return [
      { key: 'income', label: 'Indtægter', color: '#176b53' },
      { key: 'expenses', label: 'Udgifter', color: '#a44828' },
      { key: 'netCashFlow', label: 'Tilbage', color: '#345da8' },
      { key: 'budget', label: 'Budgetteret', color: BUDGET_COLOR, budget: true },
    ];
  }
  return [
    { key: 'category', label: `Udgifter · ${category.name}`, color: '#a44828' },
    { key: 'budget', label: `Budgetteret · ${category.name}`, color: BUDGET_COLOR, budget: true },
  ];
}

// One month's value for one series: a frozen report field, or null when the data
// that would answer the question is not there. Never a guess and never a zero.
function trendValue(point, series, category) {
  if (series.budget) {
    const block = trendBudgetBlock(point.id);
    if (!block) return {value: null};
    if (!category) return {value: block.plannedSpending};
    const row = block.rows.find(entry => entry.id === category.id && !entry.carryForward);
    return {value: row ? row.allocated : null};
  }
  const report = point.report;
  if (!report || report.coverage.status === 'no_data') return {value: null};
  if (series.key === 'category') {
    const found = report.categories.find(row => row.id === category.id);
    if (found) return {value: found.netSpending};
    // A fully covered month can confirm that a category had no spending; a
    // partial month cannot tell that apart from data that never arrived.
    return report.coverage.status === 'complete' ? {value: '0.00', zero: true} : {value: null};
  }
  return {value: report.measures[series.key] ?? null};
}

function trendPointLabel(point, series, value, zero) {
  if (series.budget) return `${monthName(point.id)} · ${series.label}: ${money(value)} · Budgetteret månedsplan`;
  if (zero) return `${monthName(point.id)} · ${series.label}: 0,00 kr. · Ingen kategoriserede udgifter · ${point.report.period.statusLabel} · ${point.report.coverage.label}`;
  return `${monthName(point.id)} · ${series.label}: ${money(value)} · ${point.report.period.statusLabel} · ${point.report.coverage.label}`;
}

function trendPanel() {
  const months = [...publication.months].reverse();
  const last = publication.months[0];
  const earliest = months[0];
  const rollingStart = shiftMonth(last, -11);
  const end = rangeMode === 'custom' ? (customEnd || last) : last;
  const start = rangeMode === 'custom' ? (customStart || earliest) : rangeMode === 'year' ? `${last.slice(0, 4)}-01` : rollingStart;
  const categories = categoryUniverse();
  const category = trendCategory === 'all' ? null : (categories.find(entry => entry.id === trendCategory) ?? null);
  const categoryOptions = [`<option value="all" ${category ? '' : 'selected'}>Alle kategorier</option>`]
    .concat(categories.map(entry => `<option value="${esc(entry.id)}" ${category?.id === entry.id ? 'selected' : ''}>${esc(entry.name)}</option>`))
    .join('');
  const controls = `<div class="trend-controls"><label>Kategori<select id="trend-category">${categoryOptions}</select></label><label>Periode<select id="trend-range"><option value="rolling" ${rangeMode === 'rolling' ? 'selected' : ''}>Seneste 12 måneder</option><option value="year" ${rangeMode === 'year' ? 'selected' : ''}>Indeværende år</option><option value="custom" ${rangeMode === 'custom' ? 'selected' : ''}>Egen periode</option></select></label>${rangeMode === 'custom' ? `<label>Fra måned<select id="trend-start">${monthOptions(months, start)}</select></label><label>Til måned<select id="trend-end">${monthOptions(months, end)}</select></label>` : ''}</div>`;
  const invalid = (rangeMode === 'custom' && (!months.includes(start) || !months.includes(end))) || end > last;
  const ids = invalid ? [] : calendarMonths(start, end);
  const reset = trendResetNotice ? `<p class="trend-reset" role="status">${esc(trendResetNotice)}</p>` : '';
  let body;
  if (!ids.length) {
    body = `<p class="empty" role="status">Vælg en startmåned før eller lig med slutmåneden, senest ${monthName(last)}.</p>`;
  } else {
    const points = ids.map(id => ({ id, report: activeReports.find(r => r.period.id === id) }));
    const defined = trendSeries(category);
    const series = defined.filter(entry => !entry.budget || points.some(point => trendValue(point, entry, category).value != null));
    const budgetDefined = defined.some(entry => entry.budget);
    const budgetShown = series.some(entry => entry.budget);
    // Only the chart's coordinates are computed here; every amount is a frozen report field.
    const values = points.flatMap(point => series.map(entry => trendValue(point, entry, category).value)).filter(value => value != null).map(Number);
    const low = Math.min(0, ...values), high = Math.max(0, ...values), span = high - low || 1;
    const width = Math.max(280, Math.min(1000, document.querySelector('main').clientWidth - 44)), height = 250, left = 72, right = 16, top = 18, bottom = 38;
    const x = i => left + (points.length === 1 ? .5 : i / (points.length - 1)) * (width - left - right);
    const y = value => top + (high - Number(value)) / span * (height - top - bottom);
    const ticks = [...new Set([low, 0, high])];
    const grid = ticks.map(v => `<line x1="${left}" x2="${width - right}" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="${left - 8}" y="${y(v) + 4}" text-anchor="end">${new Intl.NumberFormat('da-DK',{maximumFractionDigits:0}).format(v)}</text>`).join('');
    const stride = Math.max(1, Math.ceil(points.length / (width < 500 ? 4 : 9)));
    const gap = width < 500 ? 64 : 60;
    const keptLabels = [];
    points.forEach((_point, i) => {
      if (i % stride !== 0 && i !== points.length - 1) return;
      if (i === points.length - 1 && keptLabels.length && x(i) - x(keptLabels[keptLabels.length - 1]) < gap) keptLabels.pop();
      if (!keptLabels.length || x(i) - x(keptLabels[keptLabels.length - 1]) >= gap) keptLabels.push(i);
    });
    const labels = keptLabels.map(i => `<text x="${x(i)}" y="${height - 10}" text-anchor="${i === points.length - 1 ? 'end' : i === 0 ? 'start' : 'middle'}">${monthShort(points[i].id)}</text>`).join('');
    const paths = series.map(entry => {
      let previous = null; return points.map((p, i) => {
        const { value, zero } = trendValue(p, entry, category);
        if (value == null) { previous = null; return ''; }
        // Budget is a plan, so it never borrows the provisional actuals' look.
        const provisional = !entry.budget && (p.report.period.provisional || p.report.coverage.status !== 'complete');
        const point = { x: x(i), y: y(value), provisional };
        const line = previous ? `<line x1="${previous.x}" y1="${previous.y}" x2="${point.x}" y2="${point.y}" stroke="${entry.color}" stroke-width="2" ${provisional || previous.provisional ? 'stroke-dasharray="5 4"' : ''}/>` : '';
        const title = trendPointLabel(p, entry, value, zero);
        previous = point;
        const marker = entry.budget
          ? `<rect x="${point.x - 3.5}" y="${point.y - 3.5}" width="7" height="7" fill="${entry.color}" tabindex="0" aria-label="${esc(title)}"><title>${esc(title)}</title></rect>`
          : `<circle cx="${point.x}" cy="${point.y}" r="3.5" fill="${provisional ? 'white' : entry.color}" stroke="${entry.color}" stroke-width="2" tabindex="0" aria-label="${esc(title)}"><title>${esc(title)}</title></circle>`;
        return `${line}${marker}`;
      }).join('');
    }).join('');
    const heading = category ? `${category.name}: udgifter og budgetteret` : `Alle kategorier: ${series.map(entry => entry.label).join(', ')}`;
    const chart = values.length ? `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="chart-title chart-description"><title id="chart-title">${esc(heading)} fra ${monthName(start)} til ${monthName(end)}</title><desc id="chart-description">Månedstal for de valgte konti. ${budgetShown ? 'Budgetteret er hele månedens plan, ikke faktiske tal.' : 'Der findes ingen budgettal for denne visning.'} Huller betyder, at oplysningerne mangler, og et ukendt beløb er ikke nul. De præcise beløb og datagrundlaget findes i tabellen nedenfor.</desc>${grid}${paths}${labels}</svg>` : '<p class="empty">Der er ingen månedstal for de valgte konti i perioden. Manglende oplysninger vises ikke som nul.</p>';
    const headers = series.map(entry => `<th>${esc(entry.label)}</th>`).join('');
    const rows = points.map(p => `<tr><th scope="row">${p.report ? `<button class="text-button" type="button" data-month="${p.id}">${monthName(p.id)}</button>` : monthName(p.id)}</th>${series.map(entry => {const { value, zero } = trendValue(p, entry, category); return `<td class="value-cell${entry.budget ? ' budget-cell' : ''}">${value == null ? 'Ukendt' : esc(money(value) + (zero ? ' · ingen kategoriserede udgifter' : ''))}</td>`;}).join('')}<td>${p.report ? `${esc(p.report.period.statusLabel)}. ${esc(p.report.coverage.detail)}` : 'Ingen rapportoplysninger for denne måned.'}</td></tr>`).join('');
    const legend = series.map(entry => `<span><i class="${entry.budget ? 'swatch-budget' : 'swatch-line'}" style="background:${entry.color}"></i>${esc(entry.label)}${entry.budget ? ' <small>(plan)</small>' : ''}</span>`).join('');
    const budgetNotes = budgetShown
      ? '<p class="footnote">Budgetteret er hele månedens plan, ikke delt op efter datoen i dag. Ferie er øremærket opsparing og ikke et månedligt udgiftsbudget, så den er ikke med, og opsparede ferierester tæller ikke som forventet forbrug.</p>'
      : budgetDefined ? '<p class="footnote">Ingen budgettal i denne visning. Det opdigtede budget gælder begge konti i nutidsvisningen (juli–september 2026). Andre valg har ukendt budget, ikke nul.</p>' : '';
    body = `<p class="section-intro">${monthName(start)} – ${monthName(end)} · kr. pr. måned · samme kontovalg som overblikket</p><div class="chart-legend">${legend}</div>${chart}<p class="footnote">Stiplede linjer og hule punkter: foreløbige eller ufuldstændige tal. Firkantede punkter og en ubrudt linje: budgetterede tal, som ikke er foreløbige. Huller: oplysninger mangler — et ukendt beløb er ikke nul. Beløb uden kategori og interne overførsler er ikke med i nøgletallene.</p>${budgetNotes}<details class="chart-table"><summary>Se månedstal og datagrundlag</summary><div class="table-scroll"><table><thead><tr><th>Måned</th>${headers}<th>Datagrundlag</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
  }
  return `<section class="panel trend-panel" aria-labelledby="trend-heading"><div class="section-head"><h2 id="trend-heading">Udvikling over tid</h2>${controls}</div>${reset}${body}<p class="footnote">Perioderne tager udgangspunkt i visningens nyeste måned: ${monthName(last)}.</p></section>`;
}

/* --- the budget comparison (Enkel and Avanceret) ------------------------- */

function monthTimeProgress(month, referenceDate) {
  // Calendar-day position only; never infer time from the latest transaction.
  if (!/^\d{4}-\d{2}$/.test(month) || !/^\d{4}-\d{2}-\d{2}$/.test(referenceDate ?? '') || referenceDate.slice(0, 7) !== month) return null;
  const [year, monthNumber, day] = referenceDate.split('-').map(Number);
  if (monthNumber < 1 || monthNumber > 12) return null;
  const days = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  if (day < 1 || day > days) return null;
  return {day, days, percent: day / days * 100, referenceDate};
}

function monthTimeLegend(progress) {
  if (!progress) return '';
  const percent = new Intl.NumberFormat('da-DK', {maximumFractionDigits: 0}).format(progress.percent);
  return `<p class="month-time-legend"><span class="month-time-key" aria-hidden="true"></span><strong>Månedens tid: ${progress.day} af ${progress.days} dage (${percent} %)</strong> · ${date(progress.referenceDate)}<br><span>Stregen viser tiden, ikke forventet forbrug. Forbruget kan falde ujævnt, og posteringer kan komme senere. Ingen tidsstreg på opsparing fra flere måneder.</span></p>`;
}

function budgetPanel() {
  const b = currentBudget();
  if (!b) return `<p class="empty">Budgeteksemplet er opdigtet og gælder begge eksempelkonti samlet. Der er endnu ikke et budget for dette datagrundlag eller kontovalg.</p><button class="text-button" type="button" data-budget-demo>Åbn opdigtet budget · begge konti →</button>`;
  const simple = mode === 'simple';
  const time = monthTimeProgress(report.period.id, publication.isCurrent ? data.asOf : publication.knownAt);
  const rows = b.rows.filter(c => !simple || !c.carryForward).map(c => {
    const over = Number(c.remaining) < 0;
    const percent = Math.max(0, Math.min(100, Number(c.actual) / Number(c.available) * 100));
    const marker = time && !c.carryForward && Number(c.available) > 0
      ? `<span class="month-time-marker" style="--time-position:${time.percent}%"></span>` : '';
    return `<button class="category budget-category ${over?'over-budget':''}" type="button" data-budget-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}${c.carryForward?'<small>Opspares til senere</small>':''}</span><span class="row-amount">${money(c.actual)}<span class="arrow">›</span></span></span><span class="budget-subrow"><span>af ${money(c.available)} til rådighed</span><strong>${over?'Overskredet med '+money(String(Math.abs(Number(c.remaining)))):money(c.remaining)+' tilbage'}</strong></span><span class="bar-track${marker ? ' with-time-marker' : ''}" aria-hidden="true"><span class="bar" style="display:block;--width:${percent}%"></span>${marker}</span>${c.carryForward?`<small>${money(c.opening)} fra tidligere + ${money(c.allocated)} denne måned</small>`:''}</button>`;
  }).join('');
  // The simple view keeps the monthly comparison quiet: ordinary expense budgets,
  // the time marker, and one line about why the earmarked vacation is no expense budget.
  const savings = simple ? '' : `<section class="savings-summary" aria-labelledby="savings-heading"><h3 id="savings-heading">Opsparing efter øremærkning</h3>${badge(report.period.statusLabel, report.period.provisional)} ${badge(report.coverage.shortLabel, report.coverage.status !== 'complete')}<p class="footnote">${esc(report.coverage.detail)} Beløb uden kategori kan ændre opsparingen.</p><p>Månedens bidrag til almindelig opsparing, efter ${money(b.earmarked)} til Ferie.</p><div class="row"><span>Budget</span><strong>${money(b.plannedSavings)}</strong></div><div class="row"><span>Ud fra kendte posteringer</span><strong>${money(b.actualSavings)}</strong></div><p class="savings-variance ${Number(b.savingsDifference)<0?'over-budget':''}">${money(String(Math.abs(Number(b.savingsDifference))))} ${Number(b.savingsDifference)<0?'mindre':'mere'} end planlagt</p><details><summary>Hvordan hænger opsparingen sammen?</summary><p>Planlagt indtægt ${money(b.plannedIncome)} − almindelige budgetter ${money(b.plannedSpending)} − øremærket til Ferie ${money(b.earmarked)} = ${money(b.plannedSavings)}.</p><p>Indtægter minus faktiske udgifter ${money(report.measures.netCashFlow)} − månedens øremærkning ${money(b.earmarked)} = ${money(b.actualSavings)} til almindelig opsparing.</p><p>Ubrugte beløb i almindelige kategorier øger Opsparing; overskridelser reducerer den. Ændrede indtægter påvirker også Opsparing. Her er indtægten som planlagt.</p><p>Beløbet er månedens bidrag, ikke en kontosaldo eller den samlede opsparing. Ukendte posteringer og andre rettelser er ikke med.</p></details></section>`;
  const closing = simple
    ? '<p class="footnote">Ferie er en øremærkning til opsparing og ikke et månedligt udgiftsbudget, så den står ikke på listen. Opsparede ferierester er ikke forventet forbrug. Budgettet gælder hele måneden.</p>'
    : '<p class="footnote">Ferie er en øremærkning på tværs af de to konti, ikke en ekstra bankkonto eller en udgift. Kun kategorier markeret “Opspares til senere” fører restbeløb videre. De viste ferierester forudsætter, at de ukendte posteringer ikke er ferieudgifter.</p>';
  return `<p class="budget-notice">${esc(publication.budgetExample.notice)}</p><p class="section-intro">Brugt efter tilbagebetalinger sammenholdt med beløbet til rådighed. Tryk på en kategori for regnestykket.</p>${monthTimeLegend(time)}${rows}${savings}${closing}`;
}

/* --- the three advanced tabs -------------------------------------------- */

function overviewPanel() {
  return `<div class="period-line"><h2>${esc(report.period.label)}</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    <details class="trust ${report.coverage.status === 'complete' ? 'complete' : ''}"><summary>${esc(report.coverage.label)}</summary><p>${esc(report.coverage.detail)}</p><p>${esc(data.notice)}</p><p>${esc(report.period.detail)}</p></details>
    ${metricRow()}
    ${trendPanel()}
    ${categoriesPanel(true)}
    <p class="footnote">Forklaringer, afstemning og beløb uden kategori findes under Kontrol.</p>`;
}

function detailsPanel() {
  return `<div class="period-line"><h2>${esc(report.period.label)} · detaljer</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    <div class="columns"><div>
      <section class="panel"><h2>Kontobevægelser</h2><p class="section-intro">Vælg en konto for at se posteringerne og det oplyste datagrundlag.</p>
        ${report.accounts.map(a => `<article class="account"><div class="row"><div><h3>${esc(a.name)} <span class="ownership">${esc(a.ownerLabel)}</span></h3>${badge(a.coverage.label, a.coverage.status !== 'complete')}</div><div><strong class="balance">${money(a.balance.amount)}</strong><small>${a.balance.asOf ? 'Senest oplyst ' + date(a.balance.asOf) : 'Saldo mangler for denne måned'}</small></div></div><p>${esc(a.coverage.detail)}</p><button class="text-button" type="button" data-account="${esc(a.id)}">Se kontobevægelser →</button></article>`).join('')}
      </section>
    </div><aside>
      ${transfersPanel()}
      ${adjustmentsPanel()}
    </aside></div>`;
}

function reconciliationRow(label, value, strong = false) {
  return `<div class="recon-row ${strong ? 'recon-total' : ''}"><span>${esc(label)}</span><strong>${money(value)}</strong></div>`;
}

function checksPanel() {
  const r = report.reconciliation;
  const route = report.unclassified.operatorRoute;
  const counts = r.entryCounts;
  const known = hasEvidence();
  const countSentence = known
    ? `${countText(counts.income, 'indtægtspostering', 'indtægtsposteringer')}, ${countText(counts.categories, 'postering i kategorier', 'posteringer i kategorier')}, ${counts.unclassified} uden kategori, ${countText(counts.adjustments, 'rettelse', 'rettelser')} og ${countText(counts.transfers, 'overførsel', 'overførsler')} — ${countText(r.entryCount, 'postering', 'posteringer')} i alt.`
    : 'Antal posteringer er ukendt for denne måned.';
  const adjustmentSentence = !known
    ? 'Ingen oplysninger for måneden.'
    : report.adjustments.count
      ? `${report.adjustments.count} rettelser uden kategori er holdt uden for indtægter og udgifter.`
      : 'Ingen rettelser uden kategori i denne måned.';
  return `<div class="period-line"><h2>${esc(report.period.label)} · kontrol</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    <section class="panel"><div class="section-head"><h2>Datadækning</h2>${badge(report.coverage.shortLabel, report.coverage.status !== 'complete')}</div>
      <p class="section-intro">${esc(report.coverage.detail)}</p>
      <div class="recon-table">${report.accounts.map(a => `<div class="recon-row"><span>${esc(a.name)}</span><strong>${a.evidenceThrough ? 'Kontoudtog til og med ' + date(a.evidenceThrough) : 'Intet kontoudtog importeret'}</strong></div><p class="footnote">${esc(a.coverage.label)}. ${esc(a.coverage.detail)}</p>`).join('')}</div>
      <p class="footnote">En måned er foreløbig, indtil hver konto har et kontoudtog, der er lavet mindst syv dage efter månedens afslutning og dækker dens sidste dag. En konto uden importerede kontoudtog er undtaget. Manglende oplysninger vises som ukendte, aldrig som nul.</p>
      <p class="footnote">${esc(report.period.detail)}</p>
    </section>
    <section class="panel"><div class="section-head"><h2>Afstemning</h2>${badge(report.coverage.shortLabel, report.coverage.status !== 'complete')}</div>
      ${reconciliationRow('Indtægter', r.income)}
      ${reconciliationRow('− udgifter efter tilbagebetalinger', r.expenses)}
      ${reconciliationRow('= tilbage efter udgifter', r.netCashFlow, true)}
      ${reconciliationRow('Kategorierne summer til', r.categoryTotal)}
      <p class="section-intro">${countSentence}</p>
      <p class="footnote">De udeladte grupper tæller ikke med i indtægter og udgifter: ${esc(r.excluded.join(', ').toLowerCase())}. Derfor kan saldoene flytte sig mere end beløbet tilbage.</p>
      ${report.accounts.map(a => `<div class="recon-row"><span>${esc(a.name)}${a.balance.asOf ? ' · saldo ' + date(a.balance.asOf) : ''}</span><strong>${a.balance.amount === null ? 'Ingen saldo for måneden' : `${money(a.openingBalance)} → ${money(a.balance.amount)}`}</strong></div>`).join('')}
    </section>
    <section class="panel"><div class="section-head"><h2>Beløb uden kategori</h2>${badge(known ? countText(report.unclassified.count, 'postering', 'posteringer') : 'Antal ukendt', !known || report.unclassified.count > 0)}</div>
      <div class="unknown-grid"><div><span>Penge ind</span><strong>${money(report.unclassified.moneyIn)}</strong></div><div><span>Penge ud</span><strong>${money(report.unclassified.moneyOut)}</strong></div></div>
      <p class="section-intro">Beløbene er ikke med i indtægter, udgifter eller beløbet tilbage. Penge ind og ud vises hver for sig, så modsatrettede beløb ikke ser ud som nul.</p>
      <button class="text-button" type="button" data-detail="unknown">Se posteringerne →</button>
      <div class="route"><h3>Manglende kategorier</h3><p>${esc(route?.detail ?? '')}</p><p class="footnote">Kun til beskrivelse: prototypen kører ingen kommandoer og kan ikke rette kategorier.</p></div>
    </section>
    <section class="panel"><div class="section-head"><h2>Overførsler og rettelser</h2>${badge(known ? countText(counts.transfers + counts.adjustments, 'postering', 'posteringer') : 'Antal ukendt', !known || counts.transfers + counts.adjustments > 0)}</div>
      <p class="section-intro">${esc(report.transfers.label)} ${esc(report.transfers.detail)}</p>
      <p class="section-intro">${adjustmentSentence}</p>
      <div class="recon-row"><span>Overførsler: penge ind / ud</span><strong>${money(report.transfers.moneyIn)} / ${money(report.transfers.moneyOut)}</strong></div>
      <div class="recon-row"><span>Rettelser: penge ind / ud</span><strong>${money(report.adjustments.moneyIn)} / ${money(report.adjustments.moneyOut)}</strong></div>
      ${known ? '<button class="text-button" type="button" data-detail="transfers">Se overførsler →</button>' : ''}
      ${known && report.adjustments.count ? '<button class="text-button" type="button" data-detail="adjustments">Se rettelser →</button>' : ''}
    </section>`;
}

/* --- simple view --------------------------------------------------------- */

function simpleView() {
  return `<div class="period-line"><h2>${esc(report.period.label)}</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    ${summaryFigures()}
    ${coverageLine(report.coverage)}
    <p class="summary-note">${esc(simpleNotice())} <button type="button" class="text-button inline-button" data-explain>Se forklaring →</button></p>
    ${categoriesPanel(true)}`;
}

function advancedView() {
  if (tab === 'details') return detailsPanel();
  if (tab === 'checks') return checksPanel();
  return overviewPanel();
}

/* --- shell --------------------------------------------------------------- */

function renderModeBar() {
  el('mode-simple').setAttribute('aria-pressed', String(mode === 'simple'));
  el('mode-advanced').setAttribute('aria-pressed', String(mode === 'advanced'));
  el('advanced-nav').hidden = mode !== 'advanced';
  document.querySelectorAll('#advanced-nav button').forEach(button => button.setAttribute('aria-current', button.dataset.tab === tab ? 'page' : 'false'));
  const picker = el('publication-picker');
  picker.hidden = mode !== 'advanced';
  el('publication').innerHTML = data.publications.map(p => `<option value="${esc(p.publicationId)}" ${p.publicationId === publicationId ? 'selected' : ''}>${esc(p.label)}${p.isCurrent ? '' : ' · fortid'}</option>`).join('');
}

function renderPublicationBar() {
  const bar = el('publication-bar');
  if (publication.isCurrent) {
    bar.hidden = true;
    bar.innerHTML = '';
    return;
  }
  bar.hidden = false;
  bar.innerHTML = `<div><strong>Fortidig visning: ${esc(publication.label)}</strong><span class="publication-kind">${esc(publication.kindLabel)}</span><p>${esc(publication.detail)}</p></div><button id="back-to-current" type="button" class="button-secondary">Tilbage til nutiden</button>`;
}

function renderFooter() {
  el('footer').innerHTML = `Prototype uden redigering · ${esc(data.currency ?? 'DKK')} · Opdigtet eksempel med opdigtet nutid ${esc(data.syntheticNow)}<br>Visning: ${esc(publication.label)}${publication.isCurrent ? '' : ` (${esc(publication.kindLabel)})`} · overblikket og grafen følger dit valg af konti.`;
}

function closeDetail() {
  if (el('detail').open) el('detail').close();
}

function render() {
  if (!data) return;
  publication = data.publications.find(p => p.publicationId === publicationId) ?? data.publications[0];
  const ids = selectedAccountIds();
  el('scope-label').textContent = `${ids.length} ${ids.length === 1 ? 'KONTO VALGT' : 'KONTI VALGT'}`;
  el('selection-note').textContent = ids.length ? accountNames(ids) : 'Vælg mindst én konto for at se tal.';
  const wanted = el('month').value;
  el('month').innerHTML = publication.months.map(id => `<option value="${esc(id)}">${esc(monthName(id))}</option>`).join('');
  el('month').value = publication.months.includes(wanted) ? wanted : publication.defaultMonth;
  renderModeBar();
  renderPublicationBar();
  renderFooter();
  activeReports = currentView()?.reports ?? [];
  report = activeReports.find(r => r.period.id === el('month').value) ?? null;
  if (activeReports.length && trendCategory !== 'all' && !categoryUniverse().some(entry => entry.id === trendCategory)) {
    trendCategory = 'all';
    trendResetNotice = 'Den valgte kategori findes ikke i denne visning. Viser alle kategorier.';
  } else {
    trendResetNotice = '';
  }
  if (!report) {
    el('content').innerHTML = '<p class="empty">Ingen konti valgt. Vælg én eller flere konti ovenfor.</p>';
    return;
  }
  el('source-label').textContent = `${data.label} · ${publication.label}`;
  el('content').innerHTML = mode === 'simple' ? simpleView() : advancedView();
}

function setMode(next) {
  mode = next;
  if (next === 'simple') {
    tab = 'overview';
  }
  closeDetail();
  render();
  (next === 'simple' ? el('mode-simple') : el('mode-advanced')).focus();
}

function setTab(next) {
  tab = next;
  closeDetail();
  render();
  document.querySelector(`#advanced-nav button[data-tab="${next}"]`)?.focus();
}

function choosePublication(next) {
  publicationId = next;
  rangeMode = 'rolling';
  customStart = '';
  customEnd = '';
  closeDetail();
  render();
}

function openBudgetDemo() {
  const current = data.publications.find(page => page.publicationId === data.currentPublicationId) ?? publication;
  document.querySelectorAll('#account-options input').forEach(input => { input.checked = true; });
  publicationId = current.publicationId;
  const months = (current.budgetExample?.reports ?? []).map(entry => entry.month);
  if (months.length && !months.includes(el('month').value)) el('month').value = months[months.length - 1];
  tab = 'overview';
  spendingMode = 'budget';
  closeDetail();
  render();
  document.querySelector('[data-spending-mode="budget"]')?.focus();
}

/* --- dialogs ------------------------------------------------------------- */

function transactions(rows) {
  return rows.length ? rows.map(t => `<article class="transaction"><div class="row"><span class="row-title">${esc(t.description)}</span>${transactionAmount(t.amount)}</div><small>${date(t.date)} · ${esc(t.accountName)} · ${esc(t.kindLabel)}</small>${t.transferLabel ? `<small>${esc(t.transferLabel)}</small>` : ''}</article>`).join('') : '<p class="empty">Ingen posteringer i denne visning.</p>';
}

function transactionAmount(value) {
  // The sign is the display of one transaction, not a calculation of report figures.
  const amount = Number(value);
  const direction = amount > 0 ? 'money-in' : amount < 0 ? 'money-out' : 'money-zero';
  const label = amount > 0 ? 'Penge ind' : amount < 0 ? 'Penge ud' : 'Ingen bevægelse';
  const formatted = new Intl.NumberFormat('da-DK', {minimumFractionDigits:2,maximumFractionDigits:2,signDisplay:'exceptZero'}).format(amount).replace('-', '−');
  return `<span class="transaction-amount ${direction}" aria-label="${label}: ${formatted} kr."><strong class="row-amount">${formatted} kr.</strong></span>`;
}

function coverageNote(coverage) {
  return `<div class="trust ${coverage.status === 'complete' ? 'complete' : ''}"><strong>${esc(coverage.label)}</strong><p>${esc(coverage.detail)}</p></div>`;
}

function showDetail({title, amount, summary, rows, coverage = report.coverage, guidance = ''}) {
  el('detail-content').innerHTML = `<h2 id="detail-title">${esc(title)}</h2><p class="section-intro">${esc(report.period.label)} · ${esc(report.period.statusLabel)} · ${esc(publication.label)}</p>${amount === undefined ? '' : `<div class="detail-value">${money(amount)}</div>`}${coverageNote(coverage)}<div class="detail-summary">${summary}</div>${guidance}<p class="footnote">På hver postering betyder + penge ind og − penge ud.</p>${transactions(rows)}`;
  el('detail').showModal();
  el('detail').scrollTop = 0;
}

function showMetric(name) {
  const m = report.measures;
  if (name === 'net') showDetail({title:'Tilbage efter udgifter',amount:m.netCashFlow,summary:`<p>Indtægter: ${money(m.income)}</p><p>Udgifter: ${money(m.expenses)}</p><p>Andel af indtægterne tilbage: ${m.savingsRate === null?'Kan ikke vises uden kendte, positive indtægter':new Intl.NumberFormat('da-DK',{maximumFractionDigits:2}).format(Number(m.savingsRate))+' %'}</p><p>Posteringer uden kategori og andre rettelser er ikke med. Beløbet viser ikke en afstemt ændring i kontienes saldi.</p>`,rows:[]});
  if (name === 'income') showDetail({title:'Indtægter',amount:m.income,summary:'Indtægter med kategori, fratrukket eventuelle tilbagebetalte indtægter. Overførsler og beløb uden kategori er ikke med.',rows:report.incomeTransactions});
  if (name === 'expenses') showDetail({title:'Udgifter',amount:m.expenses,summary:'Køb og betalinger fratrukket penge tilbage i udgiftskategorierne. Overførsler og beløb uden kategori er ikke med.',rows:report.categories.flatMap(c => c.transactions)});
}

function showGroup(name) {
  const group = {unknown:report.unclassified,transfers:report.transfers,adjustments:report.adjustments}[name];
  const titles = {unknown:'Beløb uden kategori',transfers:'Mellem vores konti',adjustments:'Andre rettelser'};
  const guidance = name === 'unknown' && group.count
    ? `<section class="detail-help" aria-labelledby="category-help-title"><h3 id="category-help-title">Kan jeg tilføje en kategori?</h3><p>Kategorier kan ikke ændres i denne prototype. I kan fortsætte afprøvningen uden at rette dem.</p><p>${esc(group.operatorRoute?.detail ?? '')}</p></section>`
    : '';
  showDetail({title:titles[name],summary:`<p>Penge ind: ${money(group.moneyIn)}</p><p>Penge ud: ${money(group.moneyOut)}</p><p>${esc(group.detail)}</p>`,rows:group.transactions,guidance});
}

/* --- events -------------------------------------------------------------- */

el('login-form').addEventListener('submit', event => {
  event.preventDefault();
  el('login').hidden = true;
  el('app').hidden = false;
  el('mode-simple').focus();
});

el('logout').addEventListener('click', () => {
  closeDetail();
  el('app').hidden = true;
  el('login').hidden = false;
  el('passphrase').value = '';
  el('passphrase').focus();
});

el('mode-simple').addEventListener('click', () => setMode('simple'));
el('mode-advanced').addEventListener('click', () => setMode('advanced'));
document.querySelectorAll('#advanced-nav button').forEach(button => button.addEventListener('click', () => setTab(button.dataset.tab)));
el('publication').addEventListener('change', event => choosePublication(event.target.value));
el('month').addEventListener('change', render);
el('account-options').addEventListener('change', render);
el('select-all').addEventListener('click', () => {document.querySelectorAll('#account-options input').forEach(input => {input.checked = true;}); render();});
el('close-detail').addEventListener('click', () => el('detail').close());
el('detail').addEventListener('click', event => {if(event.target === el('detail')){const r = el('detail').getBoundingClientRect(); if(event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) el('detail').close();}});

el('publication-bar').addEventListener('click', event => {
  if (event.target.id === 'back-to-current') choosePublication(data.currentPublicationId);
});

el('content').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.hasAttribute('data-explain')) { setMode('advanced'); setTab('checks'); return; }
  if (button.dataset.spendingMode) { spendingMode = button.dataset.spendingMode; render(); document.querySelector(`[data-spending-mode="${spendingMode}"]`)?.focus(); return; }
  if (button.hasAttribute('data-budget-demo')) { openBudgetDemo(); return; }
  if (button.dataset.budgetCategory) {
    const c = currentBudget().rows.find(row => row.id === button.dataset.budgetCategory);
    const actual = report.categories.find(a => a.id === c.categoryId);
    showDetail({title:c.name+' · mod budget',amount:c.remaining,summary:`<p><strong>${Number(c.remaining)<0?'Budgettet er overskredet.':'Beregnet beløb tilbage.'}</strong> Opdigtet budget; ukendte posteringer kan ændre resultatet.</p><p>Fra tidligere måneder: ${money(c.opening)}</p><p>Denne måneds budget: ${money(c.allocated)}</p><p>Til rådighed: ${money(c.available)}</p><p>Brugt efter tilbagebetalinger: ${money(c.actual)}</p><p>${c.carryForward?'Føres videre til næste måned: '+money(c.carriedForward):'Restbeløbet føres ikke videre i kategorien. Bidrag til Opsparing i forhold til planen: '+money(c.savingsImpact)}</p>${c.carryForward?'<p>Ferie får 3.000 kr. hver måned. I dette eksempel er der ingen kendte ferieudgifter i månederne. Beløbet er øremærket og indgår ikke i den almindelige opsparing. Startbeløbet er sat til nul.</p>':''}`,rows:actual?.transactions ?? []});
    return;
  }
  if (button.dataset.month) { el('month').value = button.dataset.month; render(); el('month').focus(); return; }
  if (button.dataset.category) {
    const c = report.categories.find(row => row.id === button.dataset.category);
    showDetail({title:c.name,amount:c.netSpending,summary:`<p>Køb og betalinger: <strong>${money(c.purchases)}</strong></p><p>Penge tilbage: <strong>${money(c.refunds)}</strong></p><p>Udgifter efter tilbagebetalinger: <strong>${money(c.netSpending)}</strong></p>`,rows:c.transactions,coverage:c.coverage});
    return;
  }
  if (button.dataset.account) {
    const a = report.accounts.find(row => row.id === button.dataset.account);
    showDetail({title:a.name+' · bevægelser',amount:a.balance.amount,coverage:a.coverage,summary:`<p>${a.balance.asOf?'Saldo senest oplyst af banken: '+date(a.balance.asOf):'Ingen oplyst saldo.'}</p><p>${a.evidenceThrough?'Kontoudtog til og med '+date(a.evidenceThrough)+'.':'Der er ikke importeret et kontoudtog for denne konto.'}</p><p>${a.quietConfirmed?'Ingen bevægelser — bekræftet af kontooplysningerne.':esc(a.activityNote)}</p>`,rows:a.transactions});
    return;
  }
  const name = button.dataset.detail;
  if (name === 'income' || name === 'expenses' || name === 'net') showMetric(name);
  else if (name) showGroup(name);
});

el('content').addEventListener('change', event => {
  if (event.target.id === 'trend-range') rangeMode = event.target.value;
  else if (event.target.id === 'trend-category') trendCategory = event.target.value;
  else if (event.target.id === 'trend-start') customStart = event.target.value;
  else if (event.target.id === 'trend-end') customEnd = event.target.value;
  else return;
  render();
});

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {if (data && !el('detail').open) render();}, 150);
});

fetch('/example.json').then(response => {
  if (!response.ok) throw new Error('Rapporten kunne ikke hentes');
  return response.json();
}).then(fixture => {
  data = fixture;
  publicationId = data.currentPublicationId;
  el('account-options').innerHTML = data.availableAccounts.map(a => `<label><input type="checkbox" value="${esc(a.id)}" checked> ${esc(a.name)} <small>${esc(a.ownerLabel)}</small></label>`).join('');
  render();
}).catch(() => {
  el('content').innerHTML = '<p class="error">Rapporteksemplet kunne ikke hentes. Start prototypen med kommandoen i vejledningen (README.md), og genindlæs siden.</p>';
});
