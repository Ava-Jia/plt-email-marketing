import { useState, useEffect } from 'react'
import { api } from '../api/client'

const PAGE_SIZE = 10

export default function Customers() {
  const formatLastUpdated = (value) => {
    if (!value) return ''
    if (typeof value === 'string') {
      const [datePart, timeWithZone] = value.split('T')
      if (!timeWithZone) return value
      // 去掉时区信息（Z 或 +08:00 等），仅保留 HH:MM:SS
      const timePart = timeWithZone.replace(/Z$/, '').split(/[+-]/)[0]
      return `${datePart} ${timePart}`
    }
    return String(value)
  }

  const [summary, setSummary] = useState({ count: 0, last_updated: null })
  const [list, setList] = useState({ items: [], total: 0, page: 1, page_size: PAGE_SIZE })
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })
  const [errors, setErrors] = useState([])

  const fetchSummary = () => {
    api.get('/customers/summary').then(({ data }) => {
      setSummary({ count: data.count, last_updated: data.last_updated })
    }).catch(() => {})
  }

  const fetchList = (page = 1) => {
    api.get('/customers', { params: { page, page_size: PAGE_SIZE } }).then(({ data }) => {
      setList({ items: data.items, total: data.total, page: data.page, page_size: data.page_size })
    }).catch(() => setList(prev => ({ ...prev, items: [] })))
  }

  useEffect(() => {
    fetchSummary()
    fetchList(1)
  }, [])

  const handleDownloadTemplate = () => {
    api.get('/customers/template', { responseType: 'blob' })
      .then((res) => {
        const url = window.URL.createObjectURL(new Blob([res.data]))
        const a = document.createElement('a')
        a.href = url
        a.setAttribute('download', 'customer_template.xlsx')
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      })
      .catch(() => setMessage({ type: 'error', text: '下载失败' }))
  }

  const buildCurrentFilename = () => {
    if (!summary.last_updated) return '当前客户.xlsx'
    const formatted = formatLastUpdated(summary.last_updated) // 例如 2026-03-03 10:00:00
    const safe = formatted.replace(/[:\s]/g, '_') // Windows 文件名不能包含 :
    return `当前客户_${safe}.xlsx`
  }

  const handleDownloadCurrent = () => {
    api
      .get('/customers/download-current', { responseType: 'blob' })
      .then((res) => {
        const url = window.URL.createObjectURL(new Blob([res.data]))
        const a = document.createElement('a')
        a.href = url
        a.setAttribute('download', buildCurrentFilename())
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      })
      .catch(() => setMessage({ type: 'error', text: '下载失败' }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) {
      setMessage({ type: 'error', text: '请选择文件' })
      return
    }
    setMessage({ type: '', text: '' })
    setErrors([])
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const { data } = await api.post('/customers/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setMessage({ type: 'success', text: `上传成功，共 ${data.count} 条客户` })
      setFile(null)
      if (e.target.reset) e.target.reset()
      fetchSummary()
      fetchList(1)
    } catch (err) {
      const d = err.response?.data?.detail
      if (d?.errors && Array.isArray(d.errors)) {
        setErrors(d.errors)
        setMessage({ type: 'error', text: d.message || '校验未通过' })
      } else {
        setMessage({ type: 'error', text: typeof d === 'string' ? d : d?.message || '上传失败' })
      }
    } finally {
      setUploading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(list.total / list.page_size))
  const canPrev = list.page > 1
  const canNext = list.page < totalPages

  return (
    <div>
      <h1 className="page-title">客户管理</h1>
      <p className="page-desc">
        上传 Excel 或 CSV 将<strong>全覆盖</strong>当前客户列表，请先下载模板填写后上传。
      </p>

      <section className="section">
        <h3 className="section-title">当前客户</h3>
        <p className="text-muted">
          共 <strong>{summary.count}</strong> 条
          {summary.last_updated && (
            <>，最近更新：{formatLastUpdated(summary.last_updated)}</>
          )}
        </p>
      </section>

      {summary.count > 0 && (
        <section className="section">
          <div className="table-wrap" style={{ maxHeight: 420, overflow: 'auto' }}>
            <table className="table" style={{ tableLayout: 'fixed' }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                <tr>
                  <th style={{ width: '20%' }}>客户姓名</th>
                  <th style={{ width: '15%' }}>区域</th>
                  <th style={{ width: '30%' }}>公司特点</th>
                  <th style={{ width: '35%' }}>客户邮箱</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((row) => (
                  <tr key={row.id}>
                    <td className="cell-ellipsis">{row.customer_name}</td>
                    <td className="cell-ellipsis">{row.region}</td>
                    <td className="cell-ellipsis">{row.company_traits}</td>
                    <td className="cell-ellipsis">{row.email}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3 mt-4">
            <span className="text-muted text-sm">
              第 {list.page} / {totalPages} 页，共 {list.total} 条
            </span>
            <button type="button" className="btn" onClick={() => fetchList(list.page - 1)} disabled={!canPrev}>
              上一页
            </button>
            <button type="button" className="btn" onClick={() => fetchList(list.page + 1)} disabled={!canNext}>
              下一页
            </button>
          </div>
        </section>
      )}

      <section className="section">
        <button type="button" className="btn" onClick={handleDownloadTemplate}>下载模板</button>
        <button type="button" className="btn" onClick={handleDownloadCurrent}>下载当前客户</button>
      </section>

      <section className="section">
        <h3 className="section-title">上传客户表</h3>
        <form onSubmit={handleSubmit} className="flex items-center gap-3 flex-wrap">
          <input
            type="file"
            className="input-file mb-0"
            accept=".csv,.xlsx,.xls"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <button type="submit" className="btn btn-primary" disabled={uploading}>
            {uploading ? '上传中…' : '上传并覆盖'}
          </button>
        </form>
        {message.text && (
          <p className={message.type === 'error' ? 'text-error mt-4' : 'text-success mt-4'}>
            {message.text}
          </p>
        )}
        {errors.length > 0 && (
          <ul className="text-error mt-4">
            {errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
