import type { Order, Customer, Message } from "./api";

export function getDemoOrders(): Order[] {
  const today = new Date().toISOString().split("T")[0];
  return [
    { uid: "ORD-001", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-001", customer_name: "株式会社A", source: "LINE", items: [{ product_name: "りんご", quantity: 10, unit: "箱", temperature_zone: "冷蔵" }, { product_name: "バナナ", quantity: 20, unit: "kg", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "北関東便", delivery_time_slot: "午前中", status: "未処理", remarks: undefined },
    { uid: "ORD-002", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-002", customer_name: "株式会社B", source: "LINE", items: [{ product_name: "もも", quantity: 5, unit: "箱", temperature_zone: "冷蔵" }], delivery_carrier: "芦川便", delivery_route: "西日本便", delivery_time_slot: "14:00-16:00", status: "完了", remarks: undefined },
    { uid: "ORD-003", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-003", customer_name: "株式会社C", source: "Phone", items: [{ product_name: "メロン", quantity: 3, unit: "玉", temperature_zone: "冷凍" }], delivery_carrier: "自社便", delivery_route: "中部便", status: "製造", remarks: undefined },
    { uid: "ORD-004", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-004", customer_name: "株式会社D", source: "LINE", items: [{ product_name: "いちご", quantity: 15, unit: "パック", temperature_zone: "常温" }, { product_name: "ぶどう", quantity: 8, unit: "房", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "九州便", delivery_time_slot: "18:00-20:00", status: "配送", remarks: undefined },
    { uid: "ORD-005", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-005", customer_name: "株式会社E", source: "Phone", items: [{ product_name: "みかん", quantity: 100, unit: "個", temperature_zone: "冷凍" }], delivery_carrier: "冷凍ヤマト便", delivery_route: "北海道便", status: "要対応", remarks: "在庫不足のため担当者確認中" },
    { uid: "ORD-006", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-006", customer_name: "株式会社F", source: "LINE", items: [{ product_name: "レモン", quantity: 30, unit: "個", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "東北便", status: "完了", remarks: undefined },
  ];
}

export function getDemoMessages(orderId: string): Message[] {
  const today = new Date().toISOString().split("T")[0];
  const msgs: Record<string, Message[]> = {
    "ORD-001": [
      { id: "dm-001-1", role: "user", text: "りんご10箱とバナナ20kgをお願いします。", channel: "line", created_at: `${today}T09:00:00Z` },
      { id: "dm-001-2", role: "assistant", text: "承知しました。りんご10箱（冷蔵）とバナナ20kg（常温）ですね。配送日はいつがよろしいでしょうか？", channel: "line", created_at: `${today}T09:00:15Z` },
      { id: "dm-001-3", role: "user", text: "今日の午前中でお願いします。", channel: "line", created_at: `${today}T09:00:45Z` },
      { id: "dm-001-4", role: "assistant", text: "かしこまりました。本日午前中の北関東便で手配いたします。ご注文ありがとうございます。", channel: "line", created_at: `${today}T09:01:00Z` },
    ],
    "ORD-002": [
      { id: "dm-002-1", role: "user", text: "もも5箱お願いできますか？", channel: "line", created_at: `${today}T10:30:00Z` },
      { id: "dm-002-2", role: "assistant", text: "もも5箱（冷蔵）ですね。配送日と時間帯をお知らせください。", channel: "line", created_at: `${today}T10:30:12Z` },
      { id: "dm-002-3", role: "user", text: "今日の14時〜16時でお願いします。", channel: "line", created_at: `${today}T10:30:40Z` },
      { id: "dm-002-4", role: "assistant", text: "承知しました。本日14:00-16:00の西日本便（芦川便）で手配いたします。", channel: "line", created_at: `${today}T10:30:55Z` },
    ],
    "ORD-003": [
      { id: "dm-003-1", role: "user", text: "メロン3玉を注文したいんですけど。", channel: "phone", created_at: `${today}T11:00:00Z` },
      { id: "dm-003-2", role: "assistant", text: "メロン3玉（冷凍）ですね。配送日はいつがよろしいでしょうか？", channel: "phone", created_at: `${today}T11:00:20Z` },
      { id: "dm-003-3", role: "user", text: "明日届けてもらえますか？中部便で。", channel: "phone", created_at: `${today}T11:00:50Z` },
      { id: "dm-003-4", role: "assistant", text: "かしこまりました。中部便（自社便）で手配いたします。ご注文ありがとうございます。", channel: "phone", created_at: `${today}T11:01:05Z` },
    ],
    "ORD-004": [
      { id: "dm-004-1", role: "user", text: "いちご15パックとぶどう8房をお願いします。", channel: "line", created_at: `${today}T13:00:00Z` },
      { id: "dm-004-2", role: "assistant", text: "いちご15パック（常温）とぶどう8房（常温）ですね。配送のご希望はありますか？", channel: "line", created_at: `${today}T13:00:18Z` },
      { id: "dm-004-3", role: "user", text: "九州便で18時〜20時にお願いします。", channel: "line", created_at: `${today}T13:00:50Z` },
      { id: "dm-004-4", role: "assistant", text: "承知しました。本日18:00-20:00の九州便で手配いたします。ご注文ありがとうございます。", channel: "line", created_at: `${today}T13:01:02Z` },
    ],
    "ORD-005": [
      { id: "dm-005-1", role: "user", text: "みかん100個を注文したいです。", channel: "phone", created_at: `${today}T14:00:00Z` },
      { id: "dm-005-2", role: "assistant", text: "みかん100個（冷凍）ですね。通常のご注文数量より多いようですが、お間違いないでしょうか？", channel: "phone", created_at: `${today}T14:00:25Z` },
      { id: "dm-005-3", role: "user", text: "はい、イベント用なので多めにお願いします。", channel: "phone", created_at: `${today}T14:01:00Z` },
      { id: "dm-005-4", role: "assistant", text: "承知しました。ただ現在在庫が不足しておりますので、担当者に確認の上ご連絡いたします。", channel: "phone", created_at: `${today}T14:01:20Z` },
    ],
    "ORD-006": [
      { id: "dm-006-1", role: "user", text: "レモン30個をお願いします。", channel: "line", created_at: `${today}T15:00:00Z` },
      { id: "dm-006-2", role: "assistant", text: "レモン30個（常温）ですね。東北便でよろしいでしょうか？", channel: "line", created_at: `${today}T15:00:10Z` },
      { id: "dm-006-3", role: "user", text: "はい、それでお願いします。", channel: "line", created_at: `${today}T15:00:30Z` },
      { id: "dm-006-4", role: "assistant", text: "かしこまりました。東北便（自社便）で手配いたします。ご注文ありがとうございます。", channel: "line", created_at: `${today}T15:00:42Z` },
    ],
  };
  return msgs[orderId] || [];
}

export function getDemoCustomers(): Customer[] {
  return [
    { id: "C-001", tenant_id: "T-001", name: "株式会社テスト", short_name: "テスト社", line_user_id: undefined, phone: "03-1234-5678", email: "test@example.com", active: true },
    { id: "C-002", tenant_id: "T-001", name: "株式会社サンプル", short_name: "サンプル社", line_user_id: "U1234567890abcdef", phone: "06-9876-5432", email: undefined, active: true },
    { id: "C-003", tenant_id: "T-001", name: "有限会社デモ", short_name: "デモ社", line_user_id: undefined, phone: undefined, email: "demo@example.com", active: true },
  ];
}
