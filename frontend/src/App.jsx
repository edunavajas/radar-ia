import { useEffect, useState } from 'react'
import { getStats, search as apiSearch, getWeek, getAnswer } from './api'

const LANG_LABEL = {
  es: 'ES',
  en: 'EN',
  'en-orig': 'EN',
  'zh-Hans': '中',
  'zh-Hant': '繁',
  ja: '日',
  ko: '한',
  de: 'DE',
  fr: 'FR',
  pt: 'PT',
}

const dateFmt = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : dateFmt.format(date)
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlight(text, query) {
  const terms = (query || '').split(/\s+/).filter((t) => t.length > 2)
  if (!terms.length) return text
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi')
  const wanted = new Set(terms.map((t) => t.toLowerCase()))
  return text.split(pattern).map((part, index) =>
    wanted.has(part.toLowerCase()) ? <mark key={index}>{part}</mark> : part,
  )
}

function AnswerText({ text }) {
  if (!text) return null
  return (
    <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-200">
      {text.split(/(\[\d+\])/g).map((part, index) => {
        const match = part.match(/^\[(\d+)\]$/)
        if (!match) return part
        return (
          <a
            key={index}
            href={`#r-${match[1]}`}
            className="mx-0.5 rounded bg-radar-500/15 px-1.5 py-0.5 text-sm font-semibold text-radar-400 no-underline hover:bg-radar-500/25"
          >
            {part}
          </a>
        )
      })}
    </p>
  )
}

