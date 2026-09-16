/* THROWAWAY rendering only. All totals, categories and trust states are frozen report fields. */
const el = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => value === null ? 'Ukendt' : new Intl.NumberFormat('da-DK', {minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value)) + ' kr.';
const date = value => value ? new Intl.DateTimeFormat('da-DK', {day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')) : 'Dato mangler';
const badge = (label, warning=true) => `<span class="badge ${warning?'warning':''}">${esc(label)}</span>`;
let datasets, data, report, activeReports = [], rangeMode = 'rolling', customStart = '', customEnd = '', spendingMode = 'amounts';

function currentBudget(){
  return data.budgetExample?.accountIds.join('|')===selectedAccountIds().join('|') ? data.budgetExample.reports.find(b=>b.month===report.period.id) : null;
}
function budgetPanel(){
  const b=currentBudget();
  if(!b)return `<p class="empty">Budgeteksemplet er opdigtet og gælder begge eksempelkonti samlet. Der er endnu ikke et budget for dette datagrundlag eller kontovalg.</p><button class="text-button" data-budget-demo>Åbn opdigtet budget · begge konti →</button>`;
  const rows=b.rows.map(c=>{
    const over=Number(c.remaining)<0;
    const percent=Math.max(0,Math.min(100,Number(c.actual)/Number(c.available)*100));
    return `<button class="category budget-category ${over?'over-budget':''}" data-budget-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}${c.carryForward?'<small>Opspares til senere</small>':''}</span><span class="row-amount">${money(c.actual)}<span class="arrow">›</span></span></span><span class="budget-subrow"><span>af ${money(c.available)} til rådighed</span><strong>${over?'Overskredet med '+money(String(Math.abs(Number(c.remaining)))):money(c.remaining)+' tilbage'}</strong></span><span class="bar-track" aria-hidden="true"><span class="bar" style="display:block;--width:${percent}%"></span></span>${c.carryForward?`<small>${money(c.opening)} fra tidligere + ${money(c.allocated)} denne måned</small>`:''}</button>`;
  }).join('');
  return `<p class="budget-notice">${esc(data.budgetExample.notice)}</p><p class="section-intro">Brugt efter tilbagebetalinger sammenholdt med beløbet til rådighed. Tryk på en kategori for regnestykket.</p>${rows}<section class="savings-summary" aria-labelledby="savings-heading"><h3 id="savings-heading">Opsparing efter øremærkning</h3>${badge(report.period.statusLabel,report.period.provisional)} ${badge(report.coverage.shortLabel,report.coverage.status!=='complete')}<p class="footnote">${esc(report.coverage.detail)} Beløb uden kategori kan ændre opsparingen.</p><p>Månedens bidrag til almindelig opsparing, efter ${money(b.earmarked)} til Ferie.</p><div class="row"><span>Budget</span><strong>${money(b.plannedSavings)}</strong></div><div class="row"><span>Ud fra kendte posteringer</span><strong>${money(b.actualSavings)}</strong></div><p class="savings-variance ${Number(b.savingsDifference)<0?'over-budget':''}">${money(String(Math.abs(Number(b.savingsDifference))))} ${Number(b.savingsDifference)<0?'mindre':'mere'} end planlagt</p><details><summary>Hvordan hænger opsparingen sammen?</summary><p>Planlagt indtægt ${money(b.plannedIncome)} − almindelige budgetter ${money(b.plannedSpending)} − øremærket til Ferie ${money(b.earmarked)} = ${money(b.plannedSavings)}.</p><p>Indtægter minus faktiske udgifter ${money(report.measures.netCashFlow)} − månedens øremærkning ${money(b.earmarked)} = ${money(b.actualSavings)} til almindelig opsparing.</p><p>Ubrugte beløb i almindelige kategorier øger Opsparing; overskridelser reducerer den. Ændrede indtægter påvirker også Opsparing. Her er indtægten som planlagt.</p><p>Beløbet er månedens bidrag, ikke en kontosaldo eller den samlede opsparing. Ukendte posteringer og andre rettelser er ikke med.</p></details></section><p class="footnote">Ferie er en øremærkning på tværs af de to konti, ikke en ekstra bankkonto eller en udgift. Kun kategorier markeret “Opspares til senere” fører restbeløb videre. De viste ferierester forudsætter, at de ukendte posteringer ikke er ferieudgifter.</p>`;
}

function selectedAccountIds() {
  return [...document.querySelectorAll('#account-options input:checked')].map(input=>input.value).sort();
}

function monthIndex(id){const [year,month]=id.split('-').map(Number);return year*12+month-1;}
function monthId(index){return `${Math.floor(index/12)}-${String(index%12+1).padStart(2,'0')}`;}
function monthLabel(id){return new Intl.DateTimeFormat('da-DK',{month:'short',year:'2-digit',timeZone:'UTC'}).format(new Date(id+'-01T12:00:00Z'));}
function trendPanel(){
  const last=data.asOf.slice(0,7);
  const end=rangeMode==='custom'?(customEnd||last):last;
  const start=rangeMode==='custom'?(customStart||monthId(monthIndex(last)-11)):rangeMode==='year'?last.slice(0,4)+'-01':monthId(monthIndex(last)-11);
  const earliest=monthId(Math.min(monthIndex(last)-11,...data.reports.map(r=>monthIndex(r.period.id))));
  const monthOptions=selected=>Array.from({length:monthIndex(last)-monthIndex(earliest)+1},(_,i)=>{const id=monthId(monthIndex(earliest)+i);return `<option value="${id}" ${id===selected?'selected':''}>${new Intl.DateTimeFormat('da-DK',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(id+'-01T12:00:00Z'))}</option>`;}).join('');
  const controls=`<div class="trend-controls"><label>Periode<select id="trend-range"><option value="rolling" ${rangeMode==='rolling'?'selected':''}>Seneste 12 måneder</option><option value="year" ${rangeMode==='year'?'selected':''}>Indeværende år</option><option value="custom" ${rangeMode==='custom'?'selected':''}>Egen periode</option></select></label>${rangeMode==='custom'?`<label>Fra måned<select id="trend-start">${monthOptions(start)}</select></label><label>Til måned<select id="trend-end">${monthOptions(end)}</select></label>`:''}</div>`;
  const firstIndex=monthIndex(start),lastIndex=monthIndex(end);
  let body;
  if(!/^\d{4}-\d{2}$/.test(start)||!/^\d{4}-\d{2}$/.test(end)||firstIndex>lastIndex||lastIndex-firstIndex>119||end>last){
    body='<p class="empty" role="status">Vælg en startmåned før eller lig med slutmåneden, senest september 2026. Prototypen viser højst 120 måneder ad gangen.</p>';
  }else{
    const points=Array.from({length:lastIndex-firstIndex+1},(_,i)=>{const id=monthId(firstIndex+i);return {id,report:activeReports.find(r=>r.period.id===id)};});
    const series=[{key:'income',label:'Indtægter',color:'#176b53'},{key:'expenses',label:'Udgifter',color:'#a44828'},{key:'netCashFlow',label:'Tilbage',color:'#345da8'}];
    // Kun grafens koordinater beregnes her. Alle økonomiske værdier læses fra rapporterne.
    const values=points.flatMap(p=>series.map(s=>p.report?.measures[s.key])).filter(v=>v!=null).map(Number);
    const low=Math.min(0,...values),high=Math.max(0,...values),span=high-low||1;
    const width=Math.max(280,Math.min(1000,document.querySelector('main').clientWidth-44)),height=250,left=72,right=16,top=18,bottom=38;
    const x=i=>left+(points.length===1?.5:i/(points.length-1))*(width-left-right);
    const y=value=>top+(high-Number(value))/span*(height-top-bottom);
    const ticks=[...new Set([low,0,high])];
    const grid=ticks.map(v=>`<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end">${new Intl.NumberFormat('da-DK',{maximumFractionDigits:0}).format(v)}</text>`).join('');
    const stride=Math.max(1,Math.ceil(points.length/(width<500?4:9)));
    const labels=points.map((p,i)=>(i%stride===0||i===points.length-1)?`<text x="${x(i)}" y="${height-10}" text-anchor="${i===points.length-1?'end':i===0?'start':'middle'}">${monthLabel(p.id)}</text>`:'').join('');
    const paths=series.map(s=>{
      let previous=null;return points.map((p,i)=>{
        const value=p.report?.measures[s.key];
        if(value==null){previous=null;return '';}
        const provisional=p.report.period.provisional||p.report.coverage.status!=='complete';
        const point={x:x(i),y:y(value),provisional};
        const line=previous?`<line x1="${previous.x}" y1="${previous.y}" x2="${point.x}" y2="${point.y}" stroke="${s.color}" stroke-width="2" ${provisional||previous.provisional?'stroke-dasharray="5 4"':''}/>`:'';
        const title=`${monthLabel(p.id)} · ${s.label}: ${money(value)} · ${p.report.period.statusLabel} · ${p.report.coverage.label}`;
        previous=point;
        return `${line}<circle cx="${point.x}" cy="${point.y}" r="3.5" fill="${provisional?'white':s.color}" stroke="${s.color}" stroke-width="2" tabindex="0" aria-label="${esc(title)}"><title>${esc(title)}</title></circle>`;
      }).join('');
    }).join('');
    const chart=values.length?`<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="chart-title chart-description"><title id="chart-title">Indtægter, udgifter og beløb tilbage fra ${monthLabel(start)} til ${monthLabel(end)}</title><desc id="chart-description">Månedstal for de valgte konti. De præcise beløb og datagrundlaget findes i tabellen nedenfor.</desc>${grid}${paths}${labels}</svg>`:'<p class="empty">Der er ingen månedstal for de valgte konti i perioden. Manglende oplysninger vises ikke som nul.</p>';
    const rows=points.map(p=>`<tr><th scope="row">${p.report?`<button class="text-button" data-month="${p.id}">${monthLabel(p.id)}</button>`:monthLabel(p.id)}</th>${series.map(s=>`<td>${money(p.report?.measures[s.key]??null)}</td>`).join('')}<td>${p.report?`${esc(p.report.period.statusLabel)}. ${esc(p.report.coverage.detail)}`:'Ingen rapportoplysninger for denne måned.'}</td></tr>`).join('');
    body=`<p class="section-intro">${monthLabel(start)} – ${monthLabel(end)} · kr. pr. måned · samme kontovalg som overblikket</p><div class="chart-legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${s.label}</span>`).join('')}</div>${chart}<p class="footnote">Stiplede linjer og hule punkter: foreløbige eller ufuldstændige tal. Huller: oplysninger mangler. Ukendte beløb og interne overførsler er ikke med i nøgletallene.</p><details class="chart-table"><summary>Se månedstal og datagrundlag</summary><div class="table-scroll"><table><thead><tr><th>Måned</th><th>Indtægter</th><th>Udgifter</th><th>Tilbage</th><th>Datagrundlag</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
  }
  return `<section class="panel trend-panel" aria-labelledby="trend-heading"><div class="section-head"><h2 id="trend-heading">Udvikling over tid</h2>${controls}</div>${body}<p class="footnote">Perioderne tager udgangspunkt i eksemplets dato: 15. september 2026.</p></section>`;
}

