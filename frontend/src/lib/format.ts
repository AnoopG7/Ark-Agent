import type { ResourceType, Unit } from '../types/api'

export const RESOURCE_LABEL: Record<ResourceType, string> = {
  drinking_water: 'Drinking water',
  food_ration: 'Food rations',
  medicine_kit: 'Medicine kits',
  boat: 'Boats',
  shelter_kit: 'Shelter kits',
  blanket: 'Blankets',
}

const UNIT_SHORT: Record<Unit, string> = {
  litre: 'L',
  packet: 'packets',
  kit: 'kits',
  unit: 'boats',
  piece: 'pcs',
}

export const UNIT_OF: Record<ResourceType, Unit> = {
  drinking_water: 'litre',
  food_ration: 'packet',
  medicine_kit: 'kit',
  boat: 'unit',
  shelter_kit: 'kit',
  blanket: 'piece',
}

const numberFmt = new Intl.NumberFormat('en-IN')

export function qty(n: number, resource: ResourceType): string {
  return `${numberFmt.format(n)} ${UNIT_SHORT[UNIT_OF[resource]]}`
}

/** Amount as a phrase: "800 L of drinking water", "30 medicine kits", "1 boat". */
export function amountOf(n: number, resource: ResourceType): string {
  const label = RESOURCE_LABEL[resource].toLowerCase()
  if (UNIT_OF[resource] === 'litre') return `${numberFmt.format(n)} L of ${label}`
  return `${numberFmt.format(n)} ${n === 1 ? label.replace(/s$/, '') : label}`
}

export function num(n: number): string {
  return numberFmt.format(n)
}

export function wardName(id: string): string {
  const m = /^W-(\d{2})$/.exec(id)
  return m ? `Ward ${Number(m[1])}` : id
}

export function minutes(m: number): string {
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h} h ${rest} min` : `${h} h`
}

export function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  return new Date(iso).toLocaleDateString()
}

export function humanize(s: string): string {
  const t = s.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/**
 * Strip the Markdown a model sometimes emits despite being asked for plain text, so the chat
 * shows clean prose. Also turns gpt-oss style 【source】 citations into (source).
 */
export function plainText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/【([^】]*)】/g, ' ($1)')
}
