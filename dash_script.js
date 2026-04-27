
'use strict';

// ─── State ────────────────────────────────────────────────────────────────────
const S = {
  // Luck analyzer (existing)
  data:    { hitters: [], pitchers: [] },
  tab:     'hitters',
  sort:    { hitters: { col: 'luck_score', dir: 'desc', userSort: false },
             pitchers: { col: 'luck_score', dir: 'desc', userSort: false } },
  search:  { hitters: '', pitchers: '' },
  vfilter:    { hitters: null, pitchers: null },
  tierfilter: { hitters: null, pitchers: null },
  ready:   { hitters: false, pitchers: false },
  // View mode: 'simple' (default) | 'advanced'
  viewMode: 'simple',
  // Position data
  cbsPositions:     {},   // mlbam_id (string) -> {name, position, source}
  positionOverrides:{},   // mlbam_id (string) -> position string
  // Trade value
  league:          'league1',
  tvTab:           'hitters',   // 'all' | 'hitters' | 'pitchers'
  tvVerdictFilter: 'all',       // 'all' | 'Buy low' | 'Sell high' | 'neutral'
  tvData:          null,
  tvSearch: { all: '', hitters: '', pitchers: '' },
  tvSort:   { all:      { col: '__value', dir: 'desc' },
              hitters:  { col: '__value', dir: 'desc' },
              pitchers: { col: '__value', dir: 'desc' } },
  tvLeagueNames: { league1: 'League 1', league2: 'League 2' },
  tvMode: 'analyzer',   // 'analyzer' | 'rankings'
  // Trade analyzer
  ta: { giving: [], getting: [], dropping: [], results: null },
  taBuilt: false,
  taByName: {},   // normalizeName -> flatPlayer
  taById:   {},   // id string -> flatPlayer
  hLuckById:{},   // batter id string -> luck row
  pLuckById:{},   // pitcher id string -> luck row
  taLeague: {
    size: '12', format: 'redraft', scoring: '5x5',
    hCats: ['avg','r','hr','rbi','sb'],
    pCats: ['era','whip','w','k','svh'],
  },
};

// ─── Column definitions ───────────────────────────────────────────────────────
// fmt codes: name | int | f1 | f2 | rate (3dp) | pct (×100, 1dp%) |
//            gap (±f2, coloured) | luck (±f4, coloured) | badge | team
const HITTER_COLS = [
  { key:'name',          label:'Player',     fmt:'name'  },
  { key:'PA',            label:'PA',         fmt:'int'   },
  // ── Scoring components (v2 model) ────────────────────────────────────────
  { key:'BABIP',         label:'BABIP',      fmt:'rate'  },
  { key:'hr_fb_rate',    label:'HR/FB%',     fmt:'pct'   },
  { key:'xwOBA_gap',     label:'xwOBA Gap',  fmt:'xwoba' },
  { key:'z_contact_rate',label:'Z-Con%',     fmt:'pct'   },
  // ── Display-only metrics (informational; not in v2 scoring formula) ──────
  { key:'hard_hit_rate', label:'Hard Hit%',  fmt:'pct'   },
  { key:'barrel_rate',   label:'Barrel%',    fmt:'pct'   },
  // ── Result ───────────────────────────────────────────────────────────────
  { key:'luck_score',    label:'Luck Score', fmt:'luck'  },
  { key:'verdict',       label:'Verdict',    fmt:'badge', nosort:true },
  { key:'tier_sell',     label:'Sell Tier',  fmt:'tier',  nosort:true },
];

const PITCHER_COLS = [
  { key:'name',                  label:'Player',    fmt:'name'  },
  { key:'Team',                  label:'Team',      fmt:'team'  },
  { key:'IP',                    label:'IP',        fmt:'f1'    },
  { key:'ERA',                   label:'ERA',       fmt:'f2'    },
  { key:'FIP',                   label:'FIP',       fmt:'f2'    },
  { key:'ERA_minus_FIP',         label:'ERA−FIP',   fmt:'gap'   },
  { key:'xERA',                  label:'xERA',      fmt:'f2'    },
  { key:'BABIP_allowed',         label:'BABIP',     fmt:'rate'  },
  { key:'lob_pct',               label:'LOB%',      fmt:'pct'   },
  { key:'hard_hit_rate_allowed', label:'Hard Hit%', fmt:'pct'   },
  { key:'swstr_rate',            label:'SwStr%',    fmt:'pct'   },
  { key:'luck_score',            label:'Luck Score',fmt:'luck'  },
  { key:'verdict',               label:'Verdict',   fmt:'badge', nosort:true },
  { key:'tier_sell',             label:'Sell Tier', fmt:'tier',  nosort:true },
];

// ─── Trade value column definitions ──────────────────────────────────────────
// '__value' resolves to 'league1_value' or 'league2_value' based on S.league.
// '__esv'   resolves to 'expected_stats_value_l1' or '_l2' based on S.league.
// '_rank'   is injected per-row in renderTVTable (rank within player type).
const TV_COLS = [
  { key:'name',                   label:'Player',       fmt:'name'  },
  { key:'pos',                    label:'Pos',          fmt:'pos'   },
  { key:'__value',                label:'Trade Value',  fmt:'value' },
  { key:'__esv',                  label:'Exp Stats',    fmt:'f2'    },
  { key:'track_record_multiplier',label:'Track Rec',    fmt:'f2'    },
  { key:'quality_points',         label:'QP',           fmt:'int'   },
  { key:'luck_adjustment',        label:'Luck Adj',     fmt:'f2'    },
  { key:'verdict',                label:'Verdict',      fmt:'badge', nosort:true },
  { key:'_rank',                  label:'League Rank',  fmt:'int',   nosort:true },
];

// ─── Verdict helpers ──────────────────────────────────────────────────────────
const VERDICTS = [
  { key:'Buy low',    cls:'vBuyLow',    label:'Buy Low',    row:'rBuyLow'    },
  { key:'Slight buy', cls:'vSlightBuy', label:'Slight Buy', row:'rSlightBuy' },
  { key:'Neutral',    cls:'vNeutral',   label:'Neutral',    row:''           },
  { key:'Slight sell',cls:'vSlightSell',label:'Slight Sell',row:'rSlightSell'},
  { key:'Sell high',  cls:'vSellHigh',  label:'Sell High',  row:'rSellHigh'  },
];
const VERDICT_MAP = Object.fromEntries(VERDICTS.map(v => [v.key, v]));

function vInfo(raw) {
  return VERDICT_MAP[raw] || { key:raw, cls:'vNeutral', label: raw || 'Neutral', row:'' };
}

// ─── Number helpers ───────────────────────────────────────────────────────────
function isNA(v) {
  return v === undefined || v === null || v === ''
    || String(v).trim().toLowerCase() === 'nan'
    || String(v).trim() === '—';
}

function toNum(v) {
  if (isNA(v)) return NaN;
  const n = parseFloat(v);
  return isNaN(n) ? NaN : n;
}

// Sort key: NaN sorts last regardless of direction
function sortKey(v) {
  const n = toNum(v);
  if (!isNaN(n)) return n;
  if (isNA(v)) return null; // sorted last
  return String(v).toLowerCase();
}

// ─── Cell formatters  ─────────────────────────────────────────────────────────
// Each returns a <td>...</td> string
const F = {
  name(v)  { return `<td class="name-cell">${isNA(v) ? '—' : esc(v)}</td>`; },
  team(v)  { return isNA(v) ? `<td class="na">—</td>` : `<td>${esc(v)}</td>`; },
  int(v)   {
    const n = toNum(v);
    return isNaN(n) ? `<td class="na">—</td>` : `<td>${Math.round(n)}</td>`;
  },
  f1(v) {
    const n = toNum(v);
    return isNaN(n) ? `<td class="na">—</td>` : `<td>${n.toFixed(1)}</td>`;
  },
  f2(v) {
    const n = toNum(v);
    return isNaN(n) ? `<td class="na">—</td>` : `<td>${n.toFixed(2)}</td>`;
  },
  rate(v) {
    const n = toNum(v);
    return isNaN(n) ? `<td class="na">—</td>` : `<td>.${String(Math.round(n * 1000)).padStart(3,'0')}</td>`;
  },
  pct(v) {
    const n = toNum(v);
    return isNaN(n) ? `<td class="na">—</td>` : `<td>${(n * 100).toFixed(1)}%</td>`;
  },
  gap(v) {
    const n = toNum(v);
    if (isNaN(n)) return `<td class="na">—</td>`;
    const sign = n > 0 ? '+' : '';
    const cls  = n > 0.3 ? 'pos' : n < -0.3 ? 'neg' : '';
    return `<td class="${cls}">${sign}${n.toFixed(2)}</td>`;
  },
  // Signed .NNN rate display for xwOBA gap — coloured at ±0.020 threshold
  // Positive = player underperformed contact quality (unlucky, green)
  // Negative = player overperformed contact quality (lucky, red)
  xwoba(v) {
    const n = toNum(v);
    if (isNaN(n)) return `<td class="na">—</td>`;
    const cls  = n > 0.020 ? 'pos' : n < -0.020 ? 'neg' : '';
    const abs3 = Math.abs(Math.round(n * 1000)).toString().padStart(3, '0');
    const disp = (n < 0 ? '−.' : '+.') + abs3;
    return `<td class="${cls}">${disp}</td>`;
  },
  luck(v) {
    const n = toNum(v);
    if (isNaN(n)) return `<td class="na">—</td>`;
    const sign = n > 0 ? '+' : '';
    const cls  = n > 0.05 ? 'luck-pos' : n < -0.05 ? 'luck-neg' : 'luck-neu';
    return `<td class="${cls}">${sign}${n.toFixed(4)}</td>`;
  },
  badge(v, r) {
    const info   = vInfo(v);
    const volBadge = (r && (r.volatility_flag === true || r.volatility_flag === 'True'))
      ? `<span class="volatility-badge" title="${esc(r.volatility_label || 'High variance — signals less reliable')}">⚡</span>` : '';
    return `<td><span class="badge ${info.cls}">${info.label}</span>${volBadge}</td>`;
  },
  tier(v) {
    if (isNA(v) || v === null || v === 'None') return `<td></td>`;
    const TIER_MAP = {
      'Sell and Move On':           { cls:'tSellMoveOn', label:'Move On'    },
      'Sell High on Perception':    { cls:'tSellPerc',   label:'Perception' },
      'Veteran Regression':         { cls:'tVetReg',     label:'Vet Reg'    },
      'Slight Regression Expected': { cls:'tSlightReg',  label:'Slight Reg' },
    };
    const info = TIER_MAP[v] || { cls:'vNeutral', label: String(v) };
    return `<td><span class="badge ${info.cls}">${info.label}</span></td>`;
  },
  // 0-100 trade value badge
  value(v) {
    const n = toNum(v);
    if (isNaN(n) || n === 0) return `<td><span class="val-badge val-zero">—</span></td>`;
    const cls = n > 75 ? 'val-elite' : n > 40 ? 'val-great' : n > 10 ? 'val-good' : 'val-zero';
    return `<td><span class="val-badge ${cls}">${n.toFixed(1)}</span></td>`;
  },
  // Position abbreviation (SP/RP/C/1B/etc.)
  pos(v) {
    return isNA(v) ? `<td class="na">—</td>` : `<td class="pos-cell">${esc(v)}</td>`;
  },
};

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Position lookup ──────────────────────────────────────────────────────────
// Returns CBS-standard position string for a player, applying any override.
function getPosition(mlbamId) {
  const id = String(mlbamId);
  // Override wins
  if (S.positionOverrides[id]) return S.positionOverrides[id];
  // CBS Sports lookup
  const entry = S.cbsPositions[id];
  if (entry && entry.position && entry.position !== 'N/A') return entry.position;
  return '—';
}