function coverageNote(coverage) {
  return `<div class="trust ${coverage.status==='complete'?'complete':''}"><strong>${esc(coverage.label)}</strong><p>${esc(coverage.detail)}</p></div>`;
}
function render() {
  const ids = selectedAccountIds();
  el('scope-label').textContent = `${ids.length} ${ids.length===1?'KONTO VALGT':'KONTI VALGT'}`;
  el('selection-note').textContent = ids.length ? data.availableAccounts.filter(a=>ids.includes(a.id)).map(a=>a.name).join(' · ') : 'Vælg mindst én konto for at se tal.';
  activeReports = data.views.find(view=>view.accountIds.join('|')===ids.join('|'))?.reports ?? [];
  report = activeReports.find(r => r.period.id === el('month').value);
  el('source-label').textContent = data.label;
  if(!report){el('content').innerHTML='<p class="empty">Ingen konti valgt. Vælg én eller flere konti ovenfor.</p>';return;}
  const m = report.measures;
  el('content').innerHTML = `
    <div class="period-line"><h2>${esc(report.period.label)}</h2>${badge(report.period.statusLabel, report.period.provisional)}</div>
    <details class="trust ${report.coverage.status==='complete'?'complete':''}"><summary>${esc(report.coverage.label)}</summary><p>${esc(report.coverage.detail)}</p><p>${esc(data.notice)}</p><p>${esc(report.period.detail)}</p></details>
    <section class="metrics" aria-label="Månedens samlede beløb">
      <button class="metric" data-detail="income"><span class="label">Indtægter ↗</span><strong class="value">${money(m.income)}</strong><small>${esc(report.measureNote)} · Se posteringer</small></button>
      <button class="metric" data-detail="expenses"><span class="label">Udgifter ↘</span><strong class="value">${money(m.expenses)}</strong><small>Efter tilbagebetalinger · ${esc(report.measureNote)}</small></button>
      <button class="metric accent" data-detail="net"><span class="label">Tilbage efter udgifter</span><strong class="value">${money(m.netCashFlow)}</strong><small>Indtægter minus udgifter · ${esc(report.measureNote)}</small></button>
    </section>
    <p class="summary-note">Beløb uden kategori og interne overførsler er ikke med i tallene. Det gælder også, når kun den ene konto i en overførsel er valgt. “Tilbage efter udgifter” er indtægter minus udgifter, før penge øremærkes til fx ferie. Det er ikke det samme som ændringen i jeres saldi.</p>
    ${trendPanel()}
    <div class="columns"><div>
      <section class="panel" aria-labelledby="spending-title"><div class="section-head"><h2 id="spending-title">Hvor blev pengene af?</h2>${badge(report.coverage.shortLabel, report.coverage.status!=='complete')}</div><div class="spending-switch" role="group" aria-label="Visning af kategorier"><button data-spending-mode="amounts" aria-pressed="${spendingMode==='amounts'}">Beløb</button><button data-spending-mode="budget" aria-pressed="${spendingMode==='budget'}">Mod budget</button></div>
      ${spendingMode==='budget'?budgetPanel():`<p class="section-intro">Vælg en kategori for at se posteringerne bag beløbet. Penge tilbage trækkes fra udgifterne.</p>
      ${report.categories.map(c => `<button class="category" data-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}</span><span class="row-amount">${money(c.netSpending)}<span class="arrow">›</span></span></span>${c.netRefund?'<small>Mere tilbagebetalt end brugt denne måned</small>':`<span class="bar-track" aria-hidden="true"><span class="bar" style="display:block;--width:${c.barPercent}%"></span></span>`}</button>`).join('') || `<p class="empty">${report.coverage.status==='no_data'?'Der mangler oplysninger om udgifter for de valgte konti.':'Ingen udgifter med kategori blandt de viste posteringer.'}</p>`}
      `}
      <p class="footnote">${esc(report.coverage.detail)}</p></section>
      <section class="panel unknown"><div class="section-head"><h2>Mangler en kategori</h2>${badge(report.coverage.status==='no_data'?'Antal ukendt':`${report.unclassified.count} posteringer`,report.unclassified.count>0||report.coverage.status==='no_data')}</div><p class="section-intro">Disse beløb er ikke med i indtægter, udgifter eller beløbet tilbage. Penge ind og ud vises hver for sig.</p><div class="unknown-grid"><div><span>Penge ind</span><strong>${money(report.unclassified.moneyIn)}</strong></div><div><span>Penge ud</span><strong>${money(report.unclassified.moneyOut)}</strong></div></div><button class="text-button" data-detail="unknown">Se posteringerne →</button>${report.unclassified.count?'<p class="footnote">Kategorier kan ikke ændres i denne prototype.</p>':''}</section>
    </div><aside>
      <section class="panel"><h2>På kontiene</h2><p class="section-intro">De seneste saldi oplyst af banken i måneden eller videreført fra en tidligere dato. Det er beløb på kontiene, ikke månedens indtægter.</p>
      ${report.accounts.map(a => `<article class="account"><div class="row"><div><h3>${esc(a.name)} <span class="ownership">${esc(a.ownerLabel)}</span></h3>${badge(a.coverage.label,a.coverage.status!=='complete')}</div><div><strong class="balance">${money(a.balance.amount)}</strong><small>${a.balance.asOf ? 'Senest oplyst '+date(a.balance.asOf) : 'Saldo mangler for denne måned'}</small></div></div><p>${esc(a.coverage.detail)}</p>${a.quietConfirmed?'<p class="quiet">Ingen bevægelser denne måned — bekræftet af kontooplysningerne.</p>':''}<button class="text-button" data-account="${esc(a.id)}">Se kontobevægelser →</button></article>`).join('')}</section>
      <section class="panel"><h3>Mellem vores konti</h3><p class="transfer-note">${esc(report.transfers.label)} Disse overførsler tæller hverken som indtægter eller udgifter.</p><button class="text-button" data-detail="transfers">Se overførsler →</button></section>
      ${report.adjustments.count?`<section class="panel"><h3>Andre rettelser</h3><p class="section-intro">${report.adjustments.count} posteringer er ikke med i indtægter og udgifter.</p><button class="text-button" data-detail="adjustments">Se rettelser →</button></section>`:''}
      <p class="footnote">${esc(data.notice)}</p>
    </aside></div>`;
}
function transactions(rows) {
  return rows.length ? rows.map(t => `<article class="transaction"><div class="row"><span class="row-title">${esc(t.description)}</span>${transactionAmount(t.amount)}</div><small>${date(t.date)} · ${esc(t.accountName)} · ${esc(t.kindLabel)}</small></article>`).join('') : '<p class="empty">Ingen posteringer i denne visning.</p>';
}
function transactionAmount(value) {
  // Fortegn er visning af den enkelte postering, ikke beregning af rapporttal.
  const amount = Number(value);
  const direction = amount > 0 ? 'money-in' : amount < 0 ? 'money-out' : 'money-zero';
  const label = amount > 0 ? 'Penge ind' : amount < 0 ? 'Penge ud' : 'Ingen bevægelse';
  const formatted = new Intl.NumberFormat('da-DK', {minimumFractionDigits:2,maximumFractionDigits:2,signDisplay:'exceptZero'}).format(amount).replace('-', '−');
  return `<span class="transaction-amount ${direction}" aria-label="${label}: ${formatted} kr."><strong class="row-amount">${formatted} kr.</strong></span>`;
}
function showDetail({title,amount,summary,rows,coverage=report.coverage,guidance=''}) {
  el('detail-content').innerHTML = `<h2 id="detail-title">${esc(title)}</h2><p class="section-intro">${esc(report.period.label)} · ${esc(report.period.statusLabel)}</p>${amount===undefined?'':`<div class="detail-value">${money(amount)}</div>`}${coverageNote(coverage)}<div class="detail-summary">${summary}</div>${guidance}<p class="footnote">På hver postering betyder + penge ind og − penge ud.</p>${transactions(rows)}`;
  el('detail').showModal();
  el('detail').scrollTop = 0;
}
el('content').addEventListener('click', event => {
  const button=event.target.closest('button');
  if(!button)return;
  if(button.dataset.spendingMode){spendingMode=button.dataset.spendingMode;render();document.querySelector(`[data-spending-mode="${spendingMode}"]`).focus();return;}
  if(button.hasAttribute('data-budget-demo')){el('dataset').value='example';chooseDataset();document.querySelector('[data-spending-mode="budget"]').focus();return;}
  if(button.dataset.budgetCategory){
    const c=currentBudget().rows.find(c=>c.id===button.dataset.budgetCategory);
    const actual=report.categories.find(a=>a.id===c.categoryId);
    showDetail({title:c.name+' · mod budget',amount:c.remaining,summary:`<p><strong>${Number(c.remaining)<0?'Budgettet er overskredet.':'Beregnet beløb tilbage.'}</strong> Opdigtet budget; ukendte posteringer kan ændre resultatet.</p><p>Fra tidligere måneder: ${money(c.opening)}</p><p>Denne måneds budget: ${money(c.allocated)}</p><p>Til rådighed: ${money(c.available)}</p><p>Brugt efter tilbagebetalinger: ${money(c.actual)}</p><p>${c.carryForward?'Føres videre til næste måned: '+money(c.carriedForward):'Restbeløbet føres ikke videre i kategorien. Bidrag til Opsparing i forhold til planen: '+money(c.savingsImpact)}</p>${c.carryForward?'<p>Ferie får 3.000 kr. hver måned. I dette eksempel er der ingen kendte ferieudgifter i juli, august eller september. Beløbet er øremærket og indgår ikke i den almindelige opsparing. Startbeløbet i juli er sat til nul.</p>':''}`,rows:actual?.transactions??[]});return;
  }
  if(button.dataset.month){el('month').value=button.dataset.month;render();el('month').focus();return;}
  if(button.dataset.category){
    const c=report.categories.find(c=>c.id===button.dataset.category);
    showDetail({title:c.name,amount:c.netSpending,summary:`<p>Køb og betalinger: <strong>${money(c.purchases)}</strong></p><p>Penge tilbage: <strong>${money(c.refunds)}</strong></p><p>Udgifter efter tilbagebetalinger: <strong>${money(c.netSpending)}</strong></p>`,rows:c.transactions});
  }else if(button.dataset.account){
    const a=report.accounts.find(a=>a.id===button.dataset.account);
    showDetail({title:a.name+' · bevægelser',amount:a.balance.amount,coverage:a.coverage,summary:`<p>${a.balance.asOf?'Saldo senest oplyst af banken: '+date(a.balance.asOf):'Ingen oplyst saldo.'}</p><p>${a.quietConfirmed?'Ingen bevægelser — bekræftet af kontooplysningerne.':esc(a.activityNote)}</p>`,rows:a.transactions});
  }else{
    const name=button.dataset.detail;
    if(name==='net')showDetail({title:'Tilbage efter udgifter',amount:report.measures.netCashFlow,summary:`<p>Indtægter: ${money(report.measures.income)}</p><p>Udgifter: ${money(report.measures.expenses)}</p><p>Andel af indtægterne tilbage: ${report.measures.savingsRate===null?'Kan ikke vises uden kendte, positive indtægter':new Intl.NumberFormat('da-DK',{maximumFractionDigits:2}).format(Number(report.measures.savingsRate))+' %'}</p><p>Posteringer uden kategori og andre rettelser er ikke med. Beløbet viser ikke en afstemt ændring i kontienes saldi.</p>`,rows:[]});
    if(name==='income')showDetail({title:'Indtægter',amount:report.measures.income,summary:'Indtægter med kategori, fratrukket eventuelle tilbagebetalte indtægter. Overførsler og beløb uden kategori er ikke med.',rows:report.incomeTransactions});
    if(name==='expenses')showDetail({title:'Udgifter',amount:report.measures.expenses,summary:'Køb og betalinger fratrukket penge tilbage i udgiftskategorierne. Overførsler og beløb uden kategori er ikke med.',rows:report.categories.flatMap(c=>c.transactions)});
    const group=({unknown:report.unclassified,transfers:report.transfers,adjustments:report.adjustments})[name];
    if(group)showDetail({title:({unknown:'Mangler en kategori',transfers:'Mellem vores konti',adjustments:'Andre rettelser'})[name],summary:`<p>Penge ind: ${money(group.moneyIn)}</p><p>Penge ud: ${money(group.moneyOut)}</p><p>${esc(group.detail)}</p>`,rows:group.transactions,guidance:name==='unknown'&&group.count?'<section class="detail-help" aria-labelledby="category-help-title"><h3 id="category-help-title">Kan jeg tilføje en kategori?</h3><p>Kategorier kan ikke ændres i denne prototype. I kan fortsætte afprøvningen uden at rette dem.</p><p>Fortæl gerne, hvilken kategori I forventer for en postering, I genkender. Hvordan kategorier skal rettes i den færdige løsning, er endnu ikke fastlagt.</p></section>':''});
  }
});
el('close-detail').addEventListener('click',()=>el('detail').close());
el('detail').addEventListener('click', event=>{if(event.target===el('detail')){const r=el('detail').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)el('detail').close();}});
el('month').addEventListener('change',render);
function chooseDataset(){
  if(!datasets)return; // A selection during loading is applied when the fixtures arrive.
  const previous=el('month').value;
  data=datasets[el('dataset').value];
  el('account-options').innerHTML=data.availableAccounts.map(a=>`<label><input type="checkbox" value="${esc(a.id)}" checked> ${esc(a.name)} <small>${esc(a.ownerLabel)}</small></label>`).join('');
  el('month').innerHTML=data.reports.map(r=>`<option value="${r.period.id}">${esc(r.period.label)}</option>`).join('');
  el('month').value=data.reports.some(r=>r.period.id===previous)?previous:data.defaultMonth;
  render();
}
el('account-options').addEventListener('change',render);
el('select-all').addEventListener('click',()=>{document.querySelectorAll('#account-options input').forEach(input=>input.checked=true);render();});
el('content').addEventListener('change',event=>{
  if(event.target.id==='trend-range')rangeMode=event.target.value;
  else if(event.target.id==='trend-start')customStart=event.target.value;
  else if(event.target.id==='trend-end')customEnd=event.target.value;
  else return;
  render();
});
el('dataset').addEventListener('change',chooseDataset);
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(data&&!el('detail').open)render();},150);});
Promise.all(['/reports.json','/example.json'].map(url=>fetch(url).then(response=>{if(!response.ok)throw new Error('Rapporten kunne ikke hentes');return response.json();}))).then(([local,example])=>{
  datasets={local,example};
  if(local.kind==='synthetic'){el('dataset').value='example';el('dataset').querySelector('[value="local"]').remove();}
  chooseDataset();
}).catch(()=>{el('content').innerHTML='<p class="error">Rapporteksemplet kunne ikke hentes. Start prototypen med kommandoen i vejledningen (README.md), og genindlæs siden.</p>';});
