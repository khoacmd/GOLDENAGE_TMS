import { Navigate, Route, Routes } from 'react-router'

import { AppLayout } from './layout/AppLayout'
import { CompaniesPage } from './pages/CompaniesPage'
import { HomePage } from './pages/HomePage'
import { ImportPage } from './pages/ImportPage'
import { LoginPage } from './pages/LoginPage'
import { CustomersPage } from './pages/master/CustomersPage'
import { InventoryPage } from './pages/master/InventoryPage'
import { ProductsPage } from './pages/master/ProductsPage'
import { VehiclesPage } from './pages/master/VehiclesPage'
import { WarehousesPage } from './pages/master/WarehousesPage'
import { OrdersPage } from './pages/OrdersPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { SettingsPage } from './pages/SettingsPage'
import { UsersPage } from './pages/UsersPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="plans" element={<PlaceholderPage title="Kế hoạch giao hàng" milestone="M2" />} />
        <Route path="warehouse" element={<PlaceholderPage title="Xuất kho" milestone="M2" />} />
        <Route path="master-data">
          <Route index element={<Navigate to="customers" replace />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="warehouses" element={<WarehousesPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
        </Route>
        <Route path="imports" element={<ImportPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="companies" element={<CompaniesPage />} />
      </Route>
    </Routes>
  )
}
