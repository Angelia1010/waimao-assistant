/* 外贸订单助手 · 网页系统（原生 JS，无需构建） */
(function () {
  'use strict';

  // ------------------------------------------------------------------ 工具
  var $ = function (sel, el) { return (el || document).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function money(n, cur) { return (cur ? cur + ' ' : '') + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function startOfDay(d) { var x = new Date(d); x.setHours(0, 0, 0, 0); return x.getTime(); }
  function fmtDate(ms, withTime) {
    if (!ms) return '—';
    var d = new Date(ms);
    var s = (d.getMonth() + 1) + '/' + d.getDate();
    if (d.getFullYear() !== new Date().getFullYear()) s = d.getFullYear() + '/' + s;
    if (withTime) s += ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    return s;
  }
  function isoDate(ms) {
    if (!ms) return '';
    var d = new Date(ms);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function dueLabel(ms) {
    if (!ms) return '<span class="dim">—</span>';
    var diff = Math.round((startOfDay(ms) - startOfDay(Date.now())) / 86400000);
    if (diff < 0) return '<span class="due-late">逾期 ' + (-diff) + ' 天</span>';
    if (diff === 0) return '<span class="due-today">今天</span>';
    if (diff === 1) return '明天';
    return fmtDate(ms);
  }
  function lv(l) { return '<span class="lv lv-' + esc(l || '') + ' num">' + esc(l || '—') + '</span>'; }
  function st(s) { return s ? '<span class="st st-' + esc(s) + '">' + esc(s) + '</span>' : ''; }
  function toast(msg, err) {
    var t = document.createElement('div');
    t.className = 't' + (err ? ' err' : '');
    t.textContent = msg;
    $('#toast').appendChild(t);
    setTimeout(function () { t.remove(); }, err ? 4200 : 2400);
  }
  function copy(text) {
    var done = function () { toast('已复制'); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  }
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    ta.remove();
  }
  function draftText(d) { return String(d || '').split('\n\n💡')[0].trim(); }
  function draftTip(d) { var p = String(d || '').split('💡'); return p.length > 1 ? p[1].trim() : ''; }

  function api(method, url, body) {
    var opt = { method: method, headers: {}, credentials: 'same-origin' };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(url, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (r.status === 401 && url !== '/api/login') { state.user = null; renderLogin(); throw new Error('请先登录'); }
        if (!r.ok) throw new Error(data.error || ('请求失败（' + r.status + '）'));
        return data;
      });
    });
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>' + (label || ''); }
    else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
  }
  function fail(e) { if (e && e.message !== '请先登录') toast(e.message || '出错了', true); }

  var I = {
    home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
    leads: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    box: '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 7v10l9 4 9-4V7"/>',
    file: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>',
    bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6.5 6.5 0 0 1 3.5 6"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M4 7l8 5 8-5"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    out: '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>',
    check: '<path d="M5 12l5 5 9-10"/>'
  };
  function icon(name, size) {
    return '<svg width="' + (size || 18) + '" height="' + (size || 18) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + I[name] + '</svg>';
  }

  // ------------------------------------------------------------------ 状态
  var state = { user: null, dueCount: 0, leadsFilter: { status: '', level: '', q: '', mine: false, due: false } };
  var SOURCES = ['阿里国际站', 'WhatsApp', '展会', '官网', '邮箱', '其他'];
  var STATUSES = ['新询盘', '已报价', '跟进中', '已寄样', '已成交', '已流失'];

  // ------------------------------------------------------------------ 登录
  function renderLogin() {
    $('#root').innerHTML =
      '<div class="login"><form class="card rise" id="loginForm">' +
      '<div class="row"><div class="logo">' + icon('mail', 18).replace('currentColor', '#0B1220') + '</div><b style="font-size:16px">外贸订单助手</b></div>' +
      '<h1>登录</h1><p class="muted" style="margin:0 0 22px">账号由管理员在「成员」里创建</p>' +
      '<div class="field"><label class="f" for="lu">用户名</label><input class="input" id="lu" autocomplete="username" required></div>' +
      '<div class="field"><label class="f" for="lp">密码</label><input class="input" id="lp" type="password" autocomplete="current-password" required></div>' +
      '<div id="lerr" class="small" style="color:var(--red);min-height:20px"></div>' +
      '<button class="btn primary lg" style="width:100%;margin-top:6px" type="submit">登录</button>' +
      '<p class="small dim" style="margin:18px 0 0;text-align:center"><a href="/">返回产品介绍</a></p></form></div>';
    $('#lu').focus();
    $('#loginForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = $('button[type=submit]', e.target);
      busy(btn, true, '登录中');
      api('POST', '/api/login', { username: $('#lu').value, password: $('#lp').value }).then(function (d) {
        state.user = d.user; boot();
      }).catch(function (err) { busy(btn, false); $('#lerr').textContent = err.message; });
    });
    $('#lu').addEventListener('input', function () { $('#lerr').textContent = ''; });
    $('#lp').addEventListener('input', function () { $('#lerr').textContent = ''; });
  }

  // ------------------------------------------------------------------ 框架
  var NAV = [
    ['dashboard', '工作台', 'home'], ['leads', '询盘客户', 'leads'], ['new', '录入询盘', 'plus'],
    ['products', '产品库', 'box'], ['quotes', '报价记录', 'file'], ['notifications', '提醒', 'bell'],
    ['settings', '设置', 'gear'], ['users', '成员', 'users', true]
  ];
  function navHtml(cur) {
    return NAV.filter(function (n) { return !n[3] || state.user.role === 'admin'; }).map(function (n) {
      var count = n[0] === 'dashboard' && state.dueCount ? '<span class="count num">' + state.dueCount + '</span>' : '';
      return '<a class="nav' + (cur === n[0] ? ' on' : '') + '" href="#/' + n[0] + '">' + icon(n[2]) + '<span>' + n[1] + '</span>' + count + '</a>';
    }).join('');
  }
  function renderShell(cur) {
    if (!$('.shell')) {
      $('#root').innerHTML =
        '<div class="shell"><aside class="side"><div class="brand"><div class="logo">' + icon('mail', 17).replace('currentColor', '#0B1220') + '</div>外贸订单助手</div>' +
        '<nav id="sidenav"></nav><div class="foot"><div class="ell"><b>' + esc(state.user.name) + '</b> <span class="dim">' + (state.user.role === 'admin' ? '管理员' : '业务员') + '</span></div>' +
        '<button class="btn sm" id="logout" style="margin-top:10px;width:100%">' + icon('out', 15) + '退出登录</button></div></aside>' +
        '<div class="grow"><nav class="mtop" id="topnav"></nav><main class="main"><div class="page" id="page"></div></main></div></div>';
      $('#logout').addEventListener('click', function () {
        api('POST', '/api/logout', {}).finally(function () { state.user = null; renderLogin(); });
      });
    }
    $('#sidenav').innerHTML = navHtml(cur);
    $('#topnav').innerHTML = navHtml(cur) + '<button class="btn sm" id="logout2">退出</button>';
    $('#logout2').addEventListener('click', function () { $('#logout').click(); });
  }

  var ROUTES = {};
  function route() {
    if (!state.user) return;
    var h = (location.hash.replace(/^#\/?/, '').split('?')[0]) || 'dashboard';
    var parts = h.split('/');
    var name = ROUTES[parts[0]] ? parts[0] : 'dashboard';
    if (name === 'users' && state.user.role !== 'admin') name = 'dashboard';
    renderShell(name);
    closeDrawer(true);
    // 每次换一个新的容器，避免旧页面的事件监听叠加
    var old = $('#page');
    var page = old.cloneNode(false);
    old.parentNode.replaceChild(page, old);
    page.innerHTML = '<div class="boot">加载中…</div>';
    window.scrollTo(0, 0);
    Promise.resolve(ROUTES[name](page, parts.slice(1))).catch(fail);
  }
  window.addEventListener('hashchange', route);

  function head(title, sub, actions) {
    return '<div class="head"><div><h1>' + esc(title) + '</h1>' + (sub ? '<p>' + sub + '</p>' : '') + '</div><div class="row wrap">' + (actions || '') + '</div></div>';
  }

  // ------------------------------------------------------------------ 工作台
  ROUTES.dashboard = function (page) {
    return api('GET', '/api/dashboard').then(function (d) {
      state.dueCount = d.metrics.due_today;
      renderShell('dashboard');
      var hour = new Date().getHours();
      var hi = hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
      var m = d.metrics;
      var maxL = Math.max(1, d.levels.A, d.levels.B, d.levels.C);
      var maxS = Math.max.apply(null, [1].concat(STATUSES.map(function (s) { return d.statuses[s] || 0; })));
      page.innerHTML = head(hi + '，' + state.user.name, '今天有 <b style="color:var(--amber)">' + m.due_today + '</b> 位客户要跟进，<b>' + m.to_quote + '</b> 个 A/B 级询盘等你报价。',
        '<button class="btn" id="chkMail">' + icon('mail', 16) + '立即收邮件</button><a class="btn primary" href="#/new">' + icon('plus', 16) + '录入询盘</a>') +
        '<div class="metrics">' +
        metric('今日待跟进', m.due_today, 'leads?due=1', true) + metric('待报价（A/B 级）', m.to_quote, 'leads?status=新询盘') +
        metric('近 7 天新询盘', m.week_new, 'leads') + metric('已成交', m.won, 'leads?status=已成交') + '</div>' +
        '<div class="grid2"><div class="stack">' +
        '<div class="card"><h3>今日待跟进<span class="muted">按意向等级排序</span></h3><div id="dueList">' +
        (d.due.length ? d.due.map(dueItem).join('') : '<div class="empty">今天没有需要跟进的客户，可以专心开发新客户。</div>') + '</div></div>' +
        '<div class="card"><h3>待报价</h3>' + (d.to_quote.length ? '<div class="tbl-wrap" style="border:0;background:transparent"><table class="tbl" style="min-width:0"><tbody>' +
          d.to_quote.map(function (x) {
            return '<tr class="click" data-open="' + esc(x.id) + '"><td style="width:44px;padding-left:4px">' + lv(x.level) + '</td><td style="max-width:0;width:100%"><div class="ell"><b>' + esc(x.company) + '</b></div><div class="sub ell">' + esc(x.country || '') + ' · ' + esc(x.products || '产品待确认') + '</div></td>' +
              '<td style="text-align:right;padding-right:4px"><button class="btn sm amber" data-quote="' + esc(x.id) + '">生成报价单</button></td></tr>';
          }).join('') + '</tbody></table></div>' : '<div class="empty">没有待报价的 A/B 级询盘。</div>') + '</div>' +
        '</div><div class="stack">' +
        '<div class="card"><h3>意向等级<span class="muted">未流失的客户</span></h3><div class="bars">' +
        ['A', 'B', 'C'].map(function (l) {
          var c = { A: 'var(--amber)', B: 'var(--blue)', C: '#5B6782' }[l];
          return '<div class="b"><span>' + lv(l) + '</span><div class="track"><div class="fill" style="width:' + Math.round(d.levels[l] / maxL * 100) + '%;background:' + c + '"></div></div><span class="num" style="text-align:right">' + d.levels[l] + '</span></div>';
        }).join('') + '</div></div>' +
        '<div class="card"><h3>客户状态</h3><div class="bars">' + STATUSES.map(function (s) {
          return '<div class="b"><span>' + esc(s) + '</span><div class="track"><div class="fill" style="width:' + Math.round((d.statuses[s] || 0) / maxS * 100) + '%"></div></div><span class="num" style="text-align:right">' + (d.statuses[s] || 0) + '</span></div>';
        }).join('') + '</div></div>' +
        '<div class="card"><h3>最新询盘</h3>' + (d.recent.length ? d.recent.map(function (x) {
          return '<div class="row" style="padding:8px 0;border-bottom:1px solid var(--line);cursor:pointer" data-open="' + esc(x.id) + '">' + lv(x.level) + '<div class="grow"><div class="ell"><b>' + esc(x.company) + '</b></div><div class="small dim ell">' + esc(x.source) + ' · ' + fmtDate(x.first_at, true) + '</div></div>' + st(x.status) + '</div>';
        }).join('') : '<div class="empty">还没有询盘。去「录入询盘」粘贴第一条吧。</div>') + '</div>' +
        '</div></div>';
      $$('.metric', page).forEach(function (el) { el.addEventListener('click', function () { location.hash = '#/' + el.dataset.go; }); });
      bindCommon(page, function () { route(); });
      var cm = $('#chkMail');
      cm.addEventListener('click', function () {
        busy(cm, true, '收取中');
        api('POST', '/api/tasks/check-mail', {}).then(function (r) { toast('新询盘 ' + r.new_inquiries + ' 条'); route(); }).catch(function (e) { busy(cm, false); fail(e); });
      });
    });
  };
  function metric(label, v, go, hot) {
    return '<div class="metric' + (hot && v ? ' hot' : '') + '" data-go="' + esc(go) + '" role="link" tabindex="0"><div class="l">' + esc(label) + '</div><div class="v num">' + v + '</div></div>';
  }
  function dueItem(x) {
    var d = draftText(x.follow_draft), tip = draftTip(x.follow_draft);
    return '<div class="fu rise"><div class="row between wrap"><div class="row grow" style="cursor:pointer" data-open="' + esc(x.id) + '">' + lv(x.level) +
      '<div class="grow"><div class="ell"><b>' + esc(x.company) + '</b></div><div class="small muted">' + esc(x.country || '国家未知') + ' · 第 ' + ((x.follow_count || 0) + 1) + ' 次跟进 · 已 ' + x.days + ' 天未联系 · ' + dueLabel(x.next_at) + '</div></div></div>' +
      '<div class="row">' + (d ? '<button class="btn sm" data-copy="' + esc(d) + '">' + icon('copy', 14) + '复制话术</button>' : '<button class="btn sm" data-draft="' + esc(x.id) + '">' + icon('spark', 14) + 'AI 写话术</button>') +
      '<button class="btn sm primary" data-followed="' + esc(x.id) + '">' + icon('check', 14) + '已跟进</button></div></div>' +
      (d ? '<div class="draft">' + esc(d) + (tip ? '<div class="small" style="margin-top:8px;color:var(--amber)">💡 ' + esc(tip) + '</div>' : '') + '</div>' : '') + '</div>';
  }

  // 通用按钮：打开客户、复制、生成报价、写话术、已跟进
  function bindCommon(scope, refresh) {
    scope.addEventListener('click', function (e) {
      var t = e.target.closest('[data-copy],[data-quote],[data-draft],[data-followed],[data-open]');
      if (!t || !scope.contains(t)) return;
      if (t.dataset.copy !== undefined) { e.stopPropagation(); return copy(t.dataset.copy); }
      if (t.dataset.quote) {
        e.stopPropagation(); busy(t, true, 'AI 报价中');
        return api('POST', '/api/leads/' + t.dataset.quote + '/quote', {}).then(function (r) {
          toast('报价单 ' + r.quote_no + ' 已生成'); openLead(r.lead.id, refresh);
        }).catch(function (err) { busy(t, false); fail(err); });
      }
      if (t.dataset.draft) {
        e.stopPropagation(); busy(t, true, 'AI 撰写中');
        return api('POST', '/api/leads/' + t.dataset.draft + '/draft', {}).then(function () { refresh(); }).catch(function (err) { busy(t, false); fail(err); });
      }
      if (t.dataset.followed) {
        e.stopPropagation(); busy(t, true);
        return api('POST', '/api/leads/' + t.dataset.followed + '/followed', {}).then(function (l) {
          toast('已记录，下次跟进：' + (l.next_at ? fmtDate(l.next_at) : '不再提醒')); refresh();
        }).catch(function (err) { busy(t, false); fail(err); });
      }
      if (t.dataset.open) return openLead(t.dataset.open, refresh);
    });
  }

  // ------------------------------------------------------------------ 询盘列表
  ROUTES.leads = function (page) {
    var qs = new URLSearchParams((location.hash.split('?')[1] || ''));
    var f = state.leadsFilter;
    if (qs.has('status')) { f.status = qs.get('status'); f.due = false; }
    if (qs.has('due')) { f.due = true; f.status = ''; }
    if (location.hash.indexOf('?') >= 0) history.replaceState(null, '', '#/leads');
    page.innerHTML = head('询盘客户', '点任意一行打开客户详情：报价、跟进、沟通记录都在里面。', '<a class="btn primary" href="#/new">' + icon('plus', 16) + '录入询盘</a>') +
      '<div class="row wrap between" style="margin-bottom:14px"><div class="tabs" id="stTabs">' +
      [['', '全部']].concat(STATUSES.map(function (s) { return [s, s]; })).map(function (s) {
        return '<button class="tab' + (!f.due && f.status === s[0] ? ' on' : '') + '" data-st="' + esc(s[0]) + '">' + esc(s[1]) + '</button>';
      }).join('') + '<button class="tab' + (f.due ? ' on' : '') + '" data-due="1">今日待跟进</button></div>' +
      '<div class="row wrap"><input class="input" id="q" placeholder="搜索公司、国家、产品…" style="width:220px" value="' + esc(f.q) + '">' +
      '<select class="input" id="lvSel" style="width:110px" aria-label="意向等级"><option value="">全部等级</option>' + ['A', 'B', 'C'].map(function (l) { return '<option' + (f.level === l ? ' selected' : '') + '>' + l + '</option>'; }).join('') + '</select>' +
      '<label class="chk"><input type="checkbox" id="mine"' + (f.mine ? ' checked' : '') + '>只看我的</label></div></div>' +
      '<div id="leadTable"><div class="boot">加载中…</div></div>';
    function load() {
      var p = new URLSearchParams();
      if (f.q) p.set('q', f.q);
      if (f.status && !f.due) p.set('status', f.status);
      if (f.level) p.set('level', f.level);
      if (f.mine) p.set('mine', '1');
      if (f.due) p.set('due', '1');
      return api('GET', '/api/leads?' + p.toString()).then(function (d) {
        var box = $('#leadTable');
        if (!box) return;
        if (!d.items.length) { box.innerHTML = '<div class="card empty">没有符合条件的客户。</div>'; return; }
        box.innerHTML = '<div class="small dim" style="margin-bottom:8px">共 ' + d.total + ' 位客户</div><div class="tbl-wrap"><table class="tbl"><thead><tr><th>等级</th><th>客户公司</th><th>国家</th><th>询盘产品 / 数量</th><th>状态</th><th>下次跟进</th><th>负责人</th><th>来源</th></tr></thead><tbody>' +
          d.items.map(function (x) {
            return '<tr class="click" data-open="' + esc(x.id) + '"><td>' + lv(x.level) + '</td><td><div class="ell" style="max-width:260px"><b>' + esc(x.company) + '</b></div><div class="sub ell" style="max-width:260px">' + esc(x.contact || x.email || '') + '</div></td>' +
              '<td>' + esc(x.country || '—') + '</td><td><div class="ell" style="max-width:240px">' + esc(x.products || '—') + '</div><div class="sub ell" style="max-width:240px">' + esc(x.qty || '') + '</div></td>' +
              '<td>' + st(x.status) + (x.quote_url ? ' <span class="small dim">PDF</span>' : '') + '</td><td class="num">' + (['已报价', '跟进中'].indexOf(x.status) >= 0 ? dueLabel(x.next_at) : '<span class="dim">—</span>') + '</td>' +
              '<td>' + esc(x.owner || '—') + '</td><td class="small muted">' + esc(x.source || '') + '</td></tr>';
          }).join('') + '</tbody></table></div>';
      });
    }
    $$('#stTabs .tab', page).forEach(function (b) {
      b.addEventListener('click', function () {
        f.due = !!b.dataset.due; f.status = b.dataset.due ? '' : b.dataset.st;
        $$('#stTabs .tab', page).forEach(function (x) { x.classList.toggle('on', x === b); });
        load().catch(fail);
      });
    });
    var timer;
    $('#q').addEventListener('input', function (e) { clearTimeout(timer); timer = setTimeout(function () { f.q = e.target.value.trim(); load().catch(fail); }, 250); });
    $('#lvSel').addEventListener('change', function (e) { f.level = e.target.value; load().catch(fail); });
    $('#mine').addEventListener('change', function (e) { f.mine = e.target.checked; load().catch(fail); });
    bindCommon(page, function () { load().catch(fail); });
    return load();
  };

  // ------------------------------------------------------------------ 客户详情抽屉
  var drawerRefresh = null;
  function closeDrawer(silent) {
    var o = $('#drawer');
    if (o) { o.remove(); document.body.style.overflow = ''; if (!silent && drawerRefresh) drawerRefresh(); }
    drawerRefresh = null;
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if ($('.modal-wrap')) $('.modal-wrap').remove(); else closeDrawer(); }
  });

  function openLead(id, refresh) {
    drawerRefresh = refresh || drawerRefresh;
    var o = $('#drawer');
    if (!o) {
      o = document.createElement('div');
      o.id = 'drawer'; o.className = 'overlay';
      o.innerHTML = '<div class="drawer" role="dialog" aria-modal="true" aria-label="客户详情"><div class="db"><div class="boot">加载中…</div></div></div>';
      o.addEventListener('click', function (e) { if (e.target === o) closeDrawer(); });
      document.body.appendChild(o);
      document.body.style.overflow = 'hidden';
    }
    return api('GET', '/api/leads/' + id).then(function (l) { renderLead(o, l); }).catch(function (e) { closeDrawer(true); fail(e); });
  }

  function renderLead(o, l) {
    var isAdmin = state.user.role === 'admin';
    var active = ['已报价', '跟进中'].indexOf(l.status) >= 0;
    var d = draftText(l.follow_draft), tip = draftTip(l.follow_draft);
    var dr = $('.drawer', o);
    dr.innerHTML =
      '<div class="dh">' + lv(l.level) + '<div class="grow"><div class="ell" style="font-size:18px;font-weight:800">' + esc(l.company) + '</div>' +
      '<div class="small muted ell">' + esc([l.country, l.contact, l.email].filter(Boolean).join(' · ')) + '</div></div>' +
      '<select class="input" id="ldStatus" style="width:112px" aria-label="状态">' + STATUSES.map(function (s) { return '<option' + (s === l.status ? ' selected' : '') + '>' + s + '</option>'; }).join('') + '</select>' +
      '<button class="x" id="ldClose" aria-label="关闭">' + icon('x') + '</button></div>' +
      '<div class="db">' +
      // AI 摘要
      '<div class="card" style="border-color:rgba(79,140,255,.35)"><div class="row between"><h3 style="margin:0">' + icon('spark', 16) + ' AI 摘要</h3><span class="small dim">' + esc(l.source) + ' · ' + fmtDate(l.first_at, true) + ' 收到</span></div>' +
      '<p style="margin:10px 0 0">' + esc(l.summary || '—') + '</p>' + (l.level_reason ? '<p class="small muted" style="margin:6px 0 0">分级理由：' + esc(l.level_reason) + '</p>' : '') + '</div>' +
      // 报价
      '<div class="card"><div class="row between wrap"><h3 style="margin:0">报价</h3><div class="row">' +
      (l.quote_url ? '<a class="btn sm" href="' + esc(l.quote_url) + '" target="_blank" rel="noopener">' + icon('file', 14) + '查看 PDF</a><a class="btn sm" href="' + esc(l.quote_url) + '?download=1">下载</a>' : '') +
      '<button class="btn sm ' + (l.quote_url ? '' : 'amber') + '" id="ldQuote">' + icon('spark', 14) + (l.quote_url ? '重新生成' : '生成报价单') + '</button></div></div>' +
      (l.quote_email ? '<div class="box pre small" style="margin-top:12px">' + esc(l.quote_email) + '</div><div class="row" style="margin-top:8px"><button class="btn sm" data-copy="' + esc(l.quote_email) + '">' + icon('copy', 14) + '复制报价邮件</button></div>' :
        '<p class="small muted" style="margin:10px 0 0">按产品库价格生成英文 PDF 报价单，数量低于起订量会自动按起订量报，同时写好报价邮件草稿。</p>') +
      (l.quotes && l.quotes.length > 1 ? '<div class="small muted" style="margin-top:12px">历史报价：' + l.quotes.map(function (q) { return '<a href="' + esc(q.url) + '" target="_blank" rel="noopener">' + esc(q.no) + '</a>（' + money(q.total, q.currency) + '）'; }).join('、') + '</div>' : '') + '</div>' +
      // 跟进
      '<div class="card"><div class="row between wrap"><h3 style="margin:0">跟进</h3><div class="row small muted">已跟进 <b class="num" style="color:var(--text)">' + (l.follow_count || 0) + '</b> 次 · 最近联系 ' + fmtDate(l.last_at) + '</div></div>' +
      '<div class="row wrap" style="margin-top:12px"><label class="f" for="ldNext" style="margin:0">下次跟进</label><input class="input" type="date" id="ldNext" style="width:170px" value="' + isoDate(l.next_at) + '"><button class="btn sm" id="ldNextSave">保存日期</button></div>' +
      (d ? '<div class="box pre" style="margin-top:12px">' + esc(d) + '</div>' + (tip ? '<div class="small" style="margin-top:8px;color:var(--amber)">💡 ' + esc(tip) + '</div>' : '') : '') +
      '<div class="row wrap" style="margin-top:12px">' + (d ? '<button class="btn sm" data-copy="' + esc(d) + '">' + icon('copy', 14) + '复制话术</button>' : '') +
      '<button class="btn sm" id="ldDraft">' + icon('spark', 14) + (d ? '重写话术' : 'AI 写跟进话术') + '</button>' +
      '<button class="btn sm primary" id="ldFollowed"' + (l.status === '新询盘' ? ' disabled title="请先生成报价单"' : '') + '>' + icon('check', 14) + '我已跟进</button></div>' +
      (!active && l.status !== '新询盘' ? '<p class="small dim" style="margin:10px 0 0">状态为「' + esc(l.status) + '」，系统不会再提醒跟进。</p>' : '') +
      (l.followups && l.followups.length ? '<div class="small muted" style="margin-top:14px">' + l.followups.map(function (fu) { return '<div style="padding:6px 0;border-top:1px solid var(--line)">第 ' + fu.n + ' 次 · ' + fmtDate(fu.at, true) + (fu.by ? ' · ' + esc(fu.by) : '') + '<div class="dim ell">' + esc(draftText(fu.text)) + '</div></div>'; }).join('') + '</div>' : '') + '</div>' +
      // 信息
      '<div class="card"><div class="row between"><h3 style="margin:0">客户信息</h3><button class="btn sm" id="ldEdit">编辑</button></div><div id="ldInfo" style="margin-top:12px">' + infoView(l) + '</div></div>' +
      // 沟通记录
      '<div class="card"><h3>沟通记录</h3>' + (l.chat_log ? '<div class="log">' + esc(l.chat_log) + '</div>' : '<p class="small muted" style="margin:0">还没有记录。客户回复了什么、电话聊了什么，都可以记在这里，AI 写话术时会参考。</p>') +
      '<div class="row" style="margin-top:12px;align-items:flex-start"><textarea class="input" id="ldNote" style="min-height:64px" placeholder="例如：客户回复说下周确认数量，想要黑色款"></textarea><button class="btn" id="ldNoteBtn">添加</button></div></div>' +
      // 原文
      '<div class="card"><details class="raw"><summary>询盘原文</summary><div class="pre small" style="margin-top:8px;color:#C7D2E3">' + esc(l.raw || '—') + '</div></details></div>' +
      (isAdmin ? '<div class="row" style="justify-content:flex-end"><button class="btn sm danger" id="ldDel">删除这个客户</button></div>' : '') +
      '</div>';

    var reload = function (lead) { renderLead(o, lead); };
    $('#ldClose', dr).addEventListener('click', function () { closeDrawer(); });
    $('#ldStatus', dr).addEventListener('change', function (e) {
      api('PATCH', '/api/leads/' + l.id, { status: e.target.value }).then(function (x) { toast('状态已改为「' + x.status + '」'); reload(x); }).catch(fail);
    });
    $('#ldQuote', dr).addEventListener('click', function (e) {
      var b = e.currentTarget; busy(b, true, 'AI 报价中…');
      api('POST', '/api/leads/' + l.id + '/quote', {}).then(function (r) { toast('报价单 ' + r.quote_no + ' 已生成，合计 ' + money(r.total)); reload(r.lead); }).catch(function (err) { busy(b, false); fail(err); });
    });
    $('#ldDraft', dr).addEventListener('click', function (e) {
      var b = e.currentTarget; busy(b, true, 'AI 撰写中…');
      api('POST', '/api/leads/' + l.id + '/draft', {}).then(function (r) { reload(r.lead); }).catch(function (err) { busy(b, false); fail(err); });
    });
    $('#ldFollowed', dr).addEventListener('click', function (e) {
      var b = e.currentTarget; busy(b, true);
      api('POST', '/api/leads/' + l.id + '/followed', {}).then(function (x) { toast(x.status === '已流失' ? '已跟进 5 次未回复，标记为已流失' : '已记录，下次跟进 ' + fmtDate(x.next_at)); reload(x); }).catch(function (err) { busy(b, false); fail(err); });
    });
    $('#ldNextSave', dr).addEventListener('click', function () {
      var v = $('#ldNext', dr).value;
      if (!v) return toast('请先选择日期', true);
      api('PATCH', '/api/leads/' + l.id, { next_at: v }).then(function (x) { toast('已保存'); reload(x); }).catch(fail);
    });
    $('#ldNoteBtn', dr).addEventListener('click', function () {
      var v = $('#ldNote', dr).value.trim();
      if (!v) return toast('请先写点内容', true);
      api('POST', '/api/leads/' + l.id + '/note', { text: v }).then(reload).catch(fail);
    });
    $('#ldEdit', dr).addEventListener('click', function (e) {
      e.currentTarget.style.display = 'none';
      $('#ldInfo', dr).innerHTML = infoForm(l);
      $('#ldInfoForm', dr).addEventListener('submit', function (ev) {
        ev.preventDefault();
        var body = {};
        $$('[name]', ev.target).forEach(function (el) { body[el.name] = el.value; });
        api('PATCH', '/api/leads/' + l.id, body).then(function (x) { toast('已保存'); reload(x); }).catch(fail);
      });
      $('#ldInfoCancel', dr).addEventListener('click', function () { reload(l); });
    });
    var del = $('#ldDel', dr);
    if (del) del.addEventListener('click', function () {
      if (!window.confirm('确定删除「' + l.company + '」？此操作不能撤销。')) return;
      api('DELETE', '/api/leads/' + l.id).then(function () { toast('已删除'); closeDrawer(); }).catch(fail);
    });
    dr.onclick = function (e) {
      var t = e.target.closest('[data-copy]');
      if (t) copy(t.dataset.copy);
    };
  }
  function infoView(l) {
    var rows = [['联系人', l.contact], ['邮箱', l.email], ['国家', l.country], ['来源', l.source], ['询盘产品', l.products], ['需求数量', l.qty], ['目标价 / 预算', l.budget], ['负责人', l.owner]];
    return '<div class="kv">' + rows.map(function (r) { return '<div><div class="k">' + r[0] + '</div><div class="v">' + esc(r[1] || '—') + '</div></div>'; }).join('') + '</div>';
  }
  function infoForm(l) {
    function inp(name, label, val) { return '<div class="field"><label class="f" for="e_' + name + '">' + label + '</label><input class="input" id="e_' + name + '" name="' + name + '" value="' + esc(val || '') + '"></div>'; }
    return '<form id="ldInfoForm"><div class="form-grid">' + inp('company', '客户公司', l.company) + inp('contact', '联系人', l.contact) + inp('email', '邮箱', l.email) + inp('country', '国家', l.country) +
      '<div class="field"><label class="f" for="e_level">意向等级</label><select class="input" id="e_level" name="level">' + ['A', 'B', 'C'].map(function (x) { return '<option' + (x === l.level ? ' selected' : '') + '>' + x + '</option>'; }).join('') + '</select></div>' +
      '<div class="field"><label class="f" for="e_source">来源</label><select class="input" id="e_source" name="source">' + SOURCES.map(function (x) { return '<option' + (x === l.source ? ' selected' : '') + '>' + x + '</option>'; }).join('') + '</select></div>' +
      inp('products', '询盘产品（填产品库型号，报价更准）', l.products) + inp('qty', '需求数量', l.qty) + inp('budget', '目标价 / 预算', l.budget) + inp('owner', '负责人', l.owner) + '</div>' +
      '<div class="field"><label class="f" for="e_summary">AI 摘要</label><textarea class="input" id="e_summary" name="summary" style="min-height:70px">' + esc(l.summary) + '</textarea></div>' +
      '<div class="row"><button class="btn primary" type="submit">保存</button><button class="btn" type="button" id="ldInfoCancel">取消</button></div></form>';
  }

  // ------------------------------------------------------------------ 录入询盘
  ROUTES['new'] = function (page) {
    page.innerHTML = head('录入询盘', '阿里国际站、WhatsApp、展会名片……任何渠道的询盘，粘贴原文交给 AI。邮箱里的询盘会自动收取，不用手动录。') +
      '<div class="grid2"><form class="card" id="newForm">' +
      '<div class="form-grid"><div class="field"><label class="f" for="nSrc">来源</label><select class="input" id="nSrc">' + SOURCES.map(function (s) { return '<option>' + s + '</option>'; }).join('') + '</select></div>' +
      '<div class="field"><label class="f" for="nSender">客户邮箱或联系方式（可选）</label><input class="input" id="nSender" placeholder="john@abc-trading.com"></div></div>' +
      '<div class="field"><label class="f" for="nText">询盘原文</label><textarea class="input" id="nText" style="min-height:260px" placeholder="直接粘贴客户发来的原文，英文、西语、中文都可以"></textarea><div id="nErr" class="small" style="color:var(--red);min-height:18px;margin-top:4px"></div></div>' +
      '<button class="btn primary lg" type="submit">' + icon('spark', 17) + '交给 AI 处理</button></form>' +
      '<div id="nResult" class="stack"><div class="card"><h3>AI 会做什么</h3><div class="small muted" style="line-height:1.9">1. 判断是不是真实采购询盘，推广和垃圾信息直接过滤<br>2. 提取公司、国家、产品型号、数量、目标价<br>3. 按 A / B / C 打意向等级并写理由<br>4. A 级询盘立刻提醒到飞书群（如已配置）<br>5. 写进「询盘客户」，负责人记为你</div></div></div></div>';
    $('#nText').addEventListener('input', function () { $('#nErr').textContent = ''; });
    $('#newForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var text = $('#nText').value.trim();
      if (text.length < 10) { $('#nErr').textContent = '请粘贴完整的询盘内容'; return; }
      var btn = $('button[type=submit]', e.target);
      busy(btn, true, 'AI 正在阅读…');
      api('POST', '/api/leads', { text: text, source: $('#nSrc').value, sender: $('#nSender').value }).then(function (r) {
        busy(btn, false);
        var box = $('#nResult');
        if (!r.is_inquiry) {
          box.innerHTML = '<div class="card rise"><h3>不像采购询盘</h3><p class="muted" style="margin:0">AI 判断这条内容是推广、通知或垃圾信息，没有写进客户表。如果判断错了，可以补充更多原文后再试。</p></div>';
          return;
        }
        var l = r.lead;
        $('#nText').value = ''; $('#nSender').value = '';
        box.innerHTML = '<div class="card rise" style="border-color:rgba(79,140,255,.45)"><div class="row">' + lv(l.level) + '<div class="grow"><div style="font-weight:800;font-size:17px" class="ell">' + esc(l.company) + '</div><div class="small muted">' + esc(l.country || '国家未知') + ' · ' + esc(l.source) + '</div></div></div>' +
          '<div class="kv" style="margin-top:14px"><div><div class="k">询盘产品</div><div class="v">' + esc(l.products || '—') + '</div></div><div><div class="k">数量</div><div class="v">' + esc(l.qty || '—') + '</div></div><div><div class="k">目标价</div><div class="v">' + esc(l.budget || '—') + '</div></div></div>' +
          '<p style="margin:14px 0 0">' + esc(l.summary) + '</p><p class="small muted" style="margin:6px 0 0">分级理由：' + esc(l.level_reason) + '</p>' +
          '<div class="row wrap" style="margin-top:16px"><button class="btn amber" data-quote="' + esc(l.id) + '">生成报价单</button><button class="btn" data-open="' + esc(l.id) + '">打开客户详情</button></div></div>';
        bindCommon(box, function () { });
        toast('已写入客户表');
      }).catch(function (err) { busy(btn, false); fail(err); });
    });
  };

  // ------------------------------------------------------------------ 产品库
  ROUTES.products = function (page) {
    return api('GET', '/api/products').then(function (d) {
      page.innerHTML = head('产品库', 'AI 报价只会使用这里的型号和单价。', '<button class="btn" id="pImport">批量导入 CSV</button><button class="btn primary" id="pAdd">' + icon('plus', 16) + '新增产品</button>') +
        (d.items.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>型号</th><th>产品名称 / 规格</th><th style="text-align:right">单价</th><th style="text-align:right">起订量</th><th style="text-align:right">交期</th><th>包装</th><th></th></tr></thead><tbody>' +
          d.items.map(function (p) {
            return '<tr><td><b class="num">' + esc(p.model) + '</b></td><td><div class="ell" style="max-width:320px">' + esc(p.name) + '</div><div class="sub ell" style="max-width:320px">' + esc(p.spec) + '</div></td>' +
              '<td class="num" style="text-align:right">' + money(p.price) + '</td><td class="num" style="text-align:right">' + Number(p.moq).toLocaleString() + '</td><td class="num" style="text-align:right">' + p.lead_days + ' 天</td>' +
              '<td class="small muted"><div class="ell" style="max-width:200px">' + esc(p.packing) + '</div></td>' +
              '<td style="text-align:right;white-space:nowrap"><button class="btn sm" data-edit="' + esc(p.id) + '">编辑</button> <button class="btn sm danger" data-del="' + esc(p.id) + '" data-model="' + esc(p.model) + '">删除</button></td></tr>';
          }).join('') + '</tbody></table></div>' : '<div class="card empty">产品库还是空的。先新增几个型号，或者用 CSV 批量导入。</div>');
      var byId = {}; d.items.forEach(function (p) { byId[p.id] = p; });
      $('#pAdd').addEventListener('click', function () { productModal(null); });
      $('#pImport').addEventListener('click', importModal);
      page.addEventListener('click', function (e) {
        var ed = e.target.closest('[data-edit]'), dl = e.target.closest('[data-del]');
        if (ed) productModal(byId[ed.dataset.edit]);
        if (dl && window.confirm('删除型号 ' + dl.dataset.model + '？')) {
          api('DELETE', '/api/products/' + dl.dataset.del).then(function () { toast('已删除'); route(); }).catch(fail);
        }
      });
    });
  };
  function modal(html, onReady) {
    var w = document.createElement('div');
    w.className = 'modal-wrap';
    w.innerHTML = '<div class="modal rise" role="dialog" aria-modal="true">' + html + '</div>';
    w.addEventListener('click', function (e) { if (e.target === w) w.remove(); });
    document.body.appendChild(w);
    onReady($('.modal', w), function () { w.remove(); });
  }
  function productModal(p) {
    p = p || { model: '', name: '', spec: '', price: '', moq: '', lead_days: '', packing: '', note: '' };
    function inp(n, label, type) { return '<div class="field"><label class="f" for="p_' + n + '">' + label + '</label><input class="input" id="p_' + n + '" name="' + n + '" ' + (type ? 'type="number" step="any" min="0"' : '') + ' value="' + esc(p[n]) + '"></div>'; }
    modal('<h2>' + (p.id ? '编辑产品' : '新增产品') + '</h2><form id="pForm"><div class="form-grid">' + inp('model', '型号 *') + inp('name', '产品名称（英文，印在报价单上）') + '</div>' + inp('spec', '规格描述（英文）') +
      '<div class="form-grid">' + inp('price', '单价', 1) + inp('moq', '起订量', 1) + inp('lead_days', '交期（天）', 1) + '</div>' + inp('packing', '包装（英文）') + inp('note', '备注') +
      '<div id="pErr" class="small" style="color:var(--red);min-height:18px"></div><div class="row"><button class="btn primary" type="submit">保存</button><button class="btn" type="button" id="pCancel">取消</button></div></form>',
      function (m, close) {
        $('#pCancel', m).addEventListener('click', close);
        $('#p_model', m).focus();
        $('#pForm', m).addEventListener('submit', function (e) {
          e.preventDefault();
          var body = {};
          $$('[name]', e.target).forEach(function (el) { body[el.name] = el.value; });
          if (!body.model.trim()) { $('#pErr', m).textContent = '型号不能为空'; return; }
          api(p.id ? 'PUT' : 'POST', '/api/products' + (p.id ? '/' + p.id : ''), body).then(function () { close(); toast('已保存'); route(); })
            .catch(function (err) { $('#pErr', m).textContent = err.message; });
        });
      });
  }
  function importModal() {
    modal('<h2>批量导入产品</h2><p class="small muted" style="margin-top:-8px">从 Excel 另存为 CSV（UTF-8），把内容粘贴到下面。型号已存在的会更新，不存在的会新增。</p>' +
      '<textarea class="input" id="csvText" style="min-height:220px;font-family:monospace;font-size:12.5px" placeholder="型号,产品名称,规格描述,单价,起订量,交期(天),包装,备注&#10;HG-304A,Stainless Steel Door Hinge 4&quot;,SUS304,0.86,2000,25,100 pcs/carton,"></textarea>' +
      '<div id="cErr" class="small" style="color:var(--red);min-height:18px;margin-top:6px"></div><div class="row"><button class="btn primary" id="cGo">导入</button><button class="btn" id="cCancel">取消</button></div>',
      function (m, close) {
        $('#cCancel', m).addEventListener('click', close);
        $('#cGo', m).addEventListener('click', function (e) {
          var v = $('#csvText', m).value;
          if (!v.trim()) { $('#cErr', m).textContent = '请先粘贴 CSV 内容'; return; }
          busy(e.currentTarget, true);
          api('POST', '/api/products/import', { csv: v }).then(function (r) { close(); toast('新增 ' + r.added + ' 个，更新 ' + r.updated + ' 个'); route(); })
            .catch(function (err) { busy(e.currentTarget, false); $('#cErr', m).textContent = err.message; });
        });
      });
  }

  // ------------------------------------------------------------------ 报价记录
  ROUTES.quotes = function (page) {
    return api('GET', '/api/quotes').then(function (d) {
      page.innerHTML = head('报价记录', '每一次生成的报价单都在这里，可以随时重新下载。') +
        (d.items.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>报价单号</th><th>客户</th><th>日期</th><th style="text-align:right">金额</th><th>明细</th><th></th></tr></thead><tbody>' +
          d.items.map(function (q) {
            return '<tr><td class="num"><b>' + esc(q.no) + '</b></td><td>' + (q.lead_id ? '<a href="#" data-open="' + esc(q.lead_id) + '">' + esc(q.company) + '</a>' : esc(q.company)) + '</td><td class="num">' + fmtDate(q.at) + '</td>' +
              '<td class="num" style="text-align:right">' + money(q.total, q.currency) + '</td><td class="small muted"><div class="ell" style="max-width:340px">' + esc(q.detail.replace(/\n/g, '；')) + '</div></td>' +
              '<td style="text-align:right;white-space:nowrap">' + (q.url ? '<a class="btn sm" href="' + esc(q.url) + '" target="_blank" rel="noopener">查看</a> <a class="btn sm" href="' + esc(q.url) + '?download=1">下载</a>' : '') + '</td></tr>';
          }).join('') + '</tbody></table></div>' : '<div class="card empty">还没有生成过报价单。</div>');
      page.addEventListener('click', function (e) {
        var t = e.target.closest('[data-open]');
        if (t) { e.preventDefault(); openLead(t.dataset.open, function () { }); }
      });
    });
  };

  // ------------------------------------------------------------------ 提醒
  function md(s) {
    return esc(s).split('\n').map(function (line) {
      line = line.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
      return line.indexOf('&gt; ') === 0 ? '<blockquote>' + line.slice(5) + '</blockquote>' : line + '<br>';
    }).join('');
  }
  ROUTES.notifications = function (page) {
    return api('GET', '/api/notifications').then(function (d) {
      page.innerHTML = head('提醒', '系统推送过的所有提醒。配置了飞书群机器人的话，这些也会同时推送到飞书群。') +
        (d.items.length ? '<div class="stack" style="max-width:760px">' + d.items.map(function (n) {
          return '<div class="note"><div class="nh ' + esc(n.template || 'blue') + '"><span>' + esc(n.title) + '</span><span class="small num" style="font-weight:400;opacity:.85">' + fmtDate(n.created * 1000, true) + '</span></div><div class="nb">' + md(n.markdown) + '</div></div>';
        }).join('') + '</div>' : '<div class="card empty">还没有提醒。每天 ' + '早上的跟进清单、A 级询盘提醒都会出现在这里。</div>');
    });
  };

  // ------------------------------------------------------------------ 设置
  ROUTES.settings = function (page) {
    var isAdmin = state.user.role === 'admin';
    return api('GET', '/api/settings').then(function (d) {
      var v = d.values, s = d.status, sec = d.secrets, presets = d.presets || [];
      var dis = isAdmin ? '' : ' disabled';
      function inp(k, label, ph, type) {
        return '<div class="field"><label class="f" for="s_' + k + '">' + label + '</label><input class="input" id="s_' + k + '" name="' + k + '"' + (type ? ' type="' + type + '"' : '') + ' value="' + esc(v[k]) + '" placeholder="' + esc(ph || '') + '"' + dis + '></div>';
      }
      function secretInp(k, label, ph) {
        var set = sec[k];
        return '<div class="field"><label class="f" for="s_' + k + '">' + label + '</label><div class="row">' +
          '<input class="input grow" id="s_' + k + '" name="' + k + '" type="password" autocomplete="new-password" placeholder="' + esc(set ? '已配置 ' + set + '，留空表示不修改' : ph) + '"' + dis + '>' +
          (isAdmin && set ? '<button class="btn sm" type="button" data-clear="' + k + '">清除</button>' : '') + '</div></div>';
      }
      var curPreset = (presets.filter(function (p) { return p.base_url && v.llm_base_url && v.llm_base_url.indexOf(p.base_url.replace(/^https?:\/\//, '').split('/')[0]) >= 0; })[0] || (v.llm_base_url ? { id: 'custom' } : presets[0] || { id: 'custom' })).id;
      var badge = function (ok, yes, no) { return ok ? '<span class="st st-已报价">' + yes + '</span>' : '<span class="st st-已流失">' + no + '</span>'; };

      page.innerHTML = head('设置', isAdmin ? '保存后立即生效，不需要重启服务。' : '只有管理员可以修改设置。',
        isAdmin ? '<button class="btn" id="sDaily">立即生成今日跟进提醒</button>' : '') +
        '<div class="grid2"><form id="sForm" class="stack" autocomplete="off">' +

        // AI 大模型
        '<div class="card" id="cardLlm"><div class="row between wrap" style="margin-bottom:14px"><h3 style="margin:0">' + icon('spark', 16) + ' AI 大模型</h3>' + badge(s.llm_ready, '已连接 · ' + esc(s.llm), '演示模式') + '</div>' +
        (s.llm_ready ? '' : '<div class="box small" style="margin-bottom:14px;color:var(--amber)">还没有配置大模型密钥，系统正在用规则版 AI 演示，分级和话术质量有限，不要给真实客户用。</div>') +
        '<div class="field"><label class="f" for="s_preset">服务商</label><select class="input" id="s_preset"' + dis + '>' +
        presets.map(function (p) { return '<option value="' + esc(p.id) + '"' + (p.id === curPreset ? ' selected' : '') + '>' + esc(p.name) + '</option>'; }).join('') + '</select>' +
        '<div class="small dim" id="presetHelp" style="margin-top:6px"></div></div>' +
        '<div class="form-grid">' + inp('llm_base_url', '接口地址（base_url）', 'https://api.deepseek.com') + inp('llm_model', '模型名', 'deepseek-v4-flash') + '</div>' +
        secretInp('llm_api_key', 'API 密钥', 'sk-...') +
        (isAdmin ? '<div class="row wrap"><button class="btn" type="button" id="testLlm">' + icon('spark', 15) + '测试连接</button><span id="llmMsg" class="small"></span></div>' : '') + '</div>' +

        // 飞书
        '<div class="card" id="cardFeishu"><div class="row between wrap" style="margin-bottom:14px"><h3 style="margin:0">' + icon('bell', 16) + ' 飞书群推送</h3>' + badge(s.feishu_bot, '已开启', '未开启') + '</div>' +
        '<p class="small muted" style="margin:0 0 14px">A 级询盘和每日跟进清单会推送到飞书群。不配置也可以，提醒会保存在「提醒」页。<br>添加方法：飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人，复制 Webhook 地址。</p>' +
        inp('feishu_bot_webhook', '群机器人 Webhook 地址', 'https://open.feishu.cn/open-apis/bot/v2/hook/...') +
        secretInp('feishu_bot_secret', '签名校验密钥（添加机器人时勾了“签名校验”才需要）', '没开签名校验就留空') +
        '<div class="form-grid">' + inp('followup_time', '每天推送跟进提醒的时间', '09:00', 'time') + '</div>' +
        (isAdmin ? '<div class="row wrap"><button class="btn" type="button" id="testPush">' + icon('bell', 15) + '发送测试消息</button><span id="pushMsg" class="small"></span></div>' : '') + '</div>' +

        '<div class="card"><h3>公司信息（英文，印在报价单上）</h3><div class="form-grid">' + inp('company_name_en', '公司英文名') + inp('company_name_cn', '公司中文名（可选）') + inp('company_contact', '签名（姓名 | 职位）') + inp('company_email', '邮箱') + inp('company_phone', '电话') + inp('company_website', '网站') + '</div>' + inp('company_address', '地址') + '</div>' +
        '<div class="card"><h3>报价条款</h3><div class="form-grid">' + inp('quote_currency', '币种', 'USD') + inp('quote_incoterm', '贸易条款', 'FOB Ningbo') + inp('quote_validity_days', '报价有效期（天）', '30', 'number') + '</div>' + inp('quote_payment_terms', '付款方式', 'T/T 30% deposit, 70% before shipment') +
        '<div class="field"><label class="f" for="s_quote_bank_info">银行信息（可选，印在报价单底部）</label><textarea class="input" id="s_quote_bank_info" name="quote_bank_info" style="min-height:80px"' + dis + '>' + esc(v.quote_bank_info) + '</textarea></div></div>' +
        '<div class="card"><h3>产品展示页</h3>' + inp('landing_contact', '首页「预约演示」按钮文字（不要放微信号、手机号）', '预约演示') + '</div>' +
        (isAdmin ? '<div class="row" style="position:sticky;bottom:0;padding:12px 0;background:var(--bg)"><button class="btn primary lg" type="submit">保存设置</button><span id="sErr" class="small" style="color:var(--red)"></span></div>' : '') + '</form>' +

        '<div class="stack"><div class="card"><h3>系统状态</h3><div class="stack small">' +
        '<div class="row between"><span class="muted">大模型</span><span>' + esc(s.llm) + '</span></div>' +
        '<div class="row between"><span class="muted">业务邮箱</span><span>' + (s.mail ? esc(s.mail) : '<span class="dim">未配置（在 .env 填 IMAP_*）</span>') + '</span></div>' +
        '<div class="row between"><span class="muted">飞书群推送</span><span>' + (s.feishu_bot ? '已开启' : '<span class="dim">未开启，只在站内提醒</span>') + '</span></div></div></div>' +
        '<div class="card"><h3>密钥安全</h3><p class="small muted" style="margin:0;line-height:1.9">密钥保存在服务器自己的数据库里，页面上只显示掩码，任何人（包括管理员）都看不到原文。只有管理员能修改。<br>想更换密钥，直接填新的再保存；留空表示不修改。</p></div>' +
        '<div class="card"><h3>跟进节奏</h3><p class="small muted" style="margin:0;line-height:1.9">报价后按等级自动排下次跟进：<br>A 级：2 / 3 / 5 / 7 / 10 天<br>B 级：3 / 4 / 7 / 10 / 14 天<br>C 级：5 / 7 / 14 / 21 / 30 天<br>跟进 5 次没回复，自动标记为「已流失」。</p></div></div></div>';

      function showHelp() {
        var p = presets.filter(function (x) { return x.id === $('#s_preset').value; })[0];
        $('#presetHelp').textContent = p ? p.help : '';
      }
      showHelp();
      if (!isAdmin) return;

      var form = $('#sForm');
      var clear = [];
      function formValues() {
        var vals = {};
        $$('[name]', form).forEach(function (el) { vals[el.name] = el.value; });
        return vals;
      }
      function msg(el, text, ok) { el.textContent = text; el.style.color = ok ? 'var(--green)' : 'var(--red)'; }

      $('#s_preset').addEventListener('change', function (e) {
        var p = presets.filter(function (x) { return x.id === e.target.value; })[0];
        if (p && p.base_url) { $('#s_llm_base_url').value = p.base_url; $('#s_llm_model').value = p.model; }
        if (p && p.id === 'custom') { $('#s_llm_base_url').value = ''; $('#s_llm_model').value = ''; $('#s_llm_base_url').focus(); }
        showHelp(); $('#llmMsg').textContent = '';
      });
      $$('[data-clear]', form).forEach(function (b) {
        b.addEventListener('click', function () {
          var k = b.dataset.clear;
          if (clear.indexOf(k) < 0) clear.push(k);
          var input = $('#s_' + k);
          input.value = ''; input.placeholder = '将在保存后清除'; b.remove();
          toast('保存后生效');
        });
      });
      $('#testLlm').addEventListener('click', function (e) {
        var b = e.currentTarget, m = $('#llmMsg'); m.textContent = '';
        busy(b, true, '测试中…');
        api('POST', '/api/settings/test-llm', { values: formValues() }).then(function (r) {
          busy(b, false); msg(m, '连接成功：' + r.model + '，响应 ' + (r.ms / 1000).toFixed(1) + ' 秒。别忘了保存。', true);
        }).catch(function (err) { busy(b, false); msg(m, err.message, false); });
      });
      $('#testPush').addEventListener('click', function (e) {
        var b = e.currentTarget, m = $('#pushMsg'), vals = formValues(); m.textContent = '';
        busy(b, true, '发送中…');
        api('POST', '/api/settings/test-push', { feishu_bot_webhook: vals.feishu_bot_webhook, feishu_bot_secret: vals.feishu_bot_secret }).then(function (r) {
          busy(b, false); msg(m, r.where === 'feishu' ? '已发送，去飞书群看看' : '没填 Webhook，已发到站内「提醒」', true);
        }).catch(function (err) { busy(b, false); msg(m, err.message, false); });
      });
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var b = $('button[type=submit]', form); busy(b, true);
        api('PUT', '/api/settings', { values: formValues(), clear: clear }).then(function () {
          busy(b, false); toast('设置已保存，已生效'); route();
        }).catch(function (err) { busy(b, false); $('#sErr').textContent = err.message; });
      });
      $('#sDaily').addEventListener('click', function (e) {
        var b = e.currentTarget; busy(b, true, '生成中');
        api('POST', '/api/tasks/daily', {}).then(function (r) { busy(b, false); toast('今日跟进 ' + r.count + ' 位，已推送'); }).catch(function (err) { busy(b, false); fail(err); });
      });
    });
  };

  // ------------------------------------------------------------------ 成员
  ROUTES.users = function (page) {
    return api('GET', '/api/users').then(function (d) {
      page.innerHTML = head('成员', '业务员可以处理询盘、报价、跟进和维护产品；管理员还能修改设置、管理成员、删除客户。', '<button class="btn primary" id="uAdd">' + icon('plus', 16) + '新增成员</button>') +
        '<div class="tbl-wrap"><table class="tbl" style="min-width:640px"><thead><tr><th>姓名</th><th>用户名</th><th>角色</th><th>状态</th><th></th></tr></thead><tbody>' +
        d.items.map(function (u) {
          var me = u.id === state.user.id;
          return '<tr><td><b>' + esc(u.name) + '</b>' + (me ? ' <span class="small dim">（我）</span>' : '') + '</td><td class="num">' + esc(u.username) + '</td><td>' + (u.role === 'admin' ? '管理员' : '业务员') + '</td>' +
            '<td>' + (u.active ? '<span class="st st-已报价">正常</span>' : '<span class="st st-已流失">已停用</span>') + '</td><td style="text-align:right;white-space:nowrap">' +
            '<button class="btn sm" data-pw="' + u.id + '">重置密码</button> ' +
            (me ? '' : '<button class="btn sm" data-role="' + u.id + '" data-to="' + (u.role === 'admin' ? 'sales' : 'admin') + '">设为' + (u.role === 'admin' ? '业务员' : '管理员') + '</button> <button class="btn sm' + (u.active ? ' danger' : '') + '" data-act="' + u.id + '" data-to="' + (u.active ? '0' : '1') + '">' + (u.active ? '停用' : '启用') + '</button>') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
      $('#uAdd').addEventListener('click', function () {
        modal('<h2>新增成员</h2><form id="uForm"><div class="form-grid"><div class="field"><label class="f" for="u_name">姓名</label><input class="input" id="u_name" name="name" required></div>' +
          '<div class="field"><label class="f" for="u_username">用户名（登录用）</label><input class="input" id="u_username" name="username" required autocomplete="off"></div>' +
          '<div class="field"><label class="f" for="u_password">初始密码（至少 6 位）</label><input class="input" id="u_password" name="password" type="password" required autocomplete="new-password"></div>' +
          '<div class="field"><label class="f" for="u_role">角色</label><select class="input" id="u_role" name="role"><option value="sales">业务员</option><option value="admin">管理员</option></select></div></div>' +
          '<div id="uErr" class="small" style="color:var(--red);min-height:18px"></div><div class="row"><button class="btn primary" type="submit">创建</button><button class="btn" type="button" id="uCancel">取消</button></div></form>',
          function (m, close) {
            $('#uCancel', m).addEventListener('click', close);
            $('#u_name', m).focus();
            $('#uForm', m).addEventListener('submit', function (e) {
              e.preventDefault();
              var body = {};
              $$('[name]', e.target).forEach(function (el) { body[el.name] = el.value; });
              api('POST', '/api/users', body).then(function () { close(); toast('已创建'); route(); }).catch(function (err) { $('#uErr', m).textContent = err.message; });
            });
          });
      });
      page.addEventListener('click', function (e) {
        var pw = e.target.closest('[data-pw]'), ro = e.target.closest('[data-role]'), ac = e.target.closest('[data-act]');
        if (pw) {
          var p = window.prompt('输入新密码（至少 6 位）');
          if (p) api('PATCH', '/api/users/' + pw.dataset.pw, { password: p }).then(function () { toast('密码已重置'); }).catch(fail);
        }
        if (ro) api('PATCH', '/api/users/' + ro.dataset.role, { role: ro.dataset.to }).then(function () { toast('已更新'); route(); }).catch(fail);
        if (ac) api('PATCH', '/api/users/' + ac.dataset.act, { active: ac.dataset.to === '1' }).then(function () { toast('已更新'); route(); }).catch(fail);
      });
    });
  };

  // ------------------------------------------------------------------ 启动
  function boot() {
    api('GET', '/api/me').then(function (d) {
      state.user = d.user;
      return api('GET', '/api/dashboard').then(function (x) { state.dueCount = x.metrics.due_today; }).catch(function () { });
    }).then(function () {
      if (state.user) route();
    }).catch(function () { /* 已在 api() 里切到登录页 */ });
  }
  boot();
})();
