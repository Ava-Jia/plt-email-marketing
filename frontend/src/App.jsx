import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Customers from './pages/Customers'
import Preview from './pages/Preview'
import Records from './pages/Records'
import Admin from './pages/Admin'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/customers" replace />} />
        <Route path="customers" element={<Customers />} />
        <Route path="preview" element={<Preview />} />
        <Route path="records" element={<Records />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
