import { ActionsPage, CommandPage, InboxPage } from "./pages/IntelligencePages";
import { DealsPage, PropertiesPage } from "./pages/ListingPages";
import { CalendarPage, TasksPage } from "./pages/CalendarTasks";
import {
  AnalyticsPage,
  DocumentsPage,
  NotificationsPage,
} from "./pages/DocumentsAnalytics";
export default function WorkPages({ page }: { page: string }) {
  switch (page) {
    case "actions":
      return <ActionsPage />;
    case "command":
      return <CommandPage />;
    case "inbox":
      return <InboxPage />;
    case "properties":
      return <PropertiesPage />;
    case "deals":
      return <DealsPage />;
    case "calendar":
      return <CalendarPage />;
    case "tasks":
      return <TasksPage />;
    case "documents":
      return <DocumentsPage />;
    case "analytics":
      return <AnalyticsPage />;
    default:
      return <NotificationsPage />;
  }
}
