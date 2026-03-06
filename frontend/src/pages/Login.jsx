import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api/client'

export default function Login() {
  const [isRegister, setIsRegister] = useState(false)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const from = location.state?.from?.pathname || '/'

  const authTimeout = 15000 // 15 秒，避免请求一直挂起

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/login', { login, password }, { timeout: authTimeout })
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      navigate(from, { replace: true })
    } catch (err) {
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('请求超时，请确认后端服务已启动（默认端口 8000）')
      } else {
        setError(err.response?.data?.detail || '登录失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/register', { login, password, email }, { timeout: authTimeout })
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      navigate(from, { replace: true })
    } catch (err) {
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('请求超时，请确认后端服务已启动（默认端口 8000）')
      } else {
        const detail = err.response?.data?.detail
        setError(Array.isArray(detail) ? detail.map((x) => x.msg).join('；') : detail || '注册失败')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <h1 className="page-title brand-title">湃乐多邮件营销系统</h1>
      <h2 className="section-title-sm" style={{ marginTop: 0, marginBottom: 24 }}>{isRegister ? '注册' : '登录'}</h2>
      {isRegister ? (
        <form onSubmit={handleRegister} className="login-form">
          <div className="form-group">
            <label className="form-label">账号</label>
            <input
              type="text"
              className="input"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              required
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label className="form-label">密码</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <p className="text-muted text-sm mt-1">至少 8 位，需包含大小写字母和数字</p>
          </div>
          <div className="form-group">
            <label className="form-label">邮箱（请填写，将作为您发件时的被 CC 邮箱）</label>
            <input
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="例如: name@pltplt.com"
              autoComplete="email"
            />
          </div>
          {error && <div className="text-error mb-4">{error}</div>}
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '注册中…' : '注册'}
          </button>
        </form>
      ) : (
        <form onSubmit={handleLogin} className="login-form">
          <div className="form-group">
            <label className="form-label">账号</label>
            <input
              type="text"
              className="input"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              required
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label className="form-label">密码</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          {error && <div className="text-error mb-4">{error}</div>}
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '登录中…' : '登录'}
          </button>
        </form>
      )}
      <p className="login-footer text-muted">
        {isRegister ? (
          <>
            已有账号？{' '}
            <button type="button" className="btn btn-ghost" onClick={() => { setIsRegister(false); setError(''); }}>
              去登录
            </button>
          </>
        ) : (
          <>
            没有账号？{' '}
            <button type="button" className="btn btn-ghost" onClick={() => { setIsRegister(true); setError(''); }}>
              注册
            </button>
            <br />
            默认管理员：admin / admin123
          </>
        )}
      </p>
    </div>
  )
}