// ─── Explanation generator ────────────────────────────────────────────────────
// Generates a one-line plain-English explanation from row metrics.
// type: 'hitter' | 'pitcher'
function generateExplanation(row, type, pvEntry) {
  const first = (name) => String(name || '').split(' ')[0];
  const nm    = esc(row.name || 'This player');
  const fn    = esc(first(row.name));
  const verdict   = row.verdict || '';
  const tier      = row.tier_sell || '';
  const age_flag  = row.age_flag || '';

  if (type === 'hitter') {
    const babip    = parseFloat(row.BABIP)          || 0;
    const xgap     = parseFloat(row.xwOBA_gap)      || 0;
    const hrfb     = parseFloat(row.hr_fb_rate)     || 0;
    const hhr      = parseFloat(row.hard_hit_rate)  || 0;
    const pa       = parseInt(row.PA)               || 0;
    const age      = parseInt(row.age)              || 0;

    // CQS conversion rate flag overrides (check before normal logic)
    const convFlag = row.conversion_flag || '';
    if (convFlag === 'underperformer') {
      if (verdict === 'Buy low' || verdict === 'Slight buy') {
        return `${fn} is unlucky by the numbers — but strong contact metrics have historically produced outs. Temper expectations on the upside.`;
      }
    }
    if (convFlag === 'overperformer') {
      // FIX 1: gate overperformer language to verdict direction.
      // Sell candidates with overperformer flag need sell language, not buy language.
      if (verdict === 'Sell high' || verdict === 'Slight sell') {
        return `${fn} consistently outperforms their Statcast metrics — which makes right now the ideal time to sell. Their ceiling is already being exceeded and regression is coming even by their own elevated standard.`;
      }
      return `Don't be fooled by mediocre Statcast metrics for ${fn} — this player consistently outperforms the underlying numbers`;
    }

    // Small sample Neutral
    if (verdict === 'Neutral' && pa < 55) {
      return `Too early in the season to generate a reliable signal for ${fn} — check back in May`;
    }

    if (verdict === 'Buy low') {
      // FIX 3: CQS-aware override for floored players — career track record outweighs
      // soft-contact small-sample concern.
      const floorApplied = pvEntry && pvEntry.cqs_floor_applied;
      const cqsTier      = pvEntry && pvEntry.cqs_tier;
      if (floorApplied && cqsTier) {
        const tierLabel = cqsTier === 'Superstar' ? 'Superstar' : 'proven';
        return `${fn} is a ${tierLabel}-caliber player having an unusually cold stretch — the career track record says buy with confidence`;
      }
      // Tier 1: strong xwOBA gap + terrible BABIP — clearest buy signal
      if (xgap > 0.060 && babip < 0.270) {
        return `${fn} is making elite contact but a .${Math.round(babip*1000).toString().padStart(3,'0')} BABIP is one of the worst in baseball — strong buy before the market catches on`;
      }
      // Tier 2: strong xwOBA gap alone
      if (xgap > 0.060) {
        return `${fn}'s underlying metrics are significantly better than their stats suggest — regression incoming upward`;
      }
      // Fix 4: soft contact — hard_hit% gate fired, cap upside expectations
      if (hhr > 0 && hhr < 0.28) {
        // Near-threshold zone (26–28%): extreme BABIP with borderline contact → split language
        if (hhr >= 0.26 && babip < 0.200) {
          return `${fn} is suffering through extreme bad luck on balls in play — but soft contact limits how much they'll benefit when it normalizes. Cautious buy.`;
        }
        return `${fn} has a low BABIP but soft contact metrics suggest limited upside — mild buy at best`;
      }
      // Fix 2: pure BABIP luck case — very low BABIP with modest xwOBA gap
      if (babip < 0.220) {
        return `${fn}'s .${Math.round(babip*1000).toString().padStart(3,'0')} BABIP is one of the worst in baseball — extreme bad luck that should normalize`;
      }
      return `${fn} is unlucky — contact quality is running well ahead of their results so far this season`;
    }

    if (verdict === 'Slight buy') {
      return `${fn} is showing positive signs — modest improvement likely as luck normalizes`;
    }

    if (tier === 'Sell and Move On') {
      if (age_flag === 'Decline risk') {
        return `${fn} is ${age} posting results their contact quality doesn't support — at this age, any correction may be permanent. Get out now.`;
      }
      return `${fn}'s results are well ahead of their contact quality — this won't last. Move on.`;
    }

    if (tier === 'Sell High on Perception') {
      if (hrfb > 0.250) {
        return `${fn} is hitting HRs at an unsustainable rate (${(hrfb*100).toFixed(0)}% HR/FB) — cash in before the correction hits`;
      }
      return `${fn} is running hot even by their own elite standard — peak value right now, sell into it`;
    }

    if (tier === 'Veteran Regression') {
      if (age_flag) {
        return `${fn} is ${age} with a proven track record — sell while perception is high; any correction may linger at this age`;
      }
      return `${fn} is a proven veteran riding a lucky BABIP streak — hold unless you can get full value back`;
    }

    if (tier === 'Slight Regression Expected' || verdict === 'Slight sell') {
      return `${fn} has mild luck working in their favor — minor correction likely but nothing dramatic`;
    }

    // Genuine Neutral
    return `${fn}'s results are in line with their underlying metrics — no actionable signal in either direction`;

  } else {
    // Pitcher
    const era      = parseFloat(row.ERA)            || 0;
    const fip      = parseFloat(row.FIP)            || 0;
    const xgap     = parseFloat(row.xwoba_gap)      || 0;
    const ip       = parseFloat(row.IP)             || 0;
    const conf     = row.conf_phase                 || '';
    const age_flag = row.age_flag                   || '';
    const age      = parseInt(row.age)              || 0;
    const efip     = parseFloat(row.ERA_minus_FIP)  || 0;

    // Small sample Neutral (April phase, low IP)
    if (verdict === 'Neutral' && conf === 'April' && ip < 20) {
      return `Too early in the season to generate a reliable signal for ${fn} — check back in May`;
    }

    if (verdict === 'Buy low') {
      if (efip > 1.0) {
        return `${fn}'s ERA is ${efip.toFixed(1)} runs above their FIP — luck-driven inflation, real performance is much better`;
      }
      return `${fn}'s ERA is running well above their underlying contact quality — expect meaningful regression downward`;
    }

    if (verdict === 'Slight buy') {
      return `${fn} is showing some bad luck in their ERA — modest improvement likely as sequencing normalizes`;
    }

    if (tier === 'Sell and Move On') {
      if (age_flag === 'Decline risk') {
        return `${fn} is ${age} with ERA running ahead of contact quality — at this age structural decline is possible. Move on.`;
      }
      return `${fn}'s ERA is significantly better than their peripherals suggest — this won't hold. Sell now.`;
    }

    if (tier === 'Sell High on Perception') {
      return `${fn} is running hot and ERA looks great — underlying metrics say regression is coming. Cash in.`;
    }

    if (tier === 'Veteran Regression') {
      return `${fn} is a proven arm on a lucky stretch — sell while the ERA narrative is strong`;
    }

    if (tier === 'Slight Regression Expected' || verdict === 'Slight sell') {
      return `${fn} has mild luck working in their favor — minor ERA correction likely but nothing dramatic`;
    }

    // Genuine Neutral
    return `${fn}'s ERA and underlying metrics are tightly aligned — no meaningful luck signal in either direction`;
  }
}

// ─── View mode toggle ─────────────────────────────────────────────────────────
function toggleViewMode() {
  const wrap = document.querySelector('.tbl-wrap');
  wrap.classList.add('fading');
  setTimeout(() => {
    S.viewMode = S.viewMode === 'simple' ? 'advanced' : 'simple';
    const btn = document.getElementById('view-toggle-btn');
    if (btn) {
      btn.textContent = S.viewMode === 'simple' ? 'Advanced View' : 'Simple View';
      btn.classList.toggle('advanced', S.viewMode === 'advanced');
    }
    renderTable();
    wrap.classList.remove('fading');
  }, 150);
}

// ─── Trade value helpers ──────────────────────────────────────────────────────
function flattenPlayer(p) {
  // Hoist p.proj.X into p.proj_X for flat column key access
  const flat = Object.assign({}, p);
  if (p.proj && typeof p.proj === 'object') {
    for (const [k, v] of Object.entries(p.proj)) {
      flat['proj_' + k] = v;
    }
    delete flat.proj;
  }
  return flat;
}

function loadPlayerValues(json) {
  try {
    const parsed = typeof json === 'string' ? JSON.parse(json) : json;
    S.tvData = (parsed.players || []).map(flattenPlayer);
    S.tvLeagueNames = parsed.leagues || { league1: 'League 1', league2: 'League 2' };
    // Index by player id for O(1) trade-value lookup in Simple View gate
    S.tvById = {};
    (parsed.players || []).forEach(p => { if (p.id) S.tvById[String(p.id)] = p; });
    const note = document.getElementById('tv-gen-note');
    if (note && parsed.generated_at) {
      note.textContent = 'Projections generated ' + parsed.generated_at.replace('T', ' ').slice(0, 16)
        + ' \u00b7 ' + parsed.season_days + ' days into season';
    }
    return true;
  } catch(e) {
    console.error('player_values.json parse error:', e);
    return false;
  }
}

