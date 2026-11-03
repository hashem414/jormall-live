# JorMall UI/UX Route Migration

Status: Canonical route contract for the beauty-center workspace

All routes retain the leading `[locale]` segment. Redirect adapters must preserve safe query
parameters, active organization/session state, permission checks, and locale. Unsupported legacy gym
and trainee routes intentionally return not found because no beauty-center equivalent exists.

The header branch switcher is the workspace boundary, not an optional table filter. It has no "All
branches" choice. Owners use the same account to open each permitted branch, and operational routes
retain their route while reloading appointments, patients, doctors, services, rooms, resources,
inventory, waitlist, audit evidence, and reports for the newly active branch. Branch creation,
roles/access, organization settings, and branding remain organization-wide.

| Old route                                                  | New route                                                | Behavior                              | Reused capability                            | Permission                                             |
| ---------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------- | -------------------------------------------- | ------------------------------------------------------ |
| `/dashboard`                                               | `/dashboard`                                             | Canonical Home                        | Overview, Today, reports/Copilot projections | Widget-specific grants                                 |
| `/dashboard/today`                                         | `/dashboard/schedule/today`                              | Redirect                              | Today operations                             | `appointments.read`                                    |
| `/dashboard/calendar`                                      | `/dashboard/schedule/calendar`                           | Redirect                              | Appointment calendar/forms                   | `appointments.read`                                    |
| `/dashboard/appointments/[id]`                             | `/dashboard/schedule/appointments?appointment=[id]`      | Redirect and open drawer              | Appointment detail                           | `appointments.read` plus record/message grants per tab |
| `/dashboard/waitlist`                                      | `/dashboard/schedule/waitlist`                           | Redirect                              | Waitlist and offers                          | `waitlist.read`                                        |
| `/dashboard/customers[/[id]]`                              | `/dashboard/customers[/[id]]`                            | Canonical spelling changes only in UI | CRM                                          | `customers.read`                                       |
| `/dashboard/communications`                                | `/dashboard/inbox`                                       | Redirect                              | Conversations/messages                       | `messages.read`                                        |
| `/dashboard/services`                                      | `/dashboard/business/services`                           | Redirect                              | Catalog                                      | `services.read`                                        |
| `/dashboard/staff`                                         | `/dashboard/business/team?tab=team`                      | Redirect                              | Staff/invitations                            | `staff.read`                                           |
| `/dashboard/roles`                                         | `/dashboard/business/team?tab=roles`                     | Redirect                              | Roles/grants                                 | `roles.read`                                           |
| `/dashboard/resources`                                     | `/dashboard/business/resources`                          | Redirect                              | Scheduling resources                         | `resources.read`                                       |
| `/dashboard/branches`                                      | `/dashboard/business/branches`                           | Redirect                              | Branches                                     | `branches.read`                                        |
| `/dashboard/reports`                                       | `/dashboard/insights/reports`                            | Redirect                              | Reports/exports                              | `reports.read`                                         |
| `/dashboard/copilot`                                       | `/dashboard/insights/recommendations?source=copilot`     | Redirect                              | Copilot insights                             | Relevant read grants                                   |
| `/dashboard/predictions`                                   | `/dashboard/insights/recommendations?source=predictions` | Redirect                              | Predictive evidence                          | `predictions.read`                                     |
| `/dashboard/knowledge`                                     | `/dashboard/ai-studio/knowledge`                         | Redirect                              | Knowledge                                    | `knowledge.read`                                       |
| `/dashboard/ai-settings`                                   | `/dashboard/ai-studio/behavior`                          | Redirect                              | Prompt/evals                                 | `ai.configure`                                         |
| `/dashboard/ai-actions`                                    | `/dashboard/ai-studio/actions`                           | Redirect                              | AI action audit                              | `audit.read`                                           |
| `/dashboard/ai-usage`                                      | `/dashboard/ai-studio/usage`                             | Redirect                              | Usage                                        | `reports.read`                                         |
| `/dashboard/ai-conversations[/[id]]`                       | `/dashboard/inbox?tab=handoffs[&conversation=id]`        | Redirect                              | AI conversation evidence                     | `conversations.read`                                   |
| `/dashboard/ai-handoffs`                                   | `/dashboard/inbox?tab=handoffs`                          | Redirect                              | Handoffs                                     | `conversations.handoff`                                |
| `/dashboard/ai-channels`                                   | `/dashboard/settings/channels`                           | Redirect                              | Channel configuration                        | `ai.configure` / provider grants                       |
| `/dashboard/settings`                                      | `/dashboard/settings/organization`                       | Redirect                              | Organization settings                        | `organization.settings.manage`                         |
| `/dashboard/imports`                                       | `/dashboard/settings/imports`                            | Redirect                              | Imports                                      | `imports.manage`                                       |
| `/dashboard/audit`                                         | `/dashboard/settings/audit`                              | Redirect                              | Tenant audit                                 | `audit.read`                                           |
| `/dashboard/gym/**`, `/trainee`, `/trainee-invitations/**` | None                                                     | Return 404                            | None; feature retired                        | None                                                   |

The platform namespace remains `/[locale]/platform/**` and never shares tenant employee navigation.
