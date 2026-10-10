const sections = [
  {
    title: "📦 受注管理",
    description: "LINE・電話・メールから届いた注文をAIが解析し、受注一覧に集約します。顧客名・チャネル・配送日で絞り込み、受注詳細から会話履歴やメモを確認できます。",
  },
  {
    title: "🔄 ステータスの流れ",
    description: "注文が確定すると「受注済み」になり、配送中、完了へ進みます。数量異常や在庫不足で確認が必要な注文は「要対応」として表示され、担当者が確認・対処後に受注済みへ移せます。",
  },
  {
    title: "⚠️ AI例外・要対応",
    description: "受注一覧のバナーに確認が必要な件数を表示します。「詳細を確認」から理由、優先度、AIの推奨アクションと顧客向け文案を確認できます。",
  },
  {
    title: "📊 在庫管理",
    description: "商品ごとの在庫数と温度帯を確認できます。AIは注文時に在庫を照合し、不足している場合は顧客に代替案を提案します。",
  },
  {
    title: "👥 顧客管理",
    description: "顧客の基本情報と納品リードタイムを管理します。設定は配送予定日の計算に反映され、LINE・メール・電話からの注文を同じ顧客として扱えます。",
  },
];

export default function Help() {
  return (
    <main className="max-w-3xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">foogent の使い方</h1>
      <p className="text-sm text-gray-500 mb-8">受注業務をスマートに</p>

      <div className="space-y-4">
        {sections.map((section) => (
          <section key={section.title} className="rounded-xl border border-gray-200 bg-white p-6">
            <h2 className="text-base font-bold text-gray-900 mb-3">{section.title}</h2>
            <p className="text-sm text-gray-600 leading-relaxed">{section.description}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
