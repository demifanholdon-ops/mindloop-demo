import './character.js';
import {live} from './live.js?v=20260924-live';
import {keyOf,parseDate,shiftDay,shiftMonth,monthCells,focusRatio,createDemo} from './data.js';

const app = document.querySelector('#app');
const today = keyOf(new Date());
const storageKey = 'mindloop-ui-V2.0';
const isolated = new URLSearchParams(location.search).has('isolated');
const storage = () => isolated ? sessionStorage : localStorage;
// LAN HTTP previews on phones may not expose crypto.randomUUID (secure contexts only).
// These IDs identify local demo items; they are not credentials or security tokens.
const newEventId = () => globalThis.crypto?.randomUUID?.() ?? `event-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
let data = live.enabled ? {tasks:{},events:[],focus:{[today]:{total:0,returned:0}}} : createDemo(today);
try { const saved = !live.enabled && JSON.parse(storage().getItem(storageKey)); if (saved?.version===2 && saved.anchor===today && Array.isArray(saved.events) && saved.tasks && saved.focus) data=saved; } catch { /* Local storage is optional for the prototype. */ }
const selected = {focus:today,start:today,remember:today};
let screen='home', toastTimer;
const escape = text => String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const weekday = key => ['周日','周一','周二','周三','周四','周五','周六'][parseDate(key).getDay()];
const dateText = key => {const d=parseDate(key);return `${d.getMonth()+1}月${d.getDate()}日`;};
const monthText = key => {const d=parseDate(key);return `${d.getFullYear()}年 <strong>${d.getMonth()+1}月</strong>`;};
const sample = live.enabled ? '<span class="preview-badges"><span class="sample-badge">实时连接</span><span class="version-badge">V2.0</span></span>' : '<span class="preview-badges"><span class="sample-badge">示例数据</span><a class="version-badge" href="../../versions.html" aria-label="V2.0，查看与切换 UI 版本">V2.0</a></span>';
const arrow = (direction,action,label) => `<button class="arrow-button ${direction}" data-action="${action}" aria-label="${label}"><span aria-hidden="true">${direction==='prev'?'‹':'›'}</span></button>`;
const tasksFor = key => data.tasks[key] || [];
const stepsFor = key => tasksFor(key).flatMap(t=>t.steps);
const eventsFor = key => data.events.filter(e=>!e.cancelled&&(e.date===key||(e.recurrence==='daily'&&e.date&&e.date<=key)));
function notify(message) { const t=document.querySelector('#toast'); t.textContent=message; t.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('visible'),2400); }
function save() { try { storage().setItem(storageKey,JSON.stringify(data)); return true; } catch { notify('本机存储不可用，当前修改仅在本次打开时保留'); return false; } }
function header(title,description) { return `<header class="detail-hero"><div class="app-bar"><button class="back-button" data-nav="home" aria-label="返回首页"><span aria-hidden="true">‹</span> 返回</button><h1 tabindex="-1">${title}</h1>${sample}</div><mindloop-character app compact></mindloop-character><p>${description}</p></header>`; }
function bottomNav() {return `<nav class="bottom-nav" aria-label="功能导航">${[['focus','◎','注意力回归'],['start','✓','迈出一步'],['remember','▤','帮我记住']].map(([id,icon,title])=>`<button data-nav="${id}" class="${screen===id?'active':''}" ${screen===id?'aria-current="page"':''}><span class="nav-symbol" aria-hidden="true">${icon}</span><span>${title}</span></button>`).join('')}</nav>`;}
function home() {
  const steps=stepsFor(today), record=data.focus[today]||{total:0,returned:0};
  return `<section class="home-screen"><header class="home-bar"><a class="wordmark" href="#home">MindLoop<span>启念</span></a>${sample}</header><div class="welcome"><p>${dateText(today)}，${weekday(today)}</p><h1 tabindex="-1">慢慢来，<br>我陪你一起。</h1></div>
    <div class="character-stage"><mindloop-character app></mindloop-character>
      <button class="gesture-hint hint-top" data-gesture="remember"><span>拍拍头</span><strong>帮我记住</strong><i aria-hidden="true">↓</i></button>
      <button class="gesture-hint hint-left" data-gesture="focus"><span>拽左脸</span><strong>注意力回归</strong><i aria-hidden="true">←</i></button>
      <button class="gesture-hint hint-right" data-gesture="start"><span>拽右脸</span><strong>迈出一步</strong><i aria-hidden="true">→</i></button>
    </div><p class="home-caption">拽一拽，拍一拍。<span>从一件小事开始。</span></p>
    <section class="today-card" aria-labelledby="today-heading"><div class="section-heading"><h2 id="today-heading">今天的小小进展</h2><span>每一步都算数</span></div><div class="today-stats"><button data-nav="focus"><strong>${record.returned}<small> / ${record.total}</small></strong><span>确认回归</span></button><button data-nav="start"><strong>${steps.filter(s=>s.done).length}<small> / ${steps.length}</small></strong><span>完成小步</span></button><button data-nav="remember"><strong>${eventsFor(today).length}<small> 件</small></strong><span>帮你记住</span></button></div></section><p class="prototype-note">交互预览 · 数据仅作界面演示</p></section>`;
}
function calendar(mode) {
  const key=selected[mode], cells=monthCells(key);
  return `<div class="month-toolbar"><h2>${monthText(key)}</h2><div class="date-controls"><button class="today-button" data-action="today">今天</button>${arrow('prev','prev-month','上个月')}${arrow('next','next-month','下个月')}</div></div><div class="weekdays" aria-hidden="true">${['一','二','三','四','五','六','日'].map(d=>`<span>${d}</span>`).join('')}</div><div class="calendar ${mode==='remember'?'event-calendar':'ring-calendar'}" role="group" aria-label="${parseDate(key).getFullYear()}年${parseDate(key).getMonth()+1}月${mode==='focus'?'回归记录':'待办提醒'}日历">${cells.map(date=>{
    if(!date)return '<div class="empty-cell" aria-hidden="true"></div>';
    const day=parseDate(date).getDate(), chosen=date===key, current=date===today;
    if(mode==='focus') {
      const r=data.focus[date], ratio=focusRatio(r), label=r?`偏移${r.total}次，确认回归${r.returned}次`:'无记录';
      return `<button class="calendar-day ${chosen?'selected':''} ${current?'is-today':''}" data-date="${date}" aria-pressed="${chosen}" aria-label="${dateText(date)}，${label}"><span class="day-ring ${r?'has-record':''}"><svg viewBox="0 0 44 44" aria-hidden="true"><circle class="ring-track" cx="22" cy="22" r="18"/><circle class="ring-fill" cx="22" cy="22" r="18" pathLength="100" stroke-dasharray="${ratio*100} 100"/></svg><span>${day}</span></span>${current?'<i class="today-dot" aria-hidden="true"></i>':''}</button>`;
    }
    const entries=eventsFor(date);
    return `<button class="calendar-day ${chosen?'selected':''} ${current?'is-today':''}" data-date="${date}" aria-pressed="${chosen}" aria-label="${dateText(date)}，${entries.length?escape(entries.map(e=>e.title).join('、')):'没有事项'}"><span class="date-number">${day}</span><span class="cell-events">${entries.slice(0,2).map(e=>`<span class="mini-event ${e.kind} ${e.done?'done':''}">${escape(e.title)}</span>`).join('')}${entries.length>2?`<span class="more-events">+${entries.length-2}件</span>`:''}</span></button>`;
  }).join('')}</div>`;
}
function focus() {
  const key=selected.focus,r=data.focus[key];
  return `${header('注意力回归','走远一点，也可以慢慢回来。')}<section class="content-sheet">${calendar('focus')}<div class="calendar-legend"><span><i class="legend-ring full"></i>全部回归</span><span><i class="legend-ring half"></i>部分回归</span><span><i class="legend-ring"></i>无记录</span></div><section class="day-detail"><div class="section-heading"><h3>${dateText(key)}<span> · ${weekday(key)}</span></h3>${r?`<span class="soft-badge">${Math.round(focusRatio(r)*100)}% 已回归</span>`:''}</div>${r?`<div class="focus-summary"><div><strong>${r.total}</strong><span>偏移记录</span></div><span class="summary-arrow" aria-hidden="true">→</span><div class="green"><strong>${r.returned}</strong><span>确认回归</span></div><div><strong>${r.total-r.returned}</strong><span>未确认回归</span></div></div><p class="encouragement">${r.returned===r.total?'每一次走远，你都找到了回来的路。':'已经找回了 '+r.returned+' 次专注。剩下的，不着急。'}</p>`:'<div class="empty-state"><span class="empty-mark">○</span><h3>这一天，还没有记录</h3><p>有了偏移与回归记录，小圆环就会在这里出现。</p></div>'}<p class="metric-note">圆环 = 已确认回归 ÷ 偏移记录<br>未确认不等于没有回归，提醒次数不计作回归。</p></section></section>${bottomNav()}`;
}
function start() {
  const key=selected.start,groups=tasksFor(key),steps=stepsFor(key),done=steps.filter(s=>s.done).length;
  return `${header('迈出一步','不用一下做完，先做眼前这一小步。')}<section class="content-sheet tasks-sheet"><div class="day-toolbar">${arrow('prev','prev-day','前一天')}<div><h2>${parseDate(key).getFullYear()}年${dateText(key)}</h2><p>${weekday(key)}${key===today?' · 今天':''}</p></div>${arrow('next','next-day','后一天')}</div><div class="progress-heading"><p>这一天，迈出了 <strong>${done}</strong> 小步</p><button class="today-button" data-action="today">回到今天</button></div>${groups.length?groups.map(group=>`<section class="task-group"><div class="task-group-title"><h3>${escape(group.title)}</h3><span>${group.steps.filter(s=>s.done).length} / ${group.steps.length}</span></div><p>${escape(group.note)}</p><ul class="step-list">${group.steps.map((step,i)=>`<li class="${step.done?'completed':''}"><span class="step-index">${String(i+1).padStart(2,'0')}</span><span class="step-copy"><strong>${escape(step.title)}</strong><small>${step.done?`${step.time || '刚刚'} · 已完成`:'留给接下来的你'}</small></span><button class="check-button ${step.done?'checked':''}" data-task="${group.id}" data-step="${step.id}" role="checkbox" aria-checked="${step.done}" aria-label="${escape(step.title)}，${step.done?'已完成，点击撤销':'未完成，点击完成'}"><span aria-hidden="true">${step.done?'✓':''}</span></button></li>`).join('')}</ul></section>`).join(''):'<div class="empty-state"><span class="empty-mark">↗</span><h3>这天还没有小步记录</h3><p>被拆解的行动和完成情况，会留在这里。</p></div>'}<p class="gentle-note">${steps.length&&done===steps.length?'这些小事，都被你做到了。':'小到可以开始，就是很好的第一步。'}</p></section>${bottomNav()}`;
}
function remember() {
  const key=selected.remember,entries=eventsFor(key);
  return `${header('帮我记住','先放在我这里，给脑袋留点空隙。')}<section class="content-sheet memory-sheet">${calendar('remember')}<div class="calendar-legend event-legend"><span><i class="event-dot todo"></i>Todo 待办</span><span><i class="event-dot reminder"></i>Reminder 提醒</span></div><section class="day-detail"><div class="section-heading"><h3>${dateText(key)}<span> · ${weekday(key)}</span></h3><span class="item-count">${entries.length} 件小事</span></div>${entries.length?`<ul class="event-list">${entries.map(e=>`<li class="${e.done?'completed':''}"><span class="event-kind ${e.kind}">${e.kind==='reminder'?escape(e.time):'TODO'}</span><span class="event-copy"><strong>${escape(e.title)}</strong><small>${e.kind==='reminder'?(live.enabled?'Reminder · 到时提醒':'Reminder · 演示提醒'):e.done?'已完成':'Todo · 待完成'}</small></span>${e.kind==='todo'?`<button class="check-button ${e.done?'checked':''}" data-event="${e.id}" role="checkbox" aria-checked="${e.done}" aria-label="${escape(e.title)}，${e.done?'已完成，点击撤销':'未完成，点击完成'}"><span aria-hidden="true">${e.done?'✓':''}</span></button>`:live.enabled?`<button class="reminder-label" data-edit-item="${e.id}" aria-label="编辑${escape(e.title)}">编辑</button>`:'<span class="reminder-label">提醒</span>'}</li>`).join('')}</ul>`:'<div class="empty-state compact"><h3>这一天，先留一点空白</h3><p>想到什么，就记在这里。</p></div>'}<button class="add-button" data-action="add"><span aria-hidden="true">＋</span>记一件事</button></section></section>${bottomNav()}`;
}
const renders={home,focus,start,remember};
function render(shouldFocus=false) {
  const oldScroll=app.scrollTop;
  app.innerHTML = `<div class="screen ${screen==='home'?'is-home':'is-detail'}">${renders[screen]()}</div>`;
  if(live.enabled){const note=app.querySelector('.prototype-note');if(note)note.textContent='语音与画面识别后，小步骤会更新在这里。';}
  app.scrollTop=shouldFocus?0:oldScroll;
  if(shouldFocus) app.querySelector('h1')?.focus({preventScroll:true});
}
function navigate(next) { if(!(next in renders))return;if(next===screen)return;location.hash=next; }
function route() { const next=location.hash.slice(1);screen=next in renders?next:'home';render(true); }
window.addEventListener('hashchange',route);
app.addEventListener('character-navigate',e=> {if(screen==='home')navigate(e.detail.destination);});
app.addEventListener('click',e=>{
  const button=e.target.closest('button');if(!button)return;
  if(live.enabled&&button.dataset.editItem){live.editItem(button.dataset.editItem);return;}
  if(button.dataset.nav){navigate(button.dataset.nav);return;}
  if(button.dataset.gesture){app.querySelector('mindloop-character').activate(button.dataset.gesture);return;}
  if(button.dataset.date){selected[screen]=button.dataset.date;render();app.querySelector(`[data-date="${selected[screen]}"]`)?.focus({preventScroll:true});return;}
  if(live.enabled&&button.dataset.step){const group=tasksFor(selected.start).find(g=>g.id===button.dataset.task);const step=group?.steps.find(s=>s.id===button.dataset.step);if(!step)return;button.disabled=true;live.changeSteps(group.id,[{step_id:step.id,done:!step.done}]).catch(error=>{button.disabled=false;notify(error.message);});return;}
  if(live.enabled&&button.dataset.event){const event=data.events.find(t=>t.id===button.dataset.event);button.disabled=true;live.changeItem(event.id,{done:!event.done}).catch(error=>{button.disabled=false;notify(error.message);});return;}
  if(button.dataset.step){const group=tasksFor(selected.start).find(g=>g.id===button.dataset.task);const step=group?.steps.find(s=>s.id===button.dataset.step);if(!step)return;step.done=!step.done;if(step.done)step.time=new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});save();render();app.querySelector(`[data-step="${step.id}"]`)?.focus({preventScroll:true});return;}
  if(button.dataset.event){const event=data.events.find(t=>t.id===button.dataset.event);event.done=!event.done;save();render();app.querySelector(`[data-event="${event.id}"]`)?.focus({preventScroll:true});return;}
  const action=button.dataset.action;
  if(action==='add'){openAdd();return;}
  if(action==='today')selected[screen]=today;
  else if(action==='prev-day'||action==='next-day')selected[screen]=shiftDay(selected[screen],action==='prev-day'?-1:1);
  else if(action==='prev-month'||action==='next-month')selected[screen]=shiftMonth(selected[screen],action==='prev-month'?-1:1);
  else return;
  render();app.querySelector(`[data-action="${action}"]`)?.focus({preventScroll:true});
});
const dialog=document.querySelector('#add-dialog'),form=document.querySelector('#add-form');
function openAdd(){form.reset();form.elements.date.value=selected.remember;document.querySelector('#time-field').hidden=true;form.elements.time.required=false;dialog.showModal();}
form.addEventListener('change',e=>{if(e.target.name==='kind'){const needsTime=form.elements.kind.value==='reminder';document.querySelector('#time-field').hidden=!needsTime;form.elements.time.required=needsTime;}});
form.querySelector('[data-close]').addEventListener('click',()=>dialog.close());
form.addEventListener('submit',e=>{
  e.preventDefault();const title=form.elements.title.value.trim();if(!title){form.elements.title.setCustomValidity('请写下要记住的事情');form.elements.title.reportValidity();return;}
  const date=form.elements.date.value,kind=form.elements.kind.value;
  if(live.enabled){const submit=form.querySelector('[type="submit"]');submit.disabled=true;live.addItem({title,date,kind,time:kind==='reminder'?form.elements.time.value:null}).then(()=>{selected.remember=date;dialog.close();render();notify('已记下');}).catch(error=>notify(error.message)).finally(()=>submit.disabled=false);return;}
  data.events.push({id:newEventId(),title,date,kind,time:kind==='reminder'?form.elements.time.value:'',done:false});
  const persisted=save();selected.remember=date;dialog.close();render();if(persisted)notify('已记在本机演示日历');
});
form.elements.title.addEventListener('input',()=>form.elements.title.setCustomValidity(''));
dialog.addEventListener('close',()=>app.querySelector('[data-action="add"]')?.focus({preventScroll:true}));
route();
if(live.enabled){
  live.onState=state=>{data=state;render();};live.onMessage=notify;
  document.querySelector('.form-note').textContent='保存到当前演示后端。实体提醒需设备连接后执行。';
  live.init();
}
