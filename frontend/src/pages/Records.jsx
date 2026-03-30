import { useState, useEffect } from 'react'
import HoverFullText from '../components/HoverFullText'
import { api } from '../api/client'

const STATUS_LABELS = { queued: '排队中', sent: '已发送', failed: '发送失败', expired: '排队超时' }

export default function Records() {
  const [pageSize, setPageSize] = useState(10)
  const [list, setList] = useState({ items: [], total: 0, page: 1, page_size: 10 })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [selectedIds, setSelectedIds] = useState([])
  const [filters, setFilters] = useState({
    status: '',
    to_email: '',
    from_email: '',
    cc_email: '',
    sent_date_from: '',
    sent_date_to: '',
  })
  const [filterOptions, setFilterOptions] = useState({
    statuses: [],
    to_emails: [],
    from_emails: [],
    cc_emails: [],
  })

  const fetchFilters = () => {
    api.get('/records/filters').then(({ data }) => {
      setFilterOptions({
        statuses: data.statuses || [],
        to_emails: data.to_emails || [],
        from_emails: data.from_emails || [],
        cc_emails: data.cc_emails || [],
      })
    }).catch(() => {})
  }

  const fetchList = (page = 1, q = '', filterOverrides = null, pageSizeOverride = null) => {
    const f = filterOverrides !== null ? filterOverrides : filters
    const size = pageSizeOverride ?? pageSize
    setLoading(true)
    setError('')
    const params = {
      page,
      page_size: size,
      q: q || undefined,
      status: f.status || undefined,
      to_email: f.to_email || undefined,
      from_email: f.from_email || undefined,
      cc_email: f.cc_email || undefined,
      sent_date_from: f.sent_date_from || undefined,
      sent_date_to: f.sent_date_to || undefined,
    }
    api
      .get('/records', { params })
      .then(({ data }) => {
        setList({
          items: data.items || [],
          total: data.total || 0,
          page: data.page || page,
          page_size: data.page_size || size,
        })
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '加载失败')
        setList((prev) => ({ ...prev, items: [] }))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchFilters()
    fetchList(1)
  }, [])

  const handlePageSizeChange = (ev) => {
    const size = parseInt(ev.target.value, 10) || 10
    const normalized = Math.min(Math.max(size, 1), 100)
    setPageSize(normalized)
    // 切换每页条数时回到第 1 页
    fetchList(1, query, null, normalized)
  }

  const applyFilter = (key, value) => {
    const next = { ...filters, [key]: value }
    setFilters(next)
    fetchList(1, query, next)
  }

  const clearAllFilters = () => {
    setFilters({
      status: '',
      to_email: '',
      from_email: '',
      cc_email: '',
      sent_date_from: '',
      sent_date_to: '',
    })
    fetchList(1, query, {
      status: '',
      to_email: '',
      from_email: '',
      cc_email: '',
      sent_date_from: '',
      sent_date_to: '',
    })
  }

  const totalPages = Math.max(1, Math.ceil(list.total / list.page_size))
  const canPrev = list.page > 1
  const canNext = list.page < totalPages

  const toggleSelectRow = (row) => {
    if (row.status !== 'queued') return
    setSelectedIds((prev) =>
      prev.includes(row.id) ? prev.filter((id) => id !== row.id) : [...prev, row.id],
    )
  }

  const queuedOnPage = list.items.filter((row) => row.status === 'queued')
  const allQueuedSelected =
    queuedOnPage.length > 0 && queuedOnPage.every((row) => selectedIds.includes(row.id))
  const selectedQueuedCount = list.items.filter(
    (row) => row.status === 'queued' && selectedIds.includes(row.id),
  ).length

  const toggleSelectAllOnPage = () => {
    if (queuedOnPage.length === 0) return
    if (allQueuedSelected) {
      // 仅取消本页排队记录的勾选，其它页的选择保留
      const idsToUnselect = new Set(queuedOnPage.map((row) => row.id))
      setSelectedIds((prev) => prev.filter((id) => !idsToUnselect.has(id)))
    } else {
      const idsToAdd = queuedOnPage.map((row) => row.id)
      setSelectedIds((prev) => Array.from(new Set([...prev, ...idsToAdd])))
    }
  }

  const handleCancelSend = (row) => {
    if (row.status !== 'queued') return
    if (!window.confirm('确定要取消发送该邮件吗？取消后将从队列中移除，该邮件将不会发出。')) return
    setLoading(true)
    api
      .delete(`/records/${row.id}`)
      .then(() => {
        fetchList(list.page, query)
        fetchFilters()
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '取消失败')
      })
      .finally(() => setLoading(false))
  }

  const handleBulkCancel = () => {
    const targets = list.items.filter(
      (row) => row.status === 'queued' && selectedIds.includes(row.id),
    )
    if (!targets.length) return
    if (
      !window.confirm(
        `确定要取消这 ${targets.length} 条排队中的邮件吗？取消后将从队列中移除，这些邮件将不会发出。`,
      )
    )
      return
    setLoading(true)
    Promise.all(targets.map((row) => api.delete(`/records/${row.id}`)))
      .then(() => {
        setSelectedIds((prev) =>
          prev.filter((id) => !targets.some((row) => row.id === id)),
        )
        fetchList(list.page, query)
        fetchFilters()
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '批量取消失败')
      })
      .finally(() => setLoading(false))
  }

  const formatSentAt = (value) => {
    if (!value) return ''
    if (typeof value === 'string') {
      const s = value.trim()
      if (s.includes('T')) {
        const [datePart, timeWithZone] = s.split('T')
        if (!timeWithZone) return s
        const timePart = timeWithZone.replace(/Z$/, '').split(/[+-]/)[0]
        const timeToSecond = timePart.includes('.') ? timePart.split('.')[0] : timePart
        return `${datePart} ${timeToSecond}`
      }
      if (s.includes(' ')) {
        const [datePart, timePart] = s.split(' ')
        if (!timePart) return s
        const timeToSecond = timePart.includes('.') ? timePart.split('.')[0] : timePart
        return `${datePart} ${timeToSecond}`
      }
      return s
    }
    return String(value)
  }

  return (
    <div>
      <h1 className="page-title">邮件记录</h1>
      <p className="page-desc">
        展示当前账号的邮件发送队列与历史记录（管理员可查看所有销售的记录）。
        支持按收件人/主题/内容模糊搜索，也支持按状态/发送时间/To（客户邮箱）/From/CC筛选。
      </p>

      <section className="section mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            className="input input-width-sm"
            placeholder="输入邮箱 / 主题 / 内容"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="button" className="btn" onClick={() => fetchList(1, query)} disabled={loading}>
            搜索
          </button>
          {query && (
            <button type="button" className="btn" onClick={() => { setQuery(''); fetchList(1, ''); }} disabled={loading}>
              清空搜索
            </button>
          )}
        </div>
      </section>

      <section className="section filter-row mb-4">
        <label className="form-label">
          状态
          <select
            value={filters.status}
            onChange={(ev) => applyFilter('status', ev.target.value)}
            className="select input-sm"
          >
            <option value="">全部</option>
            {filterOptions.statuses.map((s) => (
              <option key={s} value={s}>{STATUS_LABELS[s] || s}</option>
            ))}
          </select>
        </label>
        <label className="form-label">
          发送时间
          <div className="flex items-center gap-1">
            <input
              type="date"
              className="input input-sm"
              value={filters.sent_date_from}
              onChange={(ev) => applyFilter('sent_date_from', ev.target.value)}
            />
            <span>至</span>
            <input
              type="date"
              className="input input-sm"
              value={filters.sent_date_to}
              onChange={(ev) => applyFilter('sent_date_to', ev.target.value)}
            />
          </div>
        </label>
        <label className="form-label">
          To（客户邮箱）
          <select
            value={filters.to_email}
            onChange={(ev) => applyFilter('to_email', ev.target.value)}
            className="select input-sm"
            style={{ minWidth: 180 }}
          >
            <option value="">全部</option>
            {filterOptions.to_emails.map((email) => (
              <option key={email} value={email}>{email}</option>
            ))}
          </select>
        </label>
        <label className="form-label">
          CC
          <select
            value={filters.cc_email}
            onChange={(ev) => applyFilter('cc_email', ev.target.value)}
            className="select input-sm"
            style={{ minWidth: 180 }}
          >
            <option value="">全部</option>
            {filterOptions.cc_emails.map((email) => (
              <option key={email} value={email}>{email}</option>
            ))}
          </select>
        </label>
        {(filters.status || filters.sent_date_from || filters.sent_date_to || filters.to_email || filters.from_email || filters.cc_email) && (
          <button type="button" className="btn" onClick={clearAllFilters}>清空筛选</button>
        )}
      </section>

      {error && <p className="text-error mb-4">{error}</p>}

      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : list.items.length === 0 ? (
        <p className="text-muted">暂无发送记录。</p>
      ) : (
        <section className="section">
          {selectedQueuedCount > 0 && (
            <div className="flex items-center gap-2 mb-2" style={{ justifyContent: 'space-between' }}>
              <span className="text-sm text-muted">
                已选择 {selectedQueuedCount} 条「排队中」记录
              </span>
              <button
                type="button"
                className="btn btn-danger btn-compact"
                disabled={loading}
                onClick={handleBulkCancel}
              >
                批量取消发送
              </button>
            </div>
          )}
          <div className="table-wrap">
            <table className="table" style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input
                      type="checkbox"
                      checked={allQueuedSelected}
                      onChange={toggleSelectAllOnPage}
                      disabled={queuedOnPage.length === 0}
                    />
                  </th>
                  <th style={{ width: 110 }}>状态</th>
                  <th style={{ width: 160 }}>发送时间</th>
                  <th style={{ width: 220 }}>To（客户邮箱）</th>
                  <th style={{ width: 200 }}>From</th>
                  <th style={{ width: 220 }}>CC</th>
                  <th>内容摘要</th>
                  <th className="text-right" style={{ width: 140 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((row) => {
                  const time =
                    row.status === 'sent' && row.sent_at
                      ? formatSentAt(row.sent_at)
                      : '—'
                  const att =
                    Array.isArray(row.image_names) && row.image_names.length
                      ? row.image_names.join('、')
                      : '（无）'
                  const ft = (row.fixed_text || '').trim()
                  const footerFixed = ft || '（无固定文本）'
                  const contentSummary =
                    row.content_summary ||
                    [
                      `主题：${row.subject || '（无主题）'}`,
                      '',
                      '【AI 生成内容】',
                      row.content || '（无）',
                      '',
                      '【附件】',
                      att,
                      '',
                      '【落款】',
                      '（见发件人配置）',
                      '（联系方式未填）',
                      footerFixed,
                    ].join('\n')
                  const summaryOneLine = contentSummary.replace(/\s+/g, ' ').trim()
                  const short =
                    summaryOneLine.length > 60
                      ? `${summaryOneLine.slice(0, 60)}…`
                      : summaryOneLine || '（无内容）'

                  return (
                    <tr key={row.id}>
                      <td>
                        {row.status === 'queued' && (
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(row.id)}
                            onChange={() => toggleSelectRow(row)}
                          />
                        )}
                      </td>
                      <td>
                        <span
                          className={`badge badge-${
                            row.status === 'sent'
                              ? 'sent'
                              : row.status === 'expired'
                                ? 'expired'
                                : row.status === 'failed'
                                  ? 'cancelled'
                                  : 'queued'
                          }`}
                        >
                          {STATUS_LABELS[row.status] ?? row.status}
                        </span>
                      </td>
                      <td className="text-muted">{time}</td>
                      <td>{row.to_email}</td>
                      <td>{row.from_email}</td>
                      <td>{row.cc_email || '—'}</td>
                      <td>
                        <HoverFullText
                          fullText={contentSummary}
                          style={{ cursor: 'default', display: 'block', maxWidth: 320 }}
                        >
                          <div className="cell-ellipsis text-sm">{short}</div>
                        </HoverFullText>
                      </td>
                      <td className="text-right">
                        <div className="actions-column">
                          {row.status === 'queued' && (
                            <button
                              type="button"
                              className="btn btn-danger btn-compact"
                              onClick={() => handleCancelSend(row)}
                              disabled={loading}
                            >
                              取消发送
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3 mt-4">
            <span className="text-muted text-sm">
              第 {list.page} / {totalPages} 页，共 {list.total} 条
            </span>
            <div className="flex items-center text-sm">
              <span className="text-muted">每页</span>
              <select
                value={pageSize}
                onChange={handlePageSizeChange}
                className="select input-sm"
                style={{ margin: '0 4px', width: 80 }}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
              <span className="text-muted">条</span>
            </div>
            <button type="button" className="btn" onClick={() => fetchList(list.page - 1, query)} disabled={!canPrev || loading}>
              上一页
            </button>
            <button type="button" className="btn" onClick={() => fetchList(list.page + 1, query)} disabled={!canNext || loading}>
              下一页
            </button>
            {(filters.status || filters.sent_date_from || filters.sent_date_to || filters.to_email || filters.from_email || filters.cc_email) && (
              <span className="text-muted" style={{ marginLeft: 8, fontSize: 12 }}>
                当前筛选：{[
                  filters.status && STATUS_LABELS[filters.status],
                  (filters.sent_date_from || filters.sent_date_to) &&
                    `发送时间=${filters.sent_date_from || '最早'}~${filters.sent_date_to || '最晚'}`,
                  filters.to_email && 'To',
                  filters.from_email && 'From',
                  filters.cc_email && 'Cc',
                ].filter(Boolean).join('、')}
              </span>
            )}
          </div>
        </section>
      )}
    </div>
  )
}

