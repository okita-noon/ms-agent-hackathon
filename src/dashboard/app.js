const API_BASE = '';
let orders = [];
let statusChart = null;
let sourceChart = null;

const STATUS_COLORS = {
  '未処理': { bg: 'bg-yellow-100', text: 'text-yellow-800', chart: '#eab308' },
  '製造': { bg: 'bg-blue-100', text: 'text-blue-800', chart: '#3b82f6' },
  '配送': { bg: 'bg-orange-100', text: 'text-orange-800', chart: '#f97316' },
  '完了': { bg: 'bg-green-100', text: 'text-green-800', chart: '#22c55e' },
  'キャンセル': { bg: 'bg-gray-100', text: 'text-gray-800', chart: '#6b7280' },
  '返信待ち': { bg: 'bg-red-100', text: 'text-red-800', chart: '#ef4444' },
};

const SOURCE_COLORS = {
  'LINE': '#06c755',
  'Phone': '#3b82f6',
  'Email': '#8b5cf6',
  'FAX': '#6b7280',
  'Web': '#f97316',
  '手入力': '#64748b',
};

function init() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('deliveryDate').value = today;
  updateClock();
  setInterval(updateClock, 1000);
  loadData();
}

function updateClock() {
  const now = new Date();
  document.getElementById('currentTime').textContent =
    now.toLocaleString('ja-JP', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function loadData() {
  const date = document.getElementById('deliveryDate').value;
  const btn = document.getElementById('loadBtn');
  const overlay = document.getElementById('loadingOverlay');
  btn.disabled = true;
  overlay.classList.remove('hidden');

  try {
    const resp = await fetch(`${API_BASE}/api/orders?delivery_date=${date}`);
    const data = await resp.json();
    orders = data.orders || [];
    renderStats();
    renderCharts();
    renderTable();
  } catch (e) {
    console.error('Failed to load orders:', e);
    orders = getDemoOrders();
    renderStats();
    renderCharts();
    renderTable();
  } finally {
    btn.disabled = false;
    overlay.classList.add('hidden');
  }
}

function getDemoOrders() {
  const today = new Date().toISOString().split('T')[0];
  return [
    { uid: 'ORD-001', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-001', customer_name: '株式会社A', source: 'LINE', items: [{ product_name: 'りんご', quantity: 10, unit: '箱', temperature_zone: '冷蔵' }, { product_name: 'バナナ', quantity: 20, unit: 'kg', temperature_zone: '常温' }], delivery_carrier: '自社便', delivery_route: '北関東便', status: '未処理', remarks: null },
    { uid: 'ORD-002', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-002', customer_name: '株式会社B', source: 'LINE', items: [{ product_name: 'もも', quantity: 5, unit: '箱', temperature_zone: '冷蔵' }], delivery_carrier: '芦川便', delivery_route: '西日本便', status: '完了', remarks: null },
    { uid: 'ORD-003', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-003', customer_name: '株式会社C', source: 'Phone', items: [{ product_name: 'メロン', quantity: 3, unit: '玉', temperature_zone: '冷凍' }], delivery_carrier: '自社便', delivery_route: '中部便', status: '製造', remarks: null },
    { uid: 'ORD-004', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-004', customer_name: '株式会社D', source: 'LINE', items: [{ product_name: 'いちご', quantity: 15, unit: 'パック', temperature_zone: '常温' }, { product_name: 'ぶどう', quantity: 8, unit: '房', temperature_zone: '常温' }], delivery_carrier: '自社便', delivery_route: '九州便', status: '配送', remarks: null },
    { uid: 'ORD-005', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-005', customer_name: '株式会社E', source: 'Phone', items: [{ product_name: 'みかん', quantity: 100, unit: '個', temperature_zone: '冷凍' }], delivery_carrier: '冷凍ヤマト便', delivery_route: '北海道便', status: '返信待ち', remarks: '数量確認中' },
    { uid: 'ORD-006', tenant_id: 'T-001', order_date: today, delivery_date: today, customer_id: 'C-006', customer_name: '株式会社F', source: 'LINE', items: [{ product_name: 'レモン', quantity: 30, unit: '個', temperature_zone: '常温' }], delivery_carrier: '自社便', delivery_route: '東北便', status: '完了', remarks: null },
  ];
}

function renderStats() {
  const container = document.getElementById('statsCards');
  const total = orders.length;
  const statusCounts = {};
  for (const s of Object.keys(STATUS_COLORS)) statusCounts[s] = 0;
  orders.forEach(o => { statusCounts[o.status] = (statusCounts[o.status] || 0) + 1; });

  let html = `
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-4 card-hover">
      <p class="text-xs font-medium text-gray-500 mb-1">合計</p>
      <p class="text-2xl font-bold text-gray-900">${total}</p>
    </div>`;

  for (const [status, color] of Object.entries(STATUS_COLORS)) {
    const count = statusCounts[status] || 0;
    html += `
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-4 card-hover">
      <p class="text-xs font-medium text-gray-500 mb-1">${status}</p>
      <p class="text-2xl font-bold ${color.text}">${count}</p>
    </div>`;
  }
  container.innerHTML = html;
}

function renderCharts() {
  const statusCounts = {};
  const sourceCounts = {};
  orders.forEach(o => {
    statusCounts[o.status] = (statusCounts[o.status] || 0) + 1;
    sourceCounts[o.source] = (sourceCounts[o.source] || 0) + 1;
  });

  if (statusChart) statusChart.destroy();
  if (sourceChart) sourceChart.destroy();

  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'right', labels: { boxWidth: 12, padding: 12, font: { size: 11 } } } }
  };

  const statusLabels = Object.keys(statusCounts);
  statusChart = new Chart(document.getElementById('statusChart'), {
    type: 'doughnut',
    data: {
      labels: statusLabels,
      datasets: [{ data: statusLabels.map(s => statusCounts[s]), backgroundColor: statusLabels.map(s => (STATUS_COLORS[s] || {}).chart || '#94a3b8') }]
    },
    options: chartOpts
  });

  const sourceLabels = Object.keys(sourceCounts);
  sourceChart = new Chart(document.getElementById('sourceChart'), {
    type: 'doughnut',
    data: {
      labels: sourceLabels,
      datasets: [{ data: sourceLabels.map(s => sourceCounts[s]), backgroundColor: sourceLabels.map(s => SOURCE_COLORS[s] || '#94a3b8') }]
    },
    options: chartOpts
  });
}

function renderTable() {
  const tbody = document.getElementById('orderTableBody');
  const empty = document.getElementById('emptyState');
  const count = document.getElementById('orderCount');

  count.textContent = `${orders.length}件`;

  if (orders.length === 0) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  tbody.innerHTML = orders.map(o => {
    const sc = STATUS_COLORS[o.status] || { bg: 'bg-gray-100', text: 'text-gray-800' };
    const itemsSummary = (o.items || []).map(i => `${i.product_name} ${i.quantity || ''}${i.unit || ''}`).join(', ');
    const tempBadges = [...new Set((o.items || []).map(i => i.temperature_zone))].map(t => {
      const c = t === '冷凍' ? 'bg-indigo-100 text-indigo-700' : t === '冷蔵' ? 'bg-cyan-100 text-cyan-700' : 'bg-amber-100 text-amber-700';
      return `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${c}">${t}</span>`;
    }).join(' ');

    return `
    <tr class="table-row-hover cursor-pointer" onclick='showDetail(${JSON.stringify(o).replace(/'/g, "&#39;")})'>
      <td class="px-5 py-3 whitespace-nowrap text-gray-600">${o.order_date || '-'}</td>
      <td class="px-5 py-3 font-medium text-gray-900">${o.customer_name}</td>
      <td class="px-5 py-3">
        <span class="inline-flex items-center gap-1 text-xs font-medium ${o.source === 'LINE' ? 'text-green-600' : 'text-blue-600'}">
          ${o.source}
        </span>
      </td>
      <td class="px-5 py-3 text-gray-600 max-w-xs truncate">${itemsSummary} ${tempBadges}</td>
      <td class="px-5 py-3"><span class="status-badge ${sc.bg} ${sc.text}">${o.status}</span></td>
      <td class="px-5 py-3 text-gray-500 text-xs">${o.delivery_carrier || '-'}<br>${o.delivery_route || ''}</td>
      <td class="px-5 py-3 text-gray-400 text-xs">${o.remarks || '-'}</td>
    </tr>`;
  }).join('');
}

function showDetail(order) {
  const modal = document.getElementById('orderModal');
  const content = document.getElementById('modalContent');
  const sc = STATUS_COLORS[order.status] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  const itemRows = (order.items || []).map(i => {
    const tc = i.temperature_zone === '冷凍' ? 'bg-indigo-100 text-indigo-700' : i.temperature_zone === '冷蔵' ? 'bg-cyan-100 text-cyan-700' : 'bg-amber-100 text-amber-700';
    return `
    <tr class="border-b border-gray-50">
      <td class="py-2 pr-4 font-medium">${i.product_name}</td>
      <td class="py-2 pr-4">${i.quantity || '-'}</td>
      <td class="py-2 pr-4">${i.unit || '-'}</td>
      <td class="py-2"><span class="px-1.5 py-0.5 rounded text-[10px] font-medium ${tc}">${i.temperature_zone}</span></td>
    </tr>`;
  }).join('');

  content.innerHTML = `
  <div class="p-6 space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-xs text-gray-400 mb-1">${order.uid || order.id}</p>
        <h4 class="text-lg font-bold text-gray-900">${order.customer_name}</h4>
      </div>
      <span class="status-badge ${sc.bg} ${sc.text} text-sm">${order.status}</span>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div><p class="text-xs text-gray-400">受注日</p><p class="font-medium">${order.order_date || '-'}</p></div>
      <div><p class="text-xs text-gray-400">手配日</p><p class="font-medium">${order.preparation_date || '-'}</p></div>
      <div><p class="text-xs text-gray-400">配送日</p><p class="font-medium">${order.delivery_date || '-'}</p></div>
      <div><p class="text-xs text-gray-400">チャネル</p><p class="font-medium">${order.source}</p></div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
      <div><p class="text-xs text-gray-400">配送便</p><p class="font-medium">${order.delivery_carrier || '-'}</p></div>
      <div><p class="text-xs text-gray-400">配送ルート</p><p class="font-medium">${order.delivery_route || '-'}</p></div>
      <div><p class="text-xs text-gray-400">送り状番号</p><p class="font-medium">${order.yamato_tracking_number || '-'}</p></div>
    </div>

    <div>
      <h5 class="text-sm font-semibold text-gray-700 mb-2">注文明細</h5>
      <div class="bg-gray-50 rounded-lg p-3">
        <table class="w-full text-sm">
          <thead><tr class="text-xs text-gray-500">
            <th class="text-left pb-2">商品名</th><th class="text-left pb-2">数量</th><th class="text-left pb-2">単位</th><th class="text-left pb-2">温度帯</th>
          </tr></thead>
          <tbody>${itemRows}</tbody>
        </table>
      </div>
    </div>

    ${order.remarks ? `<div><p class="text-xs text-gray-400">備考</p><p class="text-sm mt-1">${order.remarks}</p></div>` : ''}
  </div>`;

  modal.classList.remove('hidden');
}

function closeModal() {
  document.getElementById('orderModal').classList.add('hidden');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
document.getElementById('orderModal').addEventListener('click', e => { if (e.target.id === 'orderModal') closeModal(); });

init();
