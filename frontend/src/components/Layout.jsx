import { Outlet, NavLink, useNavigate } from 'react-router-dom'

export default function Layout() {
  const navigate = useNavigate()
  const userJson = localStorage.getItem('user')
  const user = userJson ? JSON.parse(userJson) : null

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        <h3 className="app-sidebar-title">湃乐多邮件营销系统</h3>
        {user && <p className="app-sidebar-user">当前用户：{user.name} ({user.role})</p>}
        <nav className="app-nav">
          <NavLink to="/customers" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>客户管理</NavLink>
          <NavLink to="/preview" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>邮件预览</NavLink>
          <NavLink to="/records" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>邮件记录</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>管理员配置</NavLink>}
        </nav>
        <div className="sidebar-actions">
          <button type="button" className="btn" onClick={handleLogout}>退出登录</button>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