// Resolve '__value' → league-specific value column
function tvValueKey() { return S.league + '_value'; }
// Resolve '__esv' → league-specific expected-stats-value column
function tvEsvKey()   { return 'expected_stats_value_' + (S.league === 'league2' ? 'l2' : 'l1'); }

function getTvCols() { return TV_COLS; }

function tvColKey(c) {
  if (c.key === '__value') return tvValueKey();
  if (c.key === '__esv')   return tvEsvKey();
  return c.key;
}

// ─── Trade value render ───────────────────────────────────────────────────────
const TV_VF_BUTTONS = [
  { key:'all',       label:'All',       cls:'vf-all' },
  { key:'Buy low',   label:'Buy Low',   cls:'vf-bl'  },
  { key:'Sell high', label:'Sell High', cls:'vf-sh'  },
  { key:'neutral',   label:'Neutral',   cls:'vf-nt'  },
];

function renderTV() {
  const isTV = S.tab === 'tradevalue';
  document.getElementById('luck-content').style.display = isTV ? 'none' : 'block';
  document.getElementById('tv-content').style.display    = isTV ? 'block' : 'none';
  document.getElementById('league-toggle').style.display = isTV ? '' : 'none';
  if (!isTV) return;

  // Sync league button states
  document.getElementById('lg-btn-1').classList.toggle('active', S.league === 'league1');
  document.getElementById('lg-btn-2').classList.toggle('active', S.league === 'league2');
  document.getElementById('lg-btn-1').textContent = S.tvLeagueNames.league1 || 'League 1';
  document.getElementById('lg-btn-2').textContent = S.tvLeagueNames.league2 || 'League 2';

  // Sync type filter buttons
  document.getElementById('tv-tab-all').classList.toggle('active', S.tvTab === 'all');
  document.getElementById('tv-tab-h').classList.toggle('active',   S.tvTab === 'hitters');
  document.getElementById('tv-tab-p').classList.toggle('active',   S.tvTab === 'pitchers');

  // Render verdict filter bar
  document.getElementById('tv-verdict-bar').innerHTML = TV_VF_BUTTONS.map(b => {
    const active = S.tvVerdictFilter === b.key ? ' active' : '';
    return `<button class="tv-vf-btn ${b.cls}${active}" onclick="setTvVerdict('${b.key}')">${b.label}</button>`;
  }).join('');

  if (!S.tvData) {
    document.getElementById('tv-head').innerHTML = '';
    document.getElementById('tv-body').innerHTML =
      `<tr><td colspan="${TV_COLS.length}" class="tv-empty">
         Trade value data not yet generated.<br>
         Run <code>python score_value.py --write</code> to create
         <code>data/player_values.json</code>, then reload the dashboard.
       </td></tr>`;
    document.getElementById('tv-results').textContent = '';
    return;
  }

  renderTVTable();
}

function renderTVTable() {
  const type = S.tvTab;   // 'all' | 'hitters' | 'pitchers'
  const vf   = S.tvVerdictFilter;
  const cols = getTvCols();
  const sort = S.tvSort[type] || S.tvSort.hitters;
  const q    = (S.tvSearch[type] || '').toLowerCase();
  const vk   = tvValueKey();

  // Pre-compute league ranks for each player type (unfiltered, full pool)
  const rankMap = {};
  ['hitter', 'pitcher'].forEach(ptype => {
    (S.tvData || [])
      .filter(p => p.type === ptype)
      .slice()
      .sort((a, b) => (b[vk] || 0) - (a[vk] || 0))
      .forEach((p, i) => { rankMap[p.id] = i + 1; });
  });

  // Map tab name ('hitters') → player type ('hitter')
  const typeFilter = { hitters: 'hitter', pitchers: 'pitcher' };

  // Filter rows
  let rows = (S.tvData || []).filter(p => {
    if (type !== 'all' && p.type !== typeFilter[type]) return false;
    if (q && !String(p.name || '').toLowerCase().includes(q)) return false;
    if (vf !== 'all') {
      const v = String(p.verdict || '').toLowerCase();
      if (vf === 'neutral') { if (!v.includes('neutral')) return false; }
      else                  { if (p.verdict !== vf) return false; }
    }
    return true;
  });

  // Sort
  const sk = sort.col === '__value' ? vk
           : sort.col === '__esv'   ? tvEsvKey()
           : sort.col;
  rows.sort((a, b) => {
    const va = sortKey(a[sk]);
    const vb = sortKey(b[sk]);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
    return sort.dir === 'desc' ? -cmp : cmp;
  });

  // Inject league rank into local row copies
  rows = rows.map(row => ({ ...row, _rank: rankMap[row.id] }));

  // Render header
  document.getElementById('tv-head').innerHTML = '<tr>' + cols.map(c => {
    if (c.nosort) return `<th style="cursor:default">${esc(c.label)}</th>`;
    const active = sort.col === c.key;
    const arr    = active ? (sort.dir === 'asc' ? ' &#9650;' : ' &#9660;') : ' <i class="sort-arrow">&#8597;</i>';
    return `<th class="${active ? 'sorted' : ''}"
                data-col="${c.key}"
                onclick="onTvSort(this.dataset.col)">${esc(c.label)}${arr}</th>`;
  }).join('') + '</tr>';

  // Render body
  if (!rows.length) {
    document.getElementById('tv-body').innerHTML =
      `<tr><td colspan="${cols.length}" class="tv-empty">No players found.</td></tr>`;
    document.getElementById('tv-results').textContent = '0 players';
    return;
  }

  document.getElementById('tv-body').innerHTML = rows.map(row => {
    const info   = vInfo(row.verdict || '');
    const rowCls = info.row || '';
    const cells  = cols.map(c => {
      const k   = tvColKey(c);
      const fmt = F[c.fmt] || F.f1;
      return fmt(row[k]);
    }).join('');
    return `<tr class="${rowCls}">${cells}</tr>`;
  }).join('');

  document.getElementById('tv-results').textContent =
    `${rows.length.toLocaleString()} players`;
}

// ─── Trade value event handlers ───────────────────────────────────────────────
function setLeague(lg) {
  S.league = lg;
  renderTV();
}

function setTvTab(tab) {
  S.tvTab = tab;
  document.getElementById('tv-search').value = S.tvSearch[tab] || '';
  renderTV();
}

function setTvVerdict(v) {
  S.tvVerdictFilter = v;
  renderTV();
}

function onTvSort(col) {
  const s = S.tvSort[S.tvTab] || S.tvSort.hitters;
  s.dir = (s.col === col && s.dir === 'desc') ? 'asc' : 'desc';
  s.col = col;
  renderTVTable();
}

function onTvSearch(val) {
  S.tvSearch[S.tvTab] = val;
  renderTVTable();
}

// ─── CSV parser ───────────────────────────────────────────────────────────────
function parseCSV(text) {
  // Normalize line endings
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  let pos = 0;
  const len = lines.length;

  function readField() {
    let f = '';
    if (pos < len && lines[pos] === '"') {
      pos++; // skip opening quote
      while (pos < len) {
        if (lines[pos] === '"') {
          pos++;
          if (pos < len && lines[pos] === '"') { f += '"'; pos++; } // escaped quote
          else break; // closing quote
        } else { f += lines[pos++]; }
      }
    } else {
      while (pos < len && lines[pos] !== ',' && lines[pos] !== '\n') {
        f += lines[pos++];
      }
    }
    return f;
  }

  function readLine() {
    const fields = [];
    while (pos < len && lines[pos] !== '\n') {
      fields.push(readField());
      if (pos < len && lines[pos] === ',') pos++;
    }
    if (pos < len) pos++; // consume newline
    return fields;
  }

  const headers = readLine().map(h => h.trim());
  const rows = [];
  while (pos < len) {
    const vals = readLine();
    if (vals.length === 0 || (vals.length === 1 && vals[0].trim() === '')) continue;
    const obj = {};
    headers.forEach((h, i) => { obj[h] = vals[i] !== undefined ? vals[i].trim() : ''; });
    rows.push(obj);
  }
  return rows;
}

// ─── Verdict counts ───────────────────────────────────────────────────────────
function verdictCounts(data) {
  const c = {};
  VERDICTS.forEach(v => { c[v.key] = 0; });
  data.forEach(r => { if (c[r.verdict] !== undefined) c[r.verdict]++; });
  return c;
}

// ─── Render: header meta ──────────────────────────────────────────────────────
function renderMeta() {
  const h = S.data.hitters.length;
  const p = S.data.pitchers.length;
  const now = new Date().toLocaleString('en-US',
    { month:'short', day:'numeric', hour:'numeric', minute:'2-digit' });
  document.getElementById('hdr-meta').innerHTML =
    `${h} batters · ${p} pitchers<br>Updated ${now}`;
}

// ─── Render: tier filter buttons ─────────────────────────────────────────────
function renderTierButtons() {
  const tab = S.tab;
  const data = S.data[tab];
  const tf = S.tierfilter[tab];

  const TIER_DEFS = [
    { key:'Sell and Move On',           cls:'tSellMoveOn', label:'Sell and Move On'     },
    { key:'Sell High on Perception',    cls:'tSellPerc',   label:'Sell High on Perception' },
    { key:'Veteran Regression',         cls:'tVetReg',     label:'Veteran Regression'   },
    { key:'Slight Regression Expected', cls:'tSlightReg',  label:'Slight Regression'    },
  ];

  const counts = {};
  data.forEach(r => { if (r.tier_sell) counts[r.tier_sell] = (counts[r.tier_sell] || 0) + 1; });
  const totalTiered = Object.values(counts).reduce((a, b) => a + b, 0);

  if (totalTiered === 0) {
    document.getElementById('tier-btns').innerHTML = '';
    return;
  }

  const btns = TIER_DEFS
    .filter(d => counts[d.key] > 0)
    .map(d => {
      const act = tf === d.key ? ' active' : '';
      return `<button class="tier-btn ${d.cls}${act}"
                      onclick="toggleTierFilter('${d.key}')">${d.label} (${counts[d.key]})</button>`;
    }).join('');
  document.getElementById('tier-btns').innerHTML = '<span class="tier-label">Sell tier:</span>' + btns;
}

