const INN_10_WEIGHTS = [2, 4, 10, 3, 5, 9, 4, 6, 8]
const INN_11_WEIGHTS = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
const INN_12_WEIGHTS = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

function checksum(digits: number[], weights: number[]): number {
  const sum = weights.reduce((acc, weight, index) => acc + weight * (digits[index] ?? 0), 0)
  return (sum % 11) % 10
}

/** ИНН юрлица (10 цифр) или ИП (12 цифр) с проверкой контрольных разрядов */
export function isValidInn(value: string): boolean {
  if (!/^\d{10}$|^\d{12}$/.test(value)) return false
  const digits = [...value].map(Number)

  if (digits.length === 10) {
    return checksum(digits, INN_10_WEIGHTS) === digits[9]
  }
  return checksum(digits, INN_11_WEIGHTS) === digits[10] && checksum(digits, INN_12_WEIGHTS) === digits[11]
}
