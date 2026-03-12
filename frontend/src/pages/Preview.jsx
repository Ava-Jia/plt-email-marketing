import { useState, useEffect } from 'react'
import { api } from '../api/client'

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const STATUS_LABELS = { active: '进行中', sending: '发送中', completed: '已完成', cancelled: '已取消' }

export default function Preview() {
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [images, setImages] = useState([])
  const [contents, setContents] = useState([])
  const [previewGeneratedOnce, setPreviewGeneratedOnce] = useState(false) // 是否已成功点击过预览生成（用于显示预览区块或空状态）
  const [selectedImageIds, setSelectedImageIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
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
  const [customerCount, setCustomerCount] = useState(0)
  const [emailSubject, setEmailSubject] = useState('') // 邮件主题（标题）
  const [queueStatus, setQueueStatus] = useState({ queued_global: 0, queued_mine: 0, rate_limit_seconds: 30, eta_minutes: 0 })
  const [queueStatusLoading, setQueueStatusLoading] = useState(false)
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
    setSendMessage({ type: '', text: '', fromMode: null })
    if (!emailSubject.trim()) {
      setError('请先填写邮件主题后再预览生成。')
      return
    }
    setGenerating(true)
    const templateId = selectedId ? parseInt(selectedId, 10) : null
    api
      .post('/preview', { template_id: templateId }, { timeout: 120000 })
      .then((r) => {
        setContents(r.data?.contents ?? [])
        if (r.data?.images?.length) setImages(r.data.images)
        setPreviewGeneratedOnce(true)
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '生成失败')
      })
      .finally(() => setGenerating(false))
  }

  const handleStartBatch = () => {
    setSendMessage({ type: '', text: '', fromMode: null })
    if (!emailSubject.trim()) {
      setSendMessage({ type: 'error', text: '请先填写邮件主题。', fromMode: 'batch' })
      return
    }
    if (!window.confirm('确定开始群发吗？系统将按客户表依次发送，每 30 秒 1 封，直到全部发送完成。')) {
      return
    }
    const templateId = selectedId ? parseInt(selectedId, 10) : null
    setSending(true)
    api
      .post('/send/batch', {
        template_id: templateId,
        image_ids: selectedImageIds.length ? selectedImageIds : null,
        subject: emailSubject.trim() || null,
      })
      .then(({ data }) => {
        setSendMessage({
          type: 'success',
          text: '已开始后台群发。你可以在「邮件记录」查看进度。',
          fromMode: 'batch',
        })
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setSendMessage({ type: 'error', text: typeof d === 'string' ? d : d?.message || err.message || '启动群发失败', fromMode: 'batch' })
      })
      .finally(() => setSending(false))
  }

  const handleCreateSchedule = () => {
    setSendMessage({ type: '', text: '', fromMode: null })
    if (!emailSubject.trim()) {
      setSendMessage({ type: 'error', text: '请先填写邮件主题。', fromMode: 'schedule' })
      return
    }
    const formTime = scheduleForm.time || '09:00'
    if (!/^\d{1,2}:\d{2}$/.test(formTime)) {
      setSendMessage({ type: 'error', text: '时间格式为 HH:MM（如 09:00）', fromMode: 'schedule' })
      return
    }
    const [h, m] = formTime.split(':').map(Number)
    if (h < 0 || h > 23 || m < 0 || m > 59) {
      setSendMessage({ type: 'error', text: '请填写有效时间', fromMode: 'schedule' })
      return
    }
    const recurrence = scheduleForm.recurrence_type || 'week'
    const payload = {
      recurrence_type: recurrence,
      time: `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`,
      repeat_count: Math.max(1, parseInt(scheduleForm.repeat_count, 10) || 1),
      template_id: selectedId ? parseInt(selectedId, 10) : null,
      image_ids: selectedImageIds.length ? selectedImageIds : null,
      subject: emailSubject.trim() || null,
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
        setSendMessage({ type: 'success', text: '计划已创建，到点将使用当前所选模版与图片物料自动发送。', fromMode: 'schedule' })
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
      <h1 className="page-title">邮件预览</h1>
      <p className="page-desc">
        从话术模版选择一条话术，从图片物料选择一张或多张图片，输入邮件主题，发送时将使用所选模版、图片物料和主题。
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
        <h4 className="section-title-sm">图片物料</h4>
        <p className="text-muted text-sm mb-2">选择图片物料（可多选），将作为附件用于预览展示及发送</p>
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

      <section className="section admin-block">
        <h4 className="section-title-sm">邮件主题（必填）</h4>
        <label className="form-group" style={{ display: 'block' }}>
          <span className="form-label">输入邮件主题（标题），将用于预览展示及发送</span>
          <input
            type="text"
            value={emailSubject}
            onChange={(e) => setEmailSubject(e.target.value)}
            placeholder="例如：湃乐多卡车产品介绍"
            className="input input-width-md"
            style={{ maxWidth: 400 }}
          />
        </label>
      </section>

      <button
        type="button"
        className="btn btn-primary mt-2 mb-6"
        onClick={handleGeneratePreview}
        disabled={loading || generating || !emailSubject.trim()}
      >
        {generating ? '生成中…' : '预览生成'}
      </button>

      {previewGeneratedOnce && (
        <section className="section admin-block">
          <h3 className="section-title">邮件预览（前 3 条客户）</h3>
          {contents.length === 0 ? (
            <p className="text-muted text-sm">
              当前客户列表为空，无法生成预览。请先在「客户管理」添加客户后再点击「预览生成」。
            </p>
          ) : (
            <div className="flex gap-4" style={{ flexDirection: 'column' }}>
              {contents.map((item, idx) => (
                <div key={idx} className="card">
                  <div className="text-muted text-sm mb-2">
                    客户：{item.customer_name || '—'} 地区：{item.region || '—'} 公司特点：{item.company_traits || '—'}
                  </div>
                  <p className="mb-2" style={{ fontSize: 14 }}>
                    <span style={{ color: 'var(--color-primary)', fontWeight: 500 }}>邮件主题：</span>
                    {' '}
                    {emailSubject.trim() || '—'}
                  </p>
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
          )}
        </section>
      )}

      <section className="section admin-block">
        <h3 className="section-title">发送设置</h3>
        <p className="text-muted text-sm mb-4">
          选择发送方式：<strong>开始群发</strong>（立刻发）、<strong>循环发送</strong>（按计划定期发）。
        </p>
        <div className="flex gap-2 mb-4 flex-wrap">
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
            循环发送（定时发）
          </button>
        </div>
        {sendMode === 'batch' && (
          <div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleStartBatch}
              disabled={sending || loading || generating || !emailSubject.trim()}
            >
              {sending ? '提交中…' : '确定开始群发'}
            </button>
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
            <p className="text-primary text-sm mt-2">
              发送内容将使用当前上方已选模版、图片物料和邮件主题：
              <strong>
                {selectedTemplate?.name || '（未选模版）'}
                {selectedImageIds.length > 0 ? `，${selectedImageIds.length} 张图片` : ''}
                ，"{emailSubject.trim() || '（请先填写上方邮件主题）'}"
              </strong>
              。
            </p>
            {customerCount > 0 ? (
              <p className="text-muted text-sm mt-1">
                发送对象是当前客户列表的 <strong>{customerCount}</strong> 位客户。
              </p>
            ) : (
              <p className="text-error text-sm mt-1">
                请先在「客户管理」上传或添加客户列表，才能选择开始群发。
              </p>
            )}
          </div>
        )}
        {sendMode === 'schedule' && (
          <div className="mt-4">
            <p className="text-muted text-sm mb-2">
              创建按周或按月的计划，到点自动将客户加入队列并按每 30 秒 发送 1 封的频率发送。时间均为北京时间。
            </p>
            <p className="text-primary text-sm mb-3">
              发送内容将使用当前上方已选模版、图片物料和邮件主题：
              <strong>
                {selectedTemplate?.name || '（未选模版）'}
                {selectedImageIds.length > 0 ? `，${selectedImageIds.length} 张图片` : ''}
                ，"{emailSubject.trim() || '（请先填写上方邮件主题）'}"
              </strong>
              。
            </p>
            {customerCount > 0 ? (
              <p className="text-muted text-sm mb-3">
                发送对象是当前客户列表的 <strong>{customerCount}</strong> 位客户。
              </p>
            ) : (
              <p className="text-error text-sm mb-3">
                请先在「客户管理」上传或添加客户列表，才能选择循环发送。
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
                disabled={sending || scheduleLoading || !emailSubject.trim()}
              >
                {sending ? '提交中…' : '创建计划'}
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
                      const badgeClass = s.status === 'active' ? 'badge-active' : s.status === 'sending' ? 'badge-active' : s.status === 'completed' ? 'badge-completed' : s.status === 'failed' ? 'badge-cancelled' : 'badge-cancelled'
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
