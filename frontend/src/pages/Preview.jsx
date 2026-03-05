import { useState, useEffect } from 'react'
import { api } from '../api/client'

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const STATUS_LABELS = { active: '进行中', completed: '已完成', cancelled: '已取消' }

export default function Preview() {
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [images, setImages] = useState([])
  const [contents, setContents] = useState([])
  const [selectedImageIds, setSelectedImageIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [sendMessage, setSendMessage] = useState({ type: '', text: '' })
  const [sendMode, setSendMode] = useState('test') // 'test' | 'batch' | 'schedule'
  const [schedules, setSchedules] = useState([])
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [scheduleForm, setScheduleForm] = useState({
    recurrence_type: 'week',
    day_of_week: 0,
    day_of_month: 1,
    time: '09:00',
    repeat_count: 1,
  })
  const [customerCount, setCustomerCount] = useState(0)
  const user = (() => {
    try {
      const j = localStorage.getItem('user')
      return j ? JSON.parse(j) : null
    } catch {
      return null
    }
  })()
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    Promise.all([
      api.get('/preview/templates').then((r) => r.data),
      api.get('/preview/images').then((r) => r.data),
      api.get('/customers/summary').then((r) => r.data).catch(() => ({ count: 0 })),
    ])
      .then(([tplList, imgList, summary]) => {
        setTemplates(tplList || [])
        setImages(imgList || [])
        setCustomerCount(summary?.count ?? 0)
        if ((tplList || []).length > 0 && !selectedId) setSelectedId(String((tplList || [])[0].id))
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '加载失败')
      })
      .finally(() => setLoading(false))
  }, [])

  const fetchSchedules = () => {
    setScheduleLoading(true)
    api.get('/send/schedules').then(({ data }) => setSchedules(data?.items || [])).catch(() => setSchedules([])).finally(() => setScheduleLoading(false))
  }
  useEffect(() => {
    if (sendMode === 'schedule') fetchSchedules()
  }, [sendMode])

  const selectedTemplate = templates.find((t) => String(t.id) === String(selectedId))
  const displayContent = selectedTemplate ? selectedTemplate.content : ''

  const selectedImages = images.filter((img) => selectedImageIds.includes(img.id))

  const handleToggleImage = (id) => {
    setSelectedImageIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const handleGeneratePreview = () => {
    setError('')
    setSendMessage({ type: '', text: '' })
    setGenerating(true)
    const templateId = selectedId ? parseInt(selectedId, 10) : null
    api
      .post('/preview', { template_id: templateId }, { timeout: 120000 })
      .then((r) => {
        setContents(r.data?.contents ?? [])
        if (r.data?.images?.length) setImages(r.data.images)
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '生成失败')
      })
      .finally(() => setGenerating(false))
  }

  const handleSendTest = () => {
    setSendMessage({ type: '', text: '' })
    if (!contents.length) {
      setSendMessage({ type: 'error', text: '请先点击「预览生成」，生成内容后再发送测试邮件。' })
      return
    }
    const first = contents[0]
    const subject = selectedTemplate?.name ? `测试：${selectedTemplate.name}` : '邮件预览测试'
    const content = (first?.content || displayContent || '').trim()
    const toEmail = first?.email
    if (!toEmail) {
      setSendMessage({ type: 'error', text: '未找到对应客户的邮箱，请检查客户列表。' })
      return
    }
    if (!content) {
      setSendMessage({ type: 'error', text: '暂无可发送的正文内容。' })
      return
    }
    setSending(true)
    api
      .post('/send/test', {
        to_email: toEmail,
        subject,
        content,
        image_ids: selectedImageIds.length ? selectedImageIds : null,
      })
      .then(() => {
        setSendMessage({ type: 'success', text: '已发送测试邮件至客户邮箱，并抄送给你的 CC 邮箱（限频：每位销售每分钟 1 封）。' })
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setSendMessage({ type: 'error', text: typeof d === 'string' ? d : d?.message || err.message || '发送失败' })
      })
      .finally(() => setSending(false))
  }

  const handleStartBatch = () => {
    setSendMessage({ type: '', text: '' })
    if (!window.confirm('确定开始群发吗？系统将按客户表依次发送，每分钟 1 封，直到全部发送完成。')) {
      return
    }
    const templateId = selectedId ? parseInt(selectedId, 10) : null
    setSending(true)
    api
      .post('/send/batch', {
        template_id: templateId,
        image_ids: selectedImageIds.length ? selectedImageIds : null,
      })
      .then(({ data }) => {
        const queued = data?.queued ?? 0
        const eta = data?.eta_minutes ?? queued
        setSendMessage({
          type: 'success',
          text: `已开始后台群发，目前队列中共有 ${queued} 封待发送邮件，预计约 ${eta} 分钟可全部发送完成。你可以在「邮件记录」查看进度。`,
        })
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setSendMessage({ type: 'error', text: typeof d === 'string' ? d : d?.message || err.message || '启动群发失败' })
      })
      .finally(() => setSending(false))
  }

  const handleCreateSchedule = () => {
    setSendMessage({ type: '', text: '' })
    const time = scheduleForm.time.trim()
    if (!/^\d{1,2}:\d{2}$/.test(time)) {
      setSendMessage({ type: 'error', text: '时间格式为 HH:MM（如 09:00）' })
      return
    }
    const [h, m] = time.split(':').map(Number)
    if (h < 0 || h > 23 || m < 0 || m > 59) {
      setSendMessage({ type: 'error', text: '请填写有效时间' })
      return
    }
    const recurrence = scheduleForm.recurrence_type || 'week'
    const payload = {
      recurrence_type: recurrence,
      time: `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`,
      repeat_count: Math.max(1, parseInt(scheduleForm.repeat_count, 10) || 1),
      template_id: selectedId ? parseInt(selectedId, 10) : null,
      image_ids: selectedImageIds.length ? selectedImageIds : null,
    }
    if (recurrence === 'week') {
      payload.day_of_week = scheduleForm.day_of_week
    } else {
      payload.day_of_month = Math.min(31, Math.max(1, parseInt(scheduleForm.day_of_month, 10) || 1))
    }
    setSending(true)
    api
      .post('/send/schedule', payload)
      .then(() => {
        setSendMessage({ type: 'success', text: '计划已创建，到点将使用当前所选模版与图片物料自动发送。' })
        fetchSchedules()
      })
      .catch((err) => setSendMessage({ type: 'error', text: err.response?.data?.detail || err.message || '创建失败' }))
      .finally(() => setSending(false))
  }

  const handleCancelSchedule = (s) => {
    if (s.status !== 'active') return
    const msg = isAdmin && s.sales_name ? `确定要取消销售「${s.sales_name}」的该计划吗？` : '确定要取消该计划吗？取消后将不再执行。'
    if (!window.confirm(msg)) return
    setSending(true)
    api
      .patch(`/send/schedules/${s.id}`)
      .then(() => { setSendMessage({ type: 'success', text: '已取消计划' }); fetchSchedules() })
      .catch((err) => setSendMessage({ type: 'error', text: err.response?.data?.detail || err.message || '取消失败' }))
      .finally(() => setSending(false))
  }

  return (
    <div>
      <h1 className="page-title">邮件预览</h1>
      <p className="page-desc">
        从模版列表选择一条话术，从图片列表选择一张或多张图片，发送时将使用所选模版和图片。
      </p>

      <section className="section admin-block">
        <h2 className="section-title">话术模版</h2>
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
          <h3 className="section-title-sm">所选话术</h3>
          <div className="card card-content">
            {loading ? '加载中…' : displayContent || '（请在上方选择一条模版）'}
          </div>
        </div>
      </section>

      <section className="section admin-block">
        <h4 className="section-title-sm">图片物料（可多选）</h4>
        {loading ? (
          <p className="text-muted">图片列表加载中…</p>
        ) : images.length === 0 ? (
          <p className="text-muted">暂无图片物料，请联系管理员在「管理员配置 - 图片物料」中上传。</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {images.map((img) => {
              const selected = selectedImageIds.includes(img.id)
              return (
                <div
                  key={img.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleToggleImage(img.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleToggleImage(img.id); } }}
                  className="card"
                  style={{
                    width: 160,
                    padding: 0,
                    overflow: 'hidden',
                    cursor: 'pointer',
                    border: selected ? '2px solid var(--color-primary)' : undefined,
                    background: selected ? 'var(--color-primary-light)' : undefined,
                  }}
                >
                  <img
                    src={img.url}
                    alt={img.name}
                    style={{ display: 'block', width: '100%', height: 'auto' }}
                    onError={(e) => {
                      e.target.style.background = '#f0f0f0'
                      e.target.alt = img.name
                    }}
                  />
                  <div className="flex items-center gap-2 text-sm text-muted" style={{ padding: '4px 8px', justifyContent: 'space-between' }}>
                    <span className="cell-ellipsis" style={{ maxWidth: 100 }}>{img.name}</span>
                    <span style={{ fontSize: 11, color: selected ? 'var(--color-primary)' : undefined }}>
                      {selected ? '已选' : '未选'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      <button
        type="button"
        className="btn btn-primary mt-2 mb-6"
        onClick={handleGeneratePreview}
        disabled={loading || generating}
      >
        {generating ? '生成中…' : '预览生成'}
      </button>

      {contents.length > 0 && (
        <section className="section admin-block">
          <h3 className="section-title">邮件预览（前 3 条客户）</h3>
          <div className="flex gap-4" style={{ flexDirection: 'column' }}>
            {contents.map((item, idx) => (
              <div key={idx} className="card">
                <div className="text-muted text-sm mb-2">
                  客户：{item.customer_name || '—'} 地区：{item.region || '—'} 公司特点：{item.company_traits || '—'}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{item.content || '—'}</div>
                {selectedImages.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-4">
                    {selectedImages.map((img) => (
                      <div key={img.id} className="card" style={{ width: 80, padding: 0, overflow: 'hidden' }}>
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
            ))}
          </div>
        </section>
      )}

      <section className="section admin-block">
        <h3 className="section-title">发送设置</h3>
        <p className="text-muted text-sm mb-4">
          选择发送方式：<strong>发送测试邮件</strong>（单封）、<strong>开始群发</strong>（立刻发）、<strong>循环发送</strong>（按计划定期发）。
        </p>
        <div className="flex gap-2 mb-4 flex-wrap">
          <button
            type="button"
            className="btn"
            onClick={() => setSendMode('test')}
            style={{
              border: sendMode === 'test' ? '2px solid var(--color-primary)' : undefined,
              background: sendMode === 'test' ? 'var(--color-primary-light)' : undefined,
            }}
          >
            发送测试邮件
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setSendMode('batch')}
            style={{
              border: sendMode === 'batch' ? '2px solid var(--color-primary)' : undefined,
              background: sendMode === 'batch' ? 'var(--color-primary-light)' : undefined,
            }}
          >
            开始群发（立刻发）
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setSendMode('schedule')}
            style={{
              border: sendMode === 'schedule' ? '2px solid var(--color-primary)' : undefined,
              background: sendMode === 'schedule' ? 'var(--color-primary-light)' : undefined,
            }}
          >
            循环发送（循环发）
          </button>
        </div>

        {sendMode === 'test' && (
          <div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSendTest}
              disabled={sending || loading || generating}
            >
              {sending ? '发送中…' : '发送测试邮件'}
            </button>
            <p className="text-primary text-sm mt-2">
              发送内容将使用当前上方已选模版与图片物料：
              <strong>
                {selectedTemplate?.name || '（未选模版）'}
                {selectedImageIds.length > 0 ? `，${selectedImageIds.length} 张图片` : ''}
              </strong>
              。
            </p>
            {customerCount > 0 && (
              <p className="text-muted text-sm mt-1">
                发送对象是当前客户列表的 <strong>{customerCount}</strong> 位客户。
              </p>
            )}
          </div>
        )}
        {sendMode === 'batch' && (
          <div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleStartBatch}
              disabled={sending || loading || generating}
            >
              {sending ? '提交中…' : '确定开始群发'}
            </button>
            <p className="text-primary text-sm mt-2">
              发送内容将使用当前上方已选模版与图片物料：
              <strong>
                {selectedTemplate?.name || '（未选模版）'}
                {selectedImageIds.length > 0 ? `，${selectedImageIds.length} 张图片` : ''}
              </strong>
              。
            </p>
            {customerCount > 0 && (
              <p className="text-muted text-sm mt-1">
                发送对象是当前客户列表的 <strong>{customerCount}</strong> 位客户。
              </p>
            )}
          </div>
        )}
        {sendMode === 'schedule' && (
          <div className="mt-4">
            <p className="text-muted text-sm mb-2">
              创建按周或按月的计划，到点自动将客户加入队列并按 1 封/分钟 发送。时间均为北京时间。
            </p>
            <p className="text-primary text-sm mb-3">
              发送内容将使用当前上方已选模版与图片物料：
              <strong>
                {selectedTemplate?.name || '（未选模版）'}
                {selectedImageIds.length > 0 ? `，${selectedImageIds.length} 张图片` : ''}
              </strong>
              。
            </p>
            {customerCount > 0 && (
              <p className="text-muted text-sm mb-3">
                发送对象是当前客户列表的 <strong>{customerCount}</strong> 位客户。
              </p>
            )}
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
                disabled={sending || scheduleLoading}
              >
                {sending ? '提交中…' : '创建计划'}
              </button>
            </div>
            <h4 className="section-title-sm">计划列表</h4>
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
                      <th>内容（模版+图片）</th>
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
                      const tplName = s.template_id ? (templates.find((t) => t.id === s.template_id)?.name || `#${s.template_id}`) : '默认'
                      const imgCount = Array.isArray(s.image_ids) ? s.image_ids.length : 0
                      const contentText = imgCount > 0 ? `${tplName} + ${imgCount} 张图片` : tplName
                      const badgeClass = s.status === 'active' ? 'badge-active' : s.status === 'completed' ? 'badge-completed' : 'badge-cancelled'
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
                          {s.created_at ? new Date(s.created_at).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                        </td>
                        {isAdmin && <td>{s.sales_name || '—'}</td>}
                        <td className="text-right">
                          {s.status === 'active' && (
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

        {sendMessage.text && (
          <p className={sendMessage.type === 'error' ? 'text-error mt-4' : 'text-success mt-4'}>
            {sendMessage.text}
          </p>
        )}
      </section>
    </div>
  )
}
