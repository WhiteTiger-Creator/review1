(() => {
  const campaign = document.documentElement.dataset.campaign;
  const pct = value => `${(value * 100).toFixed(2)}%`;
  const cell = value => { const td = document.createElement('td'); td.textContent = String(value); return td; };
  fetch(`/v1/releases/current?campaign=${encodeURIComponent(campaign)}`, {cache: 'no-store'})
    .then(response => { if (!response.ok) throw new Error(`release ${response.status}`); return response.json(); })
    .then(report => {
      const state = document.getElementById('release-state'); state.textContent = `${report.release_status.toUpperCase()} · revision ${report.model_revision}`; state.dataset.status = report.release_status;
      const metrics = [['Coverage', pct(report.coverage)], ['Balanced accuracy', pct(report.balanced_accuracy)], ['Brier', report.brier_score.toFixed(6)], ['ECE', report.ece.toFixed(6)], ['FPR gap', report.fpr_gap.toFixed(6)], ['Max drift', report.max_feature_drift.toFixed(6)]];
      const grid = document.getElementById('metric-grid'); metrics.forEach(([name,value]) => { const article=document.createElement('article'); const h=document.createElement('h2'); h.textContent=name; const p=document.createElement('p'); p.textContent=value; article.append(h,p); grid.append(article); });
      const gateBody=document.querySelector('#gate-table tbody'); Object.entries(report.gates).forEach(([name,passed]) => { const tr=document.createElement('tr'); tr.append(cell(name.replaceAll('_',' ')),cell(passed?'pass':'fail')); tr.dataset.passed=String(passed); gateBody.append(tr); });
      const cohortBody=document.querySelector('#cohort-table tbody'); report.cohorts.forEach(item => { const tr=document.createElement('tr'); tr.append(cell(item.site_id),cell(item.count),cell(pct(item.coverage)),cell(pct(item.tpr)),cell(pct(item.fpr))); cohortBody.append(tr); });
      const sampleBody=document.querySelector('#sample-table tbody'); report.samples.forEach(item => { const tr=document.createElement('tr'); const decision=item.abstained?'abstain':String(item.prediction); tr.append(cell(item.sample_id),cell(item.site_id),cell(item.label),cell(item.probability.toFixed(6)),cell(decision)); sampleBody.append(tr); });
    })
    .catch(error => { const state=document.getElementById('release-state'); state.textContent=`Release unavailable: ${error.message}`; state.dataset.status='error'; });
})();
