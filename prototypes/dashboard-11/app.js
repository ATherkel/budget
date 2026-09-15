/* THROWAWAY rendering only. All totals, categories and trust states are frozen report fields. */
const el = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => value === null ? 'Ukendt' : new Intl.NumberFormat('da-DK', {minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value)) + ' kr.';
const date = value => value ? new Intl.DateTimeFormat('da-DK', {day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')) : 'Dato mangler';
const badge = (label, warning=true) => `<span class="badge ${warning?'warning':''}">${esc(label)}</span>`;
let datasets, data, report;

function coverageNote(coverage) {
  return `<div class="trust ${coverage.status==='complete'?'complete':''}"><strong>${esc(coverage.label)}</strong><p>${esc(coverage.detail)}</p></div>`;
}
function render() {
  report = data.reports.find(r => r.period.id === el('month').value);
  el('source-label').textContent = data.label;
  const m = report.measures;
  el('content').innerHTML = `
    <div class="period-line"><h2>${esc(report.period.label)}</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    <details class="trust ${report.coverage.status==='complete'?'complete':''}"><summary>${esc(report.coverage.label)}</summary><p>${esc(report.coverage.detail)}</p><p>${esc(data.notice)}</p><p>${esc(report.period.detail)}</p></details>
    <section class="metrics" aria-label="Månedens samlede beløb">
      <button class="metric" data-detail="income"><span class="label">Indtægter ↗</span><strong class="value">${money(m.income)}</strong><small>${esc(report.measureNote)} · Se posteringer</small></button>
      <button class="metric" data-detail="expenses"><span class="label">Udgifter ↘</span><strong class="value">${money(m.expenses)}</strong><small>Efter tilbagebetalinger · ${esc(report.measureNote)}</small></button>
      <button class="metric accent" data-detail="net"><span class="label">Tilbage efter udgifter</span><strong class="value">${money(m.netCashFlow)}</strong><small>Indtægter minus udgifter · ${esc(report.measureNote)}</small></button>
    </section>
    <p class="summary-note">Beløb uden kategori og overførsler mellem de to konti er ikke med i tallene. “Tilbage efter udgifter” er indtægter minus udgifter — her også kaldet opsparing. Det er ikke det samme som ændringen i jeres saldi.</p>
    <div class="columns"><div>
      <section class="panel" aria-labelledby="spending-title"><div class="section-head"><h2 id="spending-title">Hvor blev pengene af?</h2>${badge(report.coverage.shortLabel, report.coverage.status!=='complete')}</div><p class="section-intro">Vælg en kategori for at se posteringerne bag beløbet. Penge tilbage trækkes fra udgifterne.</p>
      ${report.categories.map(c => `<button class="category" data-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}</span><span class="row-amount">${money(c.netSpending)}<span class="arrow">›</span></span></span>${c.netRefund?'<small>Mere tilbagebetalt end brugt denne måned</small>':`<span class="bar-track" aria-hidden="true"><span class="bar" style="display:block;--width:${c.barPercent}%"></span></span>`}</button>`).join('') || '<p class="empty">Ingen udgifter med kategori blandt de viste posteringer.</p>'}
      <p class="footnote">${esc(report.coverage.detail)}</p></section>
      <section class="panel unknown"><div class="section-head"><h2>Mangler en kategori</h2>${badge(`${report.unclassified.count} posteringer`,report.unclassified.count>0)}</div><p class="section-intro">Disse beløb er ikke med i indtægter, udgifter eller beløbet tilbage. Penge ind og ud vises hver for sig.</p><div class="unknown-grid"><div><span>Penge ind</span><strong>${money(report.unclassified.moneyIn)}</strong></div><div><span>Penge ud</span><strong>${money(report.unclassified.moneyOut)}</strong></div></div><button class="text-button" data-detail="unknown">Se posteringerne →</button></section>
    </div><aside>
      <section class="panel"><h2>På kontiene</h2><p class="section-intro">De seneste saldi oplyst af banken i måneden eller videreført fra en tidligere dato. Det er beløb på kontiene, ikke månedens indtægter.</p>
      ${report.accounts.map(a => `<article class="account"><div class="row"><div><h3>${esc(a.name)} <span class="ownership">${esc(a.ownerLabel)}</span></h3>${badge(a.coverage.label,a.coverage.status!=='complete')}</div><div><strong class="balance">${money(a.balance.amount)}</strong><small>${a.balance.asOf ? 'Senest oplyst '+date(a.balance.asOf) : 'Saldo mangler for denne måned'}</small></div></div><p>${esc(a.coverage.detail)}</p>${a.quietConfirmed?'<p class="quiet">Ingen bevægelser denne måned — bekræftet af kontooplysningerne.</p>':''}<button class="text-button" data-account="${esc(a.id)}">Se kontobevægelser →</button></article>`).join('')}</section>
      <section class="panel"><h3>Mellem vores konti</h3><p class="transfer-note">${esc(report.transfers.label)} Disse overførsler tæller hverken som indtægter eller udgifter.</p><button class="text-button" data-detail="transfers">Se overførsler →</button></section>
      ${report.adjustments.count?`<section class="panel"><h3>Andre rettelser</h3><p class="section-intro">${report.adjustments.count} posteringer er ikke med i indtægter og udgifter.</p><button class="text-button" data-detail="adjustments">Se rettelser →</button></section>`:''}
      <p class="footnote">${esc(data.notice)}</p>
    </aside></div>`;
}
function transactions(rows) {
  return rows.length ? rows.map(t => `<article class="transaction"><div class="row"><span class="row-title">${esc(t.description)}</span><span class="row-amount ${t.kind==='refund'?'refund':''}">${money(t.amount)}</span></div><small>${date(t.date)} · ${esc(t.accountName)} · ${esc(t.kindLabel)}</small></article>`).join('') : '<p class="empty">Ingen posteringer i denne visning.</p>';
}
function showDetail({title,amount,summary,rows,coverage=report.coverage}) {
  el('detail-content').innerHTML = `<h2 id="detail-title">${esc(title)}</h2><p class="section-intro">${esc(report.period.label)} · ${esc(report.period.statusLabel)}</p>${amount===undefined?'':`<div class="detail-value">${money(amount)}</div>`}${coverageNote(coverage)}<div class="detail-summary">${summary}</div><p class="footnote">Posteringer med minus er penge ud. Positive beløb er penge ind.</p>${transactions(rows)}`;
  el('detail').showModal();
  el('detail').scrollTop = 0;
}
el('content').addEventListener('click', event => {
  const button=event.target.closest('button');
  if(!button)return;
  if(button.dataset.category){
    const c=report.categories.find(c=>c.id===button.dataset.category);
    showDetail({title:c.name,amount:c.netSpending,summary:`<p>Køb og betalinger: <strong>${money(c.purchases)}</strong></p><p>Penge tilbage: <strong>${money(c.refunds)}</strong></p><p>Udgifter efter tilbagebetalinger: <strong>${money(c.netSpending)}</strong></p>`,rows:c.transactions});
  }else if(button.dataset.account){
    const a=report.accounts.find(a=>a.id===button.dataset.account);
    showDetail({title:a.name+' · bevægelser',amount:a.balance.amount,coverage:a.coverage,summary:`<p>${a.balance.asOf?'Saldo senest oplyst af banken: '+date(a.balance.asOf):'Ingen oplyst saldo.'}</p><p>${a.quietConfirmed?'Ingen bevægelser — bekræftet af kontooplysningerne.':esc(a.activityNote)}</p>`,rows:a.transactions});
  }else{
    const name=button.dataset.detail;
    if(name==='net')showDetail({title:'Tilbage efter udgifter',amount:report.measures.netCashFlow,summary:`<p>Indtægter: ${money(report.measures.income)}</p><p>Udgifter: ${money(report.measures.expenses)}</p><p>Andel af indtægterne tilbage: ${report.measures.savingsRate===null?'Kan ikke vises, når indtægterne er nul eller negative':new Intl.NumberFormat('da-DK',{maximumFractionDigits:2}).format(Number(report.measures.savingsRate))+' %'}</p><p>Posteringer uden kategori og andre rettelser er ikke med. Beløbet viser ikke en afstemt ændring i kontienes saldi.</p>`,rows:[]});
    if(name==='income')showDetail({title:'Indtægter',amount:report.measures.income,summary:'Indtægter med kategori, fratrukket eventuelle tilbagebetalte indtægter. Overførsler og beløb uden kategori er ikke med.',rows:report.incomeTransactions});
    if(name==='expenses')showDetail({title:'Udgifter',amount:report.measures.expenses,summary:'Køb og betalinger fratrukket penge tilbage i udgiftskategorierne. Overførsler og beløb uden kategori er ikke med.',rows:report.categories.flatMap(c=>c.transactions)});
    const group=({unknown:report.unclassified,transfers:report.transfers,adjustments:report.adjustments})[name];
    if(group)showDetail({title:({unknown:'Mangler en kategori',transfers:'Mellem vores konti',adjustments:'Andre rettelser'})[name],summary:`<p>Penge ind: ${money(group.moneyIn)}</p><p>Penge ud: ${money(group.moneyOut)}</p><p>${esc(group.detail)}</p>`,rows:group.transactions});
  }
});
el('close-detail').addEventListener('click',()=>el('detail').close());
el('detail').addEventListener('click', event=>{if(event.target===el('detail')){const r=el('detail').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)el('detail').close();}});
el('month').addEventListener('change',render);
function chooseDataset(){
  const previous=el('month').value;
  data=datasets[el('dataset').value];
  el('month').innerHTML=data.reports.map(r=>`<option value="${r.period.id}">${esc(r.period.label)}</option>`).join('');
  el('month').value=data.reports.some(r=>r.period.id===previous)?previous:data.defaultMonth;
  render();
}
el('dataset').addEventListener('change',chooseDataset);
Promise.all(['/reports.json','/example.json'].map(url=>fetch(url).then(response=>{if(!response.ok)throw new Error('Rapporten kunne ikke hentes');return response.json();}))).then(([local,example])=>{
  datasets={local,example};
  if(local.kind==='synthetic'){el('dataset').value='example';el('dataset').querySelector('[value="local"]').remove();}
  chooseDataset();
}).catch(()=>{el('content').innerHTML='<p class="error">Rapporteksemplet kunne ikke hentes. Start prototypen med kommandoen i vejledningen (README.md), og genindlæs siden.</p>';});
