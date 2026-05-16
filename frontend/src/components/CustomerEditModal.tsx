import { useState, useEffect } from "react";
import type { Customer } from "../lib/api";

interface Props {
  customer: Customer | null;
  onClose: () => void;
  onSave: (id: string, fields: Partial<Customer>) => Promise<void>;
}

export default function CustomerEditModal({ customer, onClose, onSave }: Props) {
  const [name, setName] = useState("");
  const [shortName, setShortName] = useState("");
  const [lineUserId, setLineUserId] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (customer) {
      setName(customer.name || "");
      setShortName(customer.short_name || "");
      setLineUserId(customer.line_user_id || "");
      setPhone(customer.phone || "");
      setEmail(customer.email || "");
    }
  }, [customer]);

  if (!customer) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(customer.id, {
        name,
        short_name: shortName || undefined,
        line_user_id: lineUserId || undefined,
        phone: phone || undefined,
        email: email || undefined,
      });
      onClose();
    } catch {
      alert("顧客情報の保存に失敗しました。ネットワーク接続を確認して、もう一度お試しください。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden fade-in border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center">
              <svg className="w-4 h-4 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </div>
            <h3 className="font-bold text-gray-900 text-sm">顧客編集</h3>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">顧客名</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} required
                className="input-field w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm outline-none bg-white" />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">略称</label>
              <input type="text" value={shortName} onChange={(e) => setShortName(e.target.value)}
                className="input-field w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm outline-none bg-white" />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">LINE User ID</label>
            <input type="text" value={lineUserId} onChange={(e) => setLineUserId(e.target.value)}
              placeholder="U064d0f5abe71bc0a358c923c3c42599d"
              className="input-field w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm outline-none font-mono bg-white" />
            <p className="text-[11px] text-gray-400 mt-1.5 leading-relaxed">
              「U」で始まる33文字の内部ID（LINE表示名やIDとは異なります。サーバーログで確認できます）
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">電話番号</label>
              <input type="text" value={phone} onChange={(e) => setPhone(e.target.value)}
                className="input-field w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm outline-none bg-white" />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">メール</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="input-field w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm outline-none bg-white" />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-gray-100">
            <button type="button" onClick={onClose} className="btn-press px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors">
              キャンセル
            </button>
            <button type="submit" disabled={saving}
              className="btn-press bg-brand-600 hover:bg-brand-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 shadow-sm shadow-brand-600/20 transition-all">
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
