import { useState, useEffect, useCallback } from "react";
import { fetchCustomers, updateCustomer, type Customer } from "../lib/api";
import { getDemoCustomers } from "../lib/demo";
import CustomerEditModal from "../components/CustomerEditModal";
import LoadingState from "../components/LoadingState";

export default function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Customer | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCustomers(await fetchCustomers());
    } catch {
      setCustomers(getDemoCustomers());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (id: string, fields: Partial<Customer>) => {
    await updateCustomer(id, fields);
    await load();
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">顧客管理</h2>
          <p className="text-xs text-gray-400 mt-0.5">{customers.length}件の顧客</p>
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

      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">顧客一覧</h3>
          <span className="text-xs text-gray-300 tabular-nums">{customers.length}件</span>
        </div>

        {loading && customers.length === 0 ? (
          <LoadingState
            compact
            title="顧客マスタを確認しています"
            message="LINE連携と連絡先情報を読み込んでいます"
            icon={
              <svg className="w-8 h-8 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
          />
        ) : customers.length === 0 ? (
          <div className="py-20 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <p className="text-sm text-gray-400">顧客データがありません</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-left text-[11px] font-medium text-gray-400 uppercase tracking-wider">
                  <th className="px-5 py-3">ID</th>
                  <th className="px-5 py-3">顧客名</th>
                  <th className="px-5 py-3">略称</th>
                  <th className="px-5 py-3">納品グループ</th>
                  <th className="px-5 py-3">LINE連携</th>
                  <th className="px-5 py-3">電話</th>
                  <th className="px-5 py-3">メール</th>
                  <th className="px-5 py-3">状態</th>
                  <th className="px-5 py-3">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {customers.map((c) => (
                  <tr key={c.id} className="row-hover group">
                    <td className="px-5 py-3.5 font-mono text-xs text-gray-400">{c.id}</td>
                    <td className="px-5 py-3.5 font-medium text-gray-900">{c.name}</td>
                    <td className="px-5 py-3.5 text-gray-500">{c.short_name || <span className="text-gray-300">-</span>}</td>
                    <td className="px-5 py-3.5 text-gray-500 text-xs">
                      {c.delivery_group ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
                          {c.delivery_group}
                        </span>
                      ) : <span className="text-gray-300">-</span>}
                    </td>
                    <td className="px-5 py-3.5">
                      {c.line_user_id ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-50 text-emerald-600 border border-emerald-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          連携済み
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs text-gray-400 bg-gray-50 border border-gray-100">
                          未登録
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-gray-500 text-xs tabular-nums">{c.phone || <span className="text-gray-300">-</span>}</td>
                    <td className="px-5 py-3.5 text-gray-500 text-xs">{c.email || <span className="text-gray-300">-</span>}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${
                        c.active
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : "bg-gray-50 text-gray-500 border-gray-200"
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${c.active ? "bg-emerald-500" : "bg-gray-400"}`} />
                        {c.active ? "有効" : "無効"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => setEditing(c)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-brand-600 bg-brand-50 border border-brand-200 hover:bg-brand-100 transition-colors"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                        編集
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <CustomerEditModal customer={editing} onClose={() => setEditing(null)} onSave={handleSave} />
    </>
  );
}
