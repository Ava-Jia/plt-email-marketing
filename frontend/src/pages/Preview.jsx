import React, { useState, useEffect, useCallback, useRef } from 'react'
import HoverFullText from '../components/HoverFullText'
import { api } from '../api/client'
import {
  loadPreviewGenerated,
  savePreviewGenerated,
  removeLegacyPreviewStorage,
} from '../utils/previewStorage'

const PAGE_SIZE = 10
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function readUser() {
  try {
    const j = localStorage.getItem('user')
    return j ? JSON.parse(j) : null
  } catch {
    return null
  }
}
const STATUS_LABELS = {
  active: '进行中',
  sending: '发送中',
  completed: '已完成',
  cancelled: '已取消',
  template_disabled: '该模版已被管理员禁用',
}

export default function Preview() {
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [images, setImages] = useState([])
  const [customerList, setCustomerList] = useState({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
  /** 当前登录用户在客户表中存在的 id；null 表示尚未拉完（群发 payload 需等就绪，避免混入他人缓存） */
  const [allowedCustomerIds, setAllowedCustomerIds] = useState(null)
  const [generatedContent, setGeneratedContent] = useState(() => loadPreviewGenerated(readUser()?.id)) // `${templateId}_${customerId}` -> { content, email }
  const [generatingIds, setGeneratingIds] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [sendMessage, setSendMessage] = useState({ type: '', text: '', fromMode: null }) // fromMode: 'batch' | 'schedule' | null，仅当前模式显示
  const [sendMode, setSendMode] = useState('batch') // 'batch' | 'schedule'
  const [schedules, setSchedules] = useState([])
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [scheduleForm, setScheduleForm] = useState({
    recurrence_type: 'week',
    day_of_week: 0,
    day_of_month: 1,
    time: '09:00',
    repeat_count: 1,
  })
  /** customers/summary：失败时不把 count 当作 0 */
  const [customerSummary, setCustomerSummary] = useState({ status: 'loading' })
  /** 全量客户 id 拉取失败时的说明；降级时额外提示 */
  const [customerIdsLoadError, setCustomerIdsLoadError] = useState(null)
  const [customerIdsDegraded, setCustomerIdsDegraded] = useState(false)
  const customerListRef = useRef({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
  const [queueStatus, setQueueStatus] = useState({ queued_global: 0, queued_mine: 0, rate_limit_seconds: 30, eta_minutes: 0 })
  const [queueStatusLoading, setQueueStatusLoading] = useState(false)
  const user = readUser()
  const userId = user?.id
  const isAdmin = user?.role === 'admin'

  customerListRef.current = customerList

  // 切换账号 / 进入页面：去掉旧全局 key，并按用户加载专属缓存
  useEffect(() => {
    removeLegacyPreviewStorage()
    if (userId == null || userId === '') {
      setGeneratedContent({})
      return
    }
    setGeneratedContent(loadPreviewGenerated(userId))
  }, [userId])

  // 拉取全部客户 id 用于过滤群发；summary 明确为 0 时跳过请求；失败保持 null 或部分/当前页降级
  useEffect(() => {
    if (userId == null || userId === '') {
      setAllowedCustomerIds(new Set())
      setCustomerIdsLoadError(null)
      setCustomerIdsDegraded(false)
      return
    }
    if (customerSummary.status === 'loading') {
      return
    }
    if (customerSummary.status === 'ok' && customerSummary.count === 0) {
      setAllowedCustomerIds(new Set())
      setCustomerIdsLoadError(null)
      setCustomerIdsDegraded(false)
      return
    }

    let cancelled = false
    setAllowedCustomerIds(null)
    setCustomerIdsLoadError(null)
    setCustomerIdsDegraded(false)

    ;(async () => {
      const ids = new Set()
      const pageSize = 100
      let page = 1
      let total = Infinity
      try {
        while (!cancelled && (page - 1) * pageSize < total) {
          const { data } = await api.get('/customers', { params: { page, page_size: pageSize } })
          if (cancelled) return
          for (const row of data.items || []) ids.add(row.id)
          total = data.total ?? 0
          page += 1
        }
        if (!cancelled) {
          setAllowedCustomerIds(ids)
          setCustomerIdsLoadError(null)
          setCustomerIdsDegraded(false)
        }
      } catch {
        if (cancelled) return
        if (ids.size > 0) {
          setAllowedCustomerIds(ids)
          setCustomerIdsDegraded(true)
          setCustomerIdsLoadError('客户列表未完全同步，仅包含已拉取部分；建议刷新页面后重试。')
          return
        }
        setAllowedCustomerIds(null)
        const pageIds = (customerListRef.current.items || []).map((r) => r.id)
        if (pageIds.length > 0) {
          setAllowedCustomerIds(new Set(pageIds))
          setCustomerIdsDegraded(true)
          setCustomerIdsLoadError(
            '全量客户同步失败，已暂按当前表格页客户校验群发；切换分页或刷新页面后请重新同步。',
          )
        } else {
          setCustomerIdsLoadError('无法加载客户列表，请刷新页面或检查网络后重试。')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [userId, customerSummary])

  useEffect(() => {
    Promise.all([
      api.get('/preview/templates').then((r) => r.data),
      api.get('/preview/images').then((r) => r.data),
      api
        .get('/customers/summary')
        .then((r) => ({ ok: true, data: r.data }))
        .catch(() => ({ ok: false })),
    ])
      .then(([tplList, imgList, summaryRes]) => {
        setTemplates(tplList || [])
        setImages(imgList || [])
        if (summaryRes.ok) {
          setCustomerSummary({ status: 'ok', count: summaryRes.data?.count ?? 0 })
        } else {
          setCustomerSummary({
            status: 'error',
            message: '无法加载客户数量，客户表仍可能可用；请稍后刷新页面。',
          })
        }
        if ((tplList || []).length > 0 && !selectedId) setSelectedId(String((tplList || [])[0].id))
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '加载失败')
        setCustomerSummary({ status: 'error', message: '页面数据加载异常，请刷新重试。' })
      })
      .finally(() => setLoading(false))
  }, [])

  const fetchSchedules = () => {
    setScheduleLoading(true)
    return api
      .get('/send/schedules')
      .then(({ data }) => setSchedules(data?.items ?? []))
      .catch(() => { /* 刷新失败时不清空原列表 */ })
      .finally(() => setScheduleLoading(false))
  }
  useEffect(() => {
    if (sendMode === 'schedule') fetchSchedules()
  }, [sendMode])

  const fetchQueueStatus = () => {
    setQueueStatusLoading(true)
    return api
      .get('/send/queue/status')
      .then(({ data }) => setQueueStatus(data || { queued_global: 0, queued_mine: 0, rate_limit_seconds: 30, eta_minutes: 0 }))
      .catch(() => {})
      .finally(() => setQueueStatusLoading(false))
  }
  useEffect(() => {
    if (sendMode !== 'batch') return
    fetchQueueStatus()
    const t = window.setInterval(fetchQueueStatus, 60000) // 每 1 分钟自动刷新一次
    return () => window.clearInterval(t)
  }, [sendMode])

  useEffect(() => {
    savePreviewGenerated(userId, generatedContent)
  }, [generatedContent, userId])

  const selectedTemplate = templates.find((t) => String(t.id) === String(selectedId))
  const displayContent = selectedTemplate ? selectedTemplate.content : ''

  const selectedImages = (() => {
    const ids = Array.isArray(selectedTemplate?.image_ids) ? selectedTemplate.image_ids : []
    const set = new Set(ids)
    return images.filter((img) => set.has(img.id))
  })()

  const fetchCustomers = useCallback((page = 1) => {
    api.get('/customers', { params: { page, page_size: PAGE_SIZE } })
      .then(({ data }) => setCustomerList({ items: data.items ?? [], total: data.total ?? 0, page: data.page ?? 1, page_size: data.page_size ?? PAGE_SIZE }))
      .catch(() => setCustomerList((prev) => ({ ...prev, items: [] })))
  }, [])

  const summaryStatus = customerSummary.status
  const summaryCountForEffect = customerSummary.status === 'ok' ? customerSummary.count : -1

  useEffect(() => {
    if (!selectedId) return
    if (summaryStatus === 'ok' && summaryCountForEffect === 0) return
    fetchCustomers(1)
  }, [selectedId, summaryStatus, summaryCountForEffect, fetchCustomers])

  const contentKey = (cid) => `${selectedId}_${cid}`

  const generateOne = async (customerId) => {
    const templateId = parseInt(selectedId, 10)
    if (!templateId || !customerId) return
    setGeneratingIds((s) => new Set(s).add(customerId))
    setError('')
    try {
      const { data } = await api.post('/preview/generate-one', { customer_id: customerId, template_id: templateId }, { timeout: 120000 })
      setGeneratedContent((prev) => ({
        ...prev,
        [contentKey(customerId)]: { content: data.content, email: data.email },
      }))
    } catch (err) {
      const d = err.response?.data?.detail
      setError(typeof d === 'string' ? d : d?.message || err.message || '生成失败')
    } finally {
      setGeneratingIds((s) => {
        const next = new Set(s)
        next.delete(customerId)
        return next
      })
    }
  }

  const handleGenerateAll = async () => {
    if (!selectedId) return
    if (customerSummary.status === 'loading') return
    if (customerSummary.status === 'ok' && customerSummary.count === 0) return
    const pageSize = 50
    let page = 1
    let total = customerSummary.status === 'ok' ? customerSummary.count : Infinity
    while ((page - 1) * pageSize < total) {
      const { data } = await api.get('/customers', { params: { page, page_size: pageSize } })
      const items = data.items ?? []
      if (total === Infinity && data.total != null) {
        total = data.total
      }
      for (const row of items) {
        await generateOne(row.id)
      }
      if (items.length === 0) break
      // summary 失败且接口未返回 total 时，用「最后一页不足 pageSize」判断结束
      if (total === Infinity && items.length < pageSize) break
      page += 1
    }
  }

  const handleRegenerate = (customerId) => {
    generateOne(customerId)
  }

  const builtItems = (() => {
    const items = []
    const prefix = `${selectedId}_`
    const idsReady = allowedCustomerIds !== null
    for (const [key, val] of Object.entries(generatedContent)) {
      if (!key.startsWith(prefix)) continue
      const rest = key.slice(prefix.length)
      const cid = parseInt(rest, 10)
      if (!Number.isFinite(cid)) continue
      // 未得到 allowed 集合（含全量失败且未降级）前，不把本地缓存打进群发
      if (!idsReady) continue
      if (!allowedCustomerIds.has(cid)) continue
      if (val?.content && val?.email) {
        items.push({ customer_id: cid, to_email: val.email, content: val.content })
      }
    }
    return items
  })()

  /** 仅当 summary 成功且明确为 0 时视为「真的没有客户」 */
  const hasNoCustomersConfirmed =
    customerSummary.status === 'ok' && customerSummary.count === 0

  const handleStartBatch = () => {
    setSendMessage({ type: '', text: '', fromMode: null })
    if (!builtItems.length) {
      setSendMessage({ type: 'error', text: '请先在下方表格中生成邮件内容后再开始群发。', fromMode: 'batch' })
      return
    }
    if (!window.confirm(`确定开始群发吗？将发送 ${builtItems.length} 封邮件，每 30 秒 1 封。`)) {
      return
    }
    const templateId = parseInt(selectedId, 10)
    if (!templateId) {
      setSendMessage({ type: 'error', text: '请先选择一套邮件模版。', fromMode: 'batch' })
      return
    }
    setSending(true)
    api
      .post('/send/batch', {
        template_id: templateId,
        items: builtItems,
      })
      .then(() => {
        setSendMessage({
          type: 'success',
          text: '已开始后台群发。你可以在「邮件记录」查看进度。',
          fromMode: 'batch',
        })
        setGeneratedContent((prev) => {
          const next = { ...prev }
          builtItems.forEach((it) => { delete next[contentKey(it.customer_id)] })
          return next
        })
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setSendMessage({ type: 'error', text: typeof d === 'string' ? d : d?.message || err.message || '启动群发失败', fromMode: 'batch' })
      })
      .finally(() => setSending(false))
  }

  const handleCreateSchedule = () => {
    if (sending) return
    setSending(true)
    setSendMessage({ type: '', text: '', fromMode: null })
    const formTime = scheduleForm.time || '09:00'
    if (!/^\d{1,2}:\d{2}$/.test(formTime)) {
      setSendMessage({ type: 'error', text: '时间格式为 HH:MM（如 09:00）', fromMode: 'schedule' })
      setSending(false)
      return
    }
    const [h, m] = formTime.split(':').map(Number)
    if (h < 0 || h > 23 || m < 0 || m > 59) {
      setSendMessage({ type: 'error', text: '请填写有效时间', fromMode: 'schedule' })
      setSending(false)
      return
    }
    const recurrence = scheduleForm.recurrence_type || 'week'
    const templateId = selectedId ? parseInt(selectedId, 10) : null
    if (!templateId) {
      setSendMessage({ type: 'error', text: '请先选择一套邮件模版。', fromMode: 'schedule' })
      setSending(false)
      return
    }
    if (!builtItems.length) {
      setSendMessage({ type: 'error', text: '请先在下方表格中生成邮件内容后再创建计划。', fromMode: 'schedule' })
      setSending(false)
      return
    }
    const payload = {
      recurrence_type: recurrence,
      time: `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`,
      repeat_count: Math.max(1, parseInt(scheduleForm.repeat_count, 10) || 1),
      template_id: templateId,
      items: builtItems,
    }
    if (recurrence === 'week') {
      payload.day_of_week = scheduleForm.day_of_week
    } else {
      payload.day_of_month = Math.min(31, Math.max(1, parseInt(scheduleForm.day_of_month, 10) || 1))
    }
    api
      .post('/send/schedule', payload)
      .then(() => {
        setSendMessage({ type: 'success', text: '计划已创建，到点将使用表格中的预生成内容自动发送。', fromMode: 'schedule' })
        setGeneratedContent((prev) => {
          const next = { ...prev }
          builtItems.forEach((it) => { delete next[contentKey(it.customer_id)] })
          return next
        })
        return fetchSchedules()
      })
      .then(() => {
        document.getElementById('schedule-list-heading')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
      .catch((err) => setSendMessage({ type: 'error', text: err.response?.data?.detail || err.message || '创建失败', fromMode: 'schedule' }))
      .finally(() => setSending(false))
  }

  const handleCancelSchedule = (s) => {
    if (s.status !== 'active') return
    const msg = isAdmin && s.sales_name ? `确定要取消销售「${s.sales_name}」的该计划吗？` : '确定要取消该计划吗？取消后将不再执行。'
    if (!window.confirm(msg)) return
    setSending(true)
    api
      .patch(`/send/schedules/${s.id}`)
      .then(() => { setSendMessage({ type: 'success', text: '已取消计划', fromMode: 'schedule' }); fetchSchedules() })
      .catch((err) => setSendMessage({ type: 'error', text: err.response?.data?.detail || err.message || '取消失败', fromMode: 'schedule' }))
      .finally(() => setSending(false))
  }

  return (
    <div>
      <h1 className="page-title">发送邮件</h1>
      <p className="page-desc">
        选择模版后，在下方表格中为每位客户生成邮件内容，再点击「开始群发」或「循环发送」时，将直接发送表格中的AI生成邮件内容。
      </p>

      <section className="section admin-block">
        <h2 className="section-title">邮件模版</h2>
        <label className="form-group" style={{ marginTop: 8 }}>
          <span className="form-label">选择模版</span>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="select input-width-md"
            disabled={loading}
          >
            <option value="">请选择模版</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {error && <p className="text-error mt-2">{error}</p>}

        <div style={{ marginTop: 16 }}>
          <h3 className="section-title-sm">模版文字</h3>
          <div style={{ marginTop: 8 }}>
            {loading ? '加载中…' : displayContent || '（请在上方选择一条模版）'}
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <h3 className="section-title-sm">模版图片</h3>
          {loading ? (
            <p className="text-muted">加载中…</p>
          ) : selectedImages.length === 0 ? (
            <p className="text-muted text-sm">该模版未配置图片。</p>
          ) : (
            <div className="flex flex-wrap gap-2 mt-2">
              {selectedImages.map((img) => (
                <div key={img.id} className="card" style={{ width: 200, padding: 0, overflow: 'hidden' }}>
                  <img
                    src={img.url}
                    alt={img.name}
                    style={{ display: 'block', width: '100%', height: 'auto' }}
                    onError={(e) => {
                      e.target.style.background = '#f0f0f0'
                      e.target.alt = img.name
                    }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="section admin-block">
        <h3 className="section-title">邮件生成表格</h3>
        {customerSummary.status === 'error' && (
          <p className="text-error text-sm mt-2 mb-2">{customerSummary.message}</p>
        )}
        {customerSummary.status === 'loading' && (
          <p className="text-muted text-sm mt-2 mb-2">正在同步客户数量…</p>
        )}
        {customerIdsLoadError && (
          <p className="text-error text-sm mt-2 mb-2">{customerIdsLoadError}</p>
        )}
        {!hasNoCustomersConfirmed && selectedId && (
          <p className="text-primary text-sm mt-2 mb-4">
            发送内容将使用当前上方已选模版：
            <strong>{selectedTemplate?.name || '（未选模版）'}</strong>
            。
          </p>
        )}
        {hasNoCustomersConfirmed ? (
          <p className="text-muted text-sm">
            当前客户列表为空。请先在「客户管理」添加客户。
          </p>
        ) : !selectedId ? (
          <p className="text-muted text-sm">请在上方选择一套邮件模版。</p>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4 flex-wrap">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleGenerateAll}
                disabled={
                  loading ||
                  generatingIds.size > 0 ||
                  hasNoCustomersConfirmed ||
                  customerSummary.status === 'loading'
                }
              >
                生成邮件内容
              </button>
              <span className="text-muted text-sm">
                已生成 {builtItems.length} 条，共 {customerList.total} 条客户（本页表格）
              </span>
            </div>
            {error && <p className="text-error mb-2">{error}</p>}
            <div className="table-wrap" style={{ maxHeight: 520, overflow: 'auto' }}>
              <table className="table" style={{ minWidth: 980, tableLayout: 'fixed' }}>
                <thead style={{ position: 'sticky', top: 0, zIndex: 1, background: 'var(--color-bg)' }}>
                  <tr>
                    <th style={{ width: '7%' }}>客户</th>
                    <th style={{ width: '12%' }}>邮箱</th>
                    <th style={{ width: '7%' }}>地区</th>
                    <th style={{ width: '9%' }}>公司特点</th>
                    <th style={{ width: '9%' }}>邮件模版</th>
                    <th style={{ width: '46%' }}>AI生成邮件内容</th>
                    <th style={{ width: '10%' }} className="text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {customerList.items.map((row) => {
                    const gc = generatedContent[contentKey(row.id)]
                    const isGenerating = generatingIds.has(row.id)
                    return (
                      <tr key={row.id}>
                        <td className="cell-ellipsis">{row.customer_name || '—'}</td>
                        <td className="cell-ellipsis" title={row.email || undefined}>{row.email || '—'}</td>
                        <td className="cell-ellipsis">{row.region || '—'}</td>
                        <td className="cell-ellipsis">{row.company_traits || '—'}</td>
                        <td className="cell-ellipsis">{selectedTemplate?.name || '—'}</td>
                        <td style={{ verticalAlign: 'top', paddingTop: 10, paddingBottom: 10, minHeight: 64 }}>
                          {isGenerating ? (
                            <span>生成中…</span>
                          ) : !gc?.content ? (
                            <span className="text-muted">（未生成）</span>
                          ) : (
                            <HoverFullText fullText={gc.content} style={{ cursor: 'default' }}>
                              <div
                                className="preview-content-3lines"
                                style={{ lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                              >
                                {gc.content}
                              </div>
                            </HoverFullText>
                          )}
                        </td>
                        <td className="text-right" style={{ verticalAlign: 'middle' }}>
                          <button
                            type="button"
                            className="btn"
                            style={{ padding: '2px 8px', fontSize: 12 }}
                            onClick={() => handleRegenerate(row.id)}
                            disabled={isGenerating}
                          >
                            {isGenerating ? '…' : '重新生成'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-3 mt-4">
              <span className="text-muted text-sm">
                第 {customerList.page} / {Math.max(1, Math.ceil(customerList.total / PAGE_SIZE))} 页，共 {customerList.total} 条
              </span>
              <button type="button" className="btn" onClick={() => fetchCustomers(customerList.page - 1)} disabled={customerList.page <= 1}>
                上一页
              </button>
              <button type="button" className="btn" onClick={() => fetchCustomers(customerList.page + 1)} disabled={customerList.page >= Math.ceil(customerList.total / PAGE_SIZE)}>
                下一页
              </button>
            </div>
          </>
        )}
      </section>

      <section className="section admin-block">
        <h3 className="section-title">发送设置</h3>
        {hasNoCustomersConfirmed ? (
          <p className="text-error text-sm mt-2">
            请先在「客户管理」上传或添加客户列表，才能选择开始群发。
          </p>
        ) : (
          <p className="text-muted text-sm mt-2">
            发送对象是当前客户列表的{' '}
            <strong>
              {customerSummary.status === 'ok'
                ? customerSummary.count
                : customerList.total > 0
                  ? `${customerList.total}（列表已加载，客户总数摘要不可用）`
                  : '—'}
            </strong>{' '}
            位客户。
            {customerSummary.status === 'error' && customerList.total > 0 && (
              <span className="text-muted"> 摘要接口失败时以列表为准，完整校验依赖客户同步。</span>
            )}
          </p>
        )}
        <div className="send-mode-radios mb-4" role="radiogroup" aria-label="发送方式">
          <label className="send-mode-radio">
            <input
              type="radio"
              name="sendMode"
              value="batch"
              checked={sendMode === 'batch'}
              onChange={() => setSendMode('batch')}
            />
            <span className="send-mode-radio-ui" aria-hidden />
            <span className="send-mode-radio-text">开始群发（立刻发）</span>
          </label>
          <label className="send-mode-radio">
            <input
              type="radio"
              name="sendMode"
              value="schedule"
              checked={sendMode === 'schedule'}
              onChange={() => setSendMode('schedule')}
            />
            <span className="send-mode-radio-ui" aria-hidden />
            <span className="send-mode-radio-text">循环发送（定时发）</span>
          </label>
        </div>
        {sendMode === 'batch' && (
          <div>
            <div className="flex items-center gap-3 mt-3 flex-wrap">
              <span className="text-muted text-sm">
                队列状态：全局排队 <strong>{queueStatus?.queued_global ?? 0}</strong> 封，
                我的排队 <strong>{queueStatus?.queued_mine ?? 0}</strong> 封，
                预计等待 <strong>{queueStatus?.eta_minutes ?? 0}</strong> 分钟
              </span>
              <button
                type="button"
                className="btn"
                onClick={fetchQueueStatus}
                disabled={queueStatusLoading}
              >
                {queueStatusLoading ? '刷新中…' : '刷新'}
              </button>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleStartBatch}
              disabled={sending || !selectedId || !builtItems.length}
            >
              {sending ? '提交中…' : '点击开始群发'}
            </button>
           
          </div>
        )}
        {sendMode === 'schedule' && (
          <div className="mt-4">
            <p className="text-muted text-sm mb-2">
              创建按周或按月的计划，到点自动将客户加入队列并按每 30 秒 发送 1 封的频率发送。时间均为北京时间。
            </p>
            <div className="flex flex-wrap gap-3 items-center mb-4">
              <label className="form-label" style={{ marginBottom: 0 }}>
                重复
                <select
                  value={scheduleForm.recurrence_type}
                  onChange={(e) => setScheduleForm((f) => ({ ...f, recurrence_type: e.target.value }))}
                  className="select input-sm"
                  style={{ marginLeft: 6 }}
                >
                  <option value="week">按周</option>
                  <option value="month">按月</option>
                </select>
              </label>
              {scheduleForm.recurrence_type === 'week' && (
                <label className="form-label" style={{ marginBottom: 0 }}>
                  星期
                  <select
                    value={scheduleForm.day_of_week}
                    onChange={(e) => setScheduleForm((f) => ({ ...f, day_of_week: parseInt(e.target.value, 10) }))}
                    className="select input-sm"
                    style={{ marginLeft: 6 }}
                  >
                    {WEEKDAY_LABELS.map((l, i) => (
                      <option key={i} value={i}>{l}</option>
                    ))}
                  </select>
                </label>
              )}
              {scheduleForm.recurrence_type === 'month' && (
                <label className="form-label" style={{ marginBottom: 0 }}>
                  每月几号
                  <input
                    type="number"
                    min={1}
                    max={31}
                    value={scheduleForm.day_of_month}
                    onChange={(e) => setScheduleForm((f) => ({ ...f, day_of_month: e.target.value }))}
                    className="input input-sm input-width-xs"
                    style={{ marginLeft: 6 }}
                  />
                </label>
              )}
              <label className="form-label" style={{ marginBottom: 0 }}>
                时间（HH:MM）
                <input
                  type="text"
                  value={scheduleForm.time}
                  onChange={(e) => setScheduleForm((f) => ({ ...f, time: e.target.value }))}
                  placeholder="09:00"
                  className="input input-sm"
                  style={{ marginLeft: 6, width: 72 }}
                />
              </label>
              <label className="form-label" style={{ marginBottom: 0 }}>
                循环次数
                <input
                  type="number"
                  min={1}
                  value={scheduleForm.repeat_count}
                  onChange={(e) => setScheduleForm((f) => ({ ...f, repeat_count: e.target.value }))}
                  className="input input-sm input-width-xs"
                  style={{ marginLeft: 6 }}
                />
              </label>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleCreateSchedule}
                disabled={sending || scheduleLoading || !selectedId || !builtItems.length}
              >
                {sending ? '提交中…' : '点击创建计划'}
              </button>
            </div>
            <h4 className="section-title-sm" id="schedule-list-heading">计划列表</h4>
            {scheduleLoading ? (
              <p className="text-muted">加载中…</p>
            ) : schedules.length === 0 ? (
              <p className="text-muted">暂无发送计划，请在上方创建。</p>
            ) : (
              <div className="table-wrap">
                <table className="table" style={{ minWidth: 560 }}>
                  <thead>
                    <tr>
                      <th>周期</th>
                      <th>进度</th>
                      <th>状态</th>
                      <th>模版</th>
                      <th>创建时间</th>
                      {isAdmin && <th>销售</th>}
                      <th className="text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedules.map((s) => {
                      const cycleText = (s.recurrence_type || 'week') === 'month'
                        ? `每月${s.day_of_month ?? 1}号 ${s.time}`
                        : `每周${WEEKDAY_LABELS[s.day_of_week ?? 0]} ${s.time}`
                      const tplName = s.template_id ? (s.template_name || templates.find((t) => t.id === s.template_id)?.name || `#${s.template_id}`) : '默认'
                      const imgCount = Array.isArray(templates.find((t) => t.id === s.template_id)?.image_ids)
                        ? (templates.find((t) => t.id === s.template_id)?.image_ids?.length ?? 0)
                        : 0
                      const contentText = imgCount > 0 ? `${tplName}` : tplName
                      const badgeClass = s.status === 'active' ? 'badge-active' : s.status === 'sending' ? 'badge-active' : s.status === 'completed' ? 'badge-completed' : s.status === 'failed' ? 'badge-cancelled' : s.status === 'template_disabled' ? 'badge-cancelled' : 'badge-cancelled'
                      return (
                      <tr key={s.id}>
                        <td>{cycleText}</td>
                        <td>已执行 {s.current_count} / {s.repeat_count} 次</td>
                        <td>
                          <span className={`badge ${badgeClass}`}>
                            {STATUS_LABELS[s.status] || s.status}
                          </span>
                        </td>
                        <td>{contentText}</td>
                        <td className="text-muted">
                          {s.created_at ? (() => {
                          const raw = s.created_at
                          const hasTz = /Z|[+-]\d{2}:?\d{2}$/.test(raw)
                          const d = new Date(hasTz ? raw : raw + 'Z')
                          return d.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Shanghai' })
                        })() : '—'}
                        </td>
                        {isAdmin && <td>{s.sales_name || '—'}</td>}
                        <td className="text-right">
                          {(s.status === 'active' || s.status === 'sending' || s.status === 'failed') && (
                            <button type="button" className="btn btn-danger" onClick={() => handleCancelSchedule(s)} disabled={sending}>
                              取消
                            </button>
                          )}
                        </td>
                      </tr>
                    )})}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {sendMessage.text && sendMessage.fromMode === sendMode && (
          <p className={sendMessage.type === 'error' ? 'text-error mt-4' : 'text-success mt-4'}>
            {sendMessage.text}
          </p>
        )}
      </section>
    </div>
  )
}
