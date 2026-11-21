'use strict';
const $ = id => document.getElementById(id);
const state = {items: [], selected: null, selectedCoin: null, stats: null, serverOffset: 0, mode: 'offline', statsLoading: 0, signalName:'Signal_GFIVIP_4h'};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v, signed=false) => v == null ? '—' : `${signed && v>0?'+':''}${(v*100).toLocaleString('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2})}%`;
const price = v => v == null ? '—' : '$'+v.toLocaleString('en-US',{minimumFractionDigits:v<1?4:2,maximumFractionDigits:v<1?6:2});
const money = v => v == null ? '—' : (v>0?'+':'')+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+' USDT';
const date = ms => new Date(ms).toLocaleString('vi-VN',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' UTC';
const now = () => Date.now()+state.serverOffset;
const status = t => now() >= t.exit_ms ? 'Đã kết thúc' : 'Đang mở';
async function api(path, options) {
  const response = await fetch(path, {...options, credentials:'same-origin'});
  if (!response.ok) throw new Error(`API ${response.status}: ${path}`);
  return response.json();
}
function reportError(err) { $('error').hidden=false; $('error').textContent='Kết nối đang gián đoạn. Giữ dữ liệu gần nhất; sẽ tự thử lại. '+err.message; }

function priceChart(t) {
  const hist=(t.history||[]).slice(-17), fp=t.forecast?.points||[];
  const actual=(t.actual_path||[]).slice();
  if (t.quote && !t.quote_stale && now()<t.exit_ms && t.origin !== 'backtest') actual.push({time_ms:now(),price:t.quote.price});
  const all=[...hist.map(x=>x.price),...fp.flatMap(x=>[x.p10_price,x.p90_price]),...actual.map(x=>x.price),t.entry_price].filter(Number.isFinite);
  if (!all.length) return '';
  const low=Math.min(...all),high=Math.max(...all),pad=Math.max((high-low)*.15,high*.0004),lo=low-pad,hi=high+pad;
  const W=400,H=144,x=ms=>10+380*Math.max(0,Math.min(1,((ms-t.entry_ms)/900000+16)/32)),y=p=>H-13-(p-lo)/(hi-lo)*(H-26);
  const path=(a,key)=>a.map((p,i)=>`${i?'L':'M'}${x(p.time_ms).toFixed(2)},${y(p[key]).toFixed(2)}`).join(' ');
  const band=fp.length?path(fp,'p90_price')+' '+fp.slice().reverse().map(p=>`L${x(p.time_ms)},${y(p.p10_price)}`).join(' ')+' Z':'';
  return `<svg class="price-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Giá lịch sử, đường dự báo trung bình và vùng p10 p90">
    ${[.25,.5,.75].map(k=>`<line class="chart-grid" x1="8" y1="${H*k}" x2="394" y2="${H*k}"/>`).join('')}
    <line x1="200" y1="4" x2="200" y2="137" stroke="#ffffff18" stroke-dasharray="3 4"/>
    <path d="${band}" fill="#48dfb912"/>
    ${fp.length?`<path d="${path(fp,'p90_price')}" fill="none" stroke="#48dfb94a" stroke-dasharray="4 4"/><path d="${path(fp,'p10_price')}" fill="none" stroke="#48dfb94a" stroke-dasharray="4 4"/>`:''}
    <path d="${path(hist,'price')}" fill="none" stroke="#a8b1c3" stroke-width="1.8"/>
    <path d="${path(fp,'mean_price')}" fill="none" stroke="#48dfb9" stroke-width="2" stroke-dasharray="2 4"/>
    <path d="${path(actual,'price')}" fill="none" stroke="#7aabff" stroke-width="1.9"/>
    <circle cx="200" cy="${y(t.entry_price)}" r="3" fill="#48dfb9"/>
  </svg>`;
}
function renderCards() {
  $('cards').innerHTML=state.items.map(t=>{
    const fp=t.forecast||{}, end=fp.points?.at(-1), ended=now()>=t.exit_ms;
    return `<article class="signal-card ${state.selected===t.id?'selected':''}" data-signal="${t.id}" tabindex="0" role="button" aria-label="Xem tín hiệu ${esc(t.coin)}"><p class="eyebrow">${esc(t.signal_name||state.signalName)}</p>
      <div class="card-head"><span class="coin-icon">${esc(t.coin[0])}</span><strong>${esc(t.coin)}</strong><span class="long">▲ Long · 4h</span><span class="status ${ended?'ended':''}">${status(t)}</span></div>
      <div class="chart-wrap">${priceChart(t)}</div><div class="time-row"><span>Trước tín hiệu</span><span>Nét đứt: dự báo 4h</span></div>
      <div class="card-fields"><div class="field"><small>Giá vào tham chiếu</small><strong>${price(t.entry_price)}</strong></div><div class="field"><small>${ended?'Giá thoát thật':'Giá hiện tại'}</small><strong>${price(ended?t.exit_price:(t.quote_stale?null:t.quote?.price))}</strong></div>
      <div class="field"><small>Giá trung bình lịch sử sau 4h</small><strong class="forecast-num">${price(end?.mean_price)}</strong></div><div class="field"><small>P_up lịch sử · ${fp.sample_count||0} lệnh</small><strong>${pct(fp.p_up)}</strong></div></div>
      <div class="card-note"><span class="legend-dot"></span>${fp.scope==='same_coin'?'Lịch sử cùng coin':'Lịch sử gộp 20 coin'} · ${t.notification_live?'LIVE':'BACKTEST'}<br>Vào: ${date(t.entry_ms)}<br>Thoát: ${date(t.exit_ms)}${t.settlement==='PENDING_MARKET_DATA'?'<br>Đang chờ dữ liệu giá thoát':''}</div></article>`;
  }).join('') || '<p class="muted">Chưa có tín hiệu. Hệ thống chỉ phát sau khi nến 15m đóng đủ điều kiện.</p>';
  renderSelected();
}
function renderSelected() {
  const t=state.items.find(t=>t.id===state.selected);
  if(!t)return;
  $('selected-signal').hidden=false;
  $('selected-signal').innerHTML=`<div class="signal-context"><strong>${esc(state.signalName)} · ${esc(t.coin)} ▲ LONG · ${status(t)}</strong><p>Vào ${date(t.entry_ms)} tại ${price(t.entry_price)} · Hết hạn ${date(t.exit_ms)} · ${t.exit_price?`PnL net ${money(t.net_pnl)}`:'Chưa có kết quả quyết toán'}</p></div>`;
}
function renderNotifications() {
  $('badge').textContent=state.items.filter(t=>t.unread).length;
  $('badge').hidden=!state.items.some(t=>t.unread);
  $('notification-list').innerHTML=state.items.map(t=>`<button class="notification ${t.unread?'unread':''}" data-signal="${t.id}"><span class="row"><strong>${esc(t.coin)} ▲ LONG</strong><span class="status ${now()>=t.exit_ms?'ended':''}">${status(t)}</span></span><small>${esc(state.signalName)} · ${date(t.entry_ms)}${t.notification_live?'':' · Backtest'}</small></button>`).join('')||'<p class="muted" style="padding:18px">Chưa có tín hiệu</p>';
}
function equityChart(rows) {
  if (!rows.length) return '<p class="muted">Chưa đủ dữ liệu</p>';
  const W=1000,H=300,L=12,R=91,T=20,B=30, values=rows.map(p=>p.equity),low=Math.min(...values),high=Math.max(...values),pad=Math.max((high-low)*.14,high*.002),lo=low-pad,hi=high+pad;
  const x=i=>L+i/Math.max(1,rows.length-1)*(W-L-R),y=p=>H-B-(p-lo)/(hi-lo)*(H-T-B);
  let line='',segments=[];
  rows.forEach((r,i)=>{if(i&&r.segment!==rows[i-1].segment){segments.push(line);line='';} line+=`${line?'L':'M'}${x(i).toFixed(2)},${y(r.equity).toFixed(2)} `;});segments.push(line);
  return `<svg class="equity-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Đường cong vốn mô phỏng">${[0,.25,.5,.75,1].map(k=>{const v=lo+(hi-lo)*k;return `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="${W-R+12}" y="${y(v)+4}" fill="#9da7b9" font-size="12">$${v.toLocaleString('en-US',{maximumFractionDigits:0})}</text>`}).join('')}${segments.map(d=>`<path d="${d}" fill="none" stroke="#48dfb9" stroke-width="2.5"/>`).join('')}<circle cx="${x(rows.length-1)}" cy="${y(rows.at(-1).equity)}" r="4" fill="#48dfb9"/><text x="${L}" y="${H-4}" fill="#818ca0" font-size="11">${esc(date(rows[0].time_ms))}</text><text x="${W-R}" y="${H-4}" text-anchor="end" fill="#818ca0" font-size="11">${esc(date(rows.at(-1).time_ms))}</text></svg>`;
}
async function loadStats() {
  const revision=++state.statsLoading,coin=$('scope').value==='coin'?state.selectedCoin:null;
  const s=await api('/api/stats'+(coin?'?coin='+encodeURIComponent(coin):''));
  if(revision!==state.statsLoading)return;
  state.stats=s;
  $('detail-title').textContent=coin?`${coin} · ${state.signalName}`:`${state.signalName} · Tổng thể chiến thuật 20 coin`;
  $('n-trades').textContent=s.n_trades.toLocaleString('vi-VN');$('open-count').textContent=s.open_trades+' lệnh chưa quyết toán';
  $('gross-wr').textContent=pct(s.gross_winrate);$('gross-count').textContent=`${s.gross_wins} thắng / ${s.n_trades} lệnh`;
  $('net-profit').textContent=pct(s.net_profit,true);$('net-profit').className=s.net_profit>=0?'positive':'negative';$('pnl-usdt').textContent=money(s.net_pnl);
  $('max-dd').textContent=pct(s.max_drawdown);$('sharpe').textContent=s.sharpe_ratio==null?'—':s.sharpe_ratio.toFixed(2);$('sharpe-note').textContent=`Theo ngày UTC · ${s.sharpe_observed_daily_returns} ngày quan sát`;
  $('equity-chart').innerHTML=equityChart(s.equity_curve);
  $('stats-caption').textContent=s.data_as_of_ms?`Backtest liên tục: ${date(s.data_start_ms)} → ${date(s.data_as_of_ms)} · Chi phí tổng 10 bps`:'Mẫu tham chiếu gốc 180 ngày · Chi phí tổng 10 bps';
  $('capital-note').textContent=(coin?'Hiệu suất riêng coin được chia cho mốc 500 USDT để thể hiện đóng góp. ':'Vốn chung ban đầu 10.000 USDT, cố định 500 USDT/lệnh, không chồng lệnh trong cùng coin. ')+`WR và Net PnL chỉ tính lệnh đã quyết toán; DD/Sharpe dùng equity MTM 15m. Hệ thống tự chạy bù toàn bộ lịch sử từ 25/04/2026 và tiếp tục cập nhật. Lệnh chạy bù là kết quả mô phỏng, không phải thông báo đã được gửi trước đây.`+(s.marks_quality?.missing_forward_marks?' Đang thiếu mốc giá thực: Max DD/Sharpe hiện chưa đầy đủ.':'');
}
async function refresh() {
  const data=await api('/api/notifications');state.serverOffset=data.server_time_ms-Date.now();state.items=data.items;
  renderCards();renderNotifications();$('error').hidden=true;
  if(state.selected&&!state.items.some(t=>t.id===state.selected)){$('selected-signal').hidden=true;state.selected=null;}
}
async function selectSignal(id) {
  const t=await api('/api/signals/'+encodeURIComponent(id));state.selected=id;state.selectedCoin=t.coin;
  await api('/api/notifications/'+encodeURIComponent(id)+'/read',{method:'POST'});
  const coinOption=$('scope').querySelector('option[value="coin"]');
  coinOption.disabled=false;coinOption.textContent=`Coin đang xem · ${t.coin}`;
  $('scope-hint').textContent=`Báo cáo riêng ${t.coin} hoặc toàn bộ chiến thuật 20 coin.`;
  $('scope').value='coin';
  $('selected-signal').hidden=false;$('selected-signal').innerHTML=`<div class="signal-context"><strong>${esc(t.coin)} ▲ LONG · ${status(t)}</strong><p>Vào ${date(t.entry_ms)} tại ${price(t.entry_price)} · Hết hạn ${date(t.exit_ms)} · ${t.exit_price?`PnL net ${money(t.net_pnl)}`:'Chưa có kết quả quyết toán'}</p></div>`;
  $('notifications').hidden=true;$('bell').setAttribute('aria-expanded','false');
  await Promise.all([refresh(),loadStats()]);$('detail').scrollIntoView({behavior:'smooth',block:'start'});
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,6500);}
async function health(){const h=await api('/api/health');state.mode=h.mode;const phase=h.history?.phase;const syncing=['downloading','replaying'].includes(phase);$('feed').textContent=h.mode==='offline'?'Snapshot · '+(h.data_as_of_ms?date(h.data_as_of_ms):'mẫu gốc'):syncing?'Đang đồng bộ lịch sử…':h.feed_stale||h.worker.feed_status!=='ok'?'Dữ liệu đang gián đoạn':!h.data_current?'Đang cập nhật nến mới…':'Live · đã đồng bộ';$('feed').className='feed '+(h.mode==='live'&&h.data_current&&!h.feed_stale&&h.worker.feed_status==='ok'?'live':'');}
async function main(){
  const model=await api('/api/model');state.signalName=model.signal_name;
  $('bell').onclick=()=>{const open=$('notifications').hidden;$('notifications').hidden=!open;$('bell').setAttribute('aria-expanded',String(open));};
  $('scope').onchange=()=>loadStats().catch(reportError);
  document.addEventListener('click',e=>{const card=e.target.closest('[data-signal]');if(card)selectSignal(card.dataset.signal).catch(reportError);});
  document.addEventListener('keydown',e=>{const card=e.target.closest('[data-signal]');if(card&&(e.key==='Enter'||e.key===' ')){e.preventDefault();selectSignal(card.dataset.signal).catch(reportError);}if(e.key==='Escape')$('notifications').hidden=true;});
  await Promise.all([refresh(),loadStats(),health()]);
  const stream=new EventSource('/api/events');
  stream.addEventListener('snapshot',()=>Promise.all([refresh(),loadStats()]).catch(reportError));
  stream.addEventListener('signal.opened',e=>{const v=JSON.parse(e.data);if(now()-v.entry_ms<120000)toast(`${state.signalName} · ${v.coin}: LONG 4h mới`);Promise.all([refresh(),loadStats()]).catch(reportError);});
  stream.addEventListener('history.updated',()=>Promise.all([refresh(),loadStats(),health()]).catch(reportError));
  stream.addEventListener('signal.ended',()=>Promise.all([refresh(),loadStats()]).catch(reportError));
  stream.addEventListener('stats.updated',()=>loadStats().catch(reportError));
  stream.addEventListener('equity.updated',()=>loadStats().catch(reportError));
  stream.addEventListener('quotes',e=>{const v=JSON.parse(e.data);state.serverOffset=v.server_time_ms-Date.now();for(const t of state.items){t.quote=v.quotes[t.coin];t.quote_stale=!t.quote||now()-t.quote.received_ms>20000||now()-t.quote.exchange_ms>20000;}renderCards();renderNotifications();});
  stream.onerror=()=>{$('feed').textContent='Đang kết nối lại luồng tín hiệu';$('feed').className='feed';};
  setInterval(()=>{refresh().catch(reportError);health().catch(reportError);},15000);
  setInterval(()=>loadStats().catch(reportError),60000);
  setInterval(()=>{$('clock').textContent=new Date(now()).toLocaleTimeString('vi-VN',{timeZone:'UTC'})+' UTC';renderNotifications();renderSelected();document.querySelectorAll('.signal-card').forEach(el=>{const t=state.items.find(t=>t.id===el.dataset.signal);if(t){const badge=el.querySelector('.status');badge.textContent=status(t);badge.classList.toggle('ended',now()>=t.exit_ms);}});},1000);
}
main().catch(reportError);