// ─── Render: cards ────────────────────────────────────────────────────────────
function renderCards() {
  const data   = S.data[S.tab];
  const counts = verdictCounts(data);
  const total  = data.length;
  const vf     = S.vfilter[S.tab];

  const CARD_DEF = [
    { key:'Buy low',    cls:'vBuyLow',    label:'Buy Low'    },
    { key:'Slight buy', cls:'vSlightBuy', label:'Slight Buy' },
    { key:'Neutral',    cls:'vNeutral',   label:'Neutral'    },
    { key:'Slight sell',cls:'vSlightSell',label:'Slight Sell'},
    { key:'Sell high',  cls:'vSellHigh',  label:'Sell High'  },
  ];

  document.getElementById('cards').innerHTML = CARD_DEF.map(d => {
    const n   = counts[d.key] || 0;
    const pct = total ? Math.round(n / total * 100) : 0;
    const act = vf === d.key ? ' active' : '';
    return `<div class="v-card ${d.cls}${act}"
                 data-verdict="${d.key}"
                 onclick="toggleFilter(this.dataset.verdict)">
      <div class="vc-label">${d.label}</div>
      <div class="vc-count">${n}</div>
      <div class="vc-pct">${pct}% of ${total}</div>
    </div>`;
  }).join('');
}

// ─── Render: table ────────────────────────────────────────────────────────────
function renderTable() {
  if (S.viewMode === 'simple') {
    renderSimpleTable();
  } else {
    renderAdvancedTable();
  }
}

// ─── Shared filter helper ─────────────────────────────────────────────────────
// CQS tier priority: lower = higher priority in table (SUP first)
const CQS_TIER_RANK = { 'Superstar': 0, 'Established Star': 1, 'Solid Contributor': 2 };
// Verdict bucket rank for primary grouping when sorting by luck_score
const VERDICT_BUCKET_RANK = {
  'Buy low': 0, 'Slight buy': 1, 'Neutral': 2, 'Slight sell': 3, 'Sell high': 4
};

function cqsTierRank(row, idKey) {
  const pvEntry = S.tvById && S.tvById[String(row[idKey])];
  const tier    = pvEntry && pvEntry.cqs_tier;
  return CQS_TIER_RANK[tier] ?? 3; // 3 = no tag, sorts last within bucket
}

function getFilteredRows(tab) {
  const sort  = S.sort[tab];
  const vf    = S.vfilter[tab];
  const tf    = S.tierfilter[tab];
  const q     = S.search[tab].toLowerCase();
  const idKey = tab === 'hitters' ? 'batter' : 'pitcher';

  let rows = S.data[tab].filter(r => {
    if (q && !String(r.name || '').toLowerCase().includes(q)) return false;
    if (vf && r.verdict !== vf) return false;
    if (tf && r.tier_sell !== tf) return false;
    return true;
  });

  if (sort.col && sort.col !== 'verdict') {
    const dir = sort.dir === 'asc' ? 1 : -1;

    if (sort.col === 'luck_score') {
      if (!sort.userSort) {
        // Default sort (not user-triggered): CQS tier first, then luck_score desc within tier
        rows = [...rows].sort((a, b) => {
          const tierA = cqsTierRank(a, idKey);
          const tierB = cqsTierRank(b, idKey);
          if (tierA !== tierB) return tierA - tierB;
          const la = toNum(a.luck_score), lb = toNum(b.luck_score);
          if (isNaN(la) && isNaN(lb)) return 0;
          if (isNaN(la)) return 1;
          if (isNaN(lb)) return -1;
          return lb - la; // luck_score desc within tier
        });
      } else {
        // User clicked the luck_score header: sort by absolute value (most extreme first)
        // dir='desc' → biggest |luck_score| first; dir='asc' → smallest first
        rows = [...rows].sort((a, b) => {
          const la = toNum(a.luck_score), lb = toNum(b.luck_score);
          if (isNaN(la) && isNaN(lb)) return 0;
          if (isNaN(la)) return 1;
          if (isNaN(lb)) return -1;
          return dir * (Math.abs(lb) - Math.abs(la));
        });
      }
    } else {
      rows = [...rows].sort((a, b) => {
        const ka = sortKey(a[sort.col]);
        const kb = sortKey(b[sort.col]);
        if (ka === null && kb === null) return 0;
        if (ka === null) return 1;
        if (kb === null) return -1;
        if (typeof ka === 'string' && typeof kb === 'string')
          return dir * ka.localeCompare(kb);
        if (typeof ka === 'string') return 1;
        if (typeof kb === 'string') return -1;
        return dir * (ka - kb);
      });
    }
  }
  return rows;
}

// ─── Simple view renderer ─────────────────────────────────────────────────────
function renderSimpleTable() {
  const tab   = S.tab;
  const type  = tab === 'hitters' ? 'hitter' : 'pitcher';
  const idKey = tab === 'hitters' ? 'batter' : 'pitcher';
  const rows  = getFilteredRows(tab);

  const ACTION_MAP = {
    'Buy low':    { badge:'ab-buy',       emoji:'🟢', label:'BUY LOW'                    },
    'Slight buy': { badge:'ab-sbuy',      emoji:'🟢', label:'SLIGHT BUY'                 },
    'Neutral':    { badge:'ab-neutral',   emoji:'⚪', label:'NEUTRAL'                    },
    'Slight sell':{ badge:'ab-slightreg', emoji:'🟡', label:'SLIGHT REGRESSION EXPECTED' },
    'Sell high':  { badge:'ab-sellmove',  emoji:'🔴', label:'SELL HIGH'                  },
  };

  // Seasonal confidence label — days since 2026-03-27 season start
  const SEASON_START = new Date('2026-03-27');
  const daysIntoSeason = Math.floor((new Date() - SEASON_START) / 86400000);
  const confLabel = daysIntoSeason < 1   ? null
    : daysIntoSeason <= 35  ? 'Early signal'
    : daysIntoSeason <= 90  ? 'Signal strengthening'
    : daysIntoSeason <= 150 ? 'Confirmed signal'
    :                         'Late season';

  const TIER_ACTION = {
    'Sell and Move On':           { badge:'ab-sellmove',  emoji:'🔴', label:'SELL AND MOVE ON'           },
    'Sell High on Perception':    { badge:'ab-sellperc',  emoji:'🟠', label:'SELL HIGH ON PERCEPTION'    },
    'Veteran Regression':         { badge:'ab-vetreg',    emoji:'🟡', label:'VETERAN REGRESSION'         },
    'Slight Regression Expected': { badge:'ab-slightreg', emoji:'🟡', label:'SLIGHT REGRESSION EXPECTED' },
  };

  // Head — 4 columns
  document.getElementById('tbl-head').innerHTML = `<tr>
    <th style="cursor:default;text-align:left">Player</th>
    <th style="cursor:default;text-align:left">Pos</th>
    <th style="cursor:default;text-align:left">Action</th>
    <th style="cursor:default;text-align:left">What it means</th>
  </tr>`;

  if (!rows.length) {
    document.getElementById('tbl-body').innerHTML =
      `<tr class="no-rows"><td colspan="4">🔍 No players match your search or filter.</td></tr>`;
    document.getElementById('results-info').textContent = `0 of ${S.data[tab].length.toLocaleString()} players`;
    return;
  }

  document.getElementById('tbl-body').innerHTML = rows.map(r => {
    const info    = vInfo(r.verdict);
    const rowCls  = info.row;
    const mlbamId = r[idKey];
    const pos     = getPosition(mlbamId);

    // Determine action label — tier overrides verdict for sell signals.
    // For pitchers, "Sell and Move On" is the catch-all tier (fires when no specific
    // sub-classification applies) and should not override the verdict badge; use
    // "SELL HIGH" from ACTION_MAP instead.  Specific pitcher tiers ("Sell High on
    // Perception", "Veteran Regression") do override.
    const tier    = r.tier_sell;
    const tierOverrideAllowed = tab !== 'pitchers' || tier !== 'Sell and Move On';
    const act     = (tier && TIER_ACTION[tier] && tierOverrideAllowed) ? TIER_ACTION[tier]
                  : (ACTION_MAP[r.verdict] || ACTION_MAP['Neutral']);

    // Age warning
    const ageWarn = (r.age_flag && r.age_flag !== 'nan' && r.age_flag !== 'None' && r.age_flag !== '')
      ? `<span class="age-warn" title="${esc(r.age_flag)}">⚠ ${parseInt(r.age)||''}</span>` : '';

    // Hitter trade value gate: buy low only surfaces if player has meaningful value
    let finalAct = act;
    let explain;
    const pvEntry = S.tvById && S.tvById[String(mlbamId)];
    if (tab === 'hitters' && (r.verdict === 'Buy low' || r.verdict === 'Slight buy')) {
      const maxTv = pvEntry ? Math.max(pvEntry.league1_value || 0, pvEntry.league2_value || 0) : 0;
      if (maxTv === 0 && pvEntry) {
        finalAct = ACTION_MAP['Neutral'];
        explain = `Strong luck signal but underlying metrics project modest recovery ceiling — buy for regression, not for star upside`;
      } else if (maxTv < 20) {
        finalAct = ACTION_MAP['Neutral'];
        const fn2 = esc((r.name || '').split(' ')[0]);
        explain = `${fn2} is unlucky but projected value after regression may not be worth a roster spot`;
      }
    }
    if (explain === undefined) explain = generateExplanation(r, type, pvEntry);

    // CQS floor badge: append tier indicator when floor was applied
    let cqsBadge = '';
    if (pvEntry && pvEntry.cqs_floor_applied && pvEntry.cqs_tier) {
      const tierShort = { 'Superstar': 'SUP', 'Established Star': 'EST', 'Solid Contributor': 'SOL' }[pvEntry.cqs_tier] || '';
      if (tierShort) cqsBadge = ` <span class="cqs-badge" title="Career Quality Score floor applied (${pvEntry.cqs_tier})">${tierShort}</span>`;
    }

    // Seasonal pattern badge — from player_values.json (pvEntry) with CSV fallback
    const sp = (pvEntry && pvEntry.seasonal_pattern) || r.seasonal_pattern || '';
    let seasonalBadge = '';
    if (sp && sp !== '' && sp !== 'nan' && sp !== 'None' && sp !== 'null') {
      const isVshape = sp.includes('V-shape');
      seasonalBadge = isVshape
        ? `<span class="seasonal-star" title="${esc(sp)}">&#9733;</span>`
        : `<span class="seasonal-dot"  title="${esc(sp)}">&#9679;</span>`;
    }

    const fpRank = r.fp_rank || (pvEntry && pvEntry.fp_rank);
    const rankBadge = (fpRank && fpRank <= 50)
      ? ` <span class="rank-badge" title="FantasyPros consensus rank #${fpRank}">#${fpRank}</span>`
      : '';
    const playerNameCell = `<td class="name-cell">${esc(r.name || '—')}${ageWarn}${cqsBadge}${rankBadge}</td>`;
    const posCell        = `<td class="pos-cell" style="text-align:left">${esc(pos)}</td>`;
    const showConf = confLabel && (r.verdict === 'Buy low' || r.verdict === 'Sell high');
    const confSpan = showConf ? `<span class="signal-conf">${confLabel}</span>` : '';
    const volBadge = (tab === 'pitchers' && (r.volatility_flag === true || r.volatility_flag === 'True'))
      ? `<span class="volatility-badge" title="${esc(r.volatility_label || 'High variance — signals less reliable')}">⚡</span>` : '';
    const actionCell     = `<td class="action-cell"><span class="action-badge ${finalAct.badge}">${finalAct.emoji} ${finalAct.label}</span>${volBadge}${seasonalBadge}${confSpan}</td>`;
    const explainCell    = `<td class="explain-cell"><span class="explain-text" title="${esc(explain)}">${esc(explain)}</span></td>`;

    return `<tr class="${rowCls}">${playerNameCell}${posCell}${actionCell}${explainCell}</tr>`;
  }).join('');

  document.getElementById('results-info').textContent =
    `${rows.length.toLocaleString()} of ${S.data[tab].length.toLocaleString()} players`;
}

