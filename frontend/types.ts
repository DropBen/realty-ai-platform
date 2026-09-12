export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export interface RecordBase {
  id: string;
  created_at: string;
  updated_at: string;
}
export interface Contact extends RecordBase {
  name: string;
  email: string | null;
  phone: string | null;
  kind: string;
  stage: string;
  score: number;
  score_reason: string;
  last_contact_at: string | null;
  archived: boolean;
}
export interface Property extends RecordBase {
  address: string;
  location: string;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number | null;
  status: string;
  property_type: string;
  features: string[];
  source: string;
  images: { url: string; alt: string }[];
  contact_id: string | null;
}
export interface Task extends RecordBase {
  title: string;
  status: string;
  priority: string;
  due_at: string | null;
  contact_id: string | null;
  assigned_to: string | null;
}
export interface Appointment extends RecordBase {
  all_day: boolean;
  timezone: string;
  recurrence_id: string | null;
  title: string;
  start_at: string;
  end_at: string;
  location: string;
  status: string;
  contact_id: string | null;
  external_id: string | null;
}
export interface Deal extends RecordBase {
  title: string;
  contact_id: string;
  property_id: string | null;
  stage: string;
  value: number;
  expected_close: string | null;
  commission_bps: number;
}
export interface Action extends RecordBase {
  kind: string;
  title: string;
  reason: string;
  confidence: number;
  priority: string;
  payload: { [key: string]: Json };
  status: string;
  contact_id: string | null;
  source_id: string | null;
  permission: string;
  version: number;
  error_code: string | null;
  scheduled_at: string | null;
}
export interface Communication extends RecordBase {
  contact_id: string | null;
  sender: string;
  recipient: string;
  subject: string;
  body: string;
  received_at: string;
  summary: string | null;
  analyzed: boolean;
  direction: string;
}
export interface Activity extends RecordBase {
  title: string;
  body: string;
  kind: string;
  source_id: string | null;
}
export interface Fact extends RecordBase {
  field: string;
  value: Json;
  state: string;
  confidence: number;
  source_type: string;
  source_id: string | null;
  method: string;
  quote: string;
}
export interface Preference {
  budget_min: number | null;
  budget_max: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  location: string | null;
  timeline: string | null;
  financing: string | null;
  features: string[];
  property_type: string | null;
}
export interface Match {
  property: Property;
  score: number | null;
  factors: { label: string; state: string }[];
  coverage: string;
  method: string;
}
export interface Profile {
  contact: Contact;
  preferences: Preference | null;
  activities: Activity[];
  communications: Communication[];
  tasks: Task[];
  facts: Fact[];
  appointments: Appointment[];
  commitments: Commitment[];
  missing: string[];
  matches: Match[];
}
export interface Briefing {
  generated_at: string;
  contacts: number;
  pending_actions: number;
  pipeline_value: number;
  active_deals: number;
  overdue_tasks: number;
  actions: Action[];
  tasks: Task[];
  followups: Contact[];
  appointments: Appointment[];
  routine_actions: number;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Session {
  user: {
    id: string;
    name: string;
    email: string;
    email_verified_at?: string | null;
    mfa_enabled?: boolean;
  };
  organization: {
    id: string;
    name: string;
    is_demo: boolean;
    timezone: string;
  };
  role: string;
  demo_mode?: boolean;
  require_email_verification?: boolean;
}
export interface Integrations {
  google_configured: boolean;
  ai_configured: boolean;
  billing_configured: boolean;
  demo_mode: boolean;
  connections: {
    id: string;
    email: string;
    status: string;
    scopes: string;
    last_sync_at: string | null;
    last_error: string | null;
  }[];
}
export interface Document extends RecordBase {
  reviewed_at: string | null;
  analysis: {
    classification: string;
    source_hash: string;
    state: string;
    entities: { kind: string; value: string; quote: string }[];
  } | null;
  name: string;
  mime_type: string;
  size: number;
  status: string;
  summary: string | null;
  classification: string;
  contact_id: string | null;
}
export interface Notification extends RecordBase {
  title: string;
  body: string;
  read: boolean;
  link: string;
}
export interface Workflow extends RecordBase {
  name: string;
  trigger: string;
  action: string;
  enabled: boolean;
  condition: { min_score?: number };
}
export interface Job extends RecordBase {
  kind: string;
  status: string;
  attempts: number;
  error_code: string | null;
}
export interface Audit extends RecordBase {
  action: string;
  actor_id: string;
  target_id: string;
  result: string;
}
export interface Analytics {
  pipeline: { stage: string; count: number; value: number }[];
  usage: { metric: string; quantity: number }[];
  actions: { status: string; count: number }[];
}
export interface Subscription {
  plan: string;
  status: string;
  trial_end: string | null;
  period_end: string | null;
  cancel_at_period_end: boolean;
}

export interface Commitment {
  id: string;
  contact_id: string;
  title: string;
  status: string;
  quote: string;
  source_id: string;
  confidence: number;
  version: number;
  due_at: string | null;
  responsible_user: string | null;
}
