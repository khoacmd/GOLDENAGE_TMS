import { Navigate, Route, Routes } from 'react-router'

import { AppLayout } from './layout/AppLayout'
import { CompaniesPage } from './pages/CompaniesPage'
import { DmsMasterPage } from './pages/conversions/DmsMasterPage'
import { DmsOrdersPage } from './pages/conversions/DmsOrdersPage'
import { DevicesPage } from './pages/DevicesPage'
import { HomePage } from './pages/HomePage'
import { ImportPage } from './pages/ImportPage'
import { LoginPage } from './pages/LoginPage'
import { CustomersPage } from './pages/master/CustomersPage'
import { InventoryPage } from './pages/master/InventoryPage'
import { ProductsPage } from './pages/master/ProductsPage'
import { RiverBridgesPage } from './pages/master/RiverBridgesPage'
import { VehiclesPage } from './pages/master/VehiclesPage'
import { WarehousesPage } from './pages/master/WarehousesPage'
import { OrdersPage } from './pages/OrdersPage'
import { PlanningRunPage } from './pages/plans/PlanningRunPage'
import { PlansPage } from './pages/plans/PlansPage'
import { DeliveryNotesPrint, PickingListPrint } from './pages/plans/PrintPages'
import { TripDetailPage } from './pages/plans/TripDetailPage'
import { TripEditor } from './pages/plans/TripEditor'
import { WarehousePage } from './pages/WarehousePage'
import { ReportsPage } from './pages/ReportsPage'
import { SettingsPage } from './pages/SettingsPage'
import { UsersPage } from './pages/UsersPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/print/trips/:tripId/picking" element={<PickingListPrint />} />
      <Route path="/print/trips/:tripId/delivery" element={<DeliveryNotesPrint />} />
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="plans" element={<PlansPage />} />
        <Route path="plans/runs/:runId" element={<PlanningRunPage />} />
        <Route path="trips/new" element={<TripEditor />} />
        <Route path="trips/:tripId" element={<TripDetailPage />} />
        <Route path="trips/:tripId/edit" element={<TripEditor key="edit" />} />
        <Route path="warehouse" element={<WarehousePage />} />
        <Route path="master-data">
          <Route index element={<Navigate to="customers" replace />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="warehouses" element={<WarehousesPage />} />
          <Route path="river-bridges" element={<RiverBridgesPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
        </Route>
        <Route path="reports" element={<ReportsPage />} />
        <Route path="conversions">
          <Route index element={<Navigate to="dms-orders" replace />} />
          <Route path="dms-orders" element={<DmsOrdersPage />} />
          <Route path="dms-customers" element={<DmsMasterPage key="customers" kind="customers" />} />
          <Route path="dms-products" element={<DmsMasterPage key="products" kind="products" />} />
        </Route>
        <Route path="imports" element={<ImportPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="companies" element={<CompaniesPage />} />
      </Route>
    </Routes>
  )
}
