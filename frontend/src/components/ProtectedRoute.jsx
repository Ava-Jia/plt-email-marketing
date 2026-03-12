import { Navigate, useLocation } from 'react-router-dom'

/**
 * 未登录时跳转到 /login，并记录来源以便登录后返回。
 */
export default function ProtectedRoute({ children }) {
  const location = useLocation()
  const token = localStorage.getItem('token')

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}