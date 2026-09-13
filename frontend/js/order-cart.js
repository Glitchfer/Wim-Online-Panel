/* ════════════════════════════════════════════════════
   WIM Online — Order Cart (sessionStorage-persistent)
   ════════════════════════════════════════════════════ */

class OrderCart {
  constructor(storeUuid, storeName) {
    this.storeUuid = storeUuid || '';
    this.storeName = storeName || '';
    this.items = []; // {sku, name, qty, unitPrice, unitDiscount, is_bonus, promoName, promoRef}
    this.promosApplied = [];
    this.totals = { subtotal: 0, totalDiscount: 0, strataDiscount: 0, grandTotal: 0, bonusValue: 0 };
    this.load();
  }

  get storageKey() {
    return `wim_cart_${this.storeUuid || 'default'}`;
  }

  save() {
    try {
      sessionStorage.setItem(this.storageKey, JSON.stringify({
        storeUuid: this.storeUuid,
        storeName: this.storeName,
        items: this.items,
        promosApplied: this.promosApplied,
        totals: this.totals
      }));
    } catch (e) { console.error('Cart save failed:', e); }
  }

  load() {
    try {
      const raw = sessionStorage.getItem(this.storageKey);
      if (raw) {
        const d = JSON.parse(raw);
        this.storeUuid = d.storeUuid || this.storeUuid;
        this.storeName = d.storeName || this.storeName;
        this.items = d.items || [];
        this.promosApplied = d.promosApplied || [];
        this.totals = d.totals || this.totals;
      }
    } catch (e) { console.error('Cart load failed:', e); }
  }

  clear() {
    try { sessionStorage.removeItem(this.storageKey); } catch (e) {}
    this.items = [];
    this.promosApplied = [];
    this.totals = { subtotal: 0, totalDiscount: 0, strataDiscount: 0, grandTotal: 0, bonusValue: 0 };
  }

  addProduct(sku, name, unitPrice) {
    const existing = this.items.find(i => i.sku === sku && !i.is_bonus);
    if (existing) existing.qty += 1;
    else this.items.push({ sku, name, qty: 1, unitPrice, unitDiscount: 0, is_bonus: false, promoName: '', promoRef: '' });
    this.save();
  }

  updateQty(sku, qty) {
    const idx = this.items.findIndex(i => i.sku === sku && !i.is_bonus);
    if (idx >= 0) {
      if (qty <= 0) this.items.splice(idx, 1);
      else this.items[idx].qty = qty;
    }
    // Remove bonus items tied to removed sku
    this.items = this.items.filter(i => i.is_bonus ? this.items.some(p => p.sku === i.sku && !p.is_bonus) : true);
    this.save();
  }

  removeItem(sku) {
    this.items = this.items.filter(i => !(i.sku === sku && !i.is_bonus));
    this.save();
  }

  get purchasedItems() { return this.items.filter(i => !i.is_bonus); }
  get bonusItems() { return this.items.filter(i => i.is_bonus); }
  get itemCount() { return this.purchasedItems.reduce((s, i) => s + i.qty, 0); }
  get lineCount() { return this.purchasedItems.length; }

  toPayload() {
    return {
      items: this.items.map(i => ({
        sku: i.sku, name: i.name, qty: i.qty, unitPrice: i.unitPrice,
        unitDiscount: i.unitDiscount || 0, is_bonus: !!i.is_bonus,
        promoName: i.promoName || '', promoRef: i.promoRef || ''
      })),
      promosApplied: this.promosApplied
    };
  }

  applyCalculation(calc) {
    // Replace bonus items with server-computed ones
    const purchased = this.items.filter(i => !i.is_bonus);
    const newItems = purchased.map(p => {
      const server = (calc.purchased || []).find(s => s.sku === p.sku);
      return {
        ...p,
        unitDiscount: server ? server.unitDiscount : p.unitDiscount,
      };
    });
    // Add server bonus items
    (calc.bonus || []).forEach(b => {
      newItems.push({ sku: b.sku, name: b.name, qty: b.qty, unitPrice: 0, unitDiscount: 0, is_bonus: true, promoName: b.promoName || '', promoRef: b.promoRef || '' });
    });
    this.items = newItems;
    this.promosApplied = calc.promosApplied || [];
    this.totals = {
      subtotal: calc.subtotal || 0,
      totalDiscount: calc.totalDiscount || 0,
      strataDiscount: calc.strataDiscount || 0,
      grandTotal: calc.grandTotal || 0,
      bonusValue: calc.bonusValue || 0
    };
    this.save();
  }

  static hydrateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const storeUuid = params.get('store');
    const storeName = params.get('name') || '';
    const checkinId = params.get('checkin') || '';
    if (!storeUuid) return { cart: null, storeUuid: null, storeName: '', checkinId: '' };
    return { cart: new OrderCart(storeUuid, storeName), storeUuid, storeName, checkinId };
  }
}

// Format IDR
function formatIDR(n) {
  return 'Rp ' + Number(n || 0).toLocaleString('id-ID');
}