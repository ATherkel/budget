/* THROWAWAY rendering only. All totals, categories and trust states are frozen report fields. */
const el = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => value === null ? 'Not available' : new Intl.NumberFormat('en-DK', {minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value)) + ' kr.';
const date = value => value ? new Intl.DateTimeFormat('en-GB', {day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')) : 'No date available';
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
    <section class="metrics" aria-label="Monthly totals">
      <button class="metric" data-detail="income"><span class="label">Income ↗</span><strong class="value">${money(m.income)}</strong><small>${esc(report.measureNote)} · See entries</small></button>
      <button class="metric" data-detail="expenses"><span class="label">Expenses ↘</span><strong class="value">${money(m.expenses)}</strong><small>After refunds · ${esc(report.measureNote)}</small></button>
      <button class="metric accent" data-detail="net"><span class="label">Left after expenses</span><strong class="value">${money(m.netCashFlow)}</strong><small>Income minus expenses · ${esc(report.measureNote)}</small></button>
    </section>
    <p class="summary-note">These totals exclude money that still needs a category and transfers between the two accounts. “Left after expenses” is net cash flow (also called savings here), not the change in your bank balances.</p>
    <div class="columns"><div>
      <section class="panel" aria-labelledby="spending-title"><div class="section-head"><h2 id="spending-title">Where the money went</h2>${badge(report.coverage.shortLabel, report.coverage.status!=='complete')}</div><p class="section-intro">Choose a category to see the entries behind it. Refunds reduce spending.</p>
      ${report.categories.map(c => `<button class="category" data-category="${esc(c.id)}"><span class="row"><span class="row-title">${esc(c.name)}</span><span class="row-amount">${money(c.netSpending)}<span class="arrow">›</span></span></span>${c.netRefund?'<small>More refunded than spent this month</small>':`<span class="bar-track" aria-hidden="true"><span class="bar" style="display:block;--width:${c.barPercent}%"></span></span>`}</button>`).join('') || '<p class="empty">No categorized spending in the available entries.</p>'}
      <p class="footnote">${esc(report.coverage.detail)}</p></section>
      <section class="panel unknown"><div class="section-head"><h2>Still needs a category</h2>${badge(`${report.unclassified.count} entries`,report.unclassified.count>0)}</div><p class="section-intro">These amounts are outside income, expenses and money left. Money in and out are shown separately.</p><div class="unknown-grid"><div><span>Money in</span><strong>${money(report.unclassified.moneyIn)}</strong></div><div><span>Money out</span><strong>${money(report.unclassified.moneyOut)}</strong></div></div><button class="text-button" data-detail="unknown">See these entries →</button></section>
    </div><aside>
      <section class="panel"><h2>In the accounts</h2><p class="section-intro">Last bank-stated balances in this month, or carried forward from an earlier date. This is money held, not monthly income.</p>
      ${report.accounts.map(a => `<article class="account"><div class="row"><div><h3>${esc(a.name)} <span class="ownership">${esc(a.ownerLabel)}</span></h3>${badge(a.coverage.label,a.coverage.status!=='complete')}</div><div><strong class="balance">${money(a.balance.amount)}</strong><small>${a.balance.asOf ? 'Last stated '+date(a.balance.asOf) : 'No balance for this month'}</small></div></div><p>${esc(a.coverage.detail)}</p>${a.quietConfirmed?'<p class="quiet">No activity this month — confirmed by the account evidence.</p>':''}<button class="text-button" data-account="${esc(a.id)}">See account activity →</button></article>`).join('')}</section>
      <section class="panel"><h3>Between our accounts</h3><p class="transfer-note">${esc(report.transfers.label)} These moves do not count as income or spending.</p><button class="text-button" data-detail="transfers">See transfers →</button></section>
      ${report.adjustments.count?`<section class="panel"><h3>Other corrections</h3><p class="section-intro">${report.adjustments.count} entries are outside income and expenses.</p><button class="text-button" data-detail="adjustments">See corrections →</button></section>`:''}
      <p class="footnote">${esc(data.notice)}</p>
    </aside></div>`;
}
function transactions(rows) {
  return rows.length ? rows.map(t => `<article class="transaction"><div class="row"><span class="row-title">${esc(t.description)}</span><span class="row-amount ${t.kind==='refund'?'refund':''}">${money(t.amount)}</span></div><small>${date(t.date)} · ${esc(t.accountName)} · ${esc(t.kindLabel)}</small></article>`).join('') : '<p class="empty">No entries in this view.</p>';
}
function showDetail({title,amount,summary,rows,coverage=report.coverage}) {
  el('detail-content').innerHTML = `<h2 id="detail-title">${esc(title)}</h2><p class="section-intro">${esc(report.period.label)} · ${esc(report.period.statusLabel)}</p>${amount===undefined?'':`<div class="detail-value">${money(amount)}</div>`}${coverageNote(coverage)}<div class="detail-summary">${summary}</div><p class="footnote">Entry amounts: minus means money out; plus/positive means money in.</p>${transactions(rows)}`;
  el('detail').showModal();
  el('detail').scrollTop = 0;
}
el('content').addEventListener('click', event => {
  const button=event.target.closest('button');
  if(!button)return;
  if(button.dataset.category){
    const c=report.categories.find(c=>c.id===button.dataset.category);
    showDetail({title:c.name,amount:c.netSpending,summary:`<p>Purchases: <strong>${money(c.purchases)}</strong></p><p>Refunds received: <strong>${money(c.refunds)}</strong></p><p>Spending after refunds: <strong>${money(c.netSpending)}</strong></p>`,rows:c.transactions});
  }else if(button.dataset.account){
    const a=report.accounts.find(a=>a.id===button.dataset.account);
    showDetail({title:a.name+' · activity',amount:a.balance.amount,coverage:a.coverage,summary:`<p>${a.balance.asOf?'Last bank-stated balance: '+date(a.balance.asOf):'No reported balance.'}</p><p>${a.quietConfirmed?'No activity — confirmed by the account evidence.':esc(a.activityNote)}</p>`,rows:a.transactions});
  }else{
    const name=button.dataset.detail;
    if(name==='net')showDetail({title:'Left after expenses',amount:report.measures.netCashFlow,summary:`<p>Income: ${money(report.measures.income)}</p><p>Expenses: ${money(report.measures.expenses)}</p><p>Savings rate: ${report.measures.savingsRate===null?'Not available because income is not positive':esc(report.measures.savingsRate)+'%'}</p><p>Unknown entries and other corrections are excluded. This is not a reconciled change in account balances.</p>`,rows:[]});
    if(name==='income')showDetail({title:'Income',amount:report.measures.income,summary:'Classified income, including any returned income. Transfers and unclassified money are excluded.',rows:report.incomeTransactions});
    if(name==='expenses')showDetail({title:'Expenses',amount:report.measures.expenses,summary:'Purchases less refunds in expense categories. Transfers and unclassified money are excluded.',rows:report.categories.flatMap(c=>c.transactions)});
    const group=({unknown:report.unclassified,transfers:report.transfers,adjustments:report.adjustments})[name];
    if(group)showDetail({title:({unknown:'Still needs a category',transfers:'Between our accounts',adjustments:'Other corrections'})[name],summary:`<p>Money in: ${money(group.moneyIn)}</p><p>Money out: ${money(group.moneyOut)}</p><p>${esc(group.detail)}</p>`,rows:group.transactions});
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
Promise.all(['/reports.json','/example.json'].map(url=>fetch(url).then(response=>{if(!response.ok)throw new Error('Report unavailable');return response.json();}))).then(([local,example])=>{
  datasets={local,example};
  if(local.kind==='synthetic'){el('dataset').value='example';el('dataset').querySelector('[value="local"]').remove();}
  chooseDataset();
}).catch(()=>{el('content').innerHTML='<p class="error">The frozen report could not be loaded. Start the prototype with the command in its README, then reload this page.</p>';});