// ─── Advanced view renderer ───────────────────────────────────────────────────
function renderAdvancedTable() {
  const tab  = S.tab;
  const cols = tab === 'hitters' ? HITTER_COLS : PITCHER_COLS;
  const sort = S.sort[tab];
  const rows = getFilteredRows(tab);

  // Head
  const headHTML = '<tr>' + cols.map(c => {
    if (c.nosort)
      return `<th style="cursor:default">${c.label}</th>`;
    const sorted = sort.col === c.key;
    const arrow  = sorted
      ? (sort.dir === 'desc' ? ' ↓' : ' ↑')
      : ' <i class="sort-arrow">↕</i>';
    return `<th class="${sorted ? 'sorted' : ''}"
                onclick="onSort('${c.key}')"
            >${c.label}${arrow}</th>`;
  }).join('') + '</tr>';
  document.getElementById('tbl-head').innerHTML = headHTML;

  // Body
  let bodyHTML;
  if (rows.length === 0) {
    bodyHTML = `<tr class="no-rows"><td colspan="${cols.length}">
      🔍 No players match your search or filter.
    </td></tr>`;
  } else {
    bodyHTML = rows.map(r => {
      const info   = vInfo(r.verdict);
      const rowCls = info.row;
      const cells  = cols.map(c => F[c.fmt](r[c.key], r)).join('');
      return `<tr class="${rowCls}">${cells}</tr>`;
    }).join('');
  }
  document.getElementById('tbl-body').innerHTML = bodyHTML;

  document.getElementById('results-info').textContent =
    `${rows.length.toLocaleString()} of ${S.data[tab].length.toLocaleString()} players`;
}

// ─── Render: legend ───────────────────────────────────────────────────────────
function renderLegend() {
  const isH = S.tab === 'hitters';
  const items = isH
    ? [
        ['BABIP',      'Batting avg on balls in play — primary luck signal (weight −3.0)'],
        ['HR/FB%',     'Home runs per fly ball — regresses strongly to mean (weight −0.15)'],
        ['xwOBA Gap',  'xwOBA − wOBA: positive = underperformed contact quality = unlucky (weight +1.0)'],
        ['Z-Con%',     'In-zone contact rate (weight −0.03)'],
        ['Hard Hit%',  'Exit velo ≥ 95 mph / all BBE — display only, not in v2 scoring'],
        ['Barrel%',    'Barrels / all BBE — display only, not in v2 scoring'],
      ]
    : [
        ['ERA−FIP',   'ERA above FIP — positive = unlucky'],
        ['xERA',      'Expected ERA from xwOBA allowed'],
        ['BABIP',     'Hits on BIP allowed / total BIP'],
        ['LOB%',      'Strand rate — low = unlucky'],
        ['SwStr%',    'Swinging-strike rate'],
        ['Hard Hit%', 'BBE ≥ 95 mph allowed'],
      ];

  const sign = '<strong>+score = unlucky (buy low) · −score = lucky (sell high)</strong>';
  const cols = items.map(([k,v]) =>
    `<span class="legend-item"><strong>${k}:</strong> ${v}</span>`
  ).join('');

  document.getElementById('legend').innerHTML =
    `<span>${sign}</span>${cols}`;
}

// ─── Full render ──────────────────────────────────────────────────────────────
function render() {
  renderCards();
  renderTierButtons();
  renderTable();
  renderLegend();
  const vf = S.vfilter[S.tab];
  const tf = S.tierfilter[S.tab];
  document.getElementById('clear-btn').classList.toggle('on', !!(vf || tf));
  document.getElementById('cards').classList.toggle('has-filter', !!vf);
}

// ─── Event handlers ───────────────────────────────────────────────────────────
function setTab(tab) {
  S.tab = tab;
  document.getElementById('tab-h').classList.toggle('active',  tab === 'hitters');
  document.getElementById('tab-p').classList.toggle('active',  tab === 'pitchers');
  document.getElementById('tab-tv').classList.toggle('active', tab === 'tradevalue');

  if (tab === 'tradevalue') {
    if (!S.taBuilt) { buildPlayerIndex(); loadLeagueSettings(); S.taBuilt = true; }
    renderTV();
  } else {
    renderTV(); // hides TV, shows luck-content
    document.getElementById('search').value = S.search[tab];
    // Sync toggle button label
    const btn = document.getElementById('view-toggle-btn');
    if (btn) {
      btn.textContent = S.viewMode === 'simple' ? 'Advanced View' : 'Simple View';
      btn.classList.toggle('advanced', S.viewMode === 'advanced');
    }
    render();
  }
}

function onSort(col) {
  const s = S.sort[S.tab];
  // Toggle direction only when re-clicking a column the user already explicitly sorted.
  // First click on any column (or transitioning from default load) always starts desc.
  if (s.userSort && s.col === col) {
    s.dir = s.dir === 'desc' ? 'asc' : 'desc';
  } else {
    s.dir = 'desc';
  }
  s.col = col;
  s.userSort = true;
  renderTable();
}

function onSearch(val) {
  S.search[S.tab] = val;
  renderTable();
}

function toggleFilter(verdict) {
  S.vfilter[S.tab] = S.vfilter[S.tab] === verdict ? null : verdict;
  render();
}

function toggleTierFilter(tier) {
  S.tierfilter[S.tab] = S.tierfilter[S.tab] === tier ? null : tier;
  render();
}

function clearFilter() {
  S.vfilter[S.tab]    = null;
  S.tierfilter[S.tab] = null;
  render();
}

// ─── Screen helpers ───────────────────────────────────────────────────────────
function showScreen(id) {
  ['spin-screen','load-screen','dash-screen'].forEach(s => {
    document.getElementById(s).classList.toggle('visible', s === id);
  });
}

// ─── File input handler ───────────────────────────────────────────────────────
function loadFile(input, type) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const parsed = parseCSV(e.target.result);
    S.data[type]  = parsed;
    S.ready[type] = true;

    const rowEl = document.getElementById(`fr-${type}`);
    const stEl  = document.getElementById(`fs-${type}`);
    rowEl.classList.add('loaded');
    stEl.textContent = `✓ ${parsed.length.toLocaleString()} rows loaded`;

    if (S.ready.hitters && S.ready.pitchers) {
      // Fetch player_values.json if not yet loaded (file-picker path skips init fetch)
      if (!S.tvData) {
        fetch('data/player_values.json')
          .then(r => r.ok ? r.text() : null)
          .catch(() => null)
          .then(txt => {
            if (txt) loadPlayerValues(txt);
            buildPlayerIndex();
            loadLeagueSettings();
            S.taBuilt = true;
          });
      } else if (!S.taBuilt) {
        buildPlayerIndex();
        loadLeagueSettings();
        S.taBuilt = true;
      }
      renderMeta();
      showScreen('dash-screen');
      render();
    }
  };
  reader.readAsText(file, 'UTF-8');
}

// ─── TV mode switch ───────────────────────────────────────────────────────────
function setTvMode(mode) {
  S.tvMode = mode;
  renderTV();
}

// ─── Trade Analyzer ───────────────────────────────────────────────────────────

const TA_MAXES = { giving: 4, getting: 4, dropping: 2 };

