/** Shared API / domain types — keep in sync with backend Pydantic schemas. */

export interface PageEnvelope<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiError {
  code: string
  message: string
  details: unknown
  request_id: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user_id: number
  username: string
  display_name: string
  permissions: string[]
  roles: string[]
}

export interface MeResponse {
  id: number
  username: string
  display_name: string
  status: string
  roles: string[]
  permissions: string[]
  last_login_at: string | null
}

export interface UserOut {
  id: number
  username: string
  display_name: string
  employee_id: number | null
  status: string
  roles: string[]
  last_login_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface UserCreate {
  username: string
  display_name: string
  password: string
  employee_id?: number | null
  status?: string
  role_codes?: string[]
}

export interface UserUpdate {
  display_name?: string
  employee_id?: number | null
  status?: string
  password?: string
}

export interface RoleOut {
  id: number
  code: string
  name: string
  description: string | null
  status: string
  permissions: string[]
}

export interface PermissionOut {
  id: number
  code: string
  name: string
  module: string
  description: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

// ---- M2: departments ----

export interface DepartmentOut {
  id: number
  department_code: string
  department_name: string
  parent_id: number | null
  manager_employee_id: number | null
  status: string
  created_at: string | null
  updated_at: string | null
}

export interface DepartmentCreate {
  department_code: string
  department_name: string
  parent_id?: number | null
  manager_employee_id?: number | null
  status?: string
}

export interface DepartmentUpdate {
  department_code?: string
  department_name?: string
  parent_id?: number | null
  manager_employee_id?: number | null
  status?: string
}

export interface DepartmentTreeNode {
  id: number
  department_code: string
  department_name: string
  status: string
  children: DepartmentTreeNode[]
}

// ---- M2: employees ----

export interface EmployeeOut {
  id: number
  employee_no: string
  full_name: string
  gender: string | null
  department_id: number | null
  department_code: string | null
  department_name: string | null
  position: string | null
  employment_type: string | null
  phone: string | null
  join_date: string | null
  termination_date: string | null
  employment_status: string
  accommodation_required: boolean
  shift_type: string | null
  notes: string | null
  accommodation_status: string
  created_at: string | null
  updated_at: string | null
}

export interface EmployeeCreate {
  employee_no: string
  full_name: string
  gender?: string | null
  department_id?: number | null
  position?: string | null
  employment_type?: string | null
  phone?: string | null
  join_date?: string | null
  termination_date?: string | null
  employment_status?: string
  accommodation_required?: boolean
  shift_type?: string | null
  notes?: string | null
}

export interface EmployeeUpdate {
  employee_no?: string
  full_name?: string
  gender?: string | null
  department_id?: number | null
  position?: string | null
  employment_type?: string | null
  phone?: string | null
  join_date?: string | null
  termination_date?: string | null
  employment_status?: string
  accommodation_required?: boolean
  shift_type?: string | null
  notes?: string | null
}

export interface EmployeeImportRowResult {
  row_no: number
  action: string
  employee_no: string | null
  full_name: string | null
  message: string | null
  data: Record<string, unknown> | null
}

export interface EmployeeImportPreviewOut {
  import_job_id: number
  filename: string
  total_rows: number
  create_count: number
  update_count: number
  skip_count: number
  error_count: number
  rows: EmployeeImportRowResult[]
}

export interface EmployeeImportCommitOut {
  import_job_id: number
  status: string
  total_rows: number
  success_rows: number
  failed_rows: number
  created_count: number
  updated_count: number
  skipped_count: number
  errors: EmployeeImportRowResult[]
}

export interface ImportJobOut {
  id: number
  import_type: string
  filename: string
  file_hash: string
  status: string
  total_rows: number
  success_rows: number
  failed_rows: number
  created_by: number | null
  completed_at: string | null
  created_at: string | null
}

// ---- M2: dormitories ----

export interface DormAreaOut {
  id: number
  area_code: string
  area_name: string
  address: string | null
  status: string
  description: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DormAreaCreate {
  area_code: string
  area_name: string
  address?: string | null
  status?: string
  description?: string | null
}

export interface DormAreaUpdate {
  area_code?: string
  area_name?: string
  address?: string | null
  status?: string
  description?: string | null
}

export interface BuildingOut {
  id: number
  area_id: number
  building_code: string
  building_name: string
  total_floors: number | null
  gender_policy: string
  manager_user_id: number | null
  status: string
  description: string | null
  created_at: string | null
  updated_at: string | null
}

export interface BuildingCreate {
  area_id: number
  building_code: string
  building_name: string
  total_floors?: number | null
  gender_policy?: string
  manager_user_id?: number | null
  status?: string
  description?: string | null
}

export interface BuildingUpdate {
  area_id?: number
  building_code?: string
  building_name?: string
  total_floors?: number | null
  gender_policy?: string
  manager_user_id?: number | null
  status?: string
  description?: string | null
}

export interface FloorOut {
  id: number
  building_id: number
  floor_no: number
  floor_name: string | null
  gender_policy: string
  status: string
  created_at: string | null
  updated_at: string | null
}

export interface FloorCreate {
  building_id: number
  floor_no: number
  floor_name?: string | null
  gender_policy?: string
  status?: string
}

export interface FloorUpdate {
  building_id?: number
  floor_no?: number
  floor_name?: string | null
  gender_policy?: string
  status?: string
}

export interface RoomOut {
  id: number
  floor_id: number
  room_no: string
  room_type: string
  capacity: number
  gender_policy: string
  status: string
  description: string | null
  bed_count: number
  active_bed_count: number
  created_at: string | null
  updated_at: string | null
}

export interface RoomCreate {
  floor_id: number
  room_no: string
  room_type?: string
  capacity?: number
  gender_policy?: string
  status?: string
  description?: string | null
  bed_count?: number | null
  bed_no_prefix?: string
}

export interface RoomUpdate {
  floor_id?: number
  room_no?: string
  room_type?: string
  capacity?: number
  gender_policy?: string
  status?: string
  description?: string | null
}

export interface BedOut {
  id: number
  room_id: number
  bed_no: string
  operational_status: string
  version: number
  description: string | null
  occupied: boolean
  reserved: boolean
  available: boolean
  created_at: string | null
  updated_at: string | null
}

export interface BedCreate {
  room_id: number
  bed_no: string
  operational_status?: string
  description?: string | null
}

export interface DormTreeNode {
  id: number
  node_type: string
  code: string
  name: string
  status: string
  extra: Record<string, unknown>
  children: DormTreeNode[]
}

// ---- M3 accommodation ----

export interface CheckinApplicationOut {
  id: number
  application_no: string
  employee_id: number
  employee_no?: string
  employee_name?: string
  department_id?: number | null
  application_type: string
  requested_checkin_date: string | null
  assigned_bed_id: number | null
  status: string
  reason: string | null
  notes: string | null
  submitted_by: number | null
  processed_by: number | null
  processed_at: string | null
  created_at: string | null
  updated_at: string | null
  bed?: {
    id: number
    bed_no: string
    room_no: string
    building_name: string
    area_name: string
  } | null
  reservation?: BedReservationOut | null
  accommodation?: AccommodationRecordOut | null
}

export interface BedReservationOut {
  id: number
  reservation_no: string
  application_id: number | null
  employee_id: number
  bed_id: number
  status: string
  reserved_at: string
  expires_at: string | null
  released_at: string | null
  release_reason: string | null
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AccommodationRecordOut {
  id: number
  employee_id: number
  employee_no?: string
  employee_name?: string
  bed_id: number
  application_id: number | null
  checkin_at: string
  checkout_at: string | null
  status: string
  end_reason: string | null
  created_by: number | null
  ended_by: number | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
  bed_no?: string
  room_no?: string
  floor_no?: number
  building_name?: string
  area_name?: string
}

export interface TransferRecordOut {
  id: number
  transfer_no: string
  employee_id: number
  employee_no?: string
  employee_name?: string
  source_accommodation_id: number
  source_bed_id: number
  target_bed_id: number
  target_reservation_id: number | null
  target_accommodation_id: number | null
  reason: string | null
  status: string
  requested_at: string
  completed_at: string | null
  cancelled_at: string | null
  processed_by: number | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
  source_bed?: {
    id: number
    bed_no: string
    room_no: string
    building_name: string
  }
  target_bed?: {
    id: number
    bed_no: string
    room_no: string
    building_name: string
  }
}

export interface CheckoutRecordOut {
  id: number
  checkout_no: string
  employee_id: number
  employee_no?: string
  employee_name?: string
  accommodation_id: number
  checkout_type: string
  reason: string | null
  status: string
  expected_checkout_date: string | null
  actual_checkout_at: string | null
  key_returned: boolean
  access_card_returned: boolean
  belongings_cleared: boolean
  room_inspected: boolean
  inspection_notes: string | null
  processed_by: number | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
  accommodation?: {
    id: number
    bed_id: number
    status: string
    checkin_at: string
    checkout_at: string | null
    bed_no: string
    room_no: string
    building_name: string
  }
}

export interface CheckinApplicationCreate {
  employee_id: number
  application_type?: string
  requested_checkin_date?: string | null
  reason?: string | null
  notes?: string | null
  idempotency_key?: string | null
}

export interface TransferCreate {
  employee_id: number
  target_bed_id: number
  reason?: string | null
  notes?: string | null
  idempotency_key?: string | null
}

export interface CheckoutCreate {
  employee_id: number
  checkout_type?: string
  reason?: string | null
  expected_checkout_date?: string | null
  notes?: string | null
  idempotency_key?: string | null
}

export interface EmployeeAccommodation {
  kind: 'accommodation' | 'reservation'
  id: number
  bed_id: number
  status: string
  bed_no: string
  room_no: string
  floor_no: number
  building_name: string
  area_name: string
  checkin_at?: string
  reserved_at?: string
  expires_at?: string | null
}

export interface EmployeeHistoryItem {
  id: number
  bed_id: number
  checkin_at: string
  checkout_at: string | null
  status: string
  end_reason: string | null
  bed_no: string
  room_no: string
  floor_no: number
  building_name: string
  area_name: string
}

// ---- M4: workflow todos / alerts / offboarding ----

export interface WorkflowTodoOut {
  id: number
  todo_type: string
  business_type: string
  business_id: number | null
  employee_id: number | null
  assignee_role: string | null
  assignee_user_id: number | null
  title: string
  description: string | null
  status: string
  priority: string
  due_at: string | null
  completed_at: string | null
  completed_by: number | null
  cancel_reason: string | null
  source_event_id: string | null
  created_at: string | null
  updated_at: string | null
  employee_no?: string | null
  employee_name?: string | null
}

export interface WorkflowAlertOut {
  id: number
  alert_type: string
  severity: string
  employee_id: number | null
  bed_id: number | null
  accommodation_id: number | null
  business_type: string | null
  business_id: number | null
  title: string
  detail: string | null
  status: string
  fingerprint: string
  detected_at: string
  resolved_at: string | null
  resolved_by: number | null
  resolve_reason: string | null
  created_at: string | null
  updated_at: string | null
  employee_no?: string | null
  employee_name?: string | null
}

export interface WorkflowSummary {
  pending?: number
  completed?: number
  cancelled?: number
  active?: number
  resolved?: number
  by_type: Record<string, number>
}

export interface EmployeeStatusEventOut {
  id: number
  employee_id: number
  event_type: string
  from_status: string | null
  to_status: string
  source: string
  source_event_id: string
  reason: string | null
  notes: string | null
  created_by: number | null
  created_at: string
}

export interface OffboardingResult {
  employee_id: number
  employee_no: string
  full_name: string
  employment_status: string
  termination_date: string | null
  event: EmployeeStatusEventOut | null
  event_created: boolean
  accommodation: { id: number; bed_id: number; status: string } | null
  side_effects: Record<string, unknown>
  alert_id?: number | null
}

export interface NotificationOut {
  id: number
  user_id: number | null
  role_code: string | null
  category: string
  title: string
  content: string | null
  business_type: string | null
  business_id: number | null
  read_at: string | null
  created_at: string | null
}

// ---- M5 dashboard / reports / allocation ----

export interface DashboardSummary {
  building_total: number
  room_total: number
  bed_total: number
  bed_maintenance: number
  bed_disabled: number
  occupied_beds: number
  reserved_beds: number
  vacant_beds: number
  housed_employees: number
  occupancy_rate: number
  today_checkin: number
  today_checkout: number
  terminated_still_housed: number
  active_alerts: number
  pending_todos: number
  department_housed: Array<{
    department_id: number
    department_name: string
    housed_count: number
  }>
}

export interface DashboardOccupancyItem {
  building_id: number
  building_name: string
  bed_total: number
  occupied: number
  occupancy_rate: number
}

export interface DashboardTrendPoint {
  date: string
  checkin: number
  checkout: number
}

export interface AccommodationLedgerRow {
  id: number
  employee_id: number
  employee_no: string | null
  employee_name: string | null
  employment_status: string | null
  gender: string | null
  department_id: number | null
  department_code: string | null
  department_name: string | null
  bed_id: number
  bed_no: string | null
  room_no: string | null
  floor_no: number | null
  building_name: string | null
  area_name: string | null
  checkin_at: string | null
  status: string
}

export interface VacantBedRow {
  bed_id: number
  bed_no: string
  operational_status: string
  room_id: number
  room_no?: string | null
  floor_no?: number | null
  building_name?: string | null
  area_name?: string | null
}

export interface DepartmentStatRow {
  department_id: number
  department_code: string
  department_name: string
  parent_id: number | null
  employee_count: number
  housed_count: number
  reserved_count: number
}

export interface CheckinCheckoutEventRow {
  event_type: string
  event_at: string
  employee_id: number
  employee_no: string | null
  employee_name: string | null
  department_name: string | null
  bed_id: number
  bed_no?: string | null
  room_no?: string | null
  floor_no?: number | null
  building_name?: string | null
  area_name?: string | null
  reason: string | null
  accommodation_id: number
}

export interface TransferReportRow {
  id: number
  transfer_no: string
  employee_id: number
  employee_no: string | null
  employee_name: string | null
  department_name: string | null
  old_bed_id: number | null
  old_location: Record<string, string | number | null> | null
  new_bed_id: number | null
  new_location: Record<string, string | number | null> | null
  status: string
  reason: string | null
  created_at: string | null
  completed_at: string | null
}

export interface ExceptionReportRow {
  id: number
  alert_type: string
  severity: string
  employee_id: number | null
  employee_no: string | null
  employee_name: string | null
  department_name: string | null
  title: string
  detail: string | null
  status: string
  detected_at: string | null
  resolved_at: string | null
}

export interface BedCardOut extends BedOut {
  occupant?: { id: number; employee_no: string; full_name: string } | null
  reserved_for?: { id: number; employee_no: string; full_name: string } | null
}

export interface RoomCardOut extends RoomOut {
  occupied_count: number
  reserved_count: number
  available_count: number
  beds: BedCardOut[]
}
