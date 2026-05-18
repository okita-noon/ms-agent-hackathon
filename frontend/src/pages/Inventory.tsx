import { useState, useEffect, useCallback } from "react";
import { fetchInventory, type InventoryItem } from "../lib/api";
import LoadingState from "../components/LoadingState";
import TempBadge from "../components/TempBadge";

const DEMO_INVENTORY: InventoryItem[] = [
  { product_id: "P-001", product_name: "りんご", category: null, temperature_zone: "冷蔵", quantity: 50, unit: "箱", is_variable_weight: false, price_per_unit: null },
  { product_id: "P-002", product_name: "バナナ", category: null, temperature_zone: "常温", quantity: 200, unit: "kg", is_variable_weight: false, price_per_unit: null },
  { product_id: "P-003", product_name: "みかん", category: null, temperature_zone: "冷凍", quantity: 500, unit: "個", is_variable_weight: false, price_per_unit: 400 },
  { product_id: "P-004", product_name: "ぶどう", category: null, temperature_zone: "常温", quantity: 30, unit: "房", is_variable_weight: false, price_per_unit: 1000 },
  { product_id: "P-005", product_name: "もも", category: null, temperature_zone: "冷蔵", quantity: 40, unit: "箱", is_variable_weight: true, price_per_unit: 7200 },
];

type SortKey = "product_id" | "product_name" | "quantity" | "temperature_zone";
type SortDir = "asc" | "desc";

function stockLevel(qty: number): { label: string; cls: string } {
  if (qty <= 0) return { label: "欠品", cls: "bg-red-50 text-red-700 border-red-200" };
  if (qty <= 15) return { label: "少", cls: "bg-amber-50 text-amber-700 border-amber-200" };
  if (qty <= 50) return { label: "適正", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" };
  return { label: "潤沢", cls: "bg-blue-50 text-blue-700 border-blue-200" };
}

export default function Inventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [zoneFilter, setZoneFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("product_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchInventory());
    } catch {
      setItems(DEMO_INVENTORY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const zones = ["all", ...Array.from(new Set(items.map((i) => i.temperature_zone)))];

  const filtered = items
    .filter((i) => zoneFilter === "all" || i.temperature_zone === zoneFilter)
    .filter((i) =>
      filter === "" ||
      i.product_name.includes(filter) ||
      i.product_id.toLowerCase().includes(filter.toLowerCase())
    )
    .sort((a, b) => {
      const va = a[sortKey] ?? "";
      const vb = b[sortKey] ?? "";
      const cmp = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), "ja");
      return sortDir === "asc" ? cmp : -cmp;
    });

  const totalProducts = items.length;
  const outOfStock = items.filter((i) => i.quantity <= 0).length;
  const lowStock = items.filter((i) => i.quantity > 0 && i.quantity <= 15).length;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function SortIcon({ column }: { column: SortKey }) {
    if (sortKey !== column) return <span className="text-gray-300 ml-1">↕</span>;
    return <span className="text-brand-600 ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">在庫管理</h2>
          <p className="text-xs text-gray-400 mt-0.5">{totalProducts}品目</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="btn-press bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50 shadow-sm shadow-brand-600/20"
        >
          <svg className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          更新
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6 stagger-in">
        <div className="bg-white rounded-xl border border-gray-100 px-4 py-3">
          <p className="text-[11px] text-gray-400 font-medium">全品目</p>
          <p className="text-2xl font-bold text-gray-900 tabular-nums mt-0.5">{totalProducts}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 px-4 py-3">
          <p className="text-[11px] text-gray-400 font-medium">欠品</p>
          <p className={`text-2xl font-bold tabular-nums mt-0.5 ${outOfStock > 0 ? "text-red-600" : "text-gray-900"}`}>{outOfStock}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 px-4 py-3">
          <p className="text-[11px] text-gray-400 font-medium">在庫少</p>
          <p className={`text-2xl font-bold tabular-nums mt-0.5 ${lowStock > 0 ? "text-amber-600" : "text-gray-900"}`}>{lowStock}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 px-4 py-3">
          <p className="text-[11px] text-gray-400 font-medium">適正以上</p>
          <p className="text-2xl font-bold text-emerald-600 tabular-nums mt-0.5">{totalProducts - outOfStock - lowStock}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="商品名・IDで検索"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="input-field pl-9 pr-3 py-2 w-full text-sm"
          />
        </div>
        <div className="flex rounded-md border border-gray-200 overflow-hidden text-xs font-medium">
          {zones.map((z, i) => (
            <button
              key={z}
              onClick={() => setZoneFilter(z)}
              className={`px-3 py-1.5 transition-colors duration-150 ${
                zoneFilter === z
                  ? "bg-brand-600 text-white"
                  : "bg-white text-gray-500 hover:bg-gray-50"
              } ${i > 0 ? "border-l border-gray-200" : ""}`}
            >
              {z === "all" ? "全て" : z}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">在庫一覧</h3>
          <span className="text-xs text-gray-300 tabular-nums">{filtered.length}件</span>
        </div>

        {loading && items.length === 0 ? (
          <LoadingState
            compact
            title="在庫を棚卸し中です"
            message="品目、温度帯、在庫レベルを読み込んでいます"
            icon={
              <svg className="w-8 h-8 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            }
          />
        ) : filtered.length === 0 ? (
          <div className="py-20 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </div>
            <p className="text-sm text-gray-400">在庫データがありません</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-left text-[11px] font-medium text-gray-400 uppercase tracking-wider">
                  <th className="px-5 py-3 cursor-pointer select-none" onClick={() => handleSort("product_id")}>
                    ID<SortIcon column="product_id" />
                  </th>
                  <th className="px-5 py-3 cursor-pointer select-none" onClick={() => handleSort("product_name")}>
                    商品名<SortIcon column="product_name" />
                  </th>
                  <th className="px-5 py-3 cursor-pointer select-none" onClick={() => handleSort("temperature_zone")}>
                    温度帯<SortIcon column="temperature_zone" />
                  </th>
                  <th className="px-5 py-3 cursor-pointer select-none text-right" onClick={() => handleSort("quantity")}>
                    有効在庫<SortIcon column="quantity" />
                  </th>
                  <th className="px-5 py-3">単位</th>
                  <th className="px-5 py-3">状態</th>
                  <th className="px-5 py-3">在庫レベル</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((item) => {
                  const level = stockLevel(item.quantity);
                  const pct = Math.min(item.quantity / 100, 1) * 100;
                  return (
                    <tr key={item.product_id} className="row-hover">
                      <td className="px-5 py-3.5 font-mono text-xs text-gray-400">{item.product_id}</td>
                      <td className="px-5 py-3.5">
                        <span className="font-medium text-gray-900">{item.product_name}</span>
                        {item.is_variable_weight && (
                          <span className="ml-2 text-[10px] text-purple-600 bg-purple-50 border border-purple-200 rounded px-1 py-px font-medium">不定貫</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5"><TempBadge zone={item.temperature_zone} /></td>
                      <td className="px-5 py-3.5 text-right tabular-nums font-semibold text-gray-900">{item.quantity.toLocaleString()}</td>
                      <td className="px-5 py-3.5 text-gray-500 text-xs">{item.unit}</td>
                      <td className="px-5 py-3.5">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border ${level.cls}`}>
                          {level.label}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 w-32">
                        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              item.quantity <= 0 ? "bg-red-400" :
                              item.quantity <= 15 ? "bg-amber-400" :
                              item.quantity <= 50 ? "bg-emerald-400" : "bg-blue-400"
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