function ResultCard({ item, query, translated }) {
  const [showOriginal, setShowOriginal] = useState(false)
  const isTranslated = Boolean(translated) && translated !== item.text
  const snippet = isTranslated && !showOriginal ? translated : item.text

  return (
    <article id={`r-${item.rank}`} className="card scroll-mt-24 overflow-hidden transition hover:border-radar-500/40">
      <div className="flex flex-col gap-4 p-4 sm:flex-row">
        <a
          href={item.watch_url}
          target="_blank"
          rel="noreferrer"
          className="relative shrink-0 overflow-hidden rounded-xl border border-white/10"
        >
          <img
            src={item.thumbnail_url}
            alt={item.title}
            loading="lazy"
            className="h-[90px] w-[160px] object-cover"
          />
          <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium text-white">
            {item.start_label}
          </span>
        </a>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="badge bg-white/5 text-slate-300">{LANG_LABEL[item.lang] || item.lang || '??'}</span>
            <span className="font-medium text-slate-300">{item.channel}</span>
            {item.published_at && <span>· {formatDate(item.published_at)}</span>}
          </div>
          <h3 className="mb-2 line-clamp-2 font-semibold leading-snug text-slate-100">{item.title}</h3>
          <p className="text-sm leading-6 text-slate-400">{highlight(snippet, query)}</p>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <a
              href={item.watch_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-radar-500/15 px-3 py-1.5 text-sm font-medium text-radar-400 transition hover:bg-radar-500/25"
            >
              ▶ Ver en {item.start_label}
            </a>
            {isTranslated && (
              <button
                onClick={() => setShowOriginal((value) => !value)}
                className="text-xs text-slate-500 underline decoration-dotted hover:text-slate-300"
              >
                {showOriginal ? 'Ver traducción' : 'Ver original'}
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}

function Skeleton() {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card flex animate-pulse gap-4 p-4">
          <div className="h-[90px] w-[160px] shrink-0 rounded-xl bg-white/5" />
          <div className="flex-1 space-y-3 py-1">
            <div className="h-3 w-1/3 rounded bg-white/5" />
            <div className="h-4 w-2/3 rounded bg-white/5" />
            <div className="h-3 w-full rounded bg-white/5" />
            <div className="h-3 w-4/5 rounded bg-white/5" />
          </div>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ notice }) {
  return (
    <div className="card mx-auto mt-10 max-w-2xl p-8 text-center">
      <div className="mb-3 text-4xl">📡</div>
      <h2 className="mb-2 text-lg font-semibold text-slate-100">La base está vacía</h2>
      <p className="mx-auto max-w-md text-sm leading-6 text-slate-400">
        Radar IA busca dentro de las transcripciones, así que necesita datos primero.
      </p>
      <pre className="mx-auto mt-5 w-fit rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-left text-sm text-radar-400">
        make seed
      </pre>
      <p className="mt-3 text-xs text-slate-500">
        O recolecta contenido propio editando <code>config/sources.yaml</code> y ejecutando{' '}
        <code>make ingest</code>.
      </p>
      {notice && <p className="mt-4 text-xs text-slate-600">{notice}</p>}
    </div>
  )
}

function WeekView() {
  const [topics, setTopics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    getWeek(7)
      .then((data) => alive && setTopics(data.topics || []))
      .catch(() => alive && setTopics([]))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <Skeleton />
  if (!topics.length) {
    return (
      <div className="card mt-6 p-8 text-center text-sm text-slate-400">
        No hay vídeos publicados en los últimos 7 días.
      </div>
    )
  }

  return (
    <div className="mt-6 space-y-6">
      {topics.map((topic) => (
        <section key={topic.term} className="card p-5">
          <div className="mb-4 flex items-baseline gap-3">
            <h2 className="text-lg font-semibold capitalize text-slate-100">{topic.term}</h2>
            <span className="text-xs text-slate-500">{topic.count} menciones</span>
          </div>
          <div className="space-y-3">
            {topic.samples.map((item, index) => (
              <div key={`${item.video_id}-${index}`} className="flex gap-3">
                <img
                  src={item.thumbnail_url}
                  alt=""
                  loading="lazy"
                  className="h-[54px] w-[96px] shrink-0 rounded-lg border border-white/10 object-cover"
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span>{item.channel}</span>
                    <a
                      href={item.watch_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-radar-400 hover:underline"
                    >
                      {item.start_label}
                    </a>
                  </div>
                  <p className="line-clamp-1 text-sm font-medium text-slate-200">{item.title}</p>
                  <p className="line-clamp-2 text-xs leading-5 text-slate-500">{item.text}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [tab, setTab] = useState('search')
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('q') || '')
  const [submitted, setSubmitted] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [answer, setAnswer] = useState(null)
  const [translations, setTranslations] = useState({})
  const [answerLoading, setAnswerLoading] = useState(false)

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((err) => setError(err.message))
  }, [])

  async function runSearch(value) {
    setLoading(true)
    setError('')
    setSubmitted(value)
    setAnswer(null)
    setTranslations({})
    setAnswerLoading(true)
    try {
      const payload = await apiSearch({ q: value })
      setData(payload)
      setLoading(false)
      if (payload.empty || !(payload.results || []).length) {
        setAnswerLoading(false)
        return
      }
      getAnswer({ q: value })
        .then((res) => {
          setAnswer(res.answer)
          setTranslations(res.translations || {})
        })
        .catch(() => {})
        .finally(() => setAnswerLoading(false))
    } catch (err) {
      setError(err.message)
      setData(null)
      setLoading(false)
      setAnswerLoading(false)
    }
  }

  useEffect(() => {
    if (stats && !stats.empty && query) runSearch(query)
    // solo al cargar las estadísticas
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stats])

  function onSubmit(event) {
    event.preventDefault()
    const value = query.trim()
    if (value) runSearch(value)
  }

  const results = data?.results || []

  return (
    <div className="mx-auto min-h-screen max-w-4xl px-4 pb-20 pt-10 sm:px-6">
      <header className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <svg viewBox="0 0 24 24" className="h-8 w-8 text-radar-400" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="9" opacity="0.35" />
            <circle cx="12" cy="12" r="5" />
            <path d="M12 12l6-6" strokeLinecap="round" />
            <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
          </svg>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-50">Radar IA</h1>
            <p className="text-xs text-slate-400">Qué se dice dentro de los vídeos, en cualquier idioma</p>
          </div>
        </div>
        {stats && !stats.empty && (
          <span className="hidden text-xs text-slate-500 sm:block">
            {stats.videos} vídeos · {stats.chunks} fragmentos
          </span>
        )}
      </header>

      {stats && stats.empty ? (
        <EmptyState notice={stats.notice} />
      ) : (
        <>
          <form onSubmit={onSubmit} className="mb-6">
            <div className="flex gap-3">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="¿Qué se ha dicho esta semana sobre…?"
                className="w-full rounded-2xl border border-white/10 bg-white/[0.04] px-5 py-4 text-base text-slate-100 placeholder:text-slate-500 focus:border-radar-500/60 focus:outline-none focus:ring-2 focus:ring-radar-500/30"
                autoFocus
              />
              <button
                type="submit"
                disabled={loading}
                className="shrink-0 rounded-2xl bg-radar-500 px-6 py-4 font-medium text-white transition hover:bg-radar-600 disabled:opacity-50"
              >
                Buscar
              </button>
            </div>
          </form>

          <div className="mb-6 inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1 text-sm">
            {[
              ['search', 'Buscar'],
              ['week', 'Esta semana'],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTab(value)}
                className={`rounded-lg px-4 py-1.5 font-medium transition ${
                  tab === value ? 'bg-radar-500/20 text-radar-400' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {error && (
            <div className="card mb-6 border-red-500/30 p-4 text-sm text-red-300">{error}</div>
          )}

          {tab === 'week' ? (
            <WeekView />
          ) : loading ? (
            <Skeleton />
          ) : data ? (
            <div className="space-y-5">
              {answerLoading ? (
                <div className="card border-radar-500/20 p-5">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-radar-400">
                    Respuesta
                  </div>
                  <p className="animate-pulse text-sm text-slate-500">Redactando…</p>
                </div>
              ) : answer ? (
                <div className="card border-radar-500/20 p-5">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-radar-400">
                    Respuesta
                  </div>
                  <AnswerText text={answer} />
                </div>
              ) : null}
              {!answerLoading && !answer && results.length > 0 && (
                <p className="text-xs text-slate-500">
                  Resultados sin redactar (LLM desactivado o no disponible).
                </p>
              )}
              {results.length === 0 ? (
                <div className="card p-8 text-center text-sm text-slate-400">
                  Sin resultados para «{data.query}». Prueba con otras palabras.
                </div>
              ) : (
                results.map((item) => (
                  <ResultCard
                    key={item.chunk_id}
                    item={item}
                    query={submitted}
                    translated={translations[item.chunk_id]}
                  />
                ))
              )}
            </div>
          ) : (
            <div className="card p-10 text-center text-sm text-slate-500">
              Pregunta en español; buscamos el minuto exacto aunque el vídeo esté en otro idioma.
            </div>
          )}
        </>
      )}
    </div>
  )
}
