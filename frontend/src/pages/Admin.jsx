import { useState, useEffect } from 'react'
import { api } from '../api/client'

export default function Admin() {
  return (
    <div>
      <h1 className="page-title">管理员</h1>
      <p className="page-desc">
        维护销售邮箱、图片物料、话术模版等。
      </p>
      <AdminSalesEmails />
      <AdminTemplates />
      <AdminImages />
    </div>
  )
}

function AdminSalesEmails() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  const fetchData = () => {
    setLoading(true)
    setMessage('')
    Promise.all([
      api.get('/admin/sales-email/users').then((r) => r.data || []),
      api.get('/admin/sales-email').then((r) => r.data || []),
    ])
      .then(([users, mappings]) => {
        const list = users
          .filter((u) => u.role === 'sales')
          .map((u) => {
            const m = mappings.find((x) => x.sales_id === u.id)
            return {
              id: u.id,
              name: u.name,
              login: u.login,
              role: u.role,
              pltEmail: m?.plt_email || u.cc_email || '',
              mappingId: m?.id || null,
            }
          })
        setRows(list)
      })
      .catch(() => {
        setRows([])
        setMessage('加载失败')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
  }, [])

  const handleChangeEmail = (id, value) => {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, pltEmail: value } : r)),
    )
  }

  const handleSave = (row) => {
    const email = row.pltEmail.trim()
    if (!email) {
      setMessage('请先填写 plt 邮箱')
      return
    }
    setMessage('')
    const req = row.mappingId
      ? api.put(`/admin/sales-email/${row.mappingId}`, { plt_email: email })
      : api.post('/admin/sales-email', { sales_id: row.id, plt_email: email })
    req
      .then(() => {
        fetchData()
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setMessage(typeof d === 'string' ? d : d?.message || '保存失败')
      })
  }

  const handleClear = (row) => {
    if (!row.mappingId) return
    if (!window.confirm(`确定清除【${row.name}】的 plt 邮箱配置？`)) return
    api
      .delete(`/admin/sales-email/${row.mappingId}`)
      .then(() => fetchData())
      .catch((err) => {
        const d = err.response?.data?.detail
        setMessage(typeof d === 'string' ? d : d?.message || '清除失败')
      })
  }

  return (
    <section className="section admin-block">
      <h2 className="section-title">销售邮箱</h2>
      <p className="text-muted text-sm mb-4">
        有销售注册后会自动出现在下表中，可在此为每个销售配置或更新对应的 pltplt 发件CC邮箱。
      </p>
      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : rows.length === 0 ? (
        <p className="text-muted">当前暂无销售用户。</p>
      ) : (
        <div className="table-wrap" style={{ maxWidth: 800 }}>
          <table className="table">
            <thead>
              <tr>
                <th>销售姓名</th>
                <th>账号</th>
                <th>角色</th>
                <th>plt 邮箱</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>{row.login}</td>
                  <td>{row.role}</td>
                  <td>
                    <input
                      type="email"
                      className="input input-sm"
                      value={row.pltEmail}
                      onChange={(e) => handleChangeEmail(row.id, e.target.value)}
                      placeholder="name@pltplt.com"
                      style={{ maxWidth: 260 }}
                    />
                  </td>
                  <td className="text-right">
                    <button type="button" className="btn" onClick={() => handleSave(row)}>
                      {row.mappingId ? '保存' : '创建'}
                    </button>
                    {row.mappingId && (
                      <button type="button" className="btn" onClick={() => handleClear(row)}>
                        清除
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {message && <p className="text-error mt-2">{message}</p>}
    </section>
  )
}

function AdminImages() {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')

  const fetchList = () => {
    setLoading(true)
    api
      .get('/admin/images')
      .then((r) => setList(r.data || []))
      .catch(() => setList([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchList()
  }, [])

  const handleUpload = (e) => {
    e.preventDefault()
    setError('')
    if (!file) {
      setError('请先选择一张图片')
      return
    }
    const formData = new FormData()
    formData.append('file', file)
    setUploading(true)
    api
      .post('/admin/images', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(() => {
        setFile(null)
        if (e.target && e.target.reset) e.target.reset()
        fetchList()
      })
      .catch((err) => {
        const d = err.response?.data?.detail
        setError(typeof d === 'string' ? d : d?.message || err.message || '上传失败')
      })
      .finally(() => setUploading(false))
  }

  const handleDelete = (id) => {
    if (!window.confirm('确定删除该图片物料？')) return
    api.delete(`/admin/images/${id}`).then(() => fetchList())
  }

  return (
    <section className="section admin-block">
      <h2 className="section-title">图片物料</h2>
      <p className="text-muted text-sm mb-4">
        销售在「邮件预览」页可以选择使用哪些图片物料，此处由管理员统一上传与维护。
      </p>
      <form onSubmit={handleUpload} className="mb-4 flex items-center gap-2 flex-wrap">
        <input
          type="file"
          className="input-file"
          accept=".jpg,.jpeg,.png,.gif,.webp"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <button type="submit" className="btn btn-primary" disabled={uploading}>
          {uploading ? '上传中…' : '上传图片'}
        </button>
        {error && <span className="text-error">{error}</span>}
      </form>
      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : list.length === 0 ? (
        <p className="text-muted">暂无图片物料，请在上方上传。</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {list.map((img) => (
            <div key={img.id} className="card" style={{ width: 160, padding: 0, overflow: 'hidden' }}>
              <img src={img.url} alt={img.name} style={{ display: 'block', width: '100%', height: 'auto' }} />
              <div className="flex items-center gap-2 text-sm text-muted" style={{ padding: '4px 8px', justifyContent: 'space-between' }}>
                <span className="cell-ellipsis" style={{ maxWidth: 100 }}>{img.name}</span>
                <button type="button" className="btn btn-danger" onClick={() => handleDelete(img.id)} style={{ padding: '2px 8px', fontSize: 12 }}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function AdminTemplates() {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', content: '' })

  const fetchList = () => {
    api.get('/admin/templates').then((r) => setList(r.data || [])).catch(() => setList([])).finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchList()
  }, [])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    const body = { name: form.name.trim(), content: form.content.trim() }
    if (editing) {
      api.put(`/admin/templates/${editing.id}`, body).then(() => { setEditing(null); setForm({ name: '', content: '' }); fetchList(); })
    } else {
      api.post('/admin/templates', body).then(() => { setForm({ name: '', content: '' }); fetchList(); })
    }
  }

  const handleEdit = (t) => {
    setEditing(t)
    setForm({ name: t.name, content: t.content })
  }

  const handleDelete = (id) => {
    if (!window.confirm('确定删除该模版？')) return
    api.delete(`/admin/templates/${id}`).then(() => fetchList())
  }

  const handleCancel = () => {
    setEditing(null)
    setForm({ name: '', content: '' })
  }

  return (
    <section className="section admin-block">
      <h2 className="section-title">话术模版</h2>
      <p className="text-muted text-sm mb-4">销售在「邮件预览」页从下拉框选择模版，此处可增删改。</p>
      <form onSubmit={handleSubmit} className="mb-4">
        <div className="form-group">
          <label className="form-label">模版名称</label>
          <input
            type="text"
            className="input input-width-md"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="例如：促销邀约"
          />
        </div>
        <div className="form-group">
          <label className="form-label">话术内容</label>
          <textarea
            className="textarea"
            value={form.content}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            placeholder="邮件正文……"
            rows={4}
            style={{ maxWidth: 480 }}
          />
        </div>
        <button type="submit" className="btn btn-primary">{editing ? '保存' : '新增模版'}</button>
        {editing && (
          <button type="button" className="btn" onClick={handleCancel}>取消</button>
        )}
      </form>
      {loading ? (
        <p className="text-muted">加载中…</p>
      ) : list.length === 0 ? (
        <p className="text-muted">暂无模版，请在上方新增。</p>
      ) : (
        <div className="table-wrap" style={{ maxWidth: 640 }}>
          <table className="table">
            <thead>
              <tr>
                <th>名称</th>
                <th>内容摘要</th>
                <th className="text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {list.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="cell-ellipsis" style={{ maxWidth: 320 }}>{t.content?.slice(0, 60)}…</td>
                  <td className="text-right">
                    <button type="button" className="btn" onClick={() => handleEdit(t)}>编辑</button>
                    <button type="button" className="btn btn-danger" onClick={() => handleDelete(t.id)}>删除</button>
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
