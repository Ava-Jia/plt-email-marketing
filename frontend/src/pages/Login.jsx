import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api/client'

export default function Login() {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
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

  return (
    <div className="login-page">
      <h1 className="page-title brand-title">湃乐多邮件营销系统</h1>
      <h2 className="section-title-sm" style={{ marginTop: 0, marginBottom: 24 }}>登录</h2>
      <form onSubmit={handleLogin} className="login-form">
        <div className="form-group">
          <label className="form-label">用户/邮箱</label>
          <input
            type="text"
            className="input"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            required
            placeholder="name@pltplt.com"
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
            placeholder="至少 8 位，含大小写字母和数字"
            autoComplete="current-password"
          />
        </div>
        {error && <div className="text-error mb-4">{error}</div>}
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? '登录中…' : '登录'}
        </button>
      </form>
    </div>
  )
}
