import { Route, Routes } from 'react-router'

import { AppLayout } from './layout/AppLayout'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="plans" element={<PlaceholderPage title="Kế hoạch giao hàng" milestone="M2" />} />
        <Route path="warehouse" element={<PlaceholderPage title="Xuất kho" milestone="M2" />} />
        <Route path="master-data" element={<PlaceholderPage title="Dữ liệu gốc" milestone="M1" />} />
        <Route path="users" element={<PlaceholderPage title="Người dùng" milestone="M1" />} />
        <Route path="companies" element={<PlaceholderPage title="Công ty" milestone="M1" />} />
      </Route>
    </Routes>
  )
}
