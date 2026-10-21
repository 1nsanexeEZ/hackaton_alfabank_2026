export interface LoanSummary {
  monthlyPayment: number
  totalPayment: number
  overpayment: number
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/** Аннуитетный платёж: одинаковая сумма каждый месяц */
export function calcAnnuityPayment(principal: number, annualRatePercent: number, months: number): number {
  if (principal <= 0 || months <= 0) return 0
  const monthlyRate = annualRatePercent / 100 / 12
  if (monthlyRate === 0) return principal / months
  return (principal * monthlyRate) / (1 - (1 + monthlyRate) ** -months)
}

export function calcLoanSummary(principal: number, annualRatePercent: number, months: number): LoanSummary {
  const monthlyPayment = calcAnnuityPayment(principal, annualRatePercent, months)
  const totalPayment = monthlyPayment * months
  return {
    monthlyPayment,
    totalPayment,
    overpayment: Math.max(totalPayment - principal, 0),
  }
}
