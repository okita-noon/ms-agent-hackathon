export default function Help() {
  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">foogent の使い方</h1>
      <p className="text-sm text-gray-500 mb-8">AI受発注自動一元管理システム — 操作ガイド</p>

      <section className="space-y-8">
        {/* 受注管理 */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-bold text-gray-900 mb-3">📦 受注管理</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            （ここに説明を書く）
          </p>
        </div>

        {/* AI例外・要対応 */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-bold text-gray-900 mb-3">⚠️ AI例外・要対応</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            （ここに説明を書く）
          </p>
        </div>

        {/* ステータス遷移 */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-bold text-gray-900 mb-3">🔄 ステータスの流れ</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            （ここに説明を書く）
          </p>
        </div>

        {/* 在庫管理 */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-bold text-gray-900 mb-3">📊 在庫管理</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            （ここに説明を書く）
          </p>
        </div>

        {/* 顧客管理 */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-bold text-gray-900 mb-3">👥 顧客管理</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            （ここに説明を書く）
          </p>
        </div>
      </section>
    </div>
  );
}