function normalizeName(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildPlayerIndex() {
  S.taByName = {};
  S.taById   = {};
  (S.tvData || []).forEach(p => {
    const key = normalizeName(p.name);
    if (!S.taByName[key]) S.taByName[key] = p;  // first match wins
    if (p.id) S.taById[String(p.id)] = p;
  });
  // Index luck score rows by player id
  S.hLuckById = {};
  (S.data.hitters || []).forEach(r => {
    const id = r.batter || r.id;
    if (id) S.hLuckById[String(id)] = r;
  });
  S.pLuckById = {};
  (S.data.pitchers || []).forEach(r => {
    const id = r.pitcher || r.id;
    if (id) S.pLuckById[String(id)] = r;
  });
}

function taSearchPlayers(q, excludeIds) {
  const qn   = normalizeName(q);
  if (qn.length < 2) return [];
  const excl = new Set((excludeIds || []).map(String));
  return (S.tvData || [])
    .filter(p => {
      if (excl.has(String(p.id))) return false;
      return normalizeName(p.name).includes(qn);
    })
    .sort((a, b) => {
      const an = normalizeName(a.name);
      const bn = normalizeName(b.name);
      const aStart = an.startsWith(qn) ? 0 : 1;
      const bStart = bn.startsWith(qn) ? 0 : 1;
      if (aStart !== bStart) return aStart - bStart;
      const aRank = toNum(a.fp_rank) || 9999;
      const bRank = toNum(b.fp_rank) || 9999;
      return aRank - bRank;
    })
    .slice(0, 8);
}

// All currently selected IDs across all sides
function taAllSelectedIds() {
  return [
    ...S.ta.giving.map(p => String(p.id)),
    ...S.ta.getting.map(p => String(p.id)),
    ...S.ta.dropping.map(p => String(p.id)),
  ];
}

// ── Dropdown ──────────────────────────────────────────────────────────────────
function onTaSearch(q, side) {
  if (!q || q.length < 2) { closeTaDropdown(side); return; }
  // Lazy index rebuild: covers the file-picker path where async fetch may not be done yet
  if (!S.taBuilt || Object.keys(S.taById).length === 0) {
    buildPlayerIndex();
    loadLeagueSettings();
    S.taBuilt = true;
  }
  const matches = taSearchPlayers(q, taAllSelectedIds());
  renderTaDropdown(matches, side);
}

function onTaFocus(side) {
  const inp = document.getElementById(`ta-search-${side}`);
  if (inp && inp.value.length >= 2) onTaSearch(inp.value, side);
}

function renderTaDropdown(matches, side) {
  const dd = document.getElementById(`ta-dd-${side}`);
  if (!dd) return;
  if (!matches.length) {
    if (!S.tvData) {
      dd.innerHTML = `<div class="ta-dd-item" style="color:#94a3b8;font-size:11px;cursor:default">
        player_values.json not loaded — run the pipeline and reload</div>`;
      dd.classList.add('open');
    } else {
      closeTaDropdown(side);
    }
    return;
  }

  dd.innerHTML = matches.map(p => {
    const info = vInfo(p.verdict);
    const isH  = p.type === 'hitter';
    const lRow = isH ? (S.hLuckById[String(p.id)] || {}) : (S.pLuckById[String(p.id)] || {});
    const team = lRow.Team || lRow.team || '';
    const pos  = p.pos || (isH ? 'H' : 'P');
    const rankStr = toNum(p.fp_rank) ? `#${p.fp_rank}` : '';

    return `<div class="ta-dd-item"
                 onmousedown="event.preventDefault(); addTaPlayer(${JSON.stringify(String(p.id))}, '${side}')">
      <div style="flex:1;min-width:0">
        <div class="ta-dd-name">${esc(p.name)}</div>
        <div class="ta-dd-sub">${[pos, team, rankStr].filter(Boolean).join(' · ')}</div>
      </div>
      <span class="ta-dd-badge ${info.cls}">${info.label}</span>
    </div>`;
  }).join('');

  dd.classList.add('open');
}

function closeTaDropdown(side) {
  const dd = document.getElementById(`ta-dd-${side}`);
  if (dd) dd.classList.remove('open');
}

function closeTaDropdownDelayed(side) {
  setTimeout(() => closeTaDropdown(side), 200);
}

// ── Player card management ────────────────────────────────────────────────────
function addTaPlayer(idStr, side) {
  const p = S.taById[String(idStr)];
  if (!p) return;
  if (S.ta[side].length >= TA_MAXES[side]) return;
  if (S.ta[side].some(x => String(x.id) === String(p.id))) return;
  S.ta[side].push(Object.assign({}, p));
  renderTaCards(side);
  updateTaAnalyzeButton();
  const inp = document.getElementById(`ta-search-${side}`);
  if (inp) inp.value = '';
  closeTaDropdown(side);
  // Clear stale results when roster changes
  if (S.ta.results) {
    document.getElementById('ta-results').classList.remove('visible');
    S.ta.results = null;
  }
}

function removeTaPlayer(idStr, side) {
  S.ta[side] = S.ta[side].filter(p => String(p.id) !== String(idStr));
  renderTaCards(side);
  updateTaAnalyzeButton();
  if (S.ta.results) {
    document.getElementById('ta-results').classList.remove('visible');
    S.ta.results = null;
  }
}

function renderTaCards(side) {
  const players = S.ta[side];
  const el      = document.getElementById(`ta-cards-${side}`);
  const cntEl   = document.getElementById(`ta-count-${side}`);
  if (cntEl) cntEl.textContent = players.length;
  if (!el) return;

  if (!players.length) {
    const hints = { giving:'Search for players above', getting:'Search for players above', dropping:'Waiver drops (optional)' };
    el.innerHTML = `<div class="ta-empty-hint">${hints[side]}</div>`;
    return;
  }

  el.innerHTML = players.map(p => buildTaCardHtml(p, side)).join('');
}

function buildTaCardHtml(p, side) {
  const info  = vInfo(p.verdict);
  const isH   = p.type === 'hitter';
  const lRow  = isH ? (S.hLuckById[String(p.id)] || {}) : (S.pLuckById[String(p.id)] || {});
  const team  = lRow.Team || lRow.team || '';
  const pos   = p.pos || (isH ? '—' : 'P');

  let currentLine = '', projLine = '';
  if (isH) {
    const woba  = toNum(lRow.wOBA);
    const babip = toNum(lRow.BABIP);
    if (!isNaN(woba))  currentLine += `wOBA .<strong>${Math.round(woba*1000).toString().padStart(3,'0')}</strong> `;
    if (!isNaN(babip)) currentLine += `BABIP .<strong>${Math.round(babip*1000).toString().padStart(3,'0')}</strong>`;
    const avg = toNum(p.proj_AVG), hr = toNum(p.proj_HR), r = toNum(p.proj_R);
    const rbi = toNum(p.proj_RBI), sb = toNum(p.proj_SB);
    projLine = [
      !isNaN(avg) ? `AVG .<strong>${Math.round(avg*1000).toString().padStart(3,'0')}</strong>` : null,
      !isNaN(hr)  ? `HR <strong>${Math.round(hr)}</strong>` : null,
      !isNaN(r)   ? `R <strong>${Math.round(r)}</strong>` : null,
      !isNaN(rbi) ? `RBI <strong>${Math.round(rbi)}</strong>` : null,
      !isNaN(sb)  ? `SB <strong>${Math.round(sb)}</strong>` : null,
    ].filter(Boolean).join(' · ');
  } else {
    const era = toNum(lRow.ERA), fip = toNum(lRow.FIP);
    if (!isNaN(era)) currentLine += `ERA <strong>${era.toFixed(2)}</strong> `;
    if (!isNaN(fip)) currentLine += `FIP <strong>${fip.toFixed(2)}</strong>`;
    const pEra = toNum(p.proj_ERA), pWhip = toNum(p.proj_WHIP);
    const pK   = toNum(p.proj_K),   pW    = toNum(p.proj_W);
    projLine = [
      !isNaN(pEra)  ? `ERA <strong>${pEra.toFixed(2)}</strong>` : null,
      !isNaN(pWhip) ? `WHIP <strong>${pWhip.toFixed(2)}</strong>` : null,
      !isNaN(pK)    ? `K <strong>${Math.round(pK)}</strong>` : null,
      !isNaN(pW)    ? `W <strong>${Math.round(pW)}</strong>` : null,
    ].filter(Boolean).join(' · ');
  }

  const newPitches = (lRow.new_pitches || '').split(',').filter(x => x.trim().length > 0);
  const evoSwstr  = toNum(lRow.swstr_gap);
  const hasEvo = !isH && (newPitches.length >= 2 || (!isNaN(evoSwstr) && evoSwstr > 0.015));
  const evoBadge = hasEvo ? `<div class="ta-evo-badge">⚡ New Pitcher — career discounted</div>` : '';

  return `<div class="ta-player-card">
    <div class="ta-card-top">
      <div>
        <div class="ta-card-name">${esc(p.name)}</div>
        <div class="ta-card-meta">${esc(pos)} · ${esc(team)}</div>
      </div>
      <button class="ta-remove-btn"
              onclick="removeTaPlayer('${esc(String(p.id))}','${side}')"
              title="Remove">&times;</button>
    </div>
    <span class="ta-card-badge ${info.cls}">${info.label}</span>
    ${currentLine ? `<div class="ta-card-stats">${currentLine}</div>` : ''}
    <div class="ta-card-stats">Proj: ${projLine || '—'}</div>
    ${evoBadge}
  </div>`;
}

function updateTaAnalyzeButton() {
  const btn = document.getElementById('ta-analyze-btn');
  if (btn) btn.disabled = !(S.ta.giving.length > 0 && S.ta.getting.length > 0);
}

// ── Trade computation ─────────────────────────────────────────────────────────
function getTaProj(p) {
  const isH = p.type === 'hitter';
  if (isH) return {
    type: 'hitter',
    AVG: toNum(p.proj_AVG), OBP: toNum(p.proj_OBP),
    HR:  toNum(p.proj_HR),  R:   toNum(p.proj_R),
    RBI: toNum(p.proj_RBI), SB:  toNum(p.proj_SB),
    PA:  toNum(p.PA_proj),
  };
  return {
    type: 'pitcher',
    ERA:  toNum(p.proj_ERA),  WHIP: toNum(p.proj_WHIP),
    K:    toNum(p.proj_K),    W:    toNum(p.proj_W),
    SVH:  toNum(p.proj_SVH_L1),
    IP:   toNum(p.IP_proj),
  };
}

function computeTaSide(players) {
  const hitters  = players.filter(p => p.type === 'hitter');
  const pitchers = players.filter(p => p.type === 'pitcher');

  let totalPA = 0, wAVG = 0, wOBP = 0, HR = 0, R = 0, RBI = 0, SB = 0;
  hitters.forEach(p => {
    const proj = getTaProj(p);
    const pa   = isNaN(proj.PA) || proj.PA <= 0 ? 500 : proj.PA;
    totalPA += pa;
    if (!isNaN(proj.AVG)) wAVG += proj.AVG * pa;
    if (!isNaN(proj.OBP)) wOBP += proj.OBP * pa;
    if (!isNaN(proj.HR))  HR  += proj.HR;
    if (!isNaN(proj.R))   R   += proj.R;
    if (!isNaN(proj.RBI)) RBI += proj.RBI;
    if (!isNaN(proj.SB))  SB  += proj.SB;
  });
  const h = hitters.length ? {
    AVG: totalPA ? wAVG / totalPA : NaN,
    OBP: totalPA ? wOBP / totalPA : NaN,
    HR, R, RBI, SB, PA: totalPA, count: hitters.length,
  } : null;

  let totalIP = 0, wERA = 0, wWHIP = 0, K = 0, W = 0, SVH = 0;
  pitchers.forEach(p => {
    const proj = getTaProj(p);
    const ip   = isNaN(proj.IP) || proj.IP <= 0 ? 150 : proj.IP;
    totalIP += ip;
    if (!isNaN(proj.ERA))  wERA  += proj.ERA  * ip;
    if (!isNaN(proj.WHIP)) wWHIP += proj.WHIP * ip;
    if (!isNaN(proj.K))    K  += proj.K;
    if (!isNaN(proj.W))    W  += proj.W;
    if (!isNaN(proj.SVH))  SVH += proj.SVH;
  });
  const pit = pitchers.length ? {
    ERA:  totalIP ? wERA  / totalIP : NaN,
    WHIP: totalIP ? wWHIP / totalIP : NaN,
    K, W, SVH, IP: totalIP, count: pitchers.length,
  } : null;

  return { h, pit };
}

function computeNetStats(getting, giving, dropping) {
  const ls   = S.taLeague;
  const netH = {}, netP = {};
  let wonCats = 0, totalCats = 0;

  const g = getting, v = giving, d = dropping;

  // Helper: net = getting - giving - drop (for counting stats)
  //         for rate stats weighted by PA/IP
  if (g.h || v.h) {
    const gh = g.h || {}, vh = v.h || {}, dh = (d && d.h) ? d.h : {};
    const hCats = [
      { key:'AVG', label:'AVG', isRate:true,  active: ls.hCats.includes('avg'), thresh: 0.003 },
      { key:'HR',  label:'HR',  isRate:false, active: ls.hCats.includes('hr'),  thresh: 1 },
      { key:'R',   label:'R',   isRate:false, active: ls.hCats.includes('r'),   thresh: 2 },
      { key:'RBI', label:'RBI', isRate:false, active: ls.hCats.includes('rbi'), thresh: 2 },
      { key:'SB',  label:'SB',  isRate:false, active: ls.hCats.includes('sb'),  thresh: 1 },
      { key:'OBP', label:'OBP', isRate:true,  active: ls.hCats.includes('obp'), thresh: 0.005 },
    ];
    hCats.forEach(cat => {
      if (!cat.active) return;
      const gv = gh[cat.key] || 0, vv = vh[cat.key] || 0, dv = dh[cat.key] || 0;
      const net = gv - vv - dv;
      netH[cat.key] = { val: net, label: cat.label, isRate: cat.isRate };
      totalCats++;
      if (net > cat.thresh) wonCats++;
    });
  }

  if (g.pit || v.pit) {
    const gp = g.pit || {}, vp = v.pit || {}, dp = (d && d.pit) ? d.pit : {};
    const pCats = [
      { key:'ERA',  label:'ERA',  lower:true,  active: ls.pCats.includes('era'),  thresh: 0.08 },
      { key:'WHIP', label:'WHIP', lower:true,  active: ls.pCats.includes('whip'), thresh: 0.02 },
      { key:'K',    label:'K',    lower:false, active: ls.pCats.includes('k'),    thresh: 4 },
      { key:'W',    label:'W',    lower:false, active: ls.pCats.includes('w'),    thresh: 1 },
      { key:'SVH',  label:'SV+H', lower:false, active: ls.pCats.includes('svh'),  thresh: 1 },
    ];
    pCats.forEach(cat => {
      if (!cat.active) return;
      const gv = gp[cat.key] || 0, vv = vp[cat.key] || 0, dv = dp[cat.key] || 0;
      const net = gv - vv - dv;
      const eff = cat.lower ? -net : net;   // flip sign: lower ERA = better for you
      netP[cat.key] = { val: net, label: cat.label, lower: cat.lower };
      totalCats++;
      if (eff > cat.thresh) wonCats++;
    });
  }

  return { netH, netP, wonCats, totalCats };
}

function taComputeVerdict(wonCats, totalCats) {
  if (totalCats === 0) return { cls:'vb-neutral', icon:'⚠️', label:'No Data', sub:'Add players to both sides' };
  const pct = wonCats / totalCats;
  if (pct >= 0.75) return { cls:'vb-strong',  icon:'✅', label:'Strong Trade',  sub:`You win ${wonCats} of ${totalCats} categories` };
  if (pct >= 0.60) return { cls:'vb-favor',   icon:'✅', label:'Favorable',     sub:'Slight edge in your favor'              };
  if (pct >= 0.40) return { cls:'vb-neutral', icon:'⚠️', label:'Neutral',       sub:'Even trade — depends on your needs'     };
  if (pct >= 0.25) return { cls:'vb-unfavor', icon:'⚠️', label:'Unfavorable',   sub:'Trade partner has the edge'             };
  return               { cls:'vb-avoid',   icon:'❌', label:'Avoid',          sub:'Trade strongly favors your partner'     };
}

function taSignalNote(giving, getting) {
  const buyLow    = v => v === 'Buy low';
  const slightBuy = v => v === 'Slight buy';
  const sellHigh  = v => v === 'Sell high';
  const gvBL  = giving.filter(p => buyLow(p.verdict)).length;
  const gtBL  = getting.filter(p => buyLow(p.verdict)).length;
  const gvSH  = giving.filter(p => sellHigh(p.verdict)).length;
  const gtSH  = getting.filter(p => sellHigh(p.verdict)).length;
  const gvBuy = giving.filter(p => buyLow(p.verdict) || slightBuy(p.verdict)).length;
  const gtBuy = getting.filter(p => buyLow(p.verdict) || slightBuy(p.verdict)).length;
  const gvSell = giving.filter(p => ['Sell high','Slight sell'].includes(p.verdict)).length;
  const gtSell = getting.filter(p => ['Sell high','Slight sell'].includes(p.verdict)).length;

  const note = `Giving: ${gvBuy} buy${gvBuy !== 1 ? 's' : ''}, ${gvSell} sell${gvSell !== 1 ? 's' : ''} · Getting: ${gtBuy} buy${gtBuy !== 1 ? 's' : ''}, ${gtSell} sell${gtSell !== 1 ? 's' : ''}`;
  let msg = '';
  if (gvBL > 0 && gtSH > 0 && gtBL === 0)
    msg = '⚠️ Signal alert: giving up buy-low players for sell-highs';
  else if (gtBL > 0 && gvSH > 0 && gvBL === 0)
    msg = '✅ Signal edge: getting buy-low players, giving sell-highs';
  else if (gtBL > gvBL)
    msg = '✅ Signal edge: more buy-low upside on your return';
  else if (gvBL > gtBL)
    msg = '⚠️ Signal note: giving more buy-low value than receiving';
  return { note, msg };
}

function analyzeTrade() {
  if (!S.ta.giving.length || !S.ta.getting.length) return;

  const givingSum  = computeTaSide(S.ta.giving);
  const gettingSum = computeTaSide(S.ta.getting);
  const dropSum    = S.ta.dropping.length ? computeTaSide(S.ta.dropping) : null;
  const { netH, netP, wonCats, totalCats } = computeNetStats(gettingSum, givingSum, dropSum);
  const verdict  = taComputeVerdict(wonCats, totalCats);
  const signal   = taSignalNote(S.ta.giving, S.ta.getting);

  S.ta.results = { givingSum, gettingSum, dropSum, netH, netP, verdict, signal };
  renderTradeResults();
}

// ── Results rendering ─────────────────────────────────────────────────────────
function renderTradeResults() {
  const r = S.ta.results;
  if (!r) return;
  const el = document.getElementById('ta-results');
  el.classList.add('visible');

  document.getElementById('ta-sides').innerHTML =
    buildTaSideHtml('giving',  S.ta.giving,  r.givingSum) +
    buildTaSideHtml('getting', S.ta.getting, r.gettingSum);

  renderTaNetBar(r.netH, r.netP);

  const v = r.verdict;
  const vEl = document.getElementById('ta-verdict-banner');
  vEl.className = `ta-verdict-banner ${v.cls}`;
  vEl.innerHTML = `
    <div class="ta-verdict-icon">${v.icon}</div>
    <div class="ta-verdict-label">${v.label}</div>
    <div class="ta-verdict-sub">${v.sub}</div>
    <div class="ta-verdict-signal" style="margin-top:6px">${r.signal.note}</div>
    ${r.signal.msg ? `<div class="ta-verdict-signal" style="margin-top:3px;font-weight:700">${r.signal.msg}</div>` : ''}
  `;

  setTimeout(() => el.scrollIntoView({ behavior:'smooth', block:'nearest' }), 80);
}

function buildTaSideHtml(side, players, summary) {
  const cls   = side === 'giving' ? 'ta-side-giving' : 'ta-side-getting';
  const lbl   = side === 'giving' ? `Giving Away (${players.length})` : `Getting (${players.length})`;

  const playerHtml = players.map(p => {
    const info = vInfo(p.verdict);
    const isH  = p.type === 'hitter';
    const lRow = isH ? (S.hLuckById[String(p.id)] || {}) : (S.pLuckById[String(p.id)] || {});
    const team = lRow.Team || lRow.team || '';
    const pos  = p.pos || (isH ? '—' : 'P');

    let cur = '', proj = '';
    if (isH) {
      const pa = toNum(lRow.PA), woba = toNum(lRow.wOBA), babip = toNum(lRow.BABIP);
      const parts = [];
      if (!isNaN(pa))    parts.push(`${Math.round(pa)} PA`);
      if (!isNaN(woba))  parts.push(`wOBA .<strong>${Math.round(woba*1000).toString().padStart(3,'0')}</strong>`);
      if (!isNaN(babip)) parts.push(`BABIP .<strong>${Math.round(babip*1000).toString().padStart(3,'0')}</strong>`);
      cur = parts.join(' · ');
      const avg = toNum(p.proj_AVG), hr = toNum(p.proj_HR), r2 = toNum(p.proj_R);
      const rbi = toNum(p.proj_RBI), sb = toNum(p.proj_SB);
      proj = [
        !isNaN(avg) ? `AVG .<strong>${Math.round(avg*1000).toString().padStart(3,'0')}</strong>` : null,
        !isNaN(hr)  ? `HR <strong>${Math.round(hr)}</strong>` : null,
        !isNaN(r2)  ? `R <strong>${Math.round(r2)}</strong>` : null,
        !isNaN(rbi) ? `RBI <strong>${Math.round(rbi)}</strong>` : null,
        !isNaN(sb)  ? `SB <strong>${Math.round(sb)}</strong>` : null,
      ].filter(Boolean).join(' · ');
    } else {
      const ip = toNum(lRow.IP), era = toNum(lRow.ERA), fip = toNum(lRow.FIP);
      const parts = [];
      if (!isNaN(ip))  parts.push(`${ip.toFixed(1)} IP`);
      if (!isNaN(era)) parts.push(`ERA <strong>${era.toFixed(2)}</strong>`);
      if (!isNaN(fip)) parts.push(`FIP <strong>${fip.toFixed(2)}</strong>`);
      cur = parts.join(' · ');
      const pEra = toNum(p.proj_ERA), pWhip = toNum(p.proj_WHIP);
      const pK   = toNum(p.proj_K),   pW    = toNum(p.proj_W);
      proj = [
        !isNaN(pEra)  ? `ERA <strong>${pEra.toFixed(2)}</strong>` : null,
        !isNaN(pWhip) ? `WHIP <strong>${pWhip.toFixed(2)}</strong>` : null,
        !isNaN(pK)    ? `K <strong>${Math.round(pK)}</strong>` : null,
        !isNaN(pW)    ? `W <strong>${Math.round(pW)}</strong>` : null,
      ].filter(Boolean).join(' · ');
    }

    const rNewPitches = (lRow.new_pitches || '').split(',').filter(x => x.trim().length > 0);
    const rEvoSwstr   = toNum(lRow.swstr_gap);
    const hasEvo = !isH && (rNewPitches.length >= 2 || (!isNaN(rEvoSwstr) && rEvoSwstr > 0.015));
    const evoBadge = hasEvo ? `<span class="ta-evo-badge">⚡ New Pitcher — career discounted</span>` : '';

    return `<div class="ta-result-player">
      <div class="ta-rp-name">
        ${esc(p.name)}
        <span class="badge ${info.cls}" style="font-size:10px">${info.label}</span>
        ${evoBadge}
      </div>
      <div class="ta-rp-meta">${esc(pos)} · ${esc(team)}</div>
      ${cur  ? `<div class="ta-rp-stats">${cur}</div>` : ''}
      ${proj ? `<div class="ta-rp-stats">Proj: ${proj}</div>` : ''}
    </div>`;
  }).join('');

  // Totals
  const h = summary.h, pit = summary.pit;
  let totals = '';
  if (h) {
    const avgS  = !isNaN(h.AVG) ? `.<strong>${Math.round(h.AVG*1000).toString().padStart(3,'0')}</strong>` : '—';
    totals += `<div>Hitters: AVG ${avgS} · HR <strong>${Math.round(h.HR)}</strong> · R <strong>${Math.round(h.R)}</strong> · RBI <strong>${Math.round(h.RBI)}</strong> · SB <strong>${Math.round(h.SB)}</strong></div>`;
  }
  if (pit) {
    const eraS  = !isNaN(pit.ERA)  ? `<strong>${pit.ERA.toFixed(2)}</strong>`  : '—';
    const whipS = !isNaN(pit.WHIP) ? `<strong>${pit.WHIP.toFixed(2)}</strong>` : '—';
    totals += `<div>Pitchers: ERA ${eraS} · WHIP ${whipS} · K <strong>${Math.round(pit.K)}</strong> · W <strong>${Math.round(pit.W)}</strong></div>`;
  }

  return `<div class="ta-side ${cls}">
    <div class="ta-side-hdr">${lbl}</div>
    ${playerHtml}
    ${totals ? `<div class="ta-side-totals">
      <div class="ta-side-totals-hdr">Projected Totals</div>
      <div class="ta-totals-stats">${totals}</div>
    </div>` : ''}
  </div>`;
}

function renderTaNetBar(netH, netP) {
  const el = document.getElementById('ta-net-bar');
  if (!el) return;
  const allStats = [...Object.entries(netH), ...Object.entries(netP)];
  if (!allStats.length) { el.innerHTML = ''; return; }

  const statHtml = allStats.map(([, stat]) => {
    const { val, isRate, lower, label } = stat;
    const eff = lower ? -val : val;
    const cls = eff > 0 ? 'pos' : eff < 0 ? 'neg' : 'neu';

    let disp;
    if (isRate) {
      const sign = val >= 0 ? '+' : '−';
      disp = `${sign}.${Math.abs(Math.round(val*1000)).toString().padStart(3,'0')}`;
    } else if (lower) {
      const sign = val >= 0 ? '+' : '';
      disp = `${sign}${val.toFixed(2)}`;
    } else {
      const sign = val >= 0 ? '+' : '';
      disp = `${sign}${Math.round(val)}`;
    }

    return `<div class="ta-net-stat">
      <span class="ta-net-cat">${esc(label)}</span>
      <span class="ta-net-val ${cls}">${disp}</span>
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="ta-net-hdr">Net Stats (Getting − Giving${S.ta.dropping.length ? ' − Drop' : ''})</div>
    <div class="ta-net-stats">${statHtml}</div>`;
}

function resetTrade() {
  S.ta.giving = []; S.ta.getting = []; S.ta.dropping = []; S.ta.results = null;
  ['giving','getting','dropping'].forEach(side => {
    renderTaCards(side);
    const inp = document.getElementById(`ta-search-${side}`);
    if (inp) inp.value = '';
    closeTaDropdown(side);
  });
  updateTaAnalyzeButton();
  const res = document.getElementById('ta-results');
  if (res) res.classList.remove('visible');
}

// ── League settings ───────────────────────────────────────────────────────────
function toggleLeaguePanel() {
  const p = document.getElementById('ta-league-panel');
  if (p) p.classList.toggle('open');
}

function loadLeagueSettings() {
  try {
    const raw = localStorage.getItem('signalFantasy_leagueSettings');
    if (raw) {
      const saved = JSON.parse(raw);
      S.taLeague = Object.assign({
        size:'12', format:'redraft', scoring:'5x5',
        hCats:['avg','r','hr','rbi','sb'],
        pCats:['era','whip','w','k','svh'],
      }, saved);
    }
  } catch(e) {}
  syncLeagueUI();
  renderLeagueSummary();
}

function syncLeagueUI() {
  const ls = S.taLeague;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  set('ta-ls-size',    ls.size);
  set('ta-ls-format',  ls.format);
  set('ta-ls-scoring', ls.scoring);

  const H_MAP = [['cat-avg','avg'],['cat-r','r'],['cat-hr','hr'],['cat-rbi','rbi'],
                 ['cat-sb','sb'],['cat-obp','obp'],['cat-slg','slg'],['cat-ops','ops']];
  const P_MAP = [['cat-era','era'],['cat-whip','whip'],['cat-w','w'],['cat-k','k'],
                 ['cat-svh','svh'],['cat-qs','qs'],['cat-hld','hld']];
  H_MAP.forEach(([id, key]) => { const el = document.getElementById(id); if (el) el.checked = ls.hCats.includes(key); });
  P_MAP.forEach(([id, key]) => { const el = document.getElementById(id); if (el) el.checked = ls.pCats.includes(key); });
}

function saveLeagueSettings() {
  const val = id => (document.getElementById(id) || {}).value || '';
  const chk = id => !!(document.getElementById(id) || {}).checked;
  const size    = val('ta-ls-size')    || '12';
  const format  = val('ta-ls-format')  || 'redraft';
  const scoring = val('ta-ls-scoring') || '5x5';

  const hCats = ['avg','r','hr','rbi','sb','obp','slg','ops'].filter(k => chk(`cat-${k}`));
  const pCats = ['era','whip','w','k','svh','qs','hld'].filter(k => chk(`cat-${k}`));

  S.taLeague = { size, format, scoring, hCats, pCats };
  try { localStorage.setItem('signalFantasy_leagueSettings', JSON.stringify(S.taLeague)); } catch(e) {}
  renderLeagueSummary();
  toggleLeaguePanel();
}

function renderLeagueSummary() {
  const el = document.getElementById('ta-league-summary');
  if (!el) return;
  const ls  = S.taLeague;
  const fmt = { redraft:'Redraft', keeper:'Keeper', dynasty:'Dynasty' }[ls.format] || ls.format;
  const scr = { '5x5':'5×5 Roto', points:'Points', h2h_cat:'H2H Cat', h2h_pts:'H2H Pts' }[ls.scoring] || ls.scoring;
  el.innerHTML = `<strong>${ls.size}-team</strong> · ${fmt} · ${scr}`;
}

// ─── Init: try auto-fetch, fall back to file inputs ───────────────────────────
async function init() {
  showScreen('spin-screen');

  // fetch() works when served over HTTP; fails silently on file:// — that's fine
  const tryFetch = async url => {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(r.status);
      return await r.text();
    } catch (_) { return null; }
  };

  const [hText, pText, tvText, cbsText, overrideText] = await Promise.all([
    tryFetch('luck_scores.csv'),
    tryFetch('pitcher_luck_scores.csv'),
    tryFetch('data/player_values.json'),
    tryFetch('data/cbs_positions.json'),
    tryFetch('data/position_overrides.json'),
  ]);

  // Trade value data (optional)
  if (tvText) loadPlayerValues(tvText);

  // CBS positions (optional — falls back gracefully)
  if (cbsText) {
    try {
      const cbsJson = JSON.parse(cbsText);
      S.cbsPositions = cbsJson.players || {};
      const note = document.getElementById('cbs-data-note');
      if (note) {
        const cbsCount = Object.values(S.cbsPositions)
          .filter(p => p.source === 'CBS Sports').length;
        note.textContent = `${cbsCount} players with CBS positions`;
      }
    } catch(e) { console.warn('cbs_positions.json parse error:', e); }
  }

  // Position overrides
  if (overrideText) {
    try {
      const ov = JSON.parse(overrideText);
      // Strip the _comment key
      delete ov._comment;
      S.positionOverrides = ov;
    } catch(e) { console.warn('position_overrides.json parse error:', e); }
  }

  if (hText && pText) {
    S.data.hitters  = parseCSV(hText);
    S.data.pitchers = parseCSV(pText);
    S.ready.hitters = true;
    S.ready.pitchers = true;
    // Build trade analyzer index eagerly so first tab-switch is instant
    buildPlayerIndex();
    loadLeagueSettings();
    S.taBuilt = true;
    renderMeta();
    showScreen('dash-screen');
    render();
  } else {
    showScreen('load-screen');
  }
}

document.addEventListener('DOMContentLoaded', init);
