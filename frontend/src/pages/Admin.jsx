import { useState, useEffect } from 'react'
import { api } from '../api/client'

export default function Admin() {
  return (
    <div>
      <h1 className="page-title">管理员配置</h1>
      <p className="page-desc">
        维护销售邮箱、邮件模版等。
      </p>
      <AdminSalesUsers />
      <AdminTemplates />
    </div>
  )
}

function AdminSalesUsers() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ sign_name: '', email: '', password: '', contact_phone: '' })

  const fetchData = () => {
    setLoading(true)
    setMessage('')
    api.get('/admin/sales')
      .then((r) => setRows(r.data || []))
      .catch(() => {
        setRows([])
        setMessage('加载失败')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
  }, [])

  const resetForm = () => {
    setEditing(null)
    setForm({ sign_name: '', email: '', password: '', contact_phone: '' })
  }

  const handleEdit = (row) => {
    setEditing(row)
    setForm({
      sign_name: row.sign_name || '',
      email: row.email || '',
      password: '',
      contact_phone: row.contact_phone || '',
    })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    setMessage('')
    const email = form.email.trim()
    const password = form.password.trim()
    const signName = form.sign_name.trim()

    if (signName.length > 30) {
      setMessage('用户姓名最多 30 个字符')
      return
    }
    if (!email) {
      setMessage('请填写邮箱')
      return
    }
    if (editing) {
      const body = {
        email,
        sign_name: signName || null,
        contact_phone: form.contact_phone.trim() || null,
      }
      if (password) body.password = password
      api.put(`/admin/sales/${editing.id}`, body)
        .then(() => { resetForm(); fetchData() })
        .catch((err) => {
          const d = err.response?.data?.detail
          setMessage(typeof d === 'string' ? d : d?.message || '保存失败')
        })
    } else {
      if (!password) {
        setMessage('新建时请填写密码')
        return
      }
      api.post('/admin/sales', {
        email,
        password,
        sign_name: signName || null,
        contact_phone: form.contact_phone.trim() || null,
      })
        .then(() => { resetForm(); fetchData() })
        .catch((err) => {
          const d = err.response?.data?.detail
          setMessage(typeof d === 'string' ? d : d?.message || '新建失败')
        })
    }
  }

  const handleDelete = (row) => {
    if (!window.confirm(`确定删除销售【${row.sign_name || row.email}】？删除后该账号将无法登录。`)) return
    setMessage('')
    api.delete(`/admin/sales/${row.id}`)
      .then(() => fetchData())
      .catch((err) => {
        const d = err.response?.data?.detail
        setMessage(typeof d === 'string' ? d : d?.message || '删除失败')
      })
  }

  return (
    <section className="section admin-block">
      <h2 className="section-title">销售用户管理</h2>
      <p className="text-muted text-sm mb-4">
        邮箱为登录账号，同时也是发件时被 CC 的地址。用户姓名为邮件落款首行（空则显示「湃乐多航运科技」）；第二行为 T:联系方式。
      </p>

      <form onSubmit={handleSubmit} className="mb-4" style={{ maxWidth: 600 }}>
        <div className="form-group">
          <label className="form-label">用户（落款姓名）</label>
          <input
            type="text"
            className="input input-width-md"
            value={form.sign_name}
            onChange={(e) => setForm((f) => ({ ...f, sign_name: e.target.value.slice(0, 30) }))}
            placeholder="选填，最多 30 字；空则落款显示「湃乐多航运科技」"
            maxLength={30}
          />
        </div>
        <div className="form-group">
          <label className="form-label">邮箱</label>
          <input
            type="email"
            className="input input-width-md"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            placeholder="name@pltplt.com"
            required
          />
        </div>
        <div className="form-group">
          <label className="form-label">联系方式（电话）</label>
          <input
            type="text"
            className="input input-width-md"
            value={form.contact_phone}
            onChange={(e) => setForm((f) => ({ ...f, contact_phone: e.target.value }))}
            placeholder="选填，落款第二行 T:…"
            maxLength={64}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{editing ? '新密码（不填则保持不变）' : '密码'}</label>
          <input
            type="text"
            className="input input-width-md"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            placeholder={editing ? '留空则不修改' : '至少 8 位，含大小写字母和数字'}
            required={!editing}
            minLength={editing ? undefined : 8}
          />
        </div>
        <button type="submit" className="btn btn-primary">{editing ? '保存' : '新增销售'}</button>
        {editing && (
          <button type="button" className="btn" onClick={resetForm}>取消</button>
        )}
      </form>

      {message && <p className="text-error mb-2">{message}</p>}

      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : rows.length === 0 ? (
        <p className="text-muted">当前暂无销售用户，请在上方新增。</p>
      ) : (
        <div className="table-wrap" style={{ maxWidth: 960 }}>
          <table className="table">
            <thead>
              <tr>
                <th>用户</th>
                <th>邮箱</th>
                <th>联系方式</th>
                <th>密码</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.sign_name || '—'}</td>
                  <td>{row.email || '—'}</td>
                  <td>{row.contact_phone || '—'}</td>
                  <td>{row.password || '—'}</td>
                  <td className="text-right">
                    <button type="button" className="btn" onClick={() => handleEdit(row)} style={{ marginRight: 8 }}>编辑</button>
                    <button type="button" className="btn btn-danger" onClick={() => handleDelete(row)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function AdminTemplates() {
  const [list, setList] = useState([])
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [imageError, setImageError] = useState('')
  const [showImages, setShowImages] = useState(false) // 默认不展示图片区块；编辑或上传后展示
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', content: '', fixed_text: '', image_ids: [] })
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const fetchList = () => {
    setLoading(true)
    Promise.all([
      api.get('/admin/templates').then((r) => r.data || []),
      api.get('/admin/images').then((r) => r.data || []),
    ])
      .then(([tpls, imgs]) => {
        setList(tpls || [])
        setImages(imgs || [])
      })
      .catch(() => {
        setList([])
        setImages([])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchList()
  }, [])

  useEffect(() => {
    setPage(1)
  }, [list.length])

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    const name = form.name.trim()
    if (!name) {
      setError('请先填写模版名称')
      return
    }
    const body = {
      name,
      content: form.content.trim(),
      fixed_text: form.fixed_text.trim(),
      image_ids: Array.isArray(form.image_ids) && form.image_ids.length ? form.image_ids : null,
    }
    if (editing) {
      api
        .put(`/admin/templates/${editing.id}`, body)
        .then(() => { setEditing(null); setShowImages(false); setForm({ name: '', content: '', fixed_text: '', image_ids: [] }); fetchList(); })
        .catch((err) => {
          const d = err.response?.data?.detail
          setError(typeof d === 'string' ? d : d?.message || err.message || '保存失败')
        })
    } else {
      api
        .post('/admin/templates', body)
        .then(() => { setShowImages(false); setForm({ name: '', content: '', fixed_text: '', image_ids: [] }); fetchList(); })
        .catch((err) => {
          const d = err.response?.data?.detail
          setError(typeof d === 'string' ? d : d?.message || err.message || '新增失败')
        })
    }
  }

  const handleEdit = (t) => {
    setEditing(t)
    setShowImages(true)
    setForm({
      name: t.name,
      content: t.content,
      fixed_text: t.fixed_text || '',
      image_ids: Array.isArray(t.image_ids) ? t.image_ids : [],
    })
  }

  const handleDelete = (id) => {
    if (!window.confirm('确定删除该模版？')) return
    setError('')
    api
      .delete(`/admin/templates/${id}`)
      .then(() => fetchList())
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '删除失败')
      })
  }

  const STATUS_LABELS = { pending: '待发布', enabled: '有效', disabled: '已禁用' }
  const handlePublish = (t) => {
    setError('')
    api
      .patch(`/admin/templates/${t.id}/publish`)
      .then(() => fetchList())
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '操作失败')
      })
  }
  const handleDisable = (t) => {
    if (!window.confirm('确定禁用该模版？禁用后销售端将无法使用，正在进行的发送计划将被取消。')) return
    setError('')
    api
      .patch(`/admin/templates/${t.id}/disable`)
      .then(() => fetchList())
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '操作失败')
      })
  }

  const handleCancel = () => {
    setEditing(null)
    setShowImages(false)
    setForm({ name: '', content: '', fixed_text: '', image_ids: [] })
    setError('')
  }

  const uploadImage = (pickedFile) => {
    setImageError('')
    if (!pickedFile) {
      setImageError('请先选择一张图片')
      return
    }
    const formData = new FormData()
    formData.append('file', pickedFile)
    setUploading(true)
    api
      .post('/admin/images', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => {
        const newId = r?.data?.id
        // 上传即视为选中，并展示图片区块（支持多张）
        if (typeof newId === 'number' && !Number.isNaN(newId)) {
          setForm((f) => {
            const prev = Array.isArray(f.image_ids) ? f.image_ids : []
            return { ...f, image_ids: prev.includes(newId) ? prev : [...prev, newId] }
          })
          setShowImages(true)
        }
        fetchList()
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setImageError(typeof d === 'string' ? d : d?.message || err.message || '上传失败')
      })
      .finally(() => setUploading(false))
  }

  const handlePickImage = (pickedFile) => {
    if (!pickedFile) return
    uploadImage(pickedFile)
  }

  const handleDropImage = (e) => {
    e.preventDefault()
    if (uploading) return
    const picked = e.dataTransfer?.files?.[0]
    handlePickImage(picked || null)
  }

  const handleDeleteImage = (id) => {
    if (!window.confirm('确定删除该图片物料？')) return
    setImageError('')
    api
      .delete(`/admin/images/${id}`)
      .then(() => {
        // 若该图已被当前编辑中的模版选中，同步移除
        setForm((f) => ({ ...f, image_ids: Array.isArray(f.image_ids) ? f.image_ids.filter((x) => x !== id) : [] }))
        fetchList()
      })
      .catch((err) => setImageError(err.response?.data?.detail || err.message || '删除失败'))
  }

  const total = list.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(Math.max(1, page), totalPages)
  const canPrev = safePage > 1
  const canNext = safePage < totalPages
  const pageStart = (safePage - 1) * pageSize
  const pageItems = list.slice(pageStart, pageStart + pageSize)

  return (
    <section className="section admin-block">
      <h2 className="section-title">邮件模版管理</h2>
      <p className="text-muted text-sm mb-4">
        每条记录是一套邮件模版：标题（唯一）+ 文字模版 + 固定文本 + 图片物料。管理员创建模版后需通过「发布」和「禁用」管理模版状态。
      </p>

      <form onSubmit={handleSubmit} className="mb-4">
        <div className="form-group">
          <label className="form-label">邮件标题（唯一）</label>
          <input
            type="text"
            className="input input-width-md"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="例如：湃乐多新产品上线"
          />
        </div>
        <div className="form-group">
          <label className="form-label">文字模版</label>
          <textarea
            className="textarea"
            value={form.content}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            placeholder="邮件文字模版（用于 AI 生成邮件内容）……"
            rows={4}
            style={{ maxWidth: 480 }}
          />
        </div>
        <div className="form-group">
          <label className="form-label">固定文本</label>
          <textarea
            className="textarea"
            value={form.fixed_text}
            onChange={(e) => setForm((f) => ({ ...f, fixed_text: e.target.value }))}
            placeholder="发信时在 AI 生成内容与内嵌图片之间……"
            rows={3}
            style={{ maxWidth: 480 }}
          />
        </div>
        <div className="form-group">
          <label className="form-label">图片物料（可多选，将内嵌到正文）</label>
          <label
            className="input-file-zone mb-0"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDropImage}
          >
            <input
              type="file"
              className="input-file-zone__input"
              accept=".jpg,.jpeg,.png,.gif,.webp"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0] || null
                e.target.value = ''
                handlePickImage(f)
              }}
            />
            <span className="input-file-zone__text">上传文件</span>
          </label>
          {uploading && <div className="text-muted text-sm mt-2">上传中…</div>}
          {imageError && <div className="text-error text-sm mt-2">{imageError}</div>}
          {showImages && (
            <>
              {loading ? (
                <p className="text-muted text-sm">加载图片列表中…</p>
              ) : (form.image_ids || []).length === 0 ? (
                <p className="text-muted text-sm">当前模版未选择图片。</p>
              ) : (
                <div className="flex flex-wrap gap-3" style={{ maxWidth: 720 }}>
                  {images.filter((img) => (form.image_ids || []).includes(img.id)).map((img) => {
                    const selected = true
                    return (
                      <div
                        key={img.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => {
                          setForm((f) => {
                            const prev = Array.isArray(f.image_ids) ? f.image_ids : []
                            const next = selected ? prev.filter((x) => x !== img.id) : [...prev, img.id]
                            return { ...f, image_ids: next }
                          })
                        }}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click() } }}
                        className="card"
                        style={{
                          width: 140,
                          padding: 0,
                          overflow: 'hidden',
                          cursor: 'pointer',
                          border: '2px solid var(--color-primary)',
                          background: 'var(--color-primary-light)',
                        }}
                      >
                        <img src={img.url} alt={img.name} style={{ display: 'block', width: '100%', height: 'auto' }} />
                        <div className="flex items-center gap-2 text-sm text-muted" style={{ padding: '4px 8px', justifyContent: 'space-between' }}>
                          <span className="cell-ellipsis" style={{ maxWidth: 90 }}>{img.name}</span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              className="btn btn-danger"
                              onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleDeleteImage(img.id) }}
                              style={{ padding: '2px 8px', fontSize: 12 }}
                            >
                              删除
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
        <button type="submit" className="btn btn-primary">{editing ? '保存' : '新增模版'}</button>
        {editing && (
          <button type="button" className="btn" onClick={handleCancel}>取消</button>
        )}
      </form>
      {error && <p className="text-error mt-2">{error}</p>}
      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : list.length === 0 ? (
        <p className="text-muted">暂无模版，请在上方新增。</p>
      ) : (
        <div className="table-wrap" style={{ maxWidth: 900 }}>
          <table className="table" style={{ minWidth: 880 }}>
            <thead>
              <tr>
                <th>标题</th>
                <th>内容摘要</th>
                <th>固定文本</th>
                <th>图片</th>
                <th>状态</th>
                <th style={{ width: 200, textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageItems.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="cell-ellipsis" style={{ maxWidth: 220 }} title={t.content || ''}>{t.content?.slice(0, 60)}{t.content && t.content.length > 60 ? '…' : ''}</td>
                  <td className="cell-ellipsis text-muted" style={{ maxWidth: 160 }} title={t.fixed_text || ''}>
                    {(t.fixed_text || '').trim() ? `${(t.fixed_text || '').trim().slice(0, 40)}${(t.fixed_text || '').trim().length > 40 ? '…' : ''}` : '—'}
                  </td>
                  <td className="text-muted">{Array.isArray(t.image_ids) ? `${t.image_ids.length} 张` : '0 张'}</td>
                  <td>
                    <span className={(t.status || 'pending') === 'enabled' ? 'text-success' : 'text-muted'}>
                      {STATUS_LABELS[t.status || 'pending'] || '待发布'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="flex items-center gap-2" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
                      <button
                        type="button"
                        className={(t.status || 'pending') === 'enabled' ? 'btn' : 'btn btn-primary'}
                        onClick={() => handlePublish(t)}
                        disabled={(t.status || 'pending') === 'enabled'}
                        style={{ padding: '4px 10px', fontSize: 12 }}
                        title={(t.status || 'pending') === 'enabled' ? '该模版已发布' : '发布后销售端可见'}
                      >
                        发布
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => handleDisable(t)}
                        disabled={(t.status || 'pending') !== 'enabled'}
                        style={{ padding: '4px 10px', fontSize: 12 }}
                        title={(t.status || 'pending') !== 'enabled' ? '仅对已发布的模版可禁用' : '禁用后销售端无法使用'}
                      >
                        禁用
                      </button>
                      <button type="button" className="btn" onClick={() => handleEdit(t)} style={{ padding: '4px 10px', fontSize: 12 }}>编辑</button>
                      <button type="button" className="btn btn-danger" onClick={() => handleDelete(t.id)} style={{ padding: '4px 10px', fontSize: 12 }}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-3 mt-4" style={{ padding: '8px 12px' }}>
            <span className="text-muted text-sm">
              第 {safePage} / {totalPages} 页，共 {total} 条
            </span>
            <div className="flex items-center gap-2" style={{ marginLeft: 'auto' }}>
              <button
                type="button"
                className="btn"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={!canPrev}
                style={{ padding: '4px 10px', fontSize: 12 }}
              >
                上一页
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={!canNext}
                style={{ padding: '4px 10px', fontSize: 12 }}
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
