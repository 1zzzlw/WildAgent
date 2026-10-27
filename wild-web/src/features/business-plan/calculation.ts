export interface SubscriptionAssumptions {
  price: number
  users: number
  'model-cost': number
  'service-cost': number
  'fixed-cost': number
}

export function calculateSubscription(values: SubscriptionAssumptions) {
  const unit = values.price - values['model-cost'] - values['service-cost']
  return {
    unit,
    revenue: values.price * values.users,
    contribution: unit * values.users,
    balance: unit * values.users - values['fixed-cost'],
    rate: unit / values.price * 100,
    breakEven: values['fixed-cost'] === 0 && unit >= 0 ? 0 : unit > 0 ? Math.ceil(values['fixed-cost'] / unit) : null,
    scale: Math.max(values.price, values['model-cost'] + values['service-cost']),
  }
}

export function money(value: number) {
  return (value < 0 ? '−¥' : '¥') + Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
