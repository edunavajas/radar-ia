async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Error ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

export function getStats() {
  return getJson('/api/stats')
}

export function search({ q, lang, channel, publishedAfter, limit = 8 }) {
  const params = new URLSearchParams({ q, limit: String(limit) })
  if (lang) params.set('lang', lang)
  if (channel) params.set('channel', channel)
  if (publishedAfter) params.set('published_after', publishedAfter)
  return getJson(`/api/search?${params.toString()}`)
}

export function getWeek(days = 7) {
  return getJson(`/api/week?days=${days}`)
}
